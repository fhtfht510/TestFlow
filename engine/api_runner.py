"""HTTP API step runner with Allure attachments, extraction, and assertions."""

from __future__ import annotations

import json
import mimetypes
import re
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import allure
import requests

from engine.context import TestContext, extract_json_path


def _truncate_for_display(val: Any, max_chars: int = 200_000) -> Any:
    """Truncate oversized response payloads for UI/report rendering without affecting assertions."""
    if isinstance(val, str):
        if len(val) > max_chars:
            return val[:max_chars] + "\n... [内容过大，已截断显示前 200KB]"
        return val
    if isinstance(val, dict):
        return {k: _truncate_for_display(v, max_chars) for k, v in val.items()}
    if isinstance(val, list):
        return [_truncate_for_display(item, max_chars) for item in val]
    return val


def _attach_json(name: str, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) if not isinstance(payload, str) else payload
    allure.attach(text, name=name, attachment_type=allure.attachment_type.JSON)


def _normalize_extracts(extract_cfg: Any) -> list[tuple[str, str]]:
    if isinstance(extract_cfg, dict):
        return [(str(k), str(v)) for k, v in extract_cfg.items() if k and v]
    if isinstance(extract_cfg, list):
        pairs: list[tuple[str, str]] = []
        for item in extract_cfg:
            if isinstance(item, dict) and item.get("name") and item.get("path"):
                pairs.append((str(item["name"]), str(item["path"])))
        return pairs
    return []


