#!/usr/bin/env python3
"""Ensure the deployment user's Docker CLI has a supported Compose plugin.

Uses Docker's user-local plugin installation path. Downloads are pinned and
checksum verified; neither sudo nor a Docker daemon restart is required.
"""
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

MINIMUM_VERSION = (2, 24, 4)
INSTALL_VERSION = "v2.40.3"
RELEASE_URL = f"https://github.com/docker/compose/releases/download/{INSTALL_VERSION}"


def supported_version(output):
    match = re.search(r"(?:^|\s)v?(\d+)\.(\d+)\.(\d+)", output.strip())
    return bool(match and tuple(map(int, match.groups())) >= MINIMUM_VERSION)


def compose_version():
    result = subprocess.run(
        ["docker", "compose", "version", "--short"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def download(url, destination):
    request = urllib.request.Request(url, headers={"User-Agent": "jntuh-compose-preflight"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def install_plugin(directory, architecture):
    asset = f"docker-compose-linux-{architecture}"
    directory.mkdir(parents=True, exist_ok=True)
    # Stage beside the destination so replacement is atomic on the same filesystem.
    with tempfile.TemporaryDirectory(prefix=".compose-install-", dir=directory) as staging:
        binary = Path(staging) / asset
        checksum = Path(staging) / (asset + ".sha256")
        download(f"{RELEASE_URL}/{asset}.sha256", checksum)
        parts = checksum.read_text().split()
        expected = parts[0].lower() if parts else ""
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise RuntimeError("Docker Compose release returned an invalid SHA-256 checksum")
        download(f"{RELEASE_URL}/{asset}", binary)
        digest = hashlib.sha256()
        with binary.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise RuntimeError("Docker Compose checksum mismatch; existing plugin was not replaced")
        binary.chmod(0o755)
        version = subprocess.run(
            [str(binary), "version", "--short"],
            capture_output=True, text=True, check=True,
        ).stdout
        if not supported_version(version):
            raise RuntimeError("Downloaded Compose binary does not meet the minimum version")
        binary.replace(directory / "docker-compose")


def ensure_compose():
    if shutil.which("docker") is None:
        raise RuntimeError("Docker CLI is missing; install Docker Engine before deploying")
    version = compose_version()
    if supported_version(version):
        print(f"Using Docker Compose {version}", flush=True)
        return
    if platform.system() != "Linux":
        raise RuntimeError("Docker Compose >= 2.24.4 is required; update Docker Desktop")
    architecture = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}.get(platform.machine())
    if architecture is None:
        raise RuntimeError(f"Unsupported Compose installation architecture: {platform.machine()}")
    docker_config = Path(os.environ.get("DOCKER_CONFIG") or Path.home() / ".docker")
    directory = docker_config / "cli-plugins"
    print(f"Compose plugin missing or too old; installing {INSTALL_VERSION} into {directory}", flush=True)
    install_plugin(directory, architecture)
    version = compose_version()
    if not supported_version(version):
        raise RuntimeError(
            f"Plugin installed at {directory / 'docker-compose'}, but Docker CLI cannot load it. "
            "Update the Docker CLI and check DOCKER_CONFIG."
        )
    print(f"Using Docker Compose {version}", flush=True)


if __name__ == "__main__":
    try:
        ensure_compose()
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        print(f"Compose preflight failed: {error}", file=sys.stderr)
        sys.exit(1)
