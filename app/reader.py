"""Talks directly to the nobreak over its own serial protocol.

This is SMS's proprietary protocol - internally called "TRADICIONAL" in
their PowerView software, documented in resource/protocolos/monofasico.xml
inside their installer archive. There is no vendor app involved at all:
this talks straight to the serial port.

Verified against real hardware at 2400 baud/8N1: sending the 'I' command
got back the nobreak's own model/firmware string, and 'Q' decoded to
plausible live readings (input/output voltage, frequency, temperature).
The numeric fields below are solid. The EstadoBateria status-bit mapping
is a best-effort reading of the XML's declared bit positions and has not
been independently confirmed against real events (e.g. an actual AC-loss
or battery-test) - treat those specific fields with a grain of salt until
you've checked them against your own unit's behavior.

The same XML also declares write commands (beep toggle, battery test,
timed shutdown, shutdown+restore, cancel-test, cancel-shutdown) - see
COMMANDS below. None of these have been tested against real hardware yet;
the two that cut output power (shutdown_for_seconds, shutdown_and_restore)
are marked "high" danger and calling code must treat that as a real
warning, not decoration - they power off whatever's plugged into the
nobreak.
"""
import os
import select
import termios
import time
import tty

DEVICE_PATH = os.environ.get("DEVICE_PATH", "/dev/ttyUSB0")
BAUD_RATE = int(os.environ.get("BAUD_RATE", "2400"))
READ_TIMEOUT = float(os.environ.get("READ_TIMEOUT", "1.5"))

BAUD_CONST = {
    1200: termios.B1200,
    2400: termios.B2400,
    4800: termios.B4800,
    9600: termios.B9600,
}

CMD_INFORMACOES = 0x49  # 'I'
CMD_MEDIDORES_ESTADO = 0x51  # 'Q'
MEDIDORES_RESPONSE_LEN = 18  # Tipo(1) + 7*2 numeric fields + EstadoBateria(2) + CR(1)

# Write commands from monofasico.xml. "params" lists the seconds-valued
# fields each command's Param1/2 (and Param3/4 for shutdown_and_restore)
# carry - everything else is unused 0xFF padding. "danger" is used by the
# UI/API to decide what confirmation to demand before sending.
COMMANDS = {
    "beep_toggle": {
        "byte0": 0x4D,  # 'M' MudaBeep
        "params": [],
        "danger": "low",
        "description": "Toggle the nobreak's beep on/off.",
    },
    "cancel_test": {
        "byte0": 0x44,  # 'D' CancelarTeste
        "params": [],
        "danger": "low",
        "description": "Cancel a running battery test.",
    },
    "cancel_shutdown": {
        "byte0": 0x43,  # 'C' CancelarShutdownRestore
        "params": [],
        "danger": "low",
        "description": "Cancel a pending shutdown/restore.",
    },
    "test_until_low_battery": {
        "byte0": 0x4C,  # 'L' TesteBateriaBaixa
        "params": [],
        "danger": "medium",
        "description": "Run on battery until it's low. Drains the battery; "
        "leaves less reserve for a real outage until it recharges.",
    },
    "test_for_seconds": {
        "byte0": 0x54,  # 'T' TestePorSegundos
        "params": ["seconds"],
        "danger": "medium",
        "description": "Run on battery for the given number of seconds.",
    },
    "shutdown_for_seconds": {
        "byte0": 0x53,  # 'S' ShutdownPorSegundos
        "params": ["seconds"],
        "danger": "high",
        "description": "Cuts output power for the given number of seconds - "
        "powers off everything plugged into the nobreak.",
    },
    "shutdown_and_restore": {
        "byte0": 0x52,  # 'R' ShutdownRestore
        "params": ["shutdown_seconds", "restore_seconds"],
        "danger": "high",
        "description": "Cuts output power, then restores it after a further "
        "delay - powers off everything plugged into the nobreak.",
    },
}


class PowerViewError(RuntimeError):
    """Raised when the nobreak can't be reached or its reply doesn't parse."""


def _to_signed_byte(v: int) -> int:
    return v - 256 if v >= 128 else v


def _checksum(byte_values) -> int:
    total = sum(_to_signed_byte(b) for b in byte_values)
    return (-total) & 0xFF


def _build_command(byte0: int, params=(0xFF, 0xFF, 0xFF, 0xFF)) -> bytes:
    b = bytes([byte0, *params])
    return b + bytes([_checksum(b), 0x0D])


def _open_port() -> int:
    baud = BAUD_CONST.get(BAUD_RATE)
    if baud is None:
        raise PowerViewError(f"unsupported BAUD_RATE {BAUD_RATE}")

    try:
        fd = os.open(DEVICE_PATH, os.O_RDWR | os.O_NOCTTY)
    except OSError as exc:
        raise PowerViewError(f"could not open {DEVICE_PATH}: {exc}") from exc

    try:
        tty.setraw(fd)
        attrs = termios.tcgetattr(fd)
        # Python's termios on Linux has no cfsetispeed/cfsetospeed - speed
        # is just elements 4 and 5 of what tcgetattr returns.
        attrs[4] = baud
        attrs[5] = baud
        attrs[2] = (attrs[2] & ~termios.PARENB) & ~termios.CSTOPB
        attrs[2] = (attrs[2] & ~termios.CSIZE) | termios.CS8
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except (OSError, termios.error) as exc:
        os.close(fd)
        raise PowerViewError(f"could not configure {DEVICE_PATH}: {exc}") from exc

    return fd


def _send_and_read(fd: int, request: bytes, expected_len: int) -> bytes:
    os.write(fd, request)
    deadline = time.time() + READ_TIMEOUT
    buf = b""
    while len(buf) < expected_len:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        r, _, _ = select.select([fd], [], [], remaining)
        if not r:
            break
        buf += os.read(fd, expected_len - len(buf))
    return buf