def _parse_response_body(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text


def _get_header_ci(headers: Any, name: str) -> str | None:
    target = name.strip().lower()
    for k, v in dict(headers).items():
        if str(k).lower() == target:
            return str(v)
    return None


def _extract_by_expr(expr: str, resp: requests.Response, body: Any) -> Any:
    cleaned = expr.strip()
    if cleaned.lower().startswith("header:"):
        header_name = cleaned.split(":", 1)[1].strip()
        return _get_header_ci(resp.headers, header_name)
    if cleaned.lower().startswith("regex:"):
        pattern = cleaned.split(":", 1)[1]
        m = re.search(pattern, resp.text, re.S)
        if not m:
            return None
        return m.group(1) if m.groups() else m.group(0)
    return extract_json_path(body, cleaned) if isinstance(body, (dict, list)) else None


def _evaluate_assertion(
    rule: dict[str, Any],
    resp: requests.Response,
    body: Any,
    elapsed_ms: float,
    ctx: TestContext,
) -> dict[str, Any]:
    atype = rule.get("type", "status_code")
    target = str(ctx.render(rule.get("target", "")))
    expected = ctx.render(rule.get("expected"))
    passed = False
    actual: Any = None

    if atype == "status_code":
        actual = resp.status_code
        try:
            passed = actual == int(expected)
        except (TypeError, ValueError):
            passed = False
    elif atype == "json_equals":
        actual = extract_json_path(body, target) if isinstance(body, (dict, list)) else None
        passed = actual == expected or str(actual) == str(expected)
    elif atype == "json_not_equals":
        actual = extract_json_path(body, target) if isinstance(body, (dict, list)) else None
        passed = actual != expected and str(actual) != str(expected)
    elif atype == "json_contains":
        actual = extract_json_path(body, target) if isinstance(body, (dict, list)) else None
        passed = actual is not None and str(expected) in str(actual)
    elif atype == "json_exists":
        actual = extract_json_path(body, target) if isinstance(body, (dict, list)) else None
        passed = actual is not None and actual != ""
    elif atype == "json_gt":
        actual = extract_json_path(body, target) if isinstance(body, (dict, list)) else None
        try:
            passed = actual is not None and float(actual) > float(expected)
        except (TypeError, ValueError):
            passed = False
    elif atype == "json_lt":
        actual = extract_json_path(body, target) if isinstance(body, (dict, list)) else None
        try:
            passed = actual is not None and float(actual) < float(expected)
        except (TypeError, ValueError):
            passed = False
    elif atype == "body_contains":
        actual = resp.text
        passed = str(expected) in resp.text
    elif atype == "header_contains":
        actual = _get_header_ci(resp.headers, target)
        passed = actual is not None and str(expected) in actual
    elif atype == "response_time_lt":
        actual = elapsed_ms
        try:
            passed = elapsed_ms < float(expected)
        except (TypeError, ValueError):
            passed = False
    elif atype == "regex_match":
        try:
            m = re.search(str(expected), resp.text, re.S)
        except re.error as exc:
            raise ValueError(f"正则表达式语法错误: {exc}") from exc
        actual = m.group(0) if m else None
        passed = m is not None
    else:
        raise ValueError(f"Unsupported assertion type: {atype}")

    return {
        "type": atype,
        "target": target,
        "expected": expected,
        "actual": actual,
        "passed": passed,
    }


def send_http_request(
    method: str,
    url: str,
    headers: dict[str, Any],
    params: dict[str, Any],
    body: Any,
    timeout: float,
    body_type: str = "json",
    form_fields: list[dict[str, Any]] | None = None,
    ctx: TestContext | None = None,
    session: requests.Session | None = None,
) -> tuple[requests.Response, Any]:
    """Send an HTTP request supporting json, raw, form_urlencoded, and form_data (files)."""
    render = ctx.render if ctx is not None else (lambda v: v)
    btype = (body_type or "json").lower().strip()
    clean_headers = dict(headers or {})
    kwargs: dict[str, Any] = {
        "method": method.upper(),
        "url": url,
        "headers": clean_headers,
        "params": params or {},
        "timeout": timeout,
    }

    with ExitStack() as stack:
        logged_body: Any = body
        if btype == "form_urlencoded":
            form_data: list[tuple[str, str]] = []
            for item in form_fields or []:
                k = str(render(item.get("key", ""))).strip()
                if k:
                    form_data.append((k, str(render(item.get("value", "")))))
            kwargs["data"] = form_data
            logged_body = form_data
        elif btype == "form_data":
            # Let requests generate multipart boundary automatically
            for hk in list(clean_headers.keys()):
                if hk.lower() == "content-type":
                    del clean_headers[hk]
            text_data: list[tuple[str, str]] = []
            files_data: list[tuple[str, Any]] = []
            for item in form_fields or []:
                k = str(render(item.get("key", ""))).strip()
                if not k:
                    continue
                ftype = str(item.get("type", "text")).lower()
                val = str(render(item.get("value", "")))
                if ftype == "file":
                    fpath = Path(val)
                    if not fpath.is_file():
                        raise FileNotFoundError(f"上传文件不存在: {val}")
                    mime = mimetypes.guess_type(fpath.name)[0] or "application/octet-stream"
                    fh = stack.enter_context(fpath.open("rb"))
                    files_data.append((k, (fpath.name, fh, mime)))
                else:
                    text_data.append((k, val))
            if text_data:
                kwargs["data"] = text_data
            if files_data:
                kwargs["files"] = files_data
            logged_body = [
                {"key": item.get("key"), "type": item.get("type", "text"), "value": item.get("value")}
                for item in (form_fields or [])
            ]
        else:
            if body is not None and body != "":
                if isinstance(body, (dict, list)):
                    kwargs["json"] = body
                else:
                    kwargs["data"] = str(body)

        requester = session if session is not None else requests
        resp = requester.request(**kwargs)
        return resp, logged_body


def run_api_step(
    step: dict[str, Any],
    ctx: TestContext,
    step_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one API step, update context variables, and verify assertions."""
    req = step.get("request", step)
    method = str(req.get("method", "GET")).upper()
    url = str(ctx.render(req.get("url", "")))
    headers = ctx.render(req.get("headers") or {})
    params = ctx.render(req.get("params") or {})
    json_body = ctx.render(req.get("json") if "json" in req else req.get("body"))
    body_type = str(req.get("body_type") or step.get("body_type") or "json")
    form_fields = req.get("form_fields") or step.get("form_fields") or []
    timeout = float(step.get("timeout", req.get("timeout", 15)))

    req_detail = {
        "method": method,
        "url": url,
        "headers": headers,
        "params": params,
        "body_type": body_type,
        "body": form_fields if body_type in ("form_urlencoded", "form_data") else json_body,
    }
    _attach_json("请求详情", req_detail)
    if step_record is not None:
        step_record["request"] = req_detail

    resp, _ = send_http_request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        body=json_body,
        timeout=timeout,
        body_type=body_type,
        form_fields=form_fields,
        ctx=ctx,
        session=ctx.http_session,
    )
    elapsed_ms = round(resp.elapsed.total_seconds() * 1000, 2)
    body = _parse_response_body(resp)

    resp_detail = {
        "status_code": resp.status_code,
        "elapsed_ms": elapsed_ms,
        "headers": dict(resp.headers),
        "body": _truncate_for_display(body),
    }
    _attach_json("响应详情", resp_detail)
    if step_record is not None:
        step_record["response"] = resp_detail

    extracted: dict[str, Any] = {}
    for var_name, expr in _normalize_extracts(step.get("extract")):
        val = _extract_by_expr(expr, resp, body)
        if val is not None:
            ctx.set(var_name, val)
            extracted[var_name] = val

    if extracted:
        _attach_json("提取变量", extracted)
        if step_record is not None:
            step_record["extracted"] = extracted

    assertion_results: list[dict[str, Any]] = []
    for rule in step.get("assertions") or []:
        result = _evaluate_assertion(rule, resp, body, elapsed_ms, ctx)
        assertion_results.append(result)
        if step_record is not None:
            step_record["assertions"] = assertion_results
        if not result["passed"]:
            raise AssertionError(
                f"断言失败 [{result['type']}] target={result['target']!r}: "
                f"期望={result['expected']!r}, 实际={result['actual']!r}"
            )

    if step_record is not None:
        step_record["assertions"] = assertion_results

    return {
        "status_code": resp.status_code,
        "elapsed_ms": elapsed_ms,
        "headers": dict(resp.headers),
        "body": body,
        "extracted": extracted,
        "assertions": assertion_results,
    }
