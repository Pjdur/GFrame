"""GFrame - stream this computer's screen to any browser on the network as MJPEG."""

import argparse
import ctypes
import io
import socket
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

import mss
from PIL import Image

# --- Enable DPI Awareness for accurate screen capture ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
with open("index.html", "r", encoding="utf-8") as f:
    HTML = f.read()


class StreamHandler(SimpleHTTPRequestHandler):
    """Serves the live MJPEG GFrame desktop/game stream using mss for high-speed capture."""

    def log_error(self, format, *args):
        # Suppress harmless connection abort/broken pipe errors caused by client disconnects
        if args and any(err in str(args[0]) for err in ["10053", "10054", "Broken pipe"]):
            return
        super().log_error(format, *args)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            client_ip = self.client_address[0]
            print(f"[GFrame] Screen requested by {client_ip}", flush=True)

            html = HTML
            body = html.encode('utf-8')
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(body)

        elif path == "/stream":
            client_ip = self.client_address[0]
            print(f"[GFrame] Screen requested by {client_ip}", flush=True)
            
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            try:
                # Grab the monitor index chosen via CLI (default to 1 if missing)
                monitor_idx = getattr(self.server, 'monitor_index', 1)
                
                with mss.MSS() as sct:
                    # Safely bound check in case an invalid monitor index was passed
                    if monitor_idx >= len(sct.monitors):
                        print(f"GFrame: Monitor index {monitor_idx} not found. Falling back to 1.", file=sys.stderr)
                        monitor_idx = 1
                        
                    monitor = sct.monitors[monitor_idx]
                    while True:
                        sct_img = sct.grab(monitor)
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                        buf = io.BytesIO()
                        img.save(buf, format='JPEG', quality=75)
                        frame = buf.getvalue()

                        self.wfile.write(b'--frame\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n')
                        self.wfile.write(f'Content-Length: {len(frame)}\r\n\r\n'.encode())
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                        self.wfile.flush()
                        time.sleep(0.015)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                pass
            except Exception as exc:
                print(f"GFrame: stream error: {exc!r}", file=sys.stderr)

        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()

        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, format, *args):
        pass  # silence per-request logging


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests concurrently to support streaming."""
    daemon_threads = True
    # On Windows, SO_REUSEADDR lets a second process bind an already-used port, silently
    # splitting traffic between two servers. Fail loudly there; keep the POSIX default.
    allow_reuse_address = sys.platform != "win32"


def _lan_addresses():
    """Best-effort list of non-loopback IPv4 addresses for this machine."""
    addresses = set()

    # Connecting a UDP socket picks the default route's interface without sending traffic.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 1))  # TEST-NET-1, reserved and unroutable
            addresses.add(sock.getsockname()[0])
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass

    return sorted(addr for addr in addresses if not addr.startswith("127."))


def print_urls(host, port):
    if host in ("", "0.0.0.0", "::"):
        print(f"GFrame streaming at: http://localhost:{port}", flush=True)
        for addr in _lan_addresses():
            print(f"                  or: http://{addr}:{port}", flush=True)
        print("Viewers on your network need the second URL. The stream has no authentication.", flush=True)
    else:
        print(f"GFrame streaming at: http://{host}:{port}", flush=True)


def start_server(host, port, monitor_index):
    try:
        server = ThreadedHTTPServer((host, port), StreamHandler)
        server.monitor_index = monitor_index  # Make monitor index accessible to handlers
    except OSError as exc:
        print(f"GFrame: cannot listen on {host}:{port} ({exc}).", file=sys.stderr, flush=True)
        print("Is GFrame already running? Try a different port, e.g. --port 8001.", file=sys.stderr, flush=True)
        return 1

    print_urls(host, port)
    print(f"Streaming monitor index: {monitor_index}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nGFrame stopped.")
    finally:
        server.server_close()
    return 0

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="GFrame",
        description="Stream this computer's screen to any browser on the network.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"interface to bind (default: {DEFAULT_HOST}, all interfaces)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"port to listen on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=1,
        help="monitor index to stream (default: 1 for primary screen, 0 for all screens combined)",
    )
    args = parser.parse_args(argv)
    return start_server(args.host, args.port, args.monitor)


if __name__ == "__main__":
    sys.exit(main())