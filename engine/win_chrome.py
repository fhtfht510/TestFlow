"""Native Windows DWM custom titlebar support (WM_NCCALCSIZE + native drag/resize)."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any

_CONTROLLERS: dict[int, "NativeChromeController"] = {}

if os.name == "nt":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

    LONG_PTR = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class MARGINS(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth", ctypes.c_int),
            ("cxRightWidth", ctypes.c_int),
            ("cyTopHeight", ctypes.c_int),
            ("cyBottomHeight", ctypes.c_int),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    class NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [
            ("rgrc", wintypes.RECT * 3),
            ("lppos", ctypes.c_void_p),
        ]

    class APPBARDATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uCallbackMessage", wintypes.UINT),
            ("uEdge", wintypes.UINT),
            ("rc", wintypes.RECT),
            ("lParam", wintypes.LPARAM),
        ]

    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, WNDPROC]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.CallWindowProcW.argtypes = [
        ctypes.c_void_p,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.CallWindowProcW.restype = LONG_PTR
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.ReleaseCapture.argtypes = []
    user32.ReleaseCapture.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    user32.GetDpiForWindow.restype = wintypes.UINT
    user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
    user32.GetSystemMetricsForDpi.restype = ctypes.c_int
    dwmapi.DwmSetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
    dwmapi.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(MARGINS)]
    dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
    shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(APPBARDATA)]
    shell32.SHAppBarMessage.restype = ctypes.c_size_t


def _get_hwnd(window: Any) -> int | None:
    native = getattr(window, "native", None)
    if native is None:
        return None
    handle = getattr(native, "Handle", None)
    if handle is None:
        return None
    try:
        return int(handle.ToInt64())
    except Exception:
        try:
            return int(handle)
        except Exception:
            return None


def _run_on_ui(window: Any, fn: Any) -> None:
    native = getattr(window, "native", None)
    if native is not None and getattr(native, "InvokeRequired", False):
        from System import Action

        native.Invoke(Action(fn))
    else:
        fn()


def _extend_dwm_frame(hwnd: int) -> None:
    margins = MARGINS(0, 0, 1, 0)
    dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))


def _apply_maximized_rect(hwnd: int, rect: wintypes.RECT) -> None:
    hmon = user32.MonitorFromWindow(hwnd, 2)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return

    left, top, right, bottom = (
        mi.rcWork.left,
        mi.rcWork.top,
        mi.rcWork.right,
        mi.rcWork.bottom,
    )

    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    state = shell32.SHAppBarMessage(4, ctypes.byref(abd))  # ABM_GETSTATE
    is_autohide = bool(state & 0x1)
    is_same_as_monitor = (
        left == mi.rcMonitor.left
        and top == mi.rcMonitor.top
        and right == mi.rcMonitor.right
        and bottom == mi.rcMonitor.bottom
    )
    if is_autohide or is_same_as_monitor:
        pos_data = APPBARDATA()
        pos_data.cbSize = ctypes.sizeof(APPBARDATA)
        if shell32.SHAppBarMessage(5, ctypes.byref(pos_data)):  # ABM_GETTASKBARPOS
            edge = pos_data.uEdge  # 0=left, 1=top, 2=right, 3=bottom
            if edge == 0:
                left += 1
            elif edge == 1:
                top += 1
            elif edge == 2:
                right -= 1
            else:
                bottom -= 1
        else:
            bottom -= 1

    rect.left = left
    rect.top = top
    rect.right = right
    rect.bottom = bottom


class NativeChromeController:
    """Keeps strong references to the Win32 subclass WNDPROC for a window."""

    def __init__(self, hwnd: int) -> None:
        self.hwnd = hwnd
        self.old_proc: int | None = None
        self.new_proc = WNDPROC(self._wnd_proc)

    def install(self) -> None:
        dark_val = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(self.hwnd, 20, ctypes.byref(dark_val), 4)  # DWMWA_USE_IMMERSIVE_DARK_MODE
        corner_val = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(self.hwnd, 33, ctypes.byref(corner_val), 4)  # DWMWA_WINDOW_CORNER_PREFERENCE
        _extend_dwm_frame(self.hwnd)

        self.old_proc = user32.SetWindowLongPtrW(self.hwnd, -4, self.new_proc)  # GWLP_WNDPROC
        user32.SetWindowPos(
            self.hwnd,
            None,
            0,
            0,
            0,
            0,
            0x0002 | 0x0001 | 0x0004 | 0x0020,  # NOMOVE | NOSIZE | NOZORDER | FRAMECHANGED
        )

    def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == 0x0083 and wparam:  # WM_NCCALCSIZE
            params = ctypes.cast(lparam, ctypes.POINTER(NCCALCSIZE_PARAMS)).contents
            if user32.IsZoomed(hwnd):
                _apply_maximized_rect(hwnd, params.rgrc[0])
            else:
                dpi = user32.GetDpiForWindow(hwnd) or 96
                cx = user32.GetSystemMetricsForDpi(32, dpi) + user32.GetSystemMetricsForDpi(92, dpi)
                cy = user32.GetSystemMetricsForDpi(33, dpi) + user32.GetSystemMetricsForDpi(92, dpi)
                params.rgrc[0].left += cx
                params.rgrc[0].right -= cx
                params.rgrc[0].bottom -= cy
            return 0
        if msg == 0x0006:  # WM_ACTIVATE
            _extend_dwm_frame(hwnd)
        return user32.CallWindowProcW(self.old_proc, hwnd, msg, wparam, lparam)


def install_native_chrome(window: Any) -> None:
    if os.name != "nt":
        return

    def _apply() -> None:
        hwnd = _get_hwnd(window)
        if not hwnd or hwnd in _CONTROLLERS:
            return
        ctrl = NativeChromeController(hwnd)
        _CONTROLLERS[hwnd] = ctrl
        ctrl.install()

    _run_on_ui(window, _apply)


def is_window_maximized(window: Any) -> bool:
    if os.name != "nt":
        return False
    hwnd = _get_hwnd(window)
    return bool(hwnd and user32.IsZoomed(hwnd))


def start_native_drag(window: Any) -> None:
    if os.name != "nt":
        return

    def _drag() -> None:
        hwnd = _get_hwnd(window)
        if not hwnd:
            return
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        lparam = ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)
        user32.ReleaseCapture()
        user32.PostMessageW(hwnd, 0x00A1, 2, lparam)  # WM_NCLBUTTONDOWN, HTCAPTION

    _run_on_ui(window, _drag)


def start_native_resize(window: Any, edge: str) -> None:
    if os.name != "nt":
        return
    ht_map = {
        "top": 12,        # HTTOP
        "top_left": 13,   # HTTOPLEFT
        "top_right": 14,  # HTTOPRIGHT
    }
    ht_code = ht_map.get(edge)
    if not ht_code:
        return

    def _resize() -> None:
        hwnd = _get_hwnd(window)
        if not hwnd:
            return
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        lparam = ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)
        user32.ReleaseCapture()
        user32.PostMessageW(hwnd, 0x00A1, ht_code, lparam)

    _run_on_ui(window, _resize)
