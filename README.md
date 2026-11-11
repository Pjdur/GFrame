# GFrame

Stream your desktop to any browser on your local network. Live, no plugins, no build step, one Python file.

```bash
uv run main.py
```

```text
GFrame streaming at: http://localhost:8000
                 or: http://192.168.1.42:8000
Viewers on your network need the second URL. The stream has no authentication.
```

Open the second URL on any phone, tablet, or laptop on the same network.

## What it does

- Captures a display with [`mss`](https://github.com/BoboTiG/python-mss) (Windows GDI `BitBlt` straight into a DIB section - the fastest pure-Python path).
- Encodes each frame to JPEG with Pillow.
- Serves the frames as an MJPEG stream (`multipart/x-mixed-replace`), which a plain `<img>` tag renders. No JavaScript decoding, no codec negotiation, sub-100 ms glass-to-glass on a LAN.
- Serves the viewer page itself, with a dark/light theme remembered per browser.

## How it works

```text
mss.grab(monitor)      Image.frombytes        Pillow JPEG          HTTP
BGRA bytes  --copy-->  RGB PIL image  -->  BytesIO (q75)  -->  --frame\r\n...
  (BitBlt)                                                          |
      ^                                                              v
      +---------------- sleep(15 ms) <--------- loop <---- one thread per viewer
```

Each `/stream` request gets its own thread and its own capture session, so viewers are independent (and each costs CPU).

## Requirements

- Python 3.11+
- Windows is the tested target. `mss` is cross-platform, so macOS and Linux generally work too (the DPI-awareness call is Windows-only and is skipped elsewhere).
- The viewer must be on the same network. No port forwarding needed for LAN use.

## Usage

```bash
uv run main.py [--host HOST] [--port PORT]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--host` | `0.0.0.0` | Interface to bind. Use `127.0.0.1` to keep the stream local to this machine. |
| `--port` | `8000` | Port to listen on. |

Ctrl+C stops the server. If the port is already taken you get an explicit error instead of a silent exit - pick another port with `--port 8001`.

## Endpoints

| Path | Purpose |
| --- | --- |
| `/` | Viewer page |
| `/stream` | MJPEG frame stream |
| `/favicon.ico` | `204 No Content` |

## Performance

At 1920x1080 with JPEG quality 75 expect roughly 8-15 Mbps and 30-45 fps on a modern desktop CPU. Bandwidth scales with resolution and quality; FPS is capped by capture + encode time plus the 15 ms frame pause.

Because every viewer captures and encodes independently, CPU scales linearly with the number of viewers. One or two viewers over Wi-Fi is comfortable; more is better served by the shared-producer design in the roadmap.

## Security

**GFrame has no authentication.** Anything that can reach the port can watch your screen. That is fine on a trusted home network and a problem anywhere else.

- Do not port-forward GFrame to the internet.
- For access from outside the house, put it behind a VPN or tunnel (Tailscale, WireGuard, Cloudflare Tunnel) rather than exposing the port.
- Bind `--host 127.0.0.1` if you only want to view from the same machine.

GFrame is deliberately **view-only**. Remote cursor or keyboard control is not implemented; see the roadmap for a safe design if that ever changes.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Page loads, stream stays black | Exclusive-fullscreen game or protected content - GDI `BitBlt` cannot capture it | Run the game in borderless windowed mode |
| Stream dies with `GFrame: stream error: ...` | Real capture/encode failure, now reported on stderr | Read the message; it is no longer silently swallowed |
| Phone cannot connect | `localhost` is the phone itself, or the device is on a guest VLAN | Use the LAN URL that GFrame prints, and allow the Windows Firewall prompt |
| Cannot start, port error | Another GFrame (or anything else) is on the port | `--port 8001` |
| Mouse pointer missing or flickering | mss's `with_cursor` option is Linux-only; on Windows the pointer only appears as a side effect of `CAPTUREBLT` | Known limitation |

## Roadmap

- Single capture/encode producer shared by all viewers (removes the per-viewer CPU cost).
- `?monitor=`, `?quality=`, `?scale=`, `?fps=` query parameters and a monitor picker in the UI.
- Server-side downscaling for phones, plus a FPS/latency overlay and auto-reconnect.
- Opt-in token authentication and a loopback default bind.
- WebRTC (`aiortc`) path for adaptive bitrate, and audio over WASAPI loopback.
- Optional, explicitly opt-in pointer control on a separate token - off by default, pointer-only, host-side kill switch.

## Development

```bash
uv sync      # create/refresh the virtual environment
uv run main.py
```
