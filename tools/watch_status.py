#!/usr/bin/env python3
"""Watches the nobreak's status bits once per second, to pin down what
each bit in EstadoBateria actually means on your specific unit - real
testing has already shown resource/protocolos/monofasico.xml's declared
bit positions aren't fully reliable (see README's "What's confirmed vs.
best-effort" section).

Run from inside the container (needs reader.py on the import path, hence
-w /opt/app):

    # Drives a test_for_seconds itself and watches the transition:
    docker exec -w /opt/app sms-powerview python3 /opt/tools/watch_status.py [total_seconds]

    # Pure observation, no command sent - trigger the event yourself
    # (e.g. briefly unplug AC power) right after the baseline line prints:
    docker exec -w /opt/app sms-powerview python3 /opt/tools/watch_status.py --watch [total_seconds]

Prints the raw status byte and every decoded flag, once a second, for
`total_seconds` (default 15).
"""
import sys
import time

sys.path.insert(0, "/opt/app")

import reader  # noqa: E402


def snapshot() -> str:
    try:
        data = reader.read_monitor()
    except reader.PowerViewError as exc:
        return f"error: {exc}"
    info = data["info"]
    bits = " ".join(f"{k}={v}" for k, v in info.items() if not k.startswith("_"))
    return f"{info.get('_debug_estado_byte')}  {bits}"


def main() -> None:
    args = sys.argv[1:]
    watch_only = "--watch" in args
    if watch_only:
        args.remove("--watch")
    total = int(args[0]) if args else 15

    print(f"[t=0s] baseline: {snapshot()}")

    if watch_only:
        print("watch mode - no command sent; trigger the event yourself now (e.g. briefly unplug AC power)")
    else:
        test_seconds = max(3, total - 5)
        reader.send_command("test_for_seconds", seconds=test_seconds)
        print(f"sent test_for_seconds(seconds={test_seconds})")

    for t in range(1, total + 1):
        time.sleep(1)
        print(f"[t={t}s] {snapshot()}")


if __name__ == "__main__":
    main()
