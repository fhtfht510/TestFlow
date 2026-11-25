"""Selenium & Playwright dual-engine UI step runner with Allure failure screenshots."""

from __future__ import annotations

import io
import os
import re
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any

import allure
import requests

from engine.context import TestContext
from engine.paths import DRIVERS_DIR

_NPMMIRROR_CFT = "https://registry.npmmirror.com/-/binary/chrome-for-testing/"
_SELENIUM_KEYS_CACHE: dict[str, str] | None = None


def _get_selenium_keys() -> dict[str, str]:
    global _SELENIUM_KEYS_CACHE
    if _SELENIUM_KEYS_CACHE is None:
        from selenium.webdriver.common.keys import Keys

        _SELENIUM_KEYS_CACHE = {
            "enter": Keys.ENTER,
            "return": Keys.RETURN,
            "tab": Keys.TAB,
            "escape": Keys.ESCAPE,
            "esc": Keys.ESCAPE,
            "backspace": Keys.BACKSPACE,
            "delete": Keys.DELETE,
            "space": Keys.SPACE,
            "arrowdown": Keys.ARROW_DOWN,
            "arrow_down": Keys.ARROW_DOWN,
            "down": Keys.ARROW_DOWN,
            "arrowup": Keys.ARROW_UP,
            "arrow_up": Keys.ARROW_UP,
            "up": Keys.ARROW_UP,
            "arrowleft": Keys.ARROW_LEFT,
            "left": Keys.ARROW_LEFT,
            "arrowright": Keys.ARROW_RIGHT,
            "right": Keys.ARROW_RIGHT,
            "home": Keys.HOME,
            "end": Keys.END,
        }
    return _SELENIUM_KEYS_CACHE

_PLAYWRIGHT_KEYS: dict[str, str] = {
    "enter": "Enter",
    "return": "Enter",
    "tab": "Tab",
    "escape": "Escape",
    "esc": "Escape",
    "backspace": "Backspace",
    "delete": "Delete",
    "space": "Space",
    "arrowdown": "ArrowDown",
    "arrow_down": "ArrowDown",
    "down": "ArrowDown",
    "arrowup": "ArrowUp",
    "arrow_up": "ArrowUp",
    "up": "ArrowUp",
    "arrowleft": "ArrowLeft",
    "left": "ArrowLeft",
    "arrowright": "ArrowRight",
    "right": "ArrowRight",
    "home": "Home",
    "end": "End",
}


def _detect_chrome_major_version() -> str | None:
    if os.name != "nt":
        return None
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application"),
    ]
    for base in candidates:
        if not base.exists():
            continue
        versions = [
            p.name for p in base.iterdir() if p.is_dir() and re.match(r"^\d+\.\d+\.\d+\.\d+$", p.name)
        ]
        if versions:
            latest = sorted(versions, key=lambda v: [int(x) for x in v.split(".")])[-1]
            return latest.split(".")[0]
    return None


