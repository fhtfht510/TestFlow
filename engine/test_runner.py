"""Pytest runner that executes YAML test cases and reports to Allure + builtin HTML."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import allure
import pytest
import requests
from requests.adapters import HTTPAdapter
import yaml

from engine.api_runner import run_api_step
from engine.context import TestContext
from engine.paths import BUILTIN_RESULTS_DIR, CASES_DIR, ENVS_FILE, WORK_DIR
from engine.ui_runner import BrowserSession, run_ui_step


def _load_env_vars(env_name: str) -> dict[str, Any]:
    if not ENVS_FILE.exists():
        return {}
    data = yaml.safe_load(ENVS_FILE.read_text(encoding="utf-8")) or {}
    envs = data.get("environments", data)
    selected = envs.get(env_name, {})
    return dict(selected) if isinstance(selected, dict) else {}


def _discover_cases() -> list[str]:
    raw = os.environ.get("TESTFLOW_CASES", "").strip()
    if raw:
        try:
            paths = json.loads(raw)
            return [str(Path(p)) for p in paths]
        except json.JSONDecodeError:
            return [p.strip() for p in raw.split(",") if p.strip()]
    if not CASES_DIR.exists():
        return []
    return [str(p) for p in sorted(CASES_DIR.glob("*.yaml"))]


_CASE_FILES = _discover_cases()


@pytest.mark.parametrize(
    "case_path",
    _CASE_FILES,
    ids=[Path(p).stem for p in _CASE_FILES] or None,
)
def test_case(case_path: str) -> None:
    path = Path(case_path)
    if not path.is_absolute():
        path = WORK_DIR / path
    case_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    case_name = case_data.get("name") or path.stem
    allure.dynamic.title(case_name)
    if case_data.get("description"):
        allure.dynamic.description(str(case_data["description"]))

    env_name = os.environ.get("TESTFLOW_ENV", "local_demo")
    headless = os.environ.get("TESTFLOW_HEADLESS", "1") != "0"
    ui_engine = os.environ.get("TESTFLOW_UI_ENGINE", "selenium").lower()
    browser_name = os.environ.get("TESTFLOW_BROWSER", "auto").lower()
    allure.dynamic.parent_suite("TestFlow 自动化测试")
    allure.dynamic.suite(case_name)
    allure.dynamic.feature(f"环境: {env_name}")
    allure.dynamic.story(case_name)
    allure.dynamic.label("ui_engine", ui_engine)
    allure.dynamic.label("browser", browser_name)

    ctx = TestContext(_load_env_vars(env_name))
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=16, pool_maxsize=32)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    ctx.http_session = session
    browser = BrowserSession(headless=headless, engine=ui_engine, browser=browser_name)

    case_t0 = time.perf_counter()
    case_record: dict[str, Any] = {
        "filename": path.name,
        "name": case_name,
        "description": str(case_data.get("description") or ""),
        "env": env_name,
        "ui_engine": ui_engine,
        "browser": browser_name,
        "status": "passed",
        "error": "",
        "duration_ms": 0.0,
        "steps": [],
    }

    try:
        for idx, step in enumerate(case_data.get("steps") or [], start=1):
            step_type = str(step.get("type", "api")).lower()
            step_name = step.get("name") or f"步骤 {idx} ({step_type.upper()})"
            step_record: dict[str, Any] = {
                "index": idx,
                "type": step_type,
                "name": step_name,
                "status": "passed",
                "duration_ms": 0.0,
                "error": "",
                "screenshots": [],
            }
            if step.get("enabled", True) is False:
                step_record["status"] = "skipped"
                case_record["steps"].append(step_record)
                with allure.step(f"[已跳过] {step_name}"):
                    pass
                continue

            step_t0 = time.perf_counter()
            shot_offset = len(browser.screenshots)
            try:
                with allure.step(step_name):
                    if step_type == "api":
                        run_api_step(step, ctx, step_record=step_record)
                    elif step_type == "ui":
                        step_record["ui"] = {
                            "action": step.get("action", ""),
                            "by": step.get("by", ""),
                            "locator": str(ctx.render(step.get("locator", ""))),
                            "value": str(ctx.render(step.get("value", ""))),
                        }
                        run_ui_step(step, ctx, browser)
                    else:
                        raise ValueError(f"Unknown step type: {step_type}")
            except Exception as exc:
                step_record["status"] = "failed"
                step_record["error"] = str(exc)
                case_record["status"] = "failed"
                case_record["error"] = str(exc)
                raise
            finally:
                step_record["duration_ms"] = round((time.perf_counter() - step_t0) * 1000, 2)
                if len(browser.screenshots) > shot_offset:
                    step_record["screenshots"] = browser.screenshots[shot_offset:]
                case_record["steps"].append(step_record)
    finally:
        case_record["duration_ms"] = round((time.perf_counter() - case_t0) * 1000, 2)
        try:
            BUILTIN_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            out_file = BUILTIN_RESULTS_DIR / f"{path.stem}.json"
            out_file.write_text(
                json.dumps(case_record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
        if ctx.http_session is not None:
            try:
                ctx.http_session.close()
            except Exception:
                pass
        browser.close()
