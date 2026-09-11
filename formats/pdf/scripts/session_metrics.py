"""Optional session wall-time diagnostics; stdlib only, no adapter QA integration.

Call start before work. Measurements begin at that call and cannot establish time
spent before it. Tool gaps and retries count until an explicit pause; a completed
checkpoint does not stop the clock. Pause at the end to freeze active elapsed time.
Checkpoint labels are caller-reported diagnostics, not proof of work or acceptance.
Use one writer per job. The entire JSON ledger is atomically replaced on mutation.
UTC wall-clock rollback is rejected, never converted into negative elapsed time.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile


FILENAME = "session-metrics.json"
STATUSES = ("started", "completed", "failed", "preview")
MODES = ("replace", "add_bilingual")


def _time(value=None):
    value = datetime.now(timezone.utc) if value is None else value
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Time must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _source(source):
    path = Path(source).resolve(strict=True)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "sha256": digest}


def _request(target_language, mode, pages, budget_per_page):
    if not isinstance(target_language, str) or not target_language.strip():
        raise ValueError("Target language is required")
    if mode not in MODES:
        raise ValueError("Mode must be replace or add_bilingual")
    if type(pages) is not int or pages < 1:
        raise ValueError("Pages must be a positive integer")
    if (isinstance(budget_per_page, bool) or not isinstance(budget_per_page, (int, float))
            or not math.isfinite(budget_per_page) or budget_per_page <= 0
            or not math.isfinite(pages * budget_per_page)):
        raise ValueError("Budget per page must be finite and positive")
    return {"target_language": target_language.strip().lower(), "mode": mode,
            "pages": pages, "budget_per_page_seconds": budget_per_page}


def _save(job, ledger):
    directory = Path(job)
    directory.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".session-metrics-", suffix=".tmp", delete=False) as stream:
            name = stream.name
            json.dump(ledger, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, directory / FILENAME)
    finally:
        if name is not None and Path(name).exists():
            Path(name).unlink()


def _load(job):
    with (Path(job) / FILENAME).open(encoding="utf-8") as stream:
        ledger = json.load(stream)
    try:
        if ledger["version"] != 1:
            raise ValueError("Unsupported session ledger version")
        request = ledger["request"]
        if request != _request(request["target_language"], request["mode"], request["pages"],
                               request["budget_per_page_seconds"]):
            raise ValueError("Invalid request in session ledger")
        if ledger["source"] != _source(ledger["source"]["path"]):
            raise ValueError("Source no longer matches the session ledger")
        return ledger
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("Invalid session ledger") from error


def _report(ledger, now):
    """Replay events so stored state cannot manufacture negative durations."""
    try:
        events = ledger["events"]
        if not events or events[0]["action"] != "start":
            raise ValueError("Session ledger must begin with start")
        start_time = previous = _time(events[0]["at"])
        active_duration = timedelta()
        paused = False
        for index, event in enumerate(events):
            at = _time(event["at"])
            if at < previous:
                raise ValueError("Session timestamps moved backwards")
            if not paused:
                active_duration += at - previous
            if event["active_elapsed_seconds"] != active_duration.total_seconds():
                raise ValueError("Session elapsed time does not match event chronology")
            action = event["action"]
            if action == "start" and index == 0:
                pass
            elif action == "pause" and not paused:
                paused = True
            elif action == "resume" and paused:
                paused = False
            elif (action == "checkpoint" and not paused and event["status"] in STATUSES
                  and isinstance(event["stage"], str) and event["stage"].strip()):
                pass
            else:
                raise ValueError("Invalid session event or pause/resume state")
            previous = at
        if now < previous:
            raise ValueError("Current time precedes the latest session event")
        if not paused:
            active_duration += now - previous
        active = active_duration.total_seconds()
        wall = (now - start_time).total_seconds()
        budget = ledger["request"]["pages"] * ledger["request"]["budget_per_page_seconds"]
        return {**ledger, "started_at": start_time.isoformat(), "as_of": now.isoformat(),
                "state": "paused" if paused else "active", "wall_elapsed_seconds": wall,
                "active_elapsed_seconds": active,
                "paused_seconds": (now - start_time - active_duration).total_seconds(),
                "budget_seconds": budget, "remaining_seconds": max(0, budget - active),
                "overrun_seconds": max(0, active - budget)}
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("Invalid session event ledger") from error


def start(job, source, target_language, mode, pages, budget_per_page=120, *, now=None):
    """Start once, or report an existing identical source/request without reset."""
    now = _time(now)
    request = _request(target_language, mode, pages, budget_per_page)
    binding = _source(source)
    if (Path(job) / FILENAME).exists():
        ledger = _load(job)
        if ledger["source"] != binding or ledger["request"] != request:
            raise ValueError("Source or request does not match the existing session; use another job")
        return _report(ledger, now)
    ledger = {"version": 1, "source": binding, "request": request,
              "events": [{"action": "start", "at": now.isoformat(), "active_elapsed_seconds": 0.0}]}
    _save(job, ledger)
    return _report(ledger, now)


def status(job, *, now=None):
    """Read-only report; status never changes timestamps or acceptance state."""
    return _report(_load(job), _time(now))


def _record(job, action, now, **fields):
    now = _time(now)
    ledger = _load(job)
    report = _report(ledger, now)
    ledger["events"].append({"action": action, "at": now.isoformat(),
                             "active_elapsed_seconds": report["active_elapsed_seconds"], **fields})
    result = _report(ledger, now)
    _save(job, ledger)
    return result


def checkpoint(job, stage, status, *, now=None):
    """Record a diagnostic checkpoint; repeated stages retain every attempt."""
    return _record(job, "checkpoint", now, stage=stage, status=status)


def pause(job, *, now=None):
    return _record(job, "pause", now)


def resume(job, *, now=None):
    return _record(job, "resume", now)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "checkpoint", "pause", "resume", "status"):
        command = commands.add_parser(name)
        command.add_argument("--job", required=True, type=Path)
        if name == "start":
            command.add_argument("--source", required=True, type=Path)
            command.add_argument("--target-language", required=True)
            command.add_argument("--mode", required=True, choices=MODES)
            command.add_argument("--pages", required=True, type=int)
            command.add_argument("--budget-per-page", type=float, default=120)
        elif name == "checkpoint":
            command.add_argument("--stage", required=True)
            command.add_argument("--status", required=True, choices=STATUSES)
    options = vars(parser.parse_args(argv))
    action = options.pop("command")
    try:
        result = {"start": start, "checkpoint": checkpoint, "pause": pause,
                  "resume": resume, "status": status}[action](**options)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
