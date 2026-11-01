import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest


@pytest.fixture
def startup_project(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "start.sh"
    shutil.copyfile(Path(__file__).resolve().parents[1] / "scripts" / "start.sh", script)
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    python = venv_bin / "python"
    python.write_text(
        '#!/usr/bin/env bash\n'
        'if [[ "${1:-}" == "app.py" ]]; then exit 0; fi\n'
        f'exec {shlex.quote(sys.executable)} "$@"\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    pip = venv_bin / "pip"
    pip.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$*" >> "$PIP_CALL_LOG"\n'
        'if [[ "$*" == "install --upgrade --upgrade-strategy eager -r requirements.txt" ]]; then\n'
        '  exit "${REQUIREMENTS_INSTALL_EXIT_CODE:-0}"\n'
        'fi\n',
        encoding="utf-8",
    )
    pip.chmod(0o755)
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("Pillow==13.0.0\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        VENV_DIR=str(venv_bin.parent),
        ENV_FILE=str(tmp_path / ".env.local"),
        DOWNLOAD_TOKEN_SECRET="test-startup-secret",
        PIP_CALL_LOG=str(tmp_path / "pip.log"),
        SKIP_PIP_INSTALL="0",
        REQUIREMENTS_INSTALL_EXIT_CODE="0",
    )
    return tmp_path, script, env


def _start(project):
    root, script, env = project
    return subprocess.run(["bash", str(script)], cwd=root, env=env, capture_output=True, text=True, timeout=10)


def _digest(root):
    return hashlib.sha256((root / "requirements.txt").read_bytes()).hexdigest()


@pytest.mark.parametrize("legacy_marker", [False, True])
def test_startup_installs_requirements_even_when_packages_are_importable(startup_project, legacy_marker):
    root, _, _ = startup_project
    marker = root / ".venv" / ".requirements-installed"
    if legacy_marker:
        marker.touch()

    result = _start(startup_project)

    assert result.returncode == 0, result.stderr
    assert (root / "pip.log").read_text().splitlines() == [
        "install --upgrade pip", "install --upgrade --upgrade-strategy eager -r requirements.txt",
    ]
    assert marker.read_text().strip() == _digest(root)


def test_startup_skips_install_for_unchanged_requirements(startup_project):
    root, _, _ = startup_project
    assert _start(startup_project).returncode == 0
    calls = (root / "pip.log").read_text()

    result = _start(startup_project)

    assert result.returncode == 0, result.stderr
    assert (root / "pip.log").read_text() == calls


def test_startup_installs_changed_requirements_even_with_older_mtime(startup_project):
    root, _, _ = startup_project
    assert _start(startup_project).returncode == 0
    marker = root / ".venv" / ".requirements-installed"
    requirements = root / "requirements.txt"
    requirements.write_text("Pillow==13.0.1\n", encoding="utf-8")
    os.utime(requirements, (1, 1))

    result = _start(startup_project)

    assert result.returncode == 0, result.stderr
    assert (root / "pip.log").read_text().splitlines().count("install --upgrade --upgrade-strategy eager -r requirements.txt") == 2
    assert marker.read_text().strip() == _digest(root)


def test_startup_does_not_mark_failed_installation_ready(startup_project):
    root, _, env = startup_project
    marker = root / ".venv" / ".requirements-installed"
    marker.write_text("previous-requirements-hash\n", encoding="utf-8")
    env["REQUIREMENTS_INSTALL_EXIT_CODE"] = "1"

    result = _start(startup_project)

    assert result.returncode != 0
    assert marker.read_text() == "previous-requirements-hash\n"


def test_startup_preserves_explicit_skip_install(startup_project):
    root, _, env = startup_project
    env["SKIP_PIP_INSTALL"] = "1"

    result = _start(startup_project)

    assert result.returncode == 0, result.stderr
    assert not (root / "pip.log").exists()
    assert not (root / ".venv" / ".requirements-installed").exists()
