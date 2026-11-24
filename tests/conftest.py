import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def pet_home(monkeypatch):
    # Unix socket paths are limited to ~104 bytes on macOS, so avoid pytest's long tmp_path.
    short = "/tmp" if sys.platform != "win32" and os.path.isdir("/tmp") else None
    d = Path(tempfile.mkdtemp(prefix="cpet-", dir=short))
    monkeypatch.setenv("BAO_HOME", str(d))
    monkeypatch.setenv("BAO_NO_LAUNCH", "1")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(params=["unix", "tcp"])
def transport(request, pet_home, monkeypatch):
    """Run IPC tests over the Unix socket (macOS/Linux) and TCP (Windows' transport)."""
    if request.param == "unix" and sys.platform == "win32":
        pytest.skip("no Unix sockets on Windows")
    if request.param == "tcp":
        monkeypatch.setenv("BAO_IPC", "tcp")
    else:
        monkeypatch.delenv("BAO_IPC", raising=False)
    return request.param
