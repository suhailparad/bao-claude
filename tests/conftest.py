import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def pet_home(monkeypatch):
    # Unix socket paths are limited to ~104 bytes on macOS, so avoid pytest's long tmp_path.
    d = Path(tempfile.mkdtemp(prefix="cpet-", dir="/tmp"))
    monkeypatch.setenv("BAO_HOME", str(d))
    monkeypatch.setenv("BAO_NO_LAUNCH", "1")
    yield d
    shutil.rmtree(d, ignore_errors=True)
