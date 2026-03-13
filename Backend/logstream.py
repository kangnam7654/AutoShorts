import json
import queue
import re
import time
from typing import Any


class LogStream:
    """Thread-safe log queue that can also stream SSE events."""

    def __init__(self, maxsize: int = 500):
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)

    def _drop_oldest_entry(self) -> None:
        try:
            self._queue.get_nowait()
        except queue.Empty:
            pass

    def _push_entry(self, entry: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(entry)
            return
        except queue.Full:
            self._drop_oldest_entry()

        try:
            self._queue.put_nowait(entry)
        except queue.Full:
            pass

    def clear(self) -> None:
        """Drain all pending items from the queue."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def push(self, message: str, level: str = "info") -> None:
        """Add a log entry."""
        self._push_entry(
            {
                "type": "log",
                "message": message,
                "level": level,
                "timestamp": time.time(),
            }
        )

    def push_event(self, event_type: str, data: dict | None = None) -> None:
        """Send a control event such as complete, error, or cancelled."""
        self._push_entry(
            {
                "type": event_type,
                "timestamp": time.time(),
                **(data or {}),
            }
        )

    def stream(self, timeout: float = 30.0):
        """Yield SSE-formatted entries until a terminal event arrives."""
        while True:
            try:
                entry = self._queue.get(timeout=timeout)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue

            yield f"data: {json.dumps(entry)}\n\n"
            if entry.get("type") in ("complete", "error", "cancelled"):
                return


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
log_stream = LogStream()


def log(message: str, level: str = "info") -> None:
    """Print a message and push an ANSI-stripped copy to the SSE queue."""
    print(message)
    clean_message = _ANSI_RE.sub("", str(message))
    log_stream.push(clean_message, level)
