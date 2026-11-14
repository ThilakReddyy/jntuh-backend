import hashlib
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import ensure_compose as compose


@pytest.mark.parametrize("version, expected", [
    ("", False),
    ("1.29.2", False),
    ("2.20.3", False),
    ("v2.24.3", False),
    ("v2.24.4", True),
    ("2.31.0-desktop.2", True),
    ("Docker Compose version v2.40.3", True),
    ("v5.0.0", True),
])
def test_compose_version_support(version, expected):
    assert compose.supported_version(version) is expected


def test_existing_supported_plugin_does_not_install(monkeypatch):
    monkeypatch.setattr(compose.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(compose, "compose_version", lambda: "v2.31.0")
    install = Mock()
    monkeypatch.setattr(compose, "install_plugin", install)
    compose.ensure_compose()
    install.assert_not_called()


@pytest.mark.parametrize("installed", ["", "1.29.2", "2.20.0"])
def test_missing_or_old_plugin_is_installed_for_the_deployment_user(tmp_path, monkeypatch, installed):
    monkeypatch.setattr(compose.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(compose, "compose_version", Mock(side_effect=[installed, "2.40.3"]))
    monkeypatch.setattr(compose.platform, "system", lambda: "Linux")
    monkeypatch.setattr(compose.platform, "machine", lambda: "x86_64")
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))
    install = Mock()
    monkeypatch.setattr(compose, "install_plugin", install)
    compose.ensure_compose()
    install.assert_called_once_with(tmp_path / "cli-plugins", "x86_64")


def test_missing_docker_cli_has_actionable_error(monkeypatch):
    monkeypatch.setattr(compose.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="Docker CLI is missing"):
        compose.ensure_compose()


def test_installed_plugin_must_be_discoverable(tmp_path, monkeypatch):
    monkeypatch.setattr(compose.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(compose, "compose_version", lambda: "")
    monkeypatch.setattr(compose.platform, "system", lambda: "Linux")
    monkeypatch.setattr(compose.platform, "machine", lambda: "aarch64")
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))
    monkeypatch.setattr(compose, "install_plugin", Mock())
    with pytest.raises(RuntimeError, match="Docker CLI cannot load"):
        compose.ensure_compose()


@pytest.mark.parametrize("checksum_ok", [True, False])
def test_plugin_download_is_verified_before_replacing_existing_binary(tmp_path, monkeypatch, checksum_ok):
    binary = b"test compose binary"
    plugin = tmp_path / "docker-compose"
    plugin.write_bytes(b"existing plugin")
    digest = hashlib.sha256(binary if checksum_ok else b"different binary").hexdigest()
    urls = []

    def download(url, destination):
        urls.append(url)
        destination.write_bytes((digest + "  docker-compose-linux-x86_64\n").encode() if url.endswith(".sha256") else binary)

    monkeypatch.setattr(compose, "download", download)
    run = Mock(return_value=SimpleNamespace(stdout="2.40.3"))
    monkeypatch.setattr(compose.subprocess, "run", run)
    if checksum_ok:
        compose.install_plugin(tmp_path, "x86_64")
        assert plugin.read_bytes() == binary
        assert plugin.stat().st_mode & 0o111 == 0o111
        run.assert_called_once()
    else:
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            compose.install_plugin(tmp_path, "x86_64")
        assert plugin.read_bytes() == b"existing plugin"
        run.assert_not_called()
    assert all(url.startswith(compose.RELEASE_URL + "/") for url in urls)
    assert list(tmp_path.iterdir()) == [plugin]


def test_deployment_stops_before_docker_changes_when_preflight_fails(tmp_path):
    commands = tmp_path / "bin"
    commands.mkdir()
    python = commands / "python3"
    python.write_text("#!/bin/sh\nexit 37\n")
    python.chmod(0o755)
    marker = tmp_path / "docker-called"
    docker = commands / "docker"
    docker.write_text('#!/bin/sh\ntouch "$PREFLIGHT_DOCKER_MARKER"\nexit 0\n')
    docker.chmod(0o755)
    environment = {**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                   "PREFLIGHT_DOCKER_MARKER": str(marker)}
    script = Path(__file__).resolve().parents[1] / "scripts" / "deploy.sh"
    result = subprocess.run(["bash", str(script)], cwd=tmp_path, env=environment)
    assert result.returncode == 37
    assert not marker.exists()
