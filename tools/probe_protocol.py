#!/usr/bin/env python3
"""Direct serial probe for SMS's proprietary "TRADICIONAL" protocol
(resource/protocolos/monofasico.xml in the original PowerView installer),
independent of app/reader.py or the running service.

'I' (Informacoes) and 'Q' (MedidoresEstado) are each encoded as
[cmd, 0xFF, 0xFF, 0xFF, 0xFF, checksum, 0x0D], where checksum is the
negated sum of the preceding 5 bytes, mod 256 - computed straight from
that XML's <Request> params (Comando + four 0xFF padding params) and its
<Check calc="...*-1">.

Run inside the sms-powerview container - useful for testing a different
nobreak/wiring independent of the running service, or for double-checking
raw bytes if app/reader.py's readings look wrong:

    docker exec sms-powerview python3 /opt/tools/probe_protocol.py

The running service only holds the port open briefly once per poll, so
this is safe to run alongside it; if you happen to hit a "device busy"
error from the brief overlap, just retry.

Optional args: device path, then one or more baud rates to try (defaults
to /dev/ttyUSB0 and 2400/1200/4800/9600 - 2400 8N1 is standard for this
protocol family, the others are just in case).
"""
import os
import select
import sys
import termios
import time
import tty

DEV = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
BAUDS = [int(b) for b in sys.argv[2:]] or [2400, 1200, 4800, 9600]

BAUD_CONST = {
    1200: termios.B1200,
    2400: termios.B2400,
    4800: termios.B4800,
    9600: termios.B9600,
}


def build(byte0):
    b = bytes([byte0, 0xFF, 0xFF, 0xFF, 0xFF])
    chk = (-sum(b)) & 0xFF
    return b + bytes([chk, 0x0D])


def set_baud(fd, baud):
    # Python's termios on Linux has no cfsetispeed/cfsetospeed - the speed
    # fields are just list elements 4 and 5 of what tcgetattr returns.
    attrs = termios.tcgetattr(fd)
    attrs[4] = BAUD_CONST[baud]
    attrs[5] = BAUD_CONST[baud]
    attrs[2] = (attrs[2] & ~termios.PARENB) & ~termios.CSTOPB
    attrs[2] = (attrs[2] & ~termios.CSIZE) | termios.CS8
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def probe(baud):
    fd = os.open(DEV, os.O_RDWR | os.O_NOCTTY)
    try:
        tty.setraw(fd)
        set_baud(fd, baud)
        for name, byte0 in [("I (Informacoes)", 0x49), ("Q (MedidoresEstado)", 0x51)]:
            req = build(byte0)
            os.write(fd, req)
            print(f"[{baud} baud] {name} sent: {req.hex()}")
            time.sleep(0.8)
            r, _, _ = select.select([fd], [], [], 1.5)
            if r:
                resp = os.read(fd, 256)
                print(f"[{baud} baud] {name} response: {resp.hex()}  {resp!r}")
            else:
                print(f"[{baud} baud] {name}: no response within timeout")
            time.sleep(0.3)
    finally:
        os.close(fd)


if __name__ == "__main__":
    for baud in BAUDS:
        if baud not in BAUD_CONST:
            print(f"skipping unsupported baud {baud}")
            continue
        probe(baud)
        print()
