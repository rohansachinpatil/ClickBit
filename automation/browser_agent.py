"""
automation/browser_agent.py
----------------------------
[BEGINNER GUIDE]
What is this file?
This is the "Hands" of the application. While the Executor thinks, this file actually
opens Google Chrome, types keys, and clicks buttons. 

It uses a library called "Playwright" to control the browser. It also includes a 
"Retry System" which means if a button isn't ready to be clicked, it will wait 
and try again instead of crashing.
"""

import time
import os
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

try:
    from playwright_stealth import stealth_sync
except ImportError:
    from playwright_stealth import Stealth
    def stealth_sync(page):
        Stealth().apply_stealth_sync(page)

from utils.logger import get_logger

logger = get_logger(__name__)

ACTION_DELAY = 1.0
MAX_RETRIES = 3

class BrowserObservation:
    def __init__(self, title: str, buttons: list[str], inputs: list[str], links: list[str], text_snippet: str):
        self.title = title
        self.buttons = buttons
        self.inputs = inputs
        self.links = links
        self.text_snippet = text_snippet

    def to_dict(self):
        return {
            "title": self.title,
            "buttons": self.buttons[:10],
            "inputs": self.inputs[:10],
            "links": self.links[:10],
            "text": self.text_snippet[:200] + "..."
        }

