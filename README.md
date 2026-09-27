# sms-powerview

A small, pure-Python reader **and web UI** for SMS (Legrand) nobreak/UPS
units, built for **arm64** and Home Assistant. It talks directly
to the nobreak over its own serial protocol - no vendor software, no Java,
no native extensions - and works fully on its own even without Home
Assistant.

## How it works

SMS's own "Power View" monitoring app is closed-source, but the actual
wire protocol it uses turned out to be simple, proprietary, and fully
readable straight out of the installer's own resource files
(`resource/protocolos/monofasico.xml`, internally called `"TRADICIONAL"`).
`app/reader.py` implements it directly: commands are ASCII/binary framed
with a simple checksum, sent over `/dev/ttyUSB0` at 2400 baud 8N1, using
only Python's standard library (`os`/`termios`/`tty`/`select` - no
`pyserial`, no native code, no vendor jar).

This was verified against a real unit before being built: see
`tools/probe_protocol.py`, a standalone diagnostic script that sends the
same commands independently of the running service - useful for
double-checking wiring/protocol on a different nobreak, or if a reading
ever looks wrong.

A single background thread (`app/poller.py`) owns the serial port - it
polls on an interval, persists a rolling 24h history to SQLite (via
`app/history_store.py`, stdlib only - no new dependency) under a
bind-mounted `./data` volume, and feeds everything else (MQTT, the web
UI's websocket, write commands) from that one thread, so nothing races to
open the port concurrently.

Because there's no vendor app or native library involved, the image
targets **`linux/arm64`** directly (e.g. Raspberry Pi 5) - no cross-compat
tricks needed - but is equally buildable for other architectures like
`amd64` if you want to run it elsewhere.

## What's confirmed vs. best-effort

Verified directly against real hardware:
- Input/output voltage, output frequency, temperature, output power, and
  battery charge percentage all decode to plausible real values.
- `battery_in_use` and `self_test_active` (see `reader.py`'s
  `_parse_medidores_estado`) - confirmed via `/diagnostics`: a software
  `test_for_seconds` flips both; a real AC unplug/replug flips only
  `battery_in_use`. The protocol XML's declared bit positions for these
  two were actually wrong (it named this bit "beep enabled" and that bit
  "bypass active") - they're corrected here based on what the hardware
  actually does, not what the XML claims.

Best-effort, not yet independently confirmed:
- The other boolean status bits (`battery_connected`, `battery_low`,
  `ups_ok`, `status_bit_5`, `shutdown_active`) never moved in either test
  above, so there's no real evidence for them yet either way. Worth
  running `/diagnostics` yourself (e.g. its "watch" mode during a real
  self-test, or while the battery is genuinely low) before relying on
  them for automations.
- The write/control commands (see "Nobreak control commands" below) are
  implemented straight from the protocol XML. `test_for_seconds` is
  confirmed working; the others haven't been tested. `beep_toggle`
  specifically showed **no effect at all** on the status byte when tried -
  it may not be supported by this firmware, given the XML's own bit
  position for "beep" turned out to be wrong too.
- The 2400 baud / 8N1 framing and this specific command set worked for the
  one unit this was tested against. If yours doesn't respond, run
  `tools/probe_protocol.py` (it also tries 1200/4800/9600) and check the
  other protocol files under `resource/protocolos/` in SMS's own installer
  (trifásico, Voltronic/Upsilon) if you can get a copy of it - this
  project only implements the "TRADICIONAL" one.

## Setup

1. **Find your serial adapter.** Plug in the USB-to-RS232 adapter and check
   `dmesg` / `ls /dev/ttyUSB*` on the Pi to confirm the device path (usually
   `/dev/ttyUSB0`).

2. **Configure.**
   ```
   cp .env.example .env
   ```
   Edit `.env`: set `DEVICE_PATH`; set `WEB_PASSWORD` to protect the web UI
   (see "Web UI" below - leave blank only if your network is fully
   trusted); set `MQTT_HOST` if you want automatic Home Assistant entities.
   Leave `MQTT_HOST` blank to use the plain JSON endpoint instead (see
   `homeassistant/configuration.yaml.example`).

3. **Build and run:**
   ```
   docker compose up --build -d
   ```

4. Open `http://<host>:5000/` and log in (if you set `WEB_PASSWORD`) to see
   live readings and history - independent of Home Assistant. See "Web UI"
   below for the other pages (controls, integration status, raw JSON).

If it can't read the nobreak, the UI and `/monitor` will show the error
(e.g. a serial timeout) instead of failing silently - check that against
`tools/probe_protocol.py`'s output for the same device.

## Web UI

Five pages, built as a React SPA (Vite + TypeScript + Tailwind CSS +
[shadcn/ui](https://ui.shadcn.com), see `frontend/`), served by the Flask
backend as a static build (`frontend/dist/`). Flask itself is now a pure
JSON/WebSocket API (`app/app.py`) - all page rendering moved client-side.
Sharing a top nav bar, responsive down to phone width:

- **`/` Dashboard** - a stat card per metric and per status flag, updated
  live over a websocket; a chart per numeric metric (input/output
  voltage, frequency, temperature, battery %, output power), each with
  labeled axes and a hover tooltip showing the exact value and time; and
  a **recent events** list derived from the history - state changes like
  "battery_in_use: Off → On at 14:32:10", so you can actually answer
  "did it go to battery mode a few hours ago?" without staring at a chart.
  Charts only show what's accumulated since history started (see "Data
  persistence" below) - a freshly-started, never-run-before instance has
  nothing to show yet.
- **`/controls`** - the nobreak's write commands (see below), with
  confirmation required for anything above "low" risk, both in the UI and
  re-checked server-side (a raw API call without `confirm: true` is
  rejected the same way).
- **`/integration`** - read-only Home Assistant/MQTT status: enabled,
  connected, broker, topics, and the last value published to each - so
  you can confirm the integration is actually working without opening
  Home Assistant at all.
- **`/json`** - a live, pretty-printed view of the same data `/monitor`
  serves, for poking around without a JSON viewer extension.
- **`/diagnostics`** - runs `tools/watch_status.py`'s logic (see below) in
  the browser instead of a terminal: sample the raw status byte once a
  second around either a self-driven test command or your own manual
  trigger (e.g. unplugging AC), with a live log and a one-click copy - for
  exactly the kind of "what does this bit actually mean on my unit"
  investigation this project's status bits still need.

**Login** is a single shared password (`WEB_PASSWORD`), not per-user
accounts - there's only one login form, backed by a JWT stored in an
HttpOnly cookie. Leave `WEB_PASSWORD` blank to disable login entirely
(open access to anyone who can reach the port). `JWT_SECRET` can be pinned
in `.env` if you want sessions to survive a container restart; otherwise a
random one is generated at startup and every session is invalidated on
restart (just log in again).

Any URL that isn't one of those five pages, `/monitor`, `/health`, or
under `/api/` redirects to `/` - so a stale bookmark or a typo just lands
you back on the dashboard instead of a 404.

## Data persistence

Readings are written to SQLite at `./data/history.db` (bind-mounted, see
`docker-compose.yml`) as they're polled, and pruned back to the last 24h
on every write - so history survives a container restart, but nothing
older than 24h is ever kept regardless. There's no separate backup/export
mechanism; if you want longer retention, that's what the Home Assistant
MQTT integration's own long-term history is for.

## Nobreak control commands

⚠️ **Two of these cut output power to everything plugged into the
nobreak.** Test the low-risk ones first, and think about what's actually
plugged in before using the others - if this nobreak is powering the Pi
running this container (or anything else you don't want to lose power to),
a shutdown command will take it down too.

| Command | Risk | What it does |
|---|---|---|
| `beep_toggle` | low | Toggles the nobreak's beep on/off. |
| `cancel_test` | low | Cancels a running battery test. |
| `cancel_shutdown` | low | Cancels a pending shutdown/restore. |
| `test_until_low_battery` | medium | Runs on battery until it's low - drains the battery. |
| `test_for_seconds` | medium | Runs on battery for N seconds. |
| `shutdown_for_seconds` | **high** | **Cuts output power for N seconds.** |
| `shutdown_and_restore` | **high** | **Cuts output power, restores it after a further delay.** |

These are sent from the web UI's Controls section, or directly:

```bash
curl -X POST http://<host>:5000/api/command \
  -H "Content-Type: application/json" \
  -H "Cookie: spv_token=<your session cookie>" \
  -d '{"name": "beep_toggle", "params": {}, "confirm": false}'
```

`confirm: true` is required for anything above "low" risk (the API
rejects the request otherwise, regardless of what the UI does) - for
`test_for_seconds`/`shutdown_for_seconds`/`shutdown_and_restore`, `params`
also needs the relevant seconds value(s) (`seconds`, or
`shutdown_seconds`/`restore_seconds`).

## Diagnostics: probing the protocol directly

`tools/probe_protocol.py` (baked into the image at `/opt/tools/`) sends
the same read commands `reader.py` uses, independently of the running
service - useful for confirming wiring/protocol on a different nobreak, or
sanity-checking a reading that looks wrong:

```bash
docker exec sms-powerview python3 /opt/tools/probe_protocol.py
```

It tries several baud rates automatically. A real response (readable text
for `I`, structured numeric-looking bytes for `Q`) confirms the protocol
and baud rate; a timeout on every baud means this nobreak needs a
different protocol than the one implemented here.

`tools/watch_status.py` samples the status byte once a second instead of
once per `POLL_INTERVAL` - useful for catching a fast transition (e.g.
what a test command actually does to each bit) that a 15s poll would
mostly miss:

```bash
# Drives a test_for_seconds itself and watches the transition:
docker exec -w /opt/app sms-powerview python3 /opt/tools/watch_status.py 15

# Pure observation, no command sent - trigger the event yourself
# (e.g. briefly unplug AC power) right after the baseline line prints:
docker exec -w /opt/app sms-powerview python3 /opt/tools/watch_status.py --watch 30
```

It talks to the serial port independently of the running service, same as
`probe_protocol.py` - an occasional `error: ...` line from a collision
with the app's own poll is normal noise, not a real problem.

## JSON endpoint

`GET http://<host>:5000/monitor` - unauthenticated (so Home Assistant's
REST integration, or anything else without a login flow, can use it
directly). Returns the poller's latest cached reading (at most
`POLL_INTERVAL` seconds old) rather than doing its own live read, so it
can't race with the websocket/MQTT/commands over the one serial port.

```json
{
  "status": {
    "input_voltage": { "current": "221.0" },
    "output_voltage": { "current": "114.8" },
    "output_frequency": { "current": "60.0" },
    "battery_charge": { "current": "100.0" },
    "temperature": { "current": "28.8" },
    "output_power": { "current": "38.1" }
  },
  "info": {
    "battery_in_use": "Off",
    "battery_connected": "On",
    "battery_low": "Off",
    "self_test_active": "Off",
    "ups_ok": "On",
    "status_bit_5": "On",
    "shutdown_active": "Off"
  }
}
```

`GET http://<host>:5000/health` returns `{"status": "ok"}` for use as a
liveness check (also wired up as the container's `HEALTHCHECK`). Also
unauthenticated.

## Home Assistant

Home Assistant integration is optional - this runs fine as a standalone
tool without it (see "Web UI" above). If you do want it:

**Preferred: MQTT.** Set `MQTT_HOST` (and credentials, if any) in `.env`.
The bridge publishes Home Assistant MQTT discovery configs for all status
and info fields under one device - entities appear automatically, no YAML
required. Check the web UI's integration section to confirm it's
connected and see what's actually being published.

**Alternative: REST.** Leave `MQTT_HOST` blank and add the sensors from
`homeassistant/configuration.yaml.example` to your Home Assistant
`configuration.yaml`, pointing at the `/monitor` endpoint.

## Repository layout

```
Dockerfile                       arm64-native, multi-stage (React build -> Python runtime), buildable for other archs too
docker-compose.yml                deployment (targets arm64, buildable for other archs too)
.env.example                      configuration template
app/
  reader.py                        talks to the nobreak over serial (reads + write commands)
  poller.py                        the one thread that owns the serial port; feeds history/MQTT/websocket
  history_store.py                 SQLite-backed 24h history (stdlib only)
  mqtt_publisher.py                Home Assistant MQTT discovery + publish (fed by poller)
  auth.py                          single-password JWT auth
  app.py                           Flask JSON/WebSocket API: /api/*, /monitor, /health, /ws, /ws/diagnostics
                                    - serves the built React SPA as static files for everything else
frontend/                        React + Vite + TypeScript + Tailwind + shadcn/ui SPA
  src/pages/                       Dashboard, Controls, Integration, Json, Diagnostics, Login
  src/components/                  Layout (nav), LineChart (canvas chart, ported from vanilla JS),
                                    CommandButton (danger-tiered confirm flow), shadcn ui/ primitives
  src/lib/                         api.ts (fetch client), auth-context.tsx, types.ts, ws.ts
tools/
  probe_protocol.py                standalone diagnostic - same read protocol, no service
  watch_status.py                  1s-resolution status watcher, for catching fast transitions
homeassistant/                    example REST-sensor YAML (MQTT needs none)
data/                              (created at runtime) SQLite history - bind-mounted
```

## Disclaimer

This project is not affiliated with SMS or Legrand. It implements a
serial protocol reverse-engineered from files bundled with their own
PowerView installer, including write commands that have not been tested
against real hardware; use at your own risk, especially the two commands
that cut output power.

No proprietary SMS/Legrand code or binaries (their "Power View" app,
installer, or any bundled library) are present in this repository.
