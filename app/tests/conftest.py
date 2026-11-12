"""Wspólne fixtures testów map-qa."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent
DATA_DIR = REPO_ROOT / "course-materials" / "exercise-data" / "map-qa"
FIXTURES = APP_DIR / "tests" / "fixtures"


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture()
def data_copy(tmp_path: Path) -> Path:
    """Kopia plików wejściowych z sources.json (bez zdjęć) w katalogu tymczasowym."""
    dst = tmp_path / "map-qa"
    dst.mkdir()
    for p in DATA_DIR.iterdir():
        if p.is_file():
            shutil.copy2(p, dst / p.name)
    return dst
