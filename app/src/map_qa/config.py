from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_DIR.parent
DEFAULT_DATA_DIR = REPO_ROOT / "course-materials/exercise-data/map-qa"
DEFAULT_OUT_DIR = REPO_ROOT / "reports/map-qa/runs"
DEFAULT_DB = DEFAULT_DATA_DIR / "data/map_qa.db"
THRESHOLDS_PATH = APP_DIR / "config/thresholds.toml"
MAX_LIMITS = {"decision": 25, "comparison": 5, "fallback": 10}

def resolve_repo_path(p: str | Path) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path

def load_thresholds(path: str | Path = THRESHOLDS_PATH) -> dict:
    with Path(path).open("rb") as f:
        return tomllib.load(f)

@dataclass(frozen=True)
class Limits:
    decision: int = 0
    comparison: int = 0
    fallback: int = 0
    max_cost_usd: float = 0.0
    def any_positive(self) -> bool:
        return any((self.decision, self.comparison, self.fallback))

class ArgumentValidationError(ValueError):
    pass

def validate_limits(limits: Limits) -> None:
    for name, maximum in MAX_LIMITS.items():
        value = getattr(limits, name)
        if value < 0 or value > maximum:
            raise ArgumentValidationError(f"Limit {name} musi być w zakresie 0–{maximum}.")
    if limits.max_cost_usd < 0:
        raise ArgumentValidationError("Maksymalny koszt nie może być ujemny.")
    if limits.any_positive() and limits.max_cost_usd == 0:
        raise ArgumentValidationError("Dodatnie limity wymagają dodatniego --max-cost-usd.")
