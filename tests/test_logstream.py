"""Tests for logstream.py — queue behavior and SSE formatting."""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def test_push_strips_ansi_codes_in_log_function(capsys):
    import logstream

    logstream.log_stream.clear()
    logstream.log("\x1b[31mHello\x1b[0m", "error")

    output = capsys.readouterr().out
    assert "Hello" in output

    event = next(logstream.log_stream.stream(timeout=0.01))
    assert '"message": "Hello"' in event
    assert '"level": "error"' in event


def test_stream_stops_on_terminal_event():
    from logstream import LogStream

    stream = LogStream()
    stream.push("working")
    stream.push_event("complete", {"ok": True})

    entries = list(stream.stream(timeout=0.01))

    assert len(entries) == 2
    assert '"type": "complete"' in entries[-1]

