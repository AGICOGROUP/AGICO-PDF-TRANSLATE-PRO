"""Behavior checks for optional, source-bound session wall-time diagnostics."""

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "session_metrics.py"
T0 = datetime(2026, 9, 11, tzinfo=timezone.utc)


def test_standalone_cli_is_available():
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "checkpoint" in result.stdout


@pytest.fixture
def metrics():
    assert SCRIPT.is_file(), "The standalone session timing module is not implemented"
    spec = importlib.util.spec_from_file_location("session_metrics_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def job(tmp_path, metrics):
    source = tmp_path / "input.pdf"
    source.write_bytes(b"%PDF-1.7\nsource fixture")
    directory = tmp_path / "job"
    metrics.start(directory, source, "zh", "replace", 2, now=T0)
    return directory, source


def test_repeated_start_preserves_initial_timer_and_history(metrics, job):
    directory, source = job
    metrics.checkpoint(directory, "extract", "completed", now=T0 + timedelta(seconds=20))
    before = (directory / "session-metrics.json").read_bytes()
    report = metrics.start(directory, source, "zh", "replace", 2,
                           now=T0 + timedelta(seconds=75))
    assert report["active_elapsed_seconds"] == 75
    assert report["remaining_seconds"] == 165
    assert report["started_at"] == T0.isoformat()
    assert len(report["events"]) == 2
    assert (directory / "session-metrics.json").read_bytes() == before


def test_pause_excludes_only_explicit_wait_and_resume_counts_tool_gaps(metrics, job):
    directory, _ = job
    metrics.pause(directory, now=T0 + timedelta(seconds=30))
    paused = metrics.status(directory, now=T0 + timedelta(seconds=90))
    assert paused["active_elapsed_seconds"] == 30
    assert paused["paused_seconds"] == 60
    metrics.resume(directory, now=T0 + timedelta(seconds=120))
    report = metrics.status(directory, now=T0 + timedelta(seconds=150))
    assert report["active_elapsed_seconds"] == 60
    assert report["paused_seconds"] == 90
    assert report["wall_elapsed_seconds"] == 150


def test_failed_attempt_and_retry_remain_in_history_and_budget_is_diagnostic(metrics, job):
    directory, _ = job
    metrics.checkpoint(directory, "build", "started", now=T0 + timedelta(seconds=10))
    metrics.checkpoint(directory, "build", "failed", now=T0 + timedelta(seconds=80))
    metrics.checkpoint(directory, "build", "started", now=T0 + timedelta(seconds=100))
    metrics.checkpoint(directory, "build", "preview", now=T0 + timedelta(seconds=250))
    report = metrics.checkpoint(directory, "build", "completed", now=T0 + timedelta(seconds=270))
    assert report["active_elapsed_seconds"] == 270
    assert report["remaining_seconds"] == 0
    assert report["overrun_seconds"] == 30
    attempts = report["events"][1:]
    assert [event["status"] for event in attempts] == ["started", "failed", "started", "preview", "completed"]
    assert attempts[1]["active_elapsed_seconds"] == 80
    assert attempts[1]["at"] == (T0 + timedelta(seconds=80)).isoformat()
    assert not any("qa" in key.lower() for key in report)
    assert metrics.status(directory, now=T0 + timedelta(seconds=300))["active_elapsed_seconds"] == 300


@pytest.mark.parametrize("changed", ["source", "language", "mode", "pages", "budget"])
def test_request_mismatch_does_not_reset_existing_ledger(metrics, job, changed):
    directory, source = job
    before = (directory / "session-metrics.json").read_bytes()
    args = dict(job=directory, source=source, target_language="zh", mode="replace", pages=2,
                budget_per_page=120, now=T0 + timedelta(seconds=5))
    if changed == "source":
        source.write_bytes(b"different source")
    else:
        args[{"language": "target_language", "mode": "mode", "pages": "pages", "budget": "budget_per_page"}[changed]] = {
            "language": "fr", "mode": "add_bilingual", "pages": 3, "budget": 60
        }[changed]
    with pytest.raises(ValueError, match="(?i)(source|request|match)"):
        metrics.start(**args)
    assert (directory / "session-metrics.json").read_bytes() == before


def test_source_mutation_rejected_by_checkpoints(metrics, job):
    directory, source = job
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="(?i)source"):
        metrics.checkpoint(directory, "build", "completed", now=T0 + timedelta(seconds=10))


