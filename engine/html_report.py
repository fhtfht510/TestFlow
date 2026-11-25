"""Zero-dependency standalone HTML report generator (works without Java or Allure CLI)."""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _esc(val: Any) -> str:
    return html.escape(str(val if val is not None else ""))


def _pretty(val: Any) -> str:
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False, indent=2)
    return str(val if val is not None else "")


def generate_builtin_report(
    results_dir: Path,
    report_dir: Path,
    meta: dict[str, Any] | None = None,
) -> Path:
    """Generate a single-file Chinese HTML test report from builtin JSON results."""
    report_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    if results_dir.exists():
        for jf in sorted(results_dir.glob("*.json")):
            try:
                cases.append(json.loads(jf.read_text(encoding="utf-8")))
            except Exception:
                continue

    total = len(cases)
    passed = sum(1 for c in cases if c.get("status") == "passed")
    failed = total - passed
    pass_rate = round((passed / total) * 100, 1) if total else 0.0
    total_ms = round(sum(float(c.get("duration_ms") or 0) for c in cases), 1)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta_info = meta or {}

    case_cards_html: list[str] = []
    for c_idx, c in enumerate(cases, start=1):
        status = c.get("status", "passed")
        badge_cls = "badge-pass" if status == "passed" else "badge-fail"
        badge_txt = "通过" if status == "passed" else "失败"
        steps_html: list[str] = []
        for s in c.get("steps") or []:
            st = s.get("status", "passed")
            st_cls = "st-pass" if st == "passed" else ("st-skip" if st == "skipped" else "st-fail")
            st_txt = "通过" if st == "passed" else ("跳过" if st == "skipped" else "失败")
            stype = str(s.get("type", "api")).upper()

            detail_blocks: list[str] = []
            if s.get("error"):
                detail_blocks.append(f'<div class="err-box"><strong>错误详情：</strong>{_esc(s["error"])}</div>')

            if s.get("request"):
                req = s["request"]
                detail_blocks.append(
                    f'<div class="detail-grid">'
                    f'<div><div class="detail-title">请求详情</div><pre>{_esc(_pretty(req))}</pre></div>'
                    f'<div><div class="detail-title">响应详情</div><pre>{_esc(_pretty(s.get("response") or {}))}</pre></div>'
                    f"</div>"
                )
            if s.get("extracted"):
                detail_blocks.append(
                    f'<div><div class="detail-title">提取变量</div><pre>{_esc(_pretty(s["extracted"]))}</pre></div>'
                )
            if s.get("assertions"):
                rows = "".join(
                    f'<tr><td>{_esc(a.get("type"))}</td><td>{_esc(a.get("target"))}</td>'
                    f'<td>{_esc(a.get("expected"))}</td><td>{_esc(a.get("actual"))}</td>'
                    f'<td class="{"ok" if a.get("passed") else "bad"}">{"通过" if a.get("passed") else "失败"}</td></tr>'
                    for a in s["assertions"]
                )
                detail_blocks.append(
                    f'<div><div class="detail-title">断言明细</div>'
                    f'<table class="assert-tbl"><thead><tr><th>类型</th><th>目标</th><th>期望</th><th>实际</th><th>结果</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table></div>'
                )
            if s.get("ui"):
                detail_blocks.append(
                    f'<div><div class="detail-title">UI 操作参数</div><pre>{_esc(_pretty(s["ui"]))}</pre></div>'
                )
            for shot in s.get("screenshots") or []:
                b64 = shot.get("data", "")
                if b64:
                    detail_blocks.append(
                        f'<div class="shot-wrap"><div class="detail-title">截图：{_esc(shot.get("name") or "UI截图")}</div>'
                        f'<img loading="lazy" src="data:image/png;base64,{b64}" onclick="openImg(this.src)" /></div>'
                    )

            steps_html.append(
                f'<details class="step-item {st_cls}" {"open" if st == "failed" else ""}>'
                f'<summary><span class="tag tag-{stype.lower()}">{stype}</span>'
                f'<span class="step-title">#{_esc(s.get("index"))} {_esc(s.get("name"))}</span>'
                f'<span class="step-meta">{_esc(s.get("duration_ms"))} ms · <b class="{st_cls}">{st_txt}</b></span></summary>'
                f'<div class="step-body">{"".join(detail_blocks) or "<div class=muted>无附加明细</div>"}</div>'
                f"</details>"
            )

        desc_val = c.get("description")
        desc_html = f'<p class="case-desc">{_esc(desc_val)}</p>' if desc_val else ""
        case_cards_html.append(
            f'<section class="case-card">'
            f'<div class="case-head">'
            f'<div><span class="case-idx">#{c_idx}</span><strong>{_esc(c.get("name"))}</strong>'
            f'<span class="case-file">{_esc(c.get("filename"))}</span></div>'
            f'<div class="case-right"><span class="muted">{_esc(c.get("duration_ms"))} ms</span>'
            f'<span class="badge {badge_cls}">{badge_txt}</span></div>'
            f"</div>"
            f"{desc_html}"
            f'<div class="steps-wrap">{"".join(steps_html)}</div>'
            f"</section>"
        )

    out_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TestFlow 内置测试报告</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f1f5f9; color: #0f172a; padding: 24px; }}
    .wrap {{ max-width: 1120px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }}
    .hero {{ background: linear-gradient(120deg, #0f172a, #1e3a8a); color: #fff; padding: 20px 24px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
    .hero h1 {{ margin: 0; font-size: 20px; }}
    .hero-sub {{ font-size: 12.5px; color: #cbd5e1; margin-top: 4px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
    .kpi {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; }}
    .kpi-label {{ font-size: 12px; color: #64748b; }}
    .kpi-val {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    .ok {{ color: #10b981; }} .bad {{ color: #ef4444; }}
    .bar {{ height: 8px; background: #fee2e2; border-radius: 999px; overflow: hidden; }}
    .bar-fill {{ height: 100%; background: #10b981; width: {pass_rate}%; }}
    .case-card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; }}
    .case-head {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
    .case-idx {{ display: inline-block; background: #eff6ff; color: #2563eb; padding: 2px 8px; border-radius: 6px; font-size: 12px; font-weight: 700; margin-right: 8px; }}
    .case-file {{ font-size: 12px; color: #64748b; margin-left: 8px; }}
    .case-desc {{ margin: 6px 0 0; font-size: 12.5px; color: #64748b; }}
    .case-right {{ display: flex; align-items: center; gap: 10px; }}
    .badge {{ padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
    .badge-pass {{ background: #dcfce7; color: #166534; }}
    .badge-fail {{ background: #fee2e2; color: #991b1b; }}
    .steps-wrap {{ margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }}
    .step-item {{ border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }}
    .step-item summary {{ padding: 9px 12px; background: #f8fafc; cursor: pointer; display: flex; align-items: center; gap: 8px; font-size: 13px; }}
    .step-title {{ font-weight: 600; flex: 1; }}
    .step-meta {{ font-size: 12px; color: #64748b; }}
    .st-pass {{ color: #059669; }} .st-fail {{ color: #dc2626; }} .st-skip {{ color: #d97706; }}
    .tag {{ font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 5px; }}
    .tag-api {{ background: #dbeafe; color: #1e40af; }}
    .tag-ui {{ background: #f3e8ff; color: #6d28d9; }}
    .step-body {{ padding: 12px; display: flex; flex-direction: column; gap: 10px; border-top: 1px solid #e2e8f0; }}
    .detail-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px; }}
    .detail-title {{ font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 4px; }}
    pre {{ margin: 0; background: #0f172a; color: #e2e8f0; padding: 10px; border-radius: 7px; font-size: 12px; overflow: auto; max-height: 280px; white-space: pre-wrap; word-break: break-word; }}
    .err-box {{ background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; padding: 8px 12px; border-radius: 7px; font-size: 12.5px; }}
    .assert-tbl {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    .assert-tbl th, .assert-tbl td {{ border: 1px solid #e2e8f0; padding: 6px 8px; text-align: left; }}
    .assert-tbl th {{ background: #f8fafc; color: #475569; }}
    .shot-wrap img {{ max-width: 100%; max-height: 360px; border: 1px solid #cbd5e1; border-radius: 8px; cursor: zoom-in; }}
    .muted {{ color: #64748b; font-size: 12px; }}
    #lightbox {{ position: fixed; inset: 0; background: rgba(15,23,42,.85); display: none; align-items: center; justify-content: center; z-index: 99; padding: 20px; }}
    #lightbox img {{ max-width: 95vw; max-height: 92vh; border-radius: 8px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div>
        <h1>TestFlow 自动化测试报告（内置轻量版）</h1>
        <div class="hero-sub">生成时间：{_esc(generated_at)} · 环境：{_esc(meta_info.get("env", "-"))} · 引擎：{_esc(meta_info.get("ui_engine", "-"))} · 浏览器：{_esc(meta_info.get("browser", "-"))}</div>
      </div>
      <div><span class="badge {"badge-pass" if failed == 0 else "badge-fail"}">{"全部通过" if failed == 0 else f"失败 {failed} 条"}</span></div>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="kpi-label">用例总数</div><div class="kpi-val">{total}</div></div>
      <div class="kpi"><div class="kpi-label">通过数</div><div class="kpi-val ok">{passed}</div></div>
      <div class="kpi"><div class="kpi-label">失败数</div><div class="kpi-val bad">{failed}</div></div>
      <div class="kpi"><div class="kpi-label">通过率</div><div class="kpi-val">{pass_rate}%</div></div>
      <div class="kpi"><div class="kpi-label">总耗时</div><div class="kpi-val">{total_ms} ms</div></div>
    </div>
    <div class="bar"><div class="bar-fill"></div></div>
    {"".join(case_cards_html) or '<div class="case-card muted">暂无测试结果数据。</div>'}
  </div>
  <div id="lightbox" onclick="this.style.display='none'"><img id="lightbox-img" src="" /></div>
  <script>function openImg(src){{document.getElementById('lightbox-img').src=src;document.getElementById('lightbox').style.display='flex';}}</script>
</body>
</html>
"""
    out_file = report_dir / "index.html"
    out_file.write_text(out_html, encoding="utf-8")
    return out_file