class BrowserAgent(QObject):
    """
    Manages an isolated Playwright browser session. 
    Includes a robust retry and recovery system.
    """
    action_finished = pyqtSignal(str)
    action_error = pyqtSignal(str)
    observation_ready = pyqtSignal(object)
    status_message = pyqtSignal(str)

    def __init__(self, headless: bool = False):
        super().__init__()
        self._headless = headless
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None
        self._page: Page = None
        self._is_executing = False
        logger.info("BrowserAgent Resilient Ready")

    @pyqtSlot(list)
    def execute(self, steps: list) -> None:
        """
        [BEGINNER GUIDE]
        This function receives a list of "Steps" (like a recipe) from the AI.
        It loops through each step one by one and executes it.
        """
        # Don't start a new task if we are already busy
        if self._is_executing: return
        self._is_executing = True
        
        try:
            # 1. Make sure the browser is actually open
            self._ensure_browser()
            total = len(steps)
            
            # Loop through the recipe step-by-step
            for i, raw_step in enumerate(steps, 1):
                # Health Check: Did the user close the browser manually?
                if not self._is_page_alive(): raise RuntimeError("Page closed.")

                # 2. Normalize step (Convert old strings into nice JSON objects)
                # Example: "search:cats" becomes {"command": "search", "argument": "cats"}
                if isinstance(raw_step, str):
                    cmd_part, _, arg_part = raw_step.partition(":")
                    step = {"command": cmd_part.strip().lower(), "argument": arg_part.strip()}
                else:
                    step = raw_step

                cmd = step.get("command", "").lower()
                arg = step.get("argument", "")
                if arg is None: arg = ""
                
                # Tell the UI what we are doing right now
                msg = f"Step {i}/{total}: {cmd} ({arg})"
                logger.info(msg)
                self.status_message.emit(msg)

                # ── Resilient Dispatch ────────────────────────────────────────
                # 3. Actually run the command, but use our special Retry System!
                success = self._run_with_retry(cmd, arg)
                
                # If it failed 3 times, we give up.
                if not success:
                    raise RuntimeError(f"Step {i} failed after {MAX_RETRIES} attempts.")
                
                # Wait 1 second before doing the next step so it looks human
                time.sleep(ACTION_DELAY)
            
            self.action_finished.emit("Task completed successfully")
        except Exception as e:
            logger.error(f"Execution Aborted: {e}")
            self.action_error.emit(str(e))
        finally:
            self._is_executing = False

    def _run_with_retry(self, cmd: str, arg: str) -> bool:
        """
        [BEGINNER GUIDE]
        This is our "Never Give Up" loop. 
        If a website is slow, trying to click a button immediately will crash the app.
        Instead, this loop tries, and if it fails, it waits a few seconds and tries again.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Figure out which function to call based on the command string
                if cmd == "open_url": self._open_url(arg)
                elif cmd == "search": self._search(arg)
                elif cmd == "click_text": self._click_text(arg)
                elif cmd == "click_index": self._click_index(arg)
                elif cmd == "click_first_result": self._click_first_result(arg)
                elif cmd == "type_text": self._type_text(arg)
                elif cmd == "observe": self.observe()
                else: 
                    logger.warning(f"Unknown command: {cmd}")
                    return True # Skip unknown commands instead of crashing
                
                return True # Success! We break out of the loop.
            
            except Exception as e:
                # Oh no, it failed! (e.g. Button not found yet)
                logger.warning(f"Attempt {attempt} failed for [{cmd}]: {e}")
                
                if attempt < MAX_RETRIES:
                    # Exponential Backoff: Wait 2 seconds, then 4 seconds, then 8 seconds.
                    backoff = 2 ** attempt
                    logger.info(f"Recovering... Waiting {backoff}s before retry.")
                    time.sleep(backoff)
                    
                    # Try to stabilize the page before we try again
                    self._recover_state()
                else:
                    # We tried 3 times, giving up completely.
                    logger.error(f"Final failure for [{cmd}] after {MAX_RETRIES} retries.")
        return False

    def _recover_state(self):
        """
        [BEGINNER GUIDE]
        Attempts to fix the browser if it's stuck. 
        It waits until all network traffic stops (networkidle), meaning the page is fully loaded.
        If the entire browser crashed (EPIPE), it fully restarts it.
        """
        logger.info("Stabilizing page state...")
        try:
            # First, check if the browser process completely died (EPIPE/Disconnect)
            if self._playwright and self._browser:
                if not self._browser.is_connected():
                    logger.error("Playwright transport disconnected (EPIPE). Forcing full session restart.")
                    self._teardown_browser()
                    self._ensure_browser()
                    return

            self._ensure_browser()
            if self._is_page_alive():
                self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception as e:
            logger.error(f"State recovery failed: {e}. Forcing session restart.")
            self._teardown_browser()
            self._ensure_browser()

    @pyqtSlot()
    def observe(self) -> None:
        try:
            self._ensure_browser()
            if not self._is_page_alive(): return
            obs = BrowserObservation(
                self._page.title(),
                self._page.eval_on_selector_all("button", "(bs) => bs.map(b => b.innerText)"),
                self._page.eval_on_selector_all("input", "(ins) => ins.map(i => i.placeholder)"),
                self._page.eval_on_selector_all("a", "(as) => as.map(a => a.innerText)"),
                self._page.inner_text("body")[:500]
            )
            self.observation_ready.emit(obs)
        except Exception as e:
            logger.error(f"Observation failed: {e}")

    def _ensure_browser(self):
        """Starts a new Playwright session if one doesn't exist or is corrupted."""
        try:
            if self._browser and not self._browser.is_connected():
                logger.warning("Browser disconnected. Tearing down...")
                self._teardown_browser()
                
            if self._playwright is None:
                logger.info("Initializing new Playwright session...")
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(
                    headless=self._headless, 
                    args=["--no-sandbox", "--disable-gpu", "--no-first-run"]
                )
            if self._context is None:
                self._context = self._browser.new_context(viewport={"width": 1280, "height": 800})
            if self._page is None or self._page.is_closed():
                self._page = self._context.new_page()
                stealth_sync(self._page)
        except Exception as e:
            logger.error(f"Failed to ensure browser state: {e}")
            self._teardown_browser()
            raise RuntimeError("Fatal Playwright initialization error.")

    def _teardown_browser(self):
        """Safely destroys the current Playwright session to prevent zombie processes."""
        logger.info("Tearing down Playwright session...")
        try:
            if self._page and not self._page.is_closed(): self._page.close()
        except: pass
        try:
            if self._context: self._context.close()
        except: pass
        try:
            if self._browser: self._browser.close()
        except: pass
        try:
            if self._playwright: self._playwright.stop()
        except: pass
        
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    def _is_page_alive(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    def _open_url(self, url: str):
        if not url.startswith("http"): url = "https://" + url
        self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try: self._page.wait_for_load_state("networkidle", timeout=5000)
        except: pass

    def _search(self, query: str):
        if self._page.url == "about:blank": self._open_url("google.com")
        selectors = ['textarea[name="q"]', 'input[name="search_query"]', 'input[name="q"]']
        for sel in selectors:
            loc = self._page.locator(sel)
            if loc.count() > 0 and loc.is_visible():
                loc.fill(query)
                loc.press("Enter")
                return
        # Fallback keyboard type
        self._page.keyboard.type(query)
        self._page.keyboard.press("Enter")

    def _click_text(self, text: str):
        self._page.get_by_text(text, exact=False).first.click(timeout=10000)

    def _click_index(self, index: str):
        idx = int(index) - 1
        selectors = ["ytd-video-renderer #video-title", "h3", "a"]
        for sel in selectors:
            locs = self._page.locator(sel)
            visible_count = 0
            for i in range(locs.count()):
                try:
                    if locs.nth(i).is_visible():
                        if visible_count == idx:
                            locs.nth(i).click(timeout=10000)
                            return
                        visible_count += 1
                except: continue
        raise RuntimeError(f"Index {index} not found on page.")

    def _click_first_result(self, arg=""):
        if "youtube.com" in self._page.url:
            self._page.wait_for_selector("ytd-video-renderer", timeout=10000)
            results = self._page.locator("ytd-video-renderer").all()
            for res in results:
                if res.locator(".badge-style-type-ad").count() == 0:
                    title_elem = res.locator("#video-title")
                    if title_elem.is_visible():
                        title_elem.click(timeout=10000)
                        return
        self._page.locator("h3").first.click(timeout=10000)

    def _type_text(self, text: str):
        self._page.keyboard.type(text)

    @pyqtSlot()
    def close(self):
        """Called when the application shuts down."""
        self._teardown_browser()
