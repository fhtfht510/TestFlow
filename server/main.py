"""FastAPI backend for TestFlow workbench."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine.api_runner import _truncate_for_display, send_http_request
from engine.context import TestContext
from engine.html_report import generate_builtin_report
from engine.paths import (
    ALLURE_REPORT_DIR,
    ALLURE_RESULTS_DIR,
    BUILTIN_REPORT_DIR,
    BUILTIN_RESULTS_DIR,
    BUNDLE_DIR,
    CASES_DIR,
    ENVS_FILE,
    IS_FROZEN,
    RUNNER_FILE,
    STATIC_DIR,
    WORK_DIR,
    ensure_workspace_initialized,
)
from server.demo_app import router as demo_router

ensure_workspace_initialized()

app = FastAPI(title="TestFlow 自动化测试工作台", version="1.2.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(demo_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/allure-report", StaticFiles(directory=str(ALLURE_REPORT_DIR), html=True), name="allure-report")
app.mount("/builtin-report", StaticFiles(directory=str(BUILTIN_REPORT_DIR), html=True), name="builtin-report")

_DEBUG_SESSION = requests.Session()
_DEBUG_ADAPTER = HTTPAdapter(pool_connections=16, pool_maxsize=32)
_DEBUG_SESSION.mount("http://", _DEBUG_ADAPTER)
_DEBUG_SESSION.mount("https://", _DEBUG_ADAPTER)

_CASE_META_CACHE: dict[str, tuple[float, int, dict[str, Any]]] = {}


def _read_envs() -> dict[str, dict[str, Any]]:
    if not ENVS_FILE.exists():
        return {"local_demo": {"base_url": "http://127.0.0.1:8000"}}
    data = yaml.safe_load(ENVS_FILE.read_text(encoding="utf-8")) or {}
    envs = data.get("environments", data)
    return envs if isinstance(envs, dict) else {}


def _write_envs(envs: dict[str, dict[str, Any]]) -> None:
    payload = {"environments": envs}
    ENVS_FILE.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _safe_case_path(filename: str) -> Path:
    name = filename.strip()
    if not name.endswith(".yaml"):
        name += ".yaml"
    if Path(name).name != name or ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="非法用例文件名")
    return CASES_DIR / name


def _unique_case_path(base_filename: str) -> Path:
    path = _safe_case_path(base_filename)
    if not path.exists():
        return path
    stem = path.stem
    idx = 2
    while (CASES_DIR / f"{stem}_{idx}.yaml").exists():
        idx += 1
    return CASES_DIR / f"{stem}_{idx}.yaml"


def _slugify_filename(name: str) -> str:
    stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", name.strip()).strip("_")
    return (stem or "new_case") + ".yaml"


class EnvsPayload(BaseModel):
    environments: dict[str, dict[str, Any]]


class CasePayload(BaseModel):
    filename: str | None = None
    name: str
    description: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)


class ImportYamlPayload(BaseModel):
    filename: str | None = None
    content: str


class ImportCollectionPayload(BaseModel):
    filename: str | None = None
    content: str


class DebugRequestPayload(BaseModel):
    env: str = "local_demo"
    method: str = "GET"
    url: str
    headers: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    body: Any = None
    body_type: str = "json"
    form_fields: list[dict[str, Any]] = Field(default_factory=list)
    timeout: float = 15.0


class RunPayload(BaseModel):
    env: str = "local_demo"
    cases: list[str] = Field(default_factory=list)
    headless: bool = True
    ui_engine: str = "selenium"
    browser: str = "auto"


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico")
def serve_favicon() -> Response:
    ico = STATIC_DIR / "testflow.ico"
    if ico.exists():
        return FileResponse(ico, media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/api/envs")
def get_envs() -> dict[str, Any]:
    return {"environments": _read_envs()}


@app.put("/api/envs")
def update_envs(payload: EnvsPayload) -> dict[str, Any]:
    _write_envs(payload.environments)
    return {"ok": True, "environments": payload.environments}


@app.get("/api/cases")
def list_cases() -> dict[str, Any]:
    items = []
    seen: set[str] = set()
    for path in sorted(CASES_DIR.glob("*.yaml")):
        seen.add(path.name)
        try:
            st = path.stat()
            cached = _CASE_META_CACHE.get(path.name)
            if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
                items.append(cached[2])
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                data = {}
            meta = {
                "filename": path.name,
                "name": data.get("name") or path.stem,
                "description": data.get("description", ""),
                "step_count": len(data.get("steps") or []),
            }
            _CASE_META_CACHE[path.name] = (st.st_mtime, st.st_size, meta)
            items.append(meta)
        except Exception as exc:
            items.append(
                {
                    "filename": path.name,
                    "name": path.stem,
                    "description": f"[YAML 解析异常: {exc}]",
                    "step_count": 0,
                }
            )
    for stale in [k for k in _CASE_META_CACHE if k not in seen]:
        del _CASE_META_CACHE[stale]
    return {"cases": items}


@app.get("/api/cases/{filename}")
def get_case(filename: str) -> dict[str, Any]:
    path = _safe_case_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="用例不存在")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "filename": path.name,
        "name": data.get("name") or path.stem,
        "description": data.get("description", ""),
        "steps": data.get("steps") or [],
    }


@app.post("/api/cases")
def create_case(payload: CasePayload) -> dict[str, Any]:
    filename = payload.filename or _slugify_filename(payload.name)
    path = _unique_case_path(filename)
    content = {
        "name": payload.name,
        "description": payload.description,
        "steps": payload.steps,
    }
    path.write_text(yaml.safe_dump(content, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True, "filename": path.name, **content}


@app.put("/api/cases/{filename}")
def save_case(filename: str, payload: CasePayload) -> dict[str, Any]:
    path = _safe_case_path(filename)
    content = {
        "name": payload.name,
        "description": payload.description,
        "steps": payload.steps,
    }
    path.write_text(yaml.safe_dump(content, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True, "filename": path.name, **content}


@app.delete("/api/cases/{filename}")
def delete_case(filename: str) -> dict[str, Any]:
    path = _safe_case_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="用例不存在")
    path.unlink()
    return {"ok": True}


@app.get("/api/cases/{filename}/raw")
def get_case_raw(filename: str) -> dict[str, Any]:
    path = _safe_case_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="用例不存在")
    return {"filename": path.name, "content": path.read_text(encoding="utf-8")}


@app.post("/api/cases/import_yaml")
def import_case_yaml(payload: ImportYamlPayload) -> dict[str, Any]:
    try:
        data = yaml.safe_load(payload.content) or {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"YAML 解析失败: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="YAML 根节点必须是对象")

    name = str(data.get("name") or (Path(payload.filename).stem if payload.filename else "导入用例"))
    filename = payload.filename or _slugify_filename(name)
    path = _unique_case_path(filename)

    content = {
        "name": name,
        "description": str(data.get("description", "")),
        "steps": data.get("steps") or [],
    }
    path.write_text(yaml.safe_dump(content, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True, "filename": path.name, **content}


def _schema_example(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return ""
    if "example" in schema:
        return schema["example"]
    stype = schema.get("type", "object")
    if stype == "object" or "properties" in schema:
        return {k: _schema_example(v) for k, v in (schema.get("properties") or {}).items()}
    if stype == "array":
        return [_schema_example(schema.get("items") or {})]
    if stype in ("integer", "number"):
        return 0
    if stype == "boolean":
        return True
    return ""


def _parse_postman_items(items: list[Any], prefix: str = "") -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("item"), list):
            sub_prefix = f"{prefix}{item.get('name', '')}/" if item.get("name") else prefix
            steps.extend(_parse_postman_items(item["item"], sub_prefix))
            continue

        req = item.get("request")
        if not isinstance(req, dict):
            continue
        method = str(req.get("method") or "GET").upper()
        url_obj = req.get("url")
        params: dict[str, Any] = {}
        if isinstance(url_obj, dict):
            url = str(url_obj.get("raw") or "")
            if "?" in url:
                url = url.split("?", 1)[0]
            for q in url_obj.get("query") or []:
                if isinstance(q, dict) and not q.get("disabled") and q.get("key"):
                    params[str(q["key"])] = q.get("value", "")
        else:
            url = str(url_obj or "")

        headers: dict[str, Any] = {}
        for h in req.get("header") or []:
            if isinstance(h, dict) and not h.get("disabled") and h.get("key"):
                headers[str(h["key"])] = h.get("value", "")

        req_block: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "params": params,
        }
        body = req.get("body") or {}
        if isinstance(body, dict):
            mode = body.get("mode")
            if mode == "raw" and body.get("raw"):
                try:
                    req_block["json"] = json.loads(body["raw"])
                except Exception:
                    req_block["body"] = str(body["raw"])
            elif mode == "urlencoded":
                req_block["body_type"] = "form_urlencoded"
                req_block["form_fields"] = [
                    {"key": f.get("key", ""), "value": f.get("value", ""), "type": "text"}
                    for f in (body.get("urlencoded") or [])
                    if isinstance(f, dict) and not f.get("disabled") and f.get("key")
                ]
            elif mode == "formdata":
                req_block["body_type"] = "form_data"
                req_block["form_fields"] = [
                    {
                        "key": f.get("key", ""),
                        "value": (f.get("src") if isinstance(f.get("src"), str) else "") if f.get("type") == "file" else f.get("value", ""),
                        "type": "file" if f.get("type") == "file" else "text",
                    }
                    for f in (body.get("formdata") or [])
                    if isinstance(f, dict) and not f.get("disabled") and f.get("key")
                ]

        steps.append(
            {
                "type": "api",
                "name": f"{prefix}{item.get('name') or method + ' ' + url}",
                "request": req_block,
                "extract": [],
                "assertions": [{"type": "status_code", "target": "", "expected": 200}],
            }
        )
    return steps


def _parse_openapi_doc(doc: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    servers = doc.get("servers") or []
    base = "{{base_url}}"
    if isinstance(servers, list) and servers and isinstance(servers[0], dict) and servers[0].get("url"):
        srv_url = str(servers[0]["url"]).rstrip("/")
        if srv_url.startswith(("http://", "https://")):
            base = srv_url
    elif doc.get("host"):
        scheme = (doc.get("schemes") or ["http"])[0]
        base_path = str(doc.get("basePath") or "").rstrip("/")
        base = f"{scheme}://{doc['host']}{base_path}"

    paths = doc.get("paths") or {}
    for path_str, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            m_upper = method.upper()
            if m_upper not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                continue
            if not isinstance(op, dict):
                continue
            headers: dict[str, Any] = {}
            params: dict[str, Any] = {}
            json_body: Any = None
            for p in op.get("parameters") or []:
                if not isinstance(p, dict):
                    continue
                loc = p.get("in")
                pname = p.get("name")
                if loc == "query" and pname:
                    params[str(pname)] = _schema_example(p.get("schema") or {"type": p.get("type", "string")})
                elif loc == "header" and pname:
                    headers[str(pname)] = _schema_example(p.get("schema") or {"type": p.get("type", "string")})
                elif loc == "body" and isinstance(p.get("schema"), dict):
                    json_body = _schema_example(p["schema"])

            rb = op.get("requestBody") or {}
            if isinstance(rb, dict):
                content_map = rb.get("content") or {}
                app_json = content_map.get("application/json") or {}
                if isinstance(app_json, dict) and "schema" in app_json:
                    json_body = _schema_example(app_json["schema"])

            req_block: dict[str, Any] = {
                "method": m_upper,
                "url": f"{base}{path_str}",
                "headers": headers,
                "params": params,
            }
            if json_body is not None:
                req_block["json"] = json_body

            steps.append(
                {
                    "type": "api",
                    "name": str(op.get("summary") or op.get("operationId") or f"{m_upper} {path_str}"),
                    "request": req_block,
                    "extract": [],
                    "assertions": [{"type": "status_code", "target": "", "expected": 200}],
                }
            )
    return steps


@app.post("/api/cases/import_collection")
def import_collection(payload: ImportCollectionPayload) -> dict[str, Any]:
    try:
        doc = json.loads(payload.content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败: {exc}") from exc
    if not isinstance(doc, dict):
        raise HTTPException(status_code=400, detail="集合文件必须是 JSON 对象")

    if isinstance(doc.get("item"), list):
        info = doc.get("info") or {}
        case_name = str(info.get("name") or (Path(payload.filename).stem if payload.filename else "Postman导入用例"))
        steps = _parse_postman_items(doc["item"])
        source_type = "Postman Collection"
    elif isinstance(doc.get("paths"), dict):
        info = doc.get("info") or {}
        case_name = str(info.get("title") or (Path(payload.filename).stem if payload.filename else "Swagger导入用例"))
        steps = _parse_openapi_doc(doc)
        source_type = "Swagger / OpenAPI"
    else:
        raise HTTPException(status_code=400, detail="未识别的格式：请上传 Postman Collection v2.1 或 OpenAPI/Swagger JSON")

    if not steps:
        raise HTTPException(status_code=400, detail="未能从集合中解析出任何接口步骤")

    path = _unique_case_path(_slugify_filename(case_name))
    content = {
        "name": case_name,
        "description": f"从 {source_type} 自动导入（共 {len(steps)} 个接口步骤）",
        "steps": steps,
    }
    path.write_text(yaml.safe_dump(content, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {
        "ok": True,
        "filename": path.name,
        "source_type": source_type,
        "step_count": len(steps),
        **content,
    }


@app.post("/api/debug")
def debug_request(payload: DebugRequestPayload) -> dict[str, Any]:
    envs = _read_envs()
    ctx = TestContext(envs.get(payload.env, {}))
    method = payload.method.upper()
    url = str(ctx.render(payload.url)).strip()
    if not url:
        return {"ok": False, "error": "请输入有效的接口 URL"}
    headers = ctx.render(payload.headers)
    params = ctx.render(payload.params)
    body = ctx.render(payload.body)

    try:
        _DEBUG_SESSION.cookies.clear()
        resp, _ = send_http_request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            body=body,
            timeout=payload.timeout,
            body_type=payload.body_type,
            form_fields=payload.form_fields,
            ctx=ctx,
            session=_DEBUG_SESSION,
        )
        try:
            resp_body: Any = resp.json()
        except ValueError:
            resp_body = resp.text
        return {
            "ok": True,
            "status_code": resp.status_code,
            "elapsed_ms": round(resp.elapsed.total_seconds() * 1000, 2),
            "headers": dict(resp.headers),
            "body": _truncate_for_display(resp_body),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


_ACTIVE_PROC: asyncio.subprocess.Process | None = None
_STOP_REQUESTED: bool = False
_RUN_LOCK = asyncio.Lock()


def stop_active_process_sync() -> bool:
    global _ACTIVE_PROC, _STOP_REQUESTED
    _STOP_REQUESTED = True
    proc = _ACTIVE_PROC
    if proc is None or proc.returncode is not None:
        return False
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            proc.terminate()
    except Exception:
        pass
    return True


async def _run_subprocess(cmd: list[str], env: dict[str, str], track: bool = False) -> tuple[int, str]:
    global _ACTIVE_PROC
    kwargs: dict[str, Any] = {
        "cwd": str(WORK_DIR),
        "env": env,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.STDOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = await asyncio.create_subprocess_exec(*cmd, **kwargs)
    if track:
        _ACTIVE_PROC = proc
    try:
        stdout_bytes, _ = await proc.communicate()
        output = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        return proc.returncode or 0, output
    finally:
        if track and _ACTIVE_PROC is proc:
            _ACTIVE_PROC = None


@app.post("/api/run/stop")
def stop_tests() -> dict[str, Any]:
    stopped = stop_active_process_sync()
    return {"ok": True, "stopped": stopped}


def _collect_case_results() -> dict[str, Any]:
    results: dict[str, Any] = {}
    if not BUILTIN_RESULTS_DIR.exists():
        return results
    for jf in sorted(BUILTIN_RESULTS_DIR.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            fname = data.get("filename") or f"{jf.stem}.yaml"
            results[fname] = data
        except Exception:
            continue
    return results


@app.post("/api/run")
async def run_tests(payload: RunPayload) -> dict[str, Any]:
    if _RUN_LOCK.locked():
        raise HTTPException(status_code=409, detail="已有测试任务正在运行，请等待完成或先点击停止")

    async with _RUN_LOCK:
        return await _execute_run_tests(payload)


async def _execute_run_tests(payload: RunPayload) -> dict[str, Any]:
    global _STOP_REQUESTED
    _STOP_REQUESTED = False

    prev_history = ALLURE_REPORT_DIR / "history"
    temp_history = WORK_DIR / "reports" / "_tmp_allure_history"
    if prev_history.exists():
        if temp_history.exists():
            shutil.rmtree(temp_history, ignore_errors=True)
        shutil.copytree(prev_history, temp_history, dirs_exist_ok=True)

    for d in (ALLURE_RESULTS_DIR, BUILTIN_RESULTS_DIR):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)

    if temp_history.exists():
        shutil.copytree(temp_history, ALLURE_RESULTS_DIR / "history", dirs_exist_ok=True)
        shutil.rmtree(temp_history, ignore_errors=True)

    env_props = (
        f"Environment={payload.env}\n"
        f"UI_Engine={payload.ui_engine}\n"
        f"Browser={payload.browser}\n"
        f"Headless={'Yes' if payload.headless else 'No'}\n"
        f"Run_Time={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    (ALLURE_RESULTS_DIR / "environment.properties").write_text(env_props, encoding="utf-8")

    selected_paths: list[str] = []
    if payload.cases:
        for fname in payload.cases:
            p = _safe_case_path(fname)
            if p.exists():
                selected_paths.append(str(p))
    else:
        selected_paths = [str(p) for p in sorted(CASES_DIR.glob("*.yaml"))]

    if not selected_paths:
        raise HTTPException(status_code=400, detail="没有可执行的测试用例")

    run_env = os.environ.copy()
    run_env["PYTHONIOENCODING"] = "utf-8"
    run_env["TESTFLOW_ENV"] = payload.env
    run_env["TESTFLOW_HEADLESS"] = "1" if payload.headless else "0"
    run_env["TESTFLOW_UI_ENGINE"] = payload.ui_engine
    run_env["TESTFLOW_BROWSER"] = payload.browser
    run_env["TESTFLOW_CASES"] = json.dumps(selected_paths, ensure_ascii=False)
    existing_pp = run_env.get("PYTHONPATH", "")
    run_env["PYTHONPATH"] = f"{BUNDLE_DIR}{os.pathsep}{existing_pp}" if existing_pp else str(BUNDLE_DIR)

    if IS_FROZEN:
        pytest_cmd = [
            sys.executable,
            "--run-pytest",
            str(RUNNER_FILE),
            "-v",
            "-p",
            "no:cacheprovider",
            f"--alluredir={ALLURE_RESULTS_DIR}",
        ]
    else:
        pytest_cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(RUNNER_FILE),
            "-v",
            "-p",
            "no:cacheprovider",
            f"--alluredir={ALLURE_RESULTS_DIR}",
        ]
    exit_code, pytest_output = await _run_subprocess(pytest_cmd, run_env, track=True)

    builtin_coro = asyncio.to_thread(
        generate_builtin_report,
        BUILTIN_RESULTS_DIR,
        BUILTIN_REPORT_DIR,
        {
            "env": payload.env,
            "ui_engine": payload.ui_engine,
            "browser": payload.browser,
        },
    )

    allure_bin = shutil.which("allure")
    report_generated = False
    allure_output = ""
    if allure_bin:
        if os.name == "nt" and allure_bin.lower().endswith((".bat", ".cmd")):
            allure_cmd = [
                "cmd",
                "/c",
                allure_bin,
                "generate",
                str(ALLURE_RESULTS_DIR),
                "-o",
                str(ALLURE_REPORT_DIR),
                "--lang",
                "zh",
                "--clean",
            ]
        else:
            allure_cmd = [
                allure_bin,
                "generate",
                str(ALLURE_RESULTS_DIR),
                "-o",
                str(ALLURE_REPORT_DIR),
                "--lang",
                "zh",
                "--clean",
            ]
        _, (allure_code, allure_output) = await asyncio.gather(
            builtin_coro,
            _run_subprocess(allure_cmd, run_env),
        )
        report_generated = allure_code == 0 and (ALLURE_REPORT_DIR / "index.html").exists()
    else:
        await builtin_coro

    builtin_url = "/builtin-report/index.html" if (BUILTIN_REPORT_DIR / "index.html").exists() else None

    allure_url = "/allure-report/index.html" if report_generated else None
    case_results = _collect_case_results()

    passed_match = re.search(r"(\d+)\s+passed", pytest_output)
    failed_match = re.search(r"(\d+)\s+failed", pytest_output)
    error_match = re.search(r"(\d+)\s+error", pytest_output)

    return {
        "ok": exit_code == 0 and not _STOP_REQUESTED,
        "stopped": _STOP_REQUESTED,
        "exit_code": exit_code,
        "passed": int(passed_match.group(1)) if passed_match else 0,
        "failed": (int(failed_match.group(1)) if failed_match else 0)
        + (int(error_match.group(1)) if error_match else 0),
        "log": pytest_output + ("\n" + allure_output if allure_output else ""),
        "report_url": allure_url or builtin_url,
        "allure_report_url": allure_url,
        "builtin_report_url": builtin_url,
        "case_results": case_results,
    }


@app.get("/api/report/status")
def report_status() -> dict[str, Any]:
    allure_index = ALLURE_REPORT_DIR / "index.html"
    builtin_index = BUILTIN_REPORT_DIR / "index.html"
    allure_exists = allure_index.exists()
    builtin_exists = builtin_index.exists()
    if not allure_exists and not builtin_exists:
        return {
            "exists": False,
            "allure_exists": False,
            "builtin_exists": False,
            "updated_at": None,
            "report_url": None,
            "allure_url": None,
            "builtin_url": None,
        }
    latest_mtime = max(
        allure_index.stat().st_mtime if allure_exists else 0.0,
        builtin_index.stat().st_mtime if builtin_exists else 0.0,
    )
    ts = datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M:%S")
    allure_url = "/allure-report/index.html" if allure_exists else None
    builtin_url = "/builtin-report/index.html" if builtin_exists else None
    return {
        "exists": True,
        "allure_exists": allure_exists,
        "builtin_exists": builtin_exists,
        "updated_at": ts,
        "report_url": allure_url or builtin_url,
        "allure_url": allure_url,
        "builtin_url": builtin_url,
    }