def test_invalid_state_and_backwards_clock_do_not_modify_ledger(metrics, job):
    directory, _ = job
    before = (directory / "session-metrics.json").read_bytes()
    with pytest.raises(ValueError):
        metrics.resume(directory, now=T0 + timedelta(seconds=5))
    with pytest.raises(ValueError):
        metrics.checkpoint(directory, "", "completed", now=T0)
    with pytest.raises(ValueError):
        metrics.checkpoint(directory, "build", "passed", now=T0)
    with pytest.raises(ValueError):
        metrics.status(directory, now=T0 - timedelta(seconds=1))
    assert (directory / "session-metrics.json").read_bytes() == before
    metrics.pause(directory, now=T0 + timedelta(seconds=10))
    before = (directory / "session-metrics.json").read_bytes()
    with pytest.raises(ValueError):
        metrics.pause(directory, now=T0 + timedelta(seconds=15))
    with pytest.raises(ValueError):
        metrics.checkpoint(directory, "build", "completed", now=T0 + timedelta(seconds=15))
    with pytest.raises(ValueError):
        metrics.resume(directory, now=T0 + timedelta(seconds=9))
    assert (directory / "session-metrics.json").read_bytes() == before


@pytest.mark.parametrize("field,value", [("pages", 0), ("pages", -1), ("pages", 1.5),
                                        ("budget_per_page", 0), ("budget_per_page", float("nan")),
                                        ("mode", "auto"), ("target_language", " ")])
def test_invalid_request_cannot_create_ledger(metrics, tmp_path, field, value):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"pdf fixture")
    args = dict(job=tmp_path / "bad-job", source=source, target_language="zh", mode="replace",
                pages=1, budget_per_page=120, now=T0)
    args[field] = value
    with pytest.raises(ValueError):
        metrics.start(**args)
    assert not (args["job"] / "session-metrics.json").exists()


def test_corrupt_chronology_is_rejected_without_fabricated_elapsed_time(metrics, job):
    directory, _ = job
    metrics.pause(directory, now=T0 + timedelta(seconds=10))
    path = directory / "session-metrics.json"
    ledger = json.loads(path.read_text())
    ledger["events"][1]["at"] = (T0 - timedelta(seconds=5)).isoformat()
    path.write_text(json.dumps(ledger))
    with pytest.raises(ValueError):
        metrics.status(directory, now=T0 + timedelta(seconds=20))


def test_fractional_timestamps_do_not_invent_negative_paused_time(metrics, job):
    directory, _ = job
    metrics.checkpoint(directory, "a", "completed", now=T0 + timedelta(seconds=0.1))
    metrics.checkpoint(directory, "b", "completed", now=T0 + timedelta(seconds=0.3))
    report = metrics.status(directory, now=T0 + timedelta(seconds=0.3))
    assert report["paused_seconds"] == 0
    assert report["active_elapsed_seconds"] == 0.3


def test_failed_atomic_replace_retains_original_ledger(metrics, job, monkeypatch):
    directory, _ = job
    before = (directory / "session-metrics.json").read_bytes()

    def unavailable_replace(source, destination):
        raise OSError("simulated filesystem replace failure")

    monkeypatch.setattr(metrics.os, "replace", unavailable_replace)
    with pytest.raises(OSError):
        metrics.checkpoint(directory, "build", "failed", now=T0 + timedelta(seconds=10))
    assert (directory / "session-metrics.json").read_bytes() == before
    assert not list(directory.glob(".session-metrics-*.tmp"))


def test_cli_emits_json_and_does_not_start_external_work(metrics, tmp_path, capsys):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fixture")
    directory = tmp_path / "cli-job"
    common = ["--job", str(directory)]
    assert metrics.main(["start", *common, "--source", str(source), "--target-language", "zh",
                         "--mode", "add_bilingual", "--pages", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["budget_seconds"] == 120
    assert metrics.main(["checkpoint", *common, "--stage", "render", "--status", "preview"]) == 0
    assert json.loads(capsys.readouterr().out)["events"][-1]["status"] == "preview"
    for action in ["pause", "status", "resume"]:
        assert metrics.main([action, *common]) == 0
        assert json.loads(capsys.readouterr().out)["active_elapsed_seconds"] >= 0
    assert metrics.main(["resume", *common]) == 2
    assert "error" in capsys.readouterr().err.lower()
