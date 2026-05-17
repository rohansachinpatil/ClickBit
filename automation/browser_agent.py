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
import threading
from typing import Optional
from enum import Enum
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, Error as PlaywrightError

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

from automation.observer import Observer, BrowserObservation
from automation.selector_resolver import SelectorResolver, ResolverExecutionError

class BrowserSessionState(Enum):
    DEAD = "dead"
    STARTING = "starting"
    READY = "ready"
    EXECUTING = "executing"
    RECOVERING = "recovering"
    STOPPING = "stopping"

class TransportError(Exception):
    """Raised when the underlying Playwright transport is disconnected or corrupted."""
    pass

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
        
        self._session_state = BrowserSessionState.DEAD
        self._session_generation = 0
        self._lifecycle_lock = threading.Lock()
        
        # Telemetry
        self._recovery_count = 0
        self._last_recovery_reason = ""
        self._last_transport_failure = ""
        self._session_start_time = 0
        
        self._is_executing = False
        self._observer = Observer()
        self._selector_resolver = SelectorResolver()
        logger.info("BrowserAgent Resilient Ready")

    @property
    def page(self) -> Optional[Page]:
        return self._page

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
            start_generation = self._session_generation
            
            # Loop through the recipe step-by-step
            for i, raw_step in enumerate(steps, 1):
                if start_generation != self._session_generation:
                    raise RuntimeError("Session generation changed during batch execution. Aborting remaining stale steps.")
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
            
            except ResolverExecutionError as re:
                logger.error(f"[BrowserAgent] Resolver integration error: {re}")
                self.status_message.emit(f"warning: ResolverExecutionError: {re}")
                return False
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
                    
                    # Look at the page again to see if state changed
                    self.observe()
                else:
                    # We tried 3 times, giving up completely.
                    logger.error(f"Final failure for [{cmd}] after {MAX_RETRIES} retries.")
                    # Take a final screenshot for debugging
                    if self._is_page_alive():
                        self._observer.capture_screen(self._page)
        return False

    def _recover_state(self):
        """
        [BEGINNER GUIDE]
        Attempts to fix the browser if it's stuck by waiting for network idle.
        If transport fails, the Lifecycle Manager will catch it separately.
        """
        logger.info("Stabilizing page state...")
        try:
            self._validate_transport()
            self._page.wait_for_load_state("networkidle", timeout=5000)
        except TransportError:
            # Re-raise so the outer loop handles the full session rebuild
            raise
        except Exception as e:
            logger.warning(f"State recovery (networkidle) failed: {e}")

    @pyqtSlot()
    def observe(self) -> None:
        try:
            self._ensure_browser()
            if not self._is_page_alive(): return
            
            # Use the Vision/Observation Layer
            obs = self._observer.get_page_state(self._page)
            
            # Capture a screenshot of the state just in case
            self._observer.capture_screen(self._page)
            
            self.observation_ready.emit(obs)
        except Exception as e:
            logger.error(f"Observation failed: {e}")

    def get_current_observation(self):
        """
        Synchronous observation for the AgentLoop's OBSERVE phase.
        Returns a BrowserObservation, or None if the page is not alive.
        Called directly (not via signal) from the AgentLoopWorker thread.
        NOTE: Both this and AgentLoopWorker run on the same Playwright thread
              to avoid cross-thread page access.
        """
        try:
            self._ensure_ready()
            obs = self._observer.get_page_state(self._page)
            
            # Blank-page & invalid DOM guards
            is_blank = False
            try:
                url = self._page.url
                if url == "about:blank" or url == "":
                    is_blank = True
            except Exception:
                is_blank = True
                
            if is_blank and self._session_generation > 0:
                logger.warning("[BrowserAgent] Blank page detected! Restoring context...")
                raise TransportError("Blank page detected, forcing recovery")
                
            if (not obs.title or obs.title == "Unknown") and not obs.buttons and not obs.inputs and not obs.text_blocks:
                if self._session_generation > 0:
                    logger.warning("[BrowserAgent] Invalid/Empty DOM detected! Recovering observation context.")
                    raise TransportError("Invalid DOM state, forcing recovery")

            # Attach current URL to the observation object for context
            try:
                obs.url = self._page.url
            except Exception:
                pass
            return obs
        except (PlaywrightError, TransportError) as e:
            if "Browser has been closed" in str(e) or "Target page, context or browser has been closed" in str(e) or "EPIPE" in str(e) or isinstance(e, TransportError):
                logger.error(f"[BrowserAgent] Transport failure during observation: {e}")
                self._mark_session_dead(str(e))
                self._recover_session()
                raise TransportError("Transport recovered during observation, retry needed.") from e
            logger.error(f"[BrowserAgent] get_current_observation failed: {e}")
            return None

    def execute_single_action(self, command: str, argument: str, expected_generation: int = None) -> None:
        """
        Executes ONE action through the existing resilient retry system.
        Raises on failure so AgentLoopWorker can record it.
        Called synchronously from AgentLoopWorker (same thread as BrowserAgent).
        """
        if expected_generation is not None and expected_generation != self._session_generation:
            logger.warning(f"Rejecting stale action '{command}({argument})' from generation {expected_generation}. Current generation: {self._session_generation}")
            raise TransportError("Stale action rejected due to transport recovery")
            
        try:
            self._ensure_ready()
            success = self._run_with_retry(command, argument)
            if not success:
                raise RuntimeError(f"execute_single_action: [{command}({argument})] failed after {MAX_RETRIES} retries.")
        except (PlaywrightError, TransportError) as e:
            if "Browser has been closed" in str(e) or "Target page, context or browser has been closed" in str(e) or "EPIPE" in str(e) or isinstance(e, TransportError):
                logger.error(f"Transport failure detected during action: {e}")
                self._mark_session_dead(str(e))
                self._recover_session()
                raise TransportError("Transport recovered, please generate a new action.") from e
            else:
                raise

    def get_session_generation(self) -> int:
        return self._session_generation

    def _ensure_ready(self):
        """
        Validates browser, page, and transport health, and initializes if uninitialized or DEAD.
        Ensures session is READY before proceeding.
        """
        if self._session_state == BrowserSessionState.DEAD or self._playwright is None or self._browser is None or self._page is None:
            logger.info("[BrowserAgent] Session uninitialized or DEAD. Spin up browser runtime...")
            self._ensure_browser()
        self._validate_transport()

    def _validate_transport(self):
        """Validates transport health and explicitly raises if DEAD."""
        if self._session_state == BrowserSessionState.DEAD:
            raise TransportError("Session is DEAD")
        if self._browser and not self._browser.is_connected():
            raise TransportError("Browser disconnected")
        if not self._is_page_alive():
            raise TransportError("Page is closed")

    def _mark_session_dead(self, reason: str):
        self._session_state = BrowserSessionState.DEAD
        self._last_transport_failure = reason
        self.status_message.emit("🛑 Browser transport failed!")
        logger.error(f"Session marked DEAD. Reason: {reason}")

    def _recover_session(self):
        """Full DEAD -> safe teardown -> rebuild session flow."""
        logger.info("Starting recovery sequence...")
        self.status_message.emit("🔄 Rebuilding browser transport layer...")
        self._session_state = BrowserSessionState.RECOVERING
        self._recovery_count += 1
        self._last_recovery_reason = self._last_transport_failure
        
        self._safe_teardown()
        self._ensure_browser()
        
        self._session_generation += 1
        self._session_state = BrowserSessionState.READY
        self.status_message.emit("✅ Transport layer recovered")
        logger.info(f"Recovery complete. New session generation: {self._session_generation}")

    def _safe_teardown(self):
        """Wraps teardown in a lock to prevent concurrent closures."""
        with self._lifecycle_lock:
            if self._session_state == BrowserSessionState.STOPPING:
                return
            prev_state = self._session_state
            self._session_state = BrowserSessionState.STOPPING
            self._teardown_browser_impl()
            if prev_state != BrowserSessionState.RECOVERING:
                self._session_state = BrowserSessionState.DEAD

    def _teardown_browser_impl(self):
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

    def _ensure_browser(self):
        """Starts a new Playwright session under lifecycle lock."""
        with self._lifecycle_lock:
            try:
                if self._browser and not self._browser.is_connected():
                    logger.warning("Browser disconnected. Tearing down...")
                    self._teardown_browser_impl()
                    
                if self._playwright is None:
                    self._session_state = BrowserSessionState.STARTING
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
                
                if self._session_state in [BrowserSessionState.STARTING, BrowserSessionState.DEAD]:
                    self._session_state = BrowserSessionState.READY
                    self._session_start_time = time.time()
                    
            except Exception as e:
                logger.error(f"Failed to ensure browser state: {e}")
                self._teardown_browser_impl()
                self._session_state = BrowserSessionState.DEAD
                raise RuntimeError("Fatal Playwright initialization error.")

    def _is_page_alive(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    def _open_url(self, url: str):
        if not url.startswith("http"): url = "https://" + url
        self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try: self._page.wait_for_load_state("networkidle", timeout=5000)
        except: pass

    def _search(self, query: str):
        if self._page.url == "about:blank": self._open_url("google.com")
        
        # Resolve search input semantically
        cand, conf, reason = self._selector_resolver.resolve_best_candidate(
            self._page, "search", "search"
        )
        if cand and conf > 0.4:
            self.status_message.emit(
                f"SELECTOR_RESOLUTION: Search target: {cand.tag_name}[{cand.text or cand.placeholder}] | Confidence: {conf:.2f} | Reason: {reason}"
            )
            success, sel, msg = self._selector_resolver.execute_fallback_chain(
                self._page, cand, "search", "search", query
            )
            if success:
                self.status_message.emit(f"SELECTOR_RESOLUTION: Search successful via {sel}")
                return

        # Fallback to hardcoded list
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
        cand, conf, reason = self._selector_resolver.resolve_best_candidate(
            self._page, text, "click_text"
        )
        if cand and conf > 0.4:
            self.status_message.emit(
                f"SELECTOR_RESOLUTION: Click target: {cand.tag_name}[{cand.text or cand.placeholder}] | Confidence: {conf:.2f} | Reason: {reason}"
            )
            success, sel, msg = self._selector_resolver.execute_fallback_chain(
                self._page, cand, text, "click"
            )
            if success:
                self.status_message.emit(f"SELECTOR_RESOLUTION: Click successful via {sel}")
                return

        # Playwright's native get_by_text fallback
        self._page.get_by_text(text, exact=False).first.click(timeout=10000)

    def _click_index(self, index: str):
        idx = int(index) - 1
        
        # Retrieve all candidate interactive elements and sort by prominence
        candidates = self._selector_resolver.gather_candidates(self._page)
        visible_candidates = [c for c in candidates if c.is_visible]
        
        if 0 <= idx < len(visible_candidates):
            cand = visible_candidates[idx]
            self.status_message.emit(
                f"SELECTOR_RESOLUTION: Click index {index} -> {cand.tag_name}[{cand.text or cand.placeholder}]"
            )
            success, sel, msg = self._selector_resolver.execute_fallback_chain(
                self._page, cand, index, "click"
            )
            if success:
                self.status_message.emit(f"SELECTOR_RESOLUTION: Click index successful via {sel}")
                return

        # Original exact selectors fallback
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
        
        # Semantic first result click
        cand, conf, reason = self._selector_resolver.resolve_best_candidate(
            self._page, "result", "click"
        )
        if cand and conf > 0.4:
            self.status_message.emit(
                f"SELECTOR_RESOLUTION: Click first result target: {cand.tag_name}[{cand.text}] | Conf: {conf:.2f}"
            )
            success, sel, msg = self._selector_resolver.execute_fallback_chain(
                self._page, cand, "result", "click"
            )
            if success:
                return

        self._page.locator("h3").first.click(timeout=10000)

    def _type_text(self, text: str):
        # Check if active element is an input
        is_input_active = self._page.evaluate(
            "document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA'"
        )
        if is_input_active:
            self._page.keyboard.type(text)
            return

        # Semantic typing fallback
        cand, conf, reason = self._selector_resolver.resolve_best_candidate(
            self._page, "input", "type"
        )
        if cand and conf > 0.4:
            self.status_message.emit(
                f"SELECTOR_RESOLUTION: Type target resolved: {cand.tag_name}[{cand.name or cand.placeholder}]"
            )
            success, sel, msg = self._selector_resolver.execute_fallback_chain(
                self._page, cand, "input", "type", text
            )
            if success:
                return

        self._page.keyboard.type(text)

    def restore_url(self, url: str):
        """Restores browser navigation to the specified URL after session recovery."""
        logger.info(f"[BrowserAgent] restore_url requested: {url}")
        self._ensure_ready()
        self._open_url(url)

    @pyqtSlot()
    def close(self):
        """Called when the application shuts down."""
        self._safe_teardown()