def _drain(fd: int) -> None:
    """Discards any bytes still sitting in the input buffer (e.g. an ack we
    don't model) so they don't get mistaken for the next command's reply."""
    while True:
        r, _, _ = select.select([fd], [], [], 0)
        if not r or not os.read(fd, 256):
            break


def _hexword(b: bytes) -> int:
    return int.from_bytes(b, "big")


def _parse_medidores_estado(resp: bytes) -> dict:
    if len(resp) < MEDIDORES_RESPONSE_LEN - 1:
        raise PowerViewError(f"short response from nobreak: {resp!r}")

    tensao_entrada = _hexword(resp[3:5]) / 10
    tensao_saida = _hexword(resp[5:7]) / 10
    potencia_saida = _hexword(resp[7:9]) / 10
    frequencia_saida = _hexword(resp[9:11]) / 10
    # The XML doesn't declare a /10 calc for this field like the others,
    # but the raw value (e.g. 1000) only makes sense as a percentage once
    # divided by 10 (100.0%) - applying the same convention as a best guess.
    porcentagem_bateria = _hexword(resp[11:13]) / 10
    temperatura = _hexword(resp[13:15]) / 10
    estado = resp[15] if len(resp) > 15 else 0

    def bit(n: int) -> bool:
        return bool(estado & (1 << n))

    status = {
        "input_voltage": {"current": f"{tensao_entrada:.1f}"},
        "output_voltage": {"current": f"{tensao_saida:.1f}"},
        "output_frequency": {"current": f"{frequencia_saida:.1f}"},
        "battery_charge": {"current": f"{porcentagem_bateria:.1f}"},
        "temperature": {"current": f"{temperatura:.1f}"},
        "output_power": {"current": f"{potencia_saida:.1f}"},
    }
    # Bit meanings below are corrected from real hardware tests (see
    # README/git history), not the protocol XML's declared positions,
    # which turned out to be wrong for at least bits 2 and 7 on this unit:
    #   - bit 7 flipped during BOTH a software test_for_seconds AND a real
    #     AC unplug/replug -> genuinely "running on battery", not "beep
    #     enabled" as the XML's bit position for it implied.
    #   - bit 2 flipped ONLY during the software test, never during the
    #     real AC-loss event -> genuinely "self-test active", not
    #     "bypass active".
    #   - bits 0 and 5 (previously assigned "battery_in_use" and
    #     "self_test_active" respectively, based on the XML) never moved
    #     in either test - those specific labels were wrong. Renamed to
    #     honest, non-claiming names below until there's real evidence.
    info = {
        "battery_connected": "On" if bit(0) else "Off",  # untested guess
        "battery_low": "On" if bit(1) else "Off",  # untested guess
        "self_test_active": "On" if bit(2) else "Off",  # confirmed
        "ups_ok": "On" if bit(4) else "Off",  # untested guess
        "status_bit_5": "On" if bit(5) else "Off",  # unknown - not test-related
        "shutdown_active": "On" if bit(6) else "Off",  # untested guess
        "battery_in_use": "On" if bit(7) else "Off",  # confirmed
        # Not a real field - the raw byte these 7 booleans are all read
        # from, exposed so a command's actual effect (or lack of one) can
        # be checked directly instead of trusting our bit-position guesses.
        # Visible on /json; deliberately not in mqtt_publisher's sensor
        # list so it doesn't get published as a real entity.
        "_debug_estado_byte": f"{estado:#04x}",
    }
    return {"status": status, "info": info}


def read_model() -> str:
    """Fetch the nobreak's own model/firmware identification string."""
    fd = _open_port()
    try:
        resp = _send_and_read(fd, _build_command(CMD_INFORMACOES), 18)
    finally:
        os.close(fd)

    if not resp:
        raise PowerViewError("no response from nobreak (Informacoes)")
    return resp.rstrip(b"\r").decode("ascii", errors="replace")


def read_monitor() -> dict:
    """Fetch and parse the current UPS status. Raises PowerViewError on failure."""
    fd = _open_port()
    try:
        resp = _send_and_read(fd, _build_command(CMD_MEDIDORES_ESTADO), MEDIDORES_RESPONSE_LEN)
    finally:
        os.close(fd)

    if not resp:
        raise PowerViewError(f"no response from nobreak on {DEVICE_PATH}")
    return _parse_medidores_estado(resp)


def send_command(name: str, **kwargs) -> None:
    """Sends a write command (see COMMANDS) to the nobreak. Fire-and-forget:
    these have no declared response in the protocol spec."""
    spec = COMMANDS.get(name)
    if spec is None:
        raise PowerViewError(f"unknown command {name!r}")

    params = [0xFF, 0xFF, 0xFF, 0xFF]
    for i, param_name in enumerate(spec["params"]):
        try:
            seconds = int(kwargs[param_name])
        except (KeyError, TypeError, ValueError) as exc:
            raise PowerViewError(f"{name} requires an integer {param_name!r}") from exc
        if not 0 <= seconds <= 0xFFFF:
            raise PowerViewError(f"{param_name} out of range (0-65535): {seconds}")
        params[i * 2] = (seconds >> 8) & 0xFF
        params[i * 2 + 1] = seconds & 0xFF

    fd = _open_port()
    try:
        os.write(fd, _build_command(spec["byte0"], tuple(params)))
        time.sleep(0.3)
        _drain(fd)
    except OSError as exc:
        raise PowerViewError(f"could not send {name} to {DEVICE_PATH}: {exc}") from exc
    finally:
        os.close(fd)
