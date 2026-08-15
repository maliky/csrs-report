from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "promote_production.sh"


def run_script(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_promotion_help_documents_check_and_apply_modes() -> None:
    result = run_script("--help")

    assert result.returncode == 0
    assert "--check" in result.stdout
    assert "--apply" in result.stdout
    assert "54.36.60.51" in result.stdout


def test_promotion_requires_a_full_commit_sha() -> None:
    result = run_script("--candidate", "8c6b213", "--check")

    assert result.returncode != 0
    assert "40 caracteres" in result.stderr


def test_promotion_script_keeps_release_safety_guards() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "git merge-base --is-ancestor origin/main" in source
    assert 'git push origin "$candidate:refs/heads/main"' in source
    assert "StrictHostKeyChecking=yes" in source
    assert "./scripts/backup_db.sh </dev/null" in source
    assert 'grep -F "DEPLOYMENT_OK candidate=$candidate "' in source
    assert "--force-recreate web" in source
    assert 'docker compose -p "$project" -f compose.yml ps -q web' in source
    assert "docker compose down" not in source
    assert "reset --hard" not in source
    assert "push --force" not in source


def test_images_receive_the_candidate_revision() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")

    assert 'LABEL org.opencontainers.image.revision="${CSRS_GIT_SHA}"' in dockerfile
    assert compose.count("CSRS_GIT_SHA: ${CSRS_GIT_SHA:-unknown}") == 2
