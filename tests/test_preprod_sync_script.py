from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_preprod_from_production.sh"
BACKUP_SCRIPT = ROOT / "scripts" / "backup_db.sh"
ROOT_WRAPPER = ROOT / "infrastructure" / "deploy" / "csrs-report-preprod-sync-root"
DEPLOY_WRAPPER = ROOT / "infrastructure" / "deploy" / "csrs-report-preprod-deploy-root"
TIMER = ROOT / "deploy" / "systemd" / "csrs-report-preprod-sync.timer"


def run_script(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_sync_help_documents_check_and_apply_modes() -> None:
    result = run_script("--help")

    assert result.returncode == 2
    assert "--check" in result.stderr
    assert "--apply" in result.stderr


def test_backup_rejects_an_unsafe_timestamp_before_using_docker() -> None:
    environment = os.environ.copy()
    environment["CSRS_BACKUP_TIMESTAMP"] = "../unsafe"
    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "YYYYMMDDTHHMMSSZ" in result.stderr


def test_sync_keeps_production_read_only_and_preprod_recoverable() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "StrictHostKeyChecking=yes" in source
    assert "pg_dump --format=custom --no-owner --no-acl" in source
    assert "tar --create --gzip --directory /private-media" in source
    assert "CSRS_START_NOTIFIER doit rester à 0" in source
    assert source.index("pg_restore --list") < source.index("./scripts/backup_db.sh")
    assert source.index("./scripts/backup_db.sh") < source.rindex("stop notifier web")
    assert "rollback_preprod" in source
    assert "dropdb --if-exists --force" in source
    assert "docker compose down" not in source
    assert "scp " not in source
    assert (
        ".env"
        not in source[source.index("fetch_database") : source.index("restore_database")]
    )


def test_sync_and_deploy_use_the_same_operation_lock() -> None:
    sync_source = ROOT_WRAPPER.read_text(encoding="utf-8")
    deploy_source = DEPLOY_WRAPPER.read_text(encoding="utf-8")

    lock = "/run/lock/csrs-report-preprod-deploy.lock"
    assert lock in sync_source
    assert lock in deploy_source
    assert "flock -n" in sync_source


def test_timer_runs_only_at_the_nightly_window_without_catch_up() -> None:
    source = TIMER.read_text(encoding="utf-8")

    assert "OnCalendar=*-*-* 02:30:00 UTC" in source
    assert "Persistent=false" in source
    assert "RandomizedDelaySec=0" in source
