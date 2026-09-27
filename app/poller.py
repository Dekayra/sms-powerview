"""Single background thread that owns all communication with the nobreak.

Reading is centralized here (rather than each of MQTT, /monitor, and
websocket clients independently opening the serial port) because it's a
single physical serial line - concurrent opens from multiple threads risk
"device busy" errors and interleaved reads/writes. Everything else
(MQTT publishing, websocket pushes, the JSON endpoint, the 24h history,
and now commands too) is fed through this one thread.
"""
import logging
import os
import queue
import threading
import time

from history_store import history_store
from reader import PowerViewError, read_monitor, send_command

logger = logging.getLogger("sms_powerview.poller")

POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "15"))


class Poller:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest = None
        self._latest_error = None
        self._listeners = set()  # callables: (data_dict | None, error_str | None) -> None
        self._sinks = []  # callables: (data_dict) -> None, only called on success
        self._command_queue = queue.Queue()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None

    def add_sink(self, fn) -> None:
        """Registers a callback invoked with each successful reading (e.g.
        the MQTT publisher). Must not raise - exceptions are caught+logged
        so one broken sink can't take down the poll loop."""
        self._sinks.append(fn)

    def add_listener(self, fn) -> None:
        """Registers a callback invoked on every poll, success or failure -
        used for pushing to websocket clients."""
        with self._lock:
            self._listeners.add(fn)

    def remove_listener(self, fn) -> None:
        with self._lock:
            self._listeners.discard(fn)

    def latest(self):
        """Returns (data_dict | None, error_str | None) from the most recent poll."""
        with self._lock:
            return self._latest, self._latest_error

    def history(self, since_epoch: float = 0.0):
        """Returns [{"ts": ..., "status": {...}, "info": {...}}, ...] from disk."""
        return history_store.query(since_epoch)

    def submit_command(self, name: str, kwargs: dict, timeout: float = 10.0):
        """Queues a write command to run on the poller thread and blocks
        until it's done (or times out). Raises PowerViewError on failure."""
        result_queue = queue.Queue(maxsize=1)
        self._command_queue.put((name, kwargs, result_queue))
        self._wake.set()
        try:
            outcome = result_queue.get(timeout=timeout)
        except queue.Empty:
            raise PowerViewError("command timed out waiting for the poll loop")
        if isinstance(outcome, Exception):
            raise outcome

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _drain_commands(self) -> None:
        while True:
            try:
                name, kwargs, result_queue = self._command_queue.get_nowait()
            except queue.Empty:
                return
            try:
                send_command(name, **kwargs)
                result_queue.put(True)
            except Exception as exc:
                result_queue.put(exc)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._drain_commands()
            if self._stop.is_set():
                return

            data, error = None, None
            try:
                data = read_monitor()
            except PowerViewError as exc:
                error = str(exc)
                logger.warning("could not read nobreak status: %s", exc)
            except Exception:
                logger.exception("unexpected error while polling the nobreak")
                error = "unexpected error"

            now = time.time()
            with self._lock:
                self._latest = data
                self._latest_error = error
                listeners = list(self._listeners)

            if data is not None:
                history_store.add(now, data)
                for sink in self._sinks:
                    try:
                        sink(data)
                    except Exception:
                        logger.exception("sink %r failed", sink)

            for listener in listeners:
                try:
                    listener(data, error)
                except Exception:
                    logger.exception("listener %r failed", listener)

            self._wake.wait(POLL_INTERVAL)
            self._wake.clear()


poller = Poller()
