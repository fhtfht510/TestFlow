"""Desktop & web launcher for TestFlow workbench."""

from __future__ import annotations

import socket
import sys
import threading
import time

_SPLASH_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<style>
  html, body {
    margin: 0; height: 100%; overflow: hidden;
    background: linear-gradient(135deg, #0f172a 0%, #172554 100%);
    color: #f8fafc;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    display: flex; align-items: center; justify-content: center;
  }
  .splash { display: flex; flex-direction: column; align-items: center; gap: 14px; }
  .logo {
    width: 54px; height: 54px; border-radius: 14px;
    background: linear-gradient(135deg, #3b82f6 0%, #6366f1 100%);
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 8px 24px rgba(59, 130, 246, 0.45);
  }
  .title { font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }
  .sub { font-size: 13px; color: #94a3b8; }
</style>
</head>
<body>
  <div class="splash">
    <div class="logo">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
    </div>
    <div class="title">TestFlow</div>
    <div class="sub">正在启动本地测试引擎，请稍候...</div>
  </div>
</body>
</html>"""


def _pick_port(preferred: int = 8000) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    if "--run-pytest" in sys.argv:
        idx = sys.argv.index("--run-pytest")
        import pytest

        raise SystemExit(pytest.main(sys.argv[idx + 1 :]))

    port = _pick_port(8000)

    if "--web" in sys.argv:
        import uvicorn
        from server.main import app as fastapi_app

        print("=" * 56)
        print("  TestFlow 极简接口 & UI 自动化测试工作台已启动")
        print(f"  请浏览器访问: http://127.0.0.1:{port}")
        print(f"  演示靶场页面: http://127.0.0.1:{port}/demo/page")
        print("=" * 56)
        uvicorn.run(fastapi_app, host="127.0.0.1", port=port, reload=False)
        return

    import webview
    from engine.paths import STATIC_DIR
    from engine.win_chrome import (
        install_native_chrome,
        is_window_maximized,
        start_native_drag,
        start_native_resize,
    )

    server_holder: dict[str, object] = {}

    def _run_backend() -> None:
        import uvicorn
        from server.main import app as fastapi_app

        config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning")
        srv = uvicorn.Server(config)
        server_holder["server"] = srv
        srv.run()

    threading.Thread(target=_run_backend, daemon=True).start()

    class WindowApi:
        def __init__(self) -> None:
            self._window: webview.Window | None = None

        def bind(self, win: webview.Window) -> None:
            self._window = win

        def minimize(self) -> None:
            if self._window is not None:
                self._window.minimize()

        def toggle_maximize(self) -> bool:
            if self._window is None:
                return False
            if is_window_maximized(self._window):
                self._window.restore()
                return False
            self._window.maximize()
            return True

        def is_maximized(self) -> bool:
            if self._window is None:
                return False
            return is_window_maximized(self._window)

        def start_drag(self) -> None:
            if self._window is not None:
                start_native_drag(self._window)

        def start_resize(self, edge: str) -> None:
            if self._window is not None:
                start_native_resize(self._window, edge)

        def pick_file(self) -> str:
            if self._window is None:
                return ""
            dialog_type = getattr(webview, "FileDialog", None)
            open_flag = dialog_type.OPEN if dialog_type is not None else webview.OPEN_DIALOG
            result = self._window.create_file_dialog(open_flag)
            if result and len(result) > 0:
                return str(result[0])
            return ""

        def close(self) -> None:
            if self._window is not None:
                self._window.destroy()

    api = WindowApi()
    window = webview.create_window(
        "TestFlow 极简自动化测试工作台",
        html=_SPLASH_HTML,
        js_api=api,
        width=1320,
        height=840,
        min_size=(1000, 680),
        frameless=False,
        shadow=True,
        resizable=True,
        background_color="#0f172a",
    )

    if window is not None:
        api.bind(window)
        window.events.before_show += lambda: install_native_chrome(window)

        def _sync_state(maximized: bool) -> None:
            try:
                flag = "true" if maximized else "false"
                window.evaluate_js(
                    f"window.__onWindowStateChanged && window.__onWindowStateChanged({flag});"
                )
            except Exception:
                pass

        window.events.maximized += lambda: _sync_state(True)
        window.events.restored += lambda: _sync_state(False)

        def _navigate_when_ready() -> None:
            deadline = time.time() + 20.0
            while time.time() < deadline:
                if _is_port_open(port):
                    window.load_url(f"http://127.0.0.1:{port}/")
                    return
                time.sleep(0.03)

        threading.Thread(target=_navigate_when_ready, daemon=True).start()

    ico_path = STATIC_DIR / "testflow.ico"
    webview.start(gui="edgechromium", icon=str(ico_path) if ico_path.exists() else None)
    try:
        from server.main import stop_active_process_sync

        stop_active_process_sync()
    except Exception:
        pass
    srv = server_holder.get("server")
    if srv is not None:
        srv.should_exit = True  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
