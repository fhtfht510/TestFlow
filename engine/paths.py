"""Unified path resolution for both source mode and PyInstaller frozen .exe mode."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

IS_FROZEN: bool = getattr(sys, "frozen", False)
BUNDLE_DIR: Path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WORK_DIR: Path = (
    Path(sys.executable).resolve().parent
    if IS_FROZEN
    else Path(__file__).resolve().parent.parent
)

STATIC_DIR: Path = BUNDLE_DIR / "static"
RUNNER_FILE: Path = BUNDLE_DIR / "engine" / "test_runner.py"

CASES_DIR: Path = WORK_DIR / "cases"
CONFIG_DIR: Path = WORK_DIR / "config"
ENVS_FILE: Path = CONFIG_DIR / "envs.yaml"
REPORTS_DIR: Path = WORK_DIR / "reports"
ALLURE_RESULTS_DIR: Path = REPORTS_DIR / "allure-results"
ALLURE_REPORT_DIR: Path = REPORTS_DIR / "allure-report"
BUILTIN_RESULTS_DIR: Path = REPORTS_DIR / "builtin-results"
BUILTIN_REPORT_DIR: Path = REPORTS_DIR / "builtin-report"
DRIVERS_DIR: Path = WORK_DIR / "drivers"


def ensure_workspace_initialized() -> None:
    """Create writable runtime directories and seed default config/cases on first run."""
    for d in (
        CASES_DIR,
        CONFIG_DIR,
        ALLURE_RESULTS_DIR,
        ALLURE_REPORT_DIR,
        BUILTIN_RESULTS_DIR,
        BUILTIN_REPORT_DIR,
        DRIVERS_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)

    if BUNDLE_DIR == WORK_DIR:
        return

    seed_envs = BUNDLE_DIR / "config" / "envs.yaml"
    if not ENVS_FILE.exists() and seed_envs.exists():
        shutil.copy2(seed_envs, ENVS_FILE)

    seed_cases_dir = BUNDLE_DIR / "cases"
    if seed_cases_dir.exists() and not any(CASES_DIR.glob("*.yaml")):
        for item in seed_cases_dir.glob("*.yaml"):
            shutil.copy2(item, CASES_DIR / item.name)
