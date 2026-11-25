"""Build script to package TestFlow into a slim standalone Windows desktop .exe."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DIST_APP_DIR = ROOT_DIR / "dist" / "TestFlow"
BACKUP_DIR = ROOT_DIR / "build" / "_user_data_backup"

_EXCLUDE_MODULES = [
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "qtpy",
    "shiboken2",
    "shiboken6",
    "numpy",
    "scipy",
    "pandas",
    "matplotlib",
    "PIL",
    "tkinter",
    "_tkinter",
    "babel",
    "sphinx",
    "jedi",
    "mypy",
    "IPython",
    "jupyter",
    "notebook",
    "zmq",
    "tornado",
    "webview.platforms.qt",
    "webview.platforms.gtk",
    "webview.platforms.cocoa",
    "webview.platforms.android",
    "webview.platforms.cef",
]


def _backup_user_data() -> None:
    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)
    if not DIST_APP_DIR.exists():
        return
    for sub in ("cases", "config", "drivers"):
        src = DIST_APP_DIR / sub
        if src.exists() and any(src.iterdir()):
            shutil.copytree(src, BACKUP_DIR / sub, dirs_exist_ok=True)
    if BACKUP_DIR.exists():
        print("已自动备份现有自定义用例、环境配置与浏览器驱动...")


def _restore_user_data() -> None:
    if not BACKUP_DIR.exists():
        return
    for sub in ("cases", "config", "drivers"):
        src = BACKUP_DIR / sub
        dst = DIST_APP_DIR / sub
        if src.exists():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, dirs_exist_ok=True)
    shutil.rmtree(BACKUP_DIR, ignore_errors=True)
    print("已自动恢复自定义用例、环境配置与浏览器驱动（未丢失任何数据）！")


def _dir_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 * 1024)


def _create_clean_release_zip() -> Path:
    """Create a privacy-safe release zip containing only official seed cases & config."""
    import zipfile

    zip_path = ROOT_DIR / "dist" / "TestFlow-Windows-x64.zip"
    if zip_path.exists():
        zip_path.unlink()

    staging = ROOT_DIR / "build" / "_release_staging"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    app_stage = staging / "TestFlow"
    app_stage.mkdir(parents=True, exist_ok=True)

    shutil.copy2(DIST_APP_DIR / "TestFlow.exe", app_stage / "TestFlow.exe")
    shutil.copytree(DIST_APP_DIR / "_internal", app_stage / "_internal")
    shutil.copytree(ROOT_DIR / "cases", app_stage / "cases")
    shutil.copytree(ROOT_DIR / "config", app_stage / "config")
    for empty_dir in ("drivers", "reports"):
        (app_stage / empty_dir).mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in staging.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(staging))

    shutil.rmtree(staging, ignore_errors=True)
    return zip_path


def main() -> None:
    t0 = time.perf_counter()
    _backup_user_data()

    sep = ";" if os.name == "nt" else ":"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onedir",
        "--noconsole",
        "--clean",
        "--noconfirm",
        "--name",
        "TestFlow",
        "--icon",
        str(ROOT_DIR / "static" / "testflow.ico"),
        "--add-data",
        f"static{sep}static",
        "--add-data",
        f"engine{sep}engine",
        "--add-data",
        f"cases{sep}cases",
        "--add-data",
        f"config{sep}config",
        "--collect-all",
        "allure_pytest",
        "--collect-all",
        "allure_python_commons",
        "--collect-all",
        "playwright",
        "--collect-all",
        "selenium",
        "--collect-data",
        "webview",
        "--collect-binaries",
        "webview",
        "--collect-all",
        "clr_loader",
        "--collect-all",
        "pythonnet",
        "--hidden-import",
        "webview",
        "--hidden-import",
        "webview.platforms.winforms",
        "--hidden-import",
        "webview.platforms.edgechromium",
        "--hidden-import",
        "webview.platforms.mshtml",
        "--hidden-import",
        "clr",
        "--hidden-import",
        "pythonnet",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--hidden-import",
        "engine.context",
        "--hidden-import",
        "engine.api_runner",
        "--hidden-import",
        "engine.ui_runner",
        "--hidden-import",
        "engine.paths",
        "--hidden-import",
        "engine.win_chrome",
        "--hidden-import",
        "engine.html_report",
        "--hidden-import",
        "server.main",
        "--hidden-import",
        "server.demo_app",
    ]
    for mod in _EXCLUDE_MODULES:
        cmd.extend(["--exclude-module", mod])

    conda_bin = Path(sys.prefix) / "Library" / "bin"
    if conda_bin.exists():
        for dll_name in (
            "libexpat.dll",
            "expat.dll",
            "ffi.dll",
            "ffi-8.dll",
            "ffi-7.dll",
            "libbz2.dll",
            "liblzma.dll",
            "libmpdec-4.dll",
            "sqlite3.dll",
            "yaml.dll",
        ):
            dll_path = conda_bin / dll_name
            if dll_path.exists():
                cmd.extend(["--add-binary", f"{dll_path}{sep}."])

    cmd.append("app.py")

    print("正在打包精简版 TestFlow.exe，请稍候...")
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if res.returncode != 0:
        _restore_user_data()
        raise SystemExit(res.returncode)

    _restore_user_data()
    exe_path = DIST_APP_DIR / "TestFlow.exe"
    elapsed = time.perf_counter() - t0
    size_mb = _dir_size_mb(DIST_APP_DIR)
    print(f"打包完成！耗时 {elapsed:.1f}s，体积 {size_mb:.1f} MB，可执行文件: {exe_path}")
    if "--release-zip" in sys.argv:
        zip_path = _create_clean_release_zip()
        zip_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"已生成干净 Release 发布包（不含个人用例/驱动）: {zip_path} ({zip_mb:.1f} MB)")


if __name__ == "__main__":
    main()