def _ensure_chromedriver() -> Path | None:
    major = _detect_chrome_major_version()
    if not major:
        return None

    DRIVERS_DIR.mkdir(parents=True, exist_ok=True)
    driver_path = DRIVERS_DIR / "chromedriver.exe"
    if driver_path.exists():
        try:
            res = subprocess.run(
                [str(driver_path), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if f"ChromeDriver {major}." in (res.stdout or ""):
                return driver_path
        except Exception:
            pass

    try:
        listing = requests.get(_NPMMIRROR_CFT, timeout=10)
        listing.raise_for_status()
        versions = [
            item["name"]
            for item in listing.json()
            if isinstance(item, dict) and str(item.get("name", "")).startswith(f"{major}.")
        ]
        if not versions:
            return None
        ver_dir = sorted(
            versions,
            key=lambda s: [int(x) for x in s.strip("/").split(".") if x.isdigit()],
        )[-1]
        if not ver_dir.endswith("/"):
            ver_dir += "/"
        zip_url = f"{_NPMMIRROR_CFT}{ver_dir}win64/chromedriver-win64.zip"
        resp = requests.get(zip_url, timeout=60)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for member in zf.namelist():
                if member.endswith("chromedriver.exe"):
                    driver_path.write_bytes(zf.read(member))
                    return driver_path
    except Exception:
        return None
    return None


def _escape_xpath_text(text: str) -> str:
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    parts = text.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


def _resolve_locator(by: str, locator: str) -> tuple[str, str]:
    from selenium.webdriver.common.by import By

    kind = (by or "css").lower().strip()
    if kind == "css":
        return By.CSS_SELECTOR, locator
    if kind == "xpath":
        return By.XPATH, locator
    if kind == "id":
        return By.ID, locator
    if kind == "name":
        return By.NAME, locator
    if kind == "text":
        escaped = _escape_xpath_text(locator)
        return By.XPATH, f"//*[contains(normalize-space(.), {escaped})]"
    if kind == "placeholder":
        escaped = _escape_xpath_text(locator)
        return By.XPATH, f"//*[@placeholder={escaped}]"
    raise ValueError(f"Unsupported locator strategy: {by}")


def _pw_locator(scope: Any, by: str, locator: str) -> Any:
    kind = (by or "css").lower().strip()
    if kind == "css":
        return scope.locator(locator)
    if kind == "xpath":
        return scope.locator(f"xpath={locator}")
    if kind == "id":
        return scope.locator(f"#{locator}")
    if kind == "name":
        return scope.locator(f"[name='{locator}']")
    if kind == "text":
        return scope.get_by_text(locator)
    if kind == "placeholder":
        return scope.get_by_placeholder(locator)
    raise ValueError(f"Unsupported locator strategy: {by}")


class BrowserSession:
    """Lazily initializes Selenium or Playwright browser and ensures clean teardown."""

    def __init__(
        self,
        headless: bool = True,
        engine: str = "selenium",
        browser: str = "auto",
    ) -> None:
        self.headless = headless
        self.engine = (engine or "selenium").lower().strip()
        if self.engine not in ("selenium", "playwright"):
            raise ValueError(f"Unsupported UI engine: {self.engine}")
        self.browser = (browser or "auto").lower().strip()
        if self.browser not in ("auto", "chrome", "edge", "firefox"):
            raise ValueError(f"Unsupported browser: {self.browser}")
        self.driver: Any = None
        self._pw: Any = None
        self._pw_browser: Any = None
        self._pw_context: Any = None
        self._pw_page: Any = None
        self._pw_frame: Any = None
        self.screenshots: list[dict[str, str]] = []

    def get_driver(self) -> Any:
        if self.driver is not None:
            return self.driver

        factory_map = {
            "chrome": self._start_chrome,
            "edge": self._start_edge,
            "firefox": self._start_firefox,
        }
        factories = (
            [self._start_chrome, self._start_edge, self._start_firefox]
            if self.browser == "auto"
            else [factory_map[self.browser]]
        )

        errors: list[str] = []
        for factory in factories:
            try:
                self.driver = factory()
                self.driver.implicitly_wait(2)
                return self.driver
            except Exception as exc:
                errors.append(f"{factory.__name__}: {exc}")

        raise RuntimeError(f"无法启动浏览器 ({self.browser}): " + " | ".join(errors))

    def get_page(self) -> Any:
        if self._pw_page is not None:
            return self._pw_page

        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        errors: list[str] = []

        if self.browser == "firefox":
            try:
                self._pw_browser = self._pw.firefox.launch(headless=self.headless)
            except Exception as exc:
                errors.append(f"firefox: {exc}")
        elif self.browser == "chrome":
            try:
                self._pw_browser = self._pw.chromium.launch(channel="chrome", headless=self.headless)
            except Exception as exc:
                errors.append(f"chrome: {exc}")
        elif self.browser == "edge":
            try:
                self._pw_browser = self._pw.chromium.launch(channel="msedge", headless=self.headless)
            except Exception as exc:
                errors.append(f"msedge: {exc}")
        else:
            launch_attempts = [
                {"channel": "chrome", "headless": self.headless},
                {"channel": "msedge", "headless": self.headless},
                {"headless": self.headless},
            ]
            for kwargs in launch_attempts:
                try:
                    self._pw_browser = self._pw.chromium.launch(**kwargs)
                    break
                except Exception as exc:
                    errors.append(f"{kwargs}: {exc}")

        if self._pw_browser is None:
            self._pw.stop()
            self._pw = None
            raise RuntimeError(f"Playwright 无法启动浏览器 ({self.browser}): " + " | ".join(errors))

        self._pw_context = self._pw_browser.new_context(viewport={"width": 1440, "height": 900})
        self._pw_page = self._pw_context.new_page()
        self._pw_frame = None
        return self._pw_page

    def get_pw_scope(self) -> Any:
        page = self.get_page()
        return self._pw_frame if self._pw_frame is not None else page

    def _start_chrome(self) -> Any:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service as ChromeService

        options = webdriver.ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,900")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        driver_path = _ensure_chromedriver()
        if driver_path is not None:
            return webdriver.Chrome(
                service=ChromeService(executable_path=str(driver_path)),
                options=options,
            )
        return webdriver.Chrome(options=options)

    def _start_edge(self) -> Any:
        from selenium import webdriver

        options = webdriver.EdgeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,900")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        return webdriver.Edge(options=options)

    def _start_firefox(self) -> Any:
        from selenium import webdriver

        options = webdriver.FirefoxOptions()
        if self.headless:
            options.add_argument("-headless")
        options.add_argument("--width=1440")
        options.add_argument("--height=900")
        return webdriver.Firefox(options=options)

    def capture_screenshot(self, name: str = "UI截图") -> None:
        try:
            png: bytes | None = None
            if self.engine == "playwright" and self._pw_page is not None:
                png = self._pw_page.screenshot(full_page=True)
            elif self.driver is not None:
                png = self.driver.get_screenshot_as_png()
            if png:
                import base64

                allure.attach(png, name=name, attachment_type=allure.attachment_type.PNG)
                self.screenshots.append(
                    {"name": name, "data": base64.b64encode(png).decode("ascii")}
                )
        except Exception:
            pass

    def close(self) -> None:
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None

        if self._pw_context is not None:
            try:
                self._pw_context.close()
            except Exception:
                pass
            finally:
                self._pw_context = None
                self._pw_page = None
                self._pw_frame = None

        if self._pw_browser is not None:
            try:
                self._pw_browser.close()
            except Exception:
                pass
            finally:
                self._pw_browser = None

        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            finally:
                self._pw = None


def _run_selenium_action(
    action: str,
    by: str,
    locator: str,
    value: Any,
    key: str,
    timeout: float,
    step_name: str,
    ctx: TestContext,
    browser: BrowserSession,
) -> None:
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait

    driver = browser.get_driver()
    wait = WebDriverWait(driver, timeout)

    # 页面导航
    if action == "open":
        driver.get(str(value or locator))
    elif action == "refresh":
        driver.refresh()
    elif action == "back":
        driver.back()
    elif action == "forward":
        driver.forward()

    # 鼠标与输入
    elif action == "click":
        target = _resolve_locator(by, locator)
        wait.until(EC.element_to_be_clickable(target)).click()
    elif action == "double_click":
        target = _resolve_locator(by, locator)
        elem = wait.until(EC.visibility_of_element_located(target))
        ActionChains(driver).double_click(elem).perform()
    elif action == "right_click":
        target = _resolve_locator(by, locator)
        elem = wait.until(EC.visibility_of_element_located(target))
        ActionChains(driver).context_click(elem).perform()
    elif action == "hover":
        target = _resolve_locator(by, locator)
        elem = wait.until(EC.visibility_of_element_located(target))
        ActionChains(driver).move_to_element(elem).perform()
    elif action == "input":
        target = _resolve_locator(by, locator)
        elem = wait.until(EC.visibility_of_element_located(target))
        elem.clear()
        elem.send_keys(str(value))
    elif action == "clear":
        target = _resolve_locator(by, locator)
        elem = wait.until(EC.visibility_of_element_located(target))
        elem.clear()
    elif action == "press_key":
        raw_key = str(value or "Enter").strip()
        send_val = _get_selenium_keys().get(raw_key.lower(), raw_key)
        if locator:
            target = _resolve_locator(by, locator)
            elem = wait.until(EC.visibility_of_element_located(target))
            elem.send_keys(send_val)
        else:
            ActionChains(driver).send_keys(send_val).perform()
    elif action == "select_option":
        target = _resolve_locator(by, locator)
        elem = wait.until(EC.visibility_of_element_located(target))
        sel = Select(elem)
        opt_val = str(value)
        try:
            sel.select_by_visible_text(opt_val)
        except Exception:
            sel.select_by_value(opt_val)
    elif action == "upload_file":
        target = _resolve_locator(by, locator)
        elem = wait.until(EC.presence_of_element_located(target))
        elem.send_keys(str(Path(str(value)).resolve()))
    elif action == "scroll_to":
        if locator:
            target = _resolve_locator(by, locator)
            elem = wait.until(EC.presence_of_element_located(target))
            driver.execute_script("arguments[0].scrollIntoView({behavior:'instant', block:'center'});", elem)
        else:
            pos = str(value or "bottom").strip().lower()
            if pos == "top":
                driver.execute_script("window.scrollTo(0, 0);")
            elif pos == "bottom":
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            else:
                driver.execute_script("window.scrollTo(0, Number(arguments[0]) || 0);", pos)

    # 等待与窗口/框架
    elif action == "wait":
        time.sleep(float(value or 1))
    elif action == "wait_element":
        target = _resolve_locator(by, locator)
        wait.until(EC.visibility_of_element_located(target))
    elif action == "switch_tab":
        handles = driver.window_handles
        idx = int(str(value or "-1"))
        driver.switch_to.window(handles[idx])
    elif action == "close_tab":
        driver.close()
        if driver.window_handles:
            driver.switch_to.window(driver.window_handles[-1])
    elif action == "switch_iframe":
        if not locator or locator.lower() == "default":
            driver.switch_to.default_content()
        else:
            target = _resolve_locator(by, locator)
            wait.until(EC.frame_to_be_available_and_switch_to_it(target))
    elif action == "handle_alert":
        mode = str(value or "accept").strip().lower()
        alert = wait.until(EC.alert_is_present())
        if mode == "dismiss":
            alert.dismiss()
        else:
            alert.accept()

    # 断言校验
    elif action == "assert_text":
        expected = str(value)
        wait.until(
            lambda d: expected in d.find_element(By.TAG_NAME, "body").text
            or expected in d.page_source
        )
    elif action == "assert_title":
        wait.until(EC.title_contains(str(value)))
    elif action == "assert_url":
        wait.until(EC.url_contains(str(value)))
    elif action == "assert_element":
        target = _resolve_locator(by, locator)
        wait.until(EC.visibility_of_element_located(target))
    elif action == "assert_element_text":
        target = _resolve_locator(by, locator)
        expected = str(value)
        wait.until(
            lambda d: expected in (d.find_element(*target).text or "")
        )
    elif action == "assert_element_hidden":
        target = _resolve_locator(by, locator)
        wait.until(EC.invisibility_of_element_located(target))

    # 数据与高级
    elif action == "get_text":
        target = _resolve_locator(by, locator)
        elem = wait.until(EC.visibility_of_element_located(target))
        text_val = elem.text
        var_name = key or str(value or "").strip()
        if var_name:
            ctx.set(var_name, text_val)
            allure.attach(text_val, name=f"提取变量 {var_name}", attachment_type=allure.attachment_type.TEXT)
    elif action == "set_local_storage":
        storage_key = key or locator
        driver.execute_script(
            "window.localStorage.setItem(arguments[0], arguments[1]);",
            storage_key,
            str(value),
        )
    elif action == "set_cookie":
        cookie_name = key or locator
        driver.add_cookie({"name": cookie_name, "value": str(value)})
    elif action == "execute_js":
        driver.execute_script(str(value))
    elif action == "screenshot":
        browser.capture_screenshot(name=step_name or "UI截图")
    else:
        raise ValueError(f"Unsupported UI action: {action}")


def _run_playwright_action(
    action: str,
    by: str,
    locator: str,
    value: Any,
    key: str,
    timeout: float,
    step_name: str,
    ctx: TestContext,
    browser: BrowserSession,
) -> None:
    from playwright.sync_api import expect

    page = browser.get_page()
    scope = browser.get_pw_scope()
    timeout_ms = int(timeout * 1000)

    # 页面导航
    if action == "open":
        browser._pw_frame = None
        page.goto(str(value or locator), wait_until="domcontentloaded", timeout=timeout_ms)
    elif action == "refresh":
        page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
    elif action == "back":
        page.go_back(wait_until="domcontentloaded", timeout=timeout_ms)
    elif action == "forward":
        page.go_forward(wait_until="domcontentloaded", timeout=timeout_ms)

    # 鼠标与输入
    elif action == "click":
        _pw_locator(scope, by, locator).first.click(timeout=timeout_ms)
    elif action == "double_click":
        _pw_locator(scope, by, locator).first.dblclick(timeout=timeout_ms)
    elif action == "right_click":
        _pw_locator(scope, by, locator).first.click(button="right", timeout=timeout_ms)
    elif action == "hover":
        _pw_locator(scope, by, locator).first.hover(timeout=timeout_ms)
    elif action == "input":
        _pw_locator(scope, by, locator).first.fill(str(value), timeout=timeout_ms)
    elif action == "clear":
        _pw_locator(scope, by, locator).first.fill("", timeout=timeout_ms)
    elif action == "press_key":
        raw_key = str(value or "Enter").strip()
        pw_key = _PLAYWRIGHT_KEYS.get(raw_key.lower(), raw_key)
        if locator:
            _pw_locator(scope, by, locator).first.press(pw_key, timeout=timeout_ms)
        else:
            page.keyboard.press(pw_key)
    elif action == "select_option":
        loc = _pw_locator(scope, by, locator).first
        opt_val = str(value)
        try:
            loc.select_option(label=opt_val, timeout=timeout_ms)
        except Exception:
            loc.select_option(value=opt_val, timeout=timeout_ms)
    elif action == "upload_file":
        _pw_locator(scope, by, locator).first.set_input_files(
            str(Path(str(value)).resolve()), timeout=timeout_ms
        )
    elif action == "scroll_to":
        if locator:
            _pw_locator(scope, by, locator).first.scroll_into_view_if_needed(timeout=timeout_ms)
        else:
            pos = str(value or "bottom").strip().lower()
            if pos == "top":
                page.evaluate("window.scrollTo(0, 0)")
            elif pos == "bottom":
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            else:
                page.evaluate("y => window.scrollTo(0, Number(y) || 0)", pos)

    # 等待与窗口/框架
    elif action == "wait":
        page.wait_for_timeout(int(float(value or 1) * 1000))
    elif action == "wait_element":
        _pw_locator(scope, by, locator).first.wait_for(state="visible", timeout=timeout_ms)
    elif action == "switch_tab":
        pages = page.context.pages
        idx = int(str(value or "-1"))
        target_page = pages[idx]
        target_page.bring_to_front()
        browser._pw_page = target_page
        browser._pw_frame = None
    elif action == "close_tab":
        pages = page.context.pages
        page.close()
        remaining = [p for p in pages if not p.is_closed()]
        if remaining:
            browser._pw_page = remaining[-1]
            browser._pw_page.bring_to_front()
            browser._pw_frame = None
    elif action == "switch_iframe":
        if not locator or locator.lower() == "default":
            browser._pw_frame = None
        else:
            iframe_elem = _pw_locator(page, by, locator).first.element_handle(timeout=timeout_ms)
            frame = iframe_elem.content_frame() if iframe_elem else None
            if frame is None:
                raise RuntimeError(f"未找到 iframe: {locator}")
            browser._pw_frame = frame
    elif action == "handle_alert":
        mode = str(value or "accept").strip().lower()
        page.once("dialog", lambda d: d.dismiss() if mode == "dismiss" else d.accept())

    # 断言校验
    elif action == "assert_text":
        expect(scope.locator("body")).to_contain_text(str(value), timeout=timeout_ms)
    elif action == "assert_title":
        expect(page).to_have_title(re.compile(re.escape(str(value))), timeout=timeout_ms)
    elif action == "assert_url":
        expect(page).to_have_url(re.compile(re.escape(str(value))), timeout=timeout_ms)
    elif action == "assert_element":
        expect(_pw_locator(scope, by, locator).first).to_be_visible(timeout=timeout_ms)
    elif action == "assert_element_text":
        expect(_pw_locator(scope, by, locator).first).to_contain_text(str(value), timeout=timeout_ms)
    elif action == "assert_element_hidden":
        expect(_pw_locator(scope, by, locator).first).to_be_hidden(timeout=timeout_ms)

    # 数据与高级
    elif action == "get_text":
        text_val = _pw_locator(scope, by, locator).first.inner_text(timeout=timeout_ms)
        var_name = key or str(value or "").strip()
        if var_name:
            ctx.set(var_name, text_val)
            allure.attach(text_val, name=f"提取变量 {var_name}", attachment_type=allure.attachment_type.TEXT)
    elif action == "set_local_storage":
        storage_key = key or locator
        page.evaluate(
            "([k, v]) => window.localStorage.setItem(k, v)",
            [storage_key, str(value)],
        )
    elif action == "set_cookie":
        cookie_name = key or locator
        page.context.add_cookies(
            [{"name": cookie_name, "value": str(value), "url": page.url}]
        )
    elif action == "execute_js":
        page.evaluate(str(value))
    elif action == "screenshot":
        browser.capture_screenshot(name=step_name or "UI截图")
    else:
        raise ValueError(f"Unsupported UI action: {action}")


def run_ui_step(step: dict[str, Any], ctx: TestContext, browser: BrowserSession) -> None:
    """Execute one UI action via Selenium or Playwright with automatic failure screenshot."""
    action = str(step.get("action", "")).lower().strip()
    by = str(step.get("by", "css"))
    locator = str(ctx.render(step.get("locator", "")))
    value = ctx.render(step.get("value", ""))
    key = str(ctx.render(step.get("key", "")))
    timeout = float(step.get("timeout", 10))
    step_name = str(step.get("name") or "UI截图")

    try:
        if browser.engine == "playwright":
            _run_playwright_action(action, by, locator, value, key, timeout, step_name, ctx, browser)
        else:
            _run_selenium_action(action, by, locator, value, key, timeout, step_name, ctx, browser)
    except Exception:
        browser.capture_screenshot(name="UI失败截图")
        raise
