"""
automation/primitive_actions.py
--------------------------------
Deterministic action primitives for high-frequency workflows (Google, YouTube).
Bypasses LLM planning steps and executes robustly in a single synchronous cycle.
"""

import time
from playwright.sync_api import Page
from utils.logger import get_logger
from automation.ui_state_engine import UIStateEngine
from agent.transition_validator import TransitionValidator

logger = get_logger(__name__)

class PrimitiveActions:
    """Orchestrates deterministic action sequences with embedded transition and performance validation."""
    
    @staticmethod
    def youtube_search(page: Page, query: str) -> dict:
        """Navigates to YouTube, locates the search field via resilient fallback hierarchy, and triggers query search."""
        start_time = time.perf_counter()
        logger.info(f"[PrimitiveActions] Launching youtube_search primitive for: '{query}'")
        snap_before = TransitionValidator.take_snapshot(page)
        
        try:
            if "youtube.com" not in page.url:
                page.goto("https://youtube.com", timeout=12000, wait_until="load")
                
            # 1. Fallback selectors for YouTube search field
            selectors = ["input#search", "ytd-searchbox input", 'input[name="search_query"]', 'input[placeholder*="Search" i]']
            target_sel = None
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        target_sel = sel
                        break
                except Exception:
                    pass
                    
            if not target_sel:
                # 2. Role locator fallback
                target_sel = 'role=textbox[name="Search" i]'
                
            logger.info(f"[PrimitiveActions] YouTube target resolved to '{target_sel}'. Typing query...")
            loc = page.locator(target_sel).first
            loc.click(timeout=5000)
            
            # Resilient clear and input sequence
            loc.fill("")
            page.wait_for_timeout(100)
            loc.type(query)
            loc.press("Enter")
            
            page.wait_for_load_state("networkidle", timeout=6000)
            page.wait_for_timeout(1000)
            
            snap_after = TransitionValidator.take_snapshot(page)
            score = TransitionValidator.compute_transition_score(snap_before, snap_after)
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            success = score >= 0.15 or "results?search_query=" in page.url
            
            telemetry = {
                "event_type": "primitive_executed",
                "primitive": "youtube_search",
                "transition_score": score,
                "duration_ms": duration_ms,
                "success": success
            }
            logger.info(f"[PrimitiveActions] youtube_search completed: {telemetry}")
            return telemetry
            
        except Exception as e:
            logger.error(f"[PrimitiveActions] youtube_search failed: {e}")
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "event_type": "primitive_executed",
                "primitive": "youtube_search",
                "transition_score": 0.0,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def play_first_video(page: Page, argument: str = "") -> dict:
        """Deterministically extracts and clicks the first video result link on the YouTube active results view."""
        start_time = time.perf_counter()
        logger.info("[PrimitiveActions] Launching play_first_video primitive...")
        snap_before = TransitionValidator.take_snapshot(page)
        
        try:
            # 1. Fallback selectors for YouTube primary video results
            selectors = [
                "ytd-video-renderer a#video-title",
                "ytd-video-renderer a#thumbnail",
                "a#video-title-link",
                "h3 a.ytd-video-renderer",
                "ytd-video-renderer a"
            ]
            target_sel = None
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        target_sel = sel
                        break
                except Exception:
                    pass
                    
            if not target_sel:
                # 2. Native role fallback matching anchors
                target_sel = 'role=link[name*="video" i]'
                
            logger.info(f"[PrimitiveActions] Video target resolved to '{target_sel}'. Triggering click...")
            loc = page.locator(target_sel).first
            loc.click(timeout=5000)
            
            # Wait for play page transition
            page.wait_for_load_state("load", timeout=12000)
            page.wait_for_timeout(2000)
            
            snap_after = TransitionValidator.take_snapshot(page)
            score = TransitionValidator.compute_transition_score(snap_before, snap_after)
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            success = score >= 0.15 or "/watch?v=" in page.url
            
            telemetry = {
                "event_type": "primitive_executed",
                "primitive": "play_first_video",
                "transition_score": score,
                "duration_ms": duration_ms,
                "success": success
            }
            logger.info(f"[PrimitiveActions] play_first_video completed: {telemetry}")
            return telemetry
            
        except Exception as e:
            logger.error(f"[PrimitiveActions] play_first_video failed: {e}")
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "event_type": "primitive_executed",
                "primitive": "play_first_video",
                "transition_score": 0.0,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def google_search(page: Page, query: str) -> dict:
        """Navigates to Google, targets query entry box with robust fallback selectors, and submits query search."""
        start_time = time.perf_counter()
        logger.info(f"[PrimitiveActions] Launching google_search primitive for: '{query}'")
        snap_before = TransitionValidator.take_snapshot(page)
        
        try:
            if "google.com" not in page.url:
                page.goto("https://google.com", timeout=10000, wait_until="load")
                
            selectors = ['textarea[name="q"]', 'input[name="q"]', 'input[title="Search" i]', 'input[placeholder*="Search" i]']
            target_sel = None
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        target_sel = sel
                        break
                except Exception:
                    pass
                    
            if not target_sel:
                target_sel = 'role=combobox'
                
            logger.info(f"[PrimitiveActions] Google target resolved to '{target_sel}'. Typing query...")
            loc = page.locator(target_sel).first
            loc.click(timeout=5000)
            
            loc.fill("")
            page.wait_for_timeout(100)
            loc.type(query)
            loc.press("Enter")
            
            page.wait_for_load_state("networkidle", timeout=6000)
            page.wait_for_timeout(1000)
            
            snap_after = TransitionValidator.take_snapshot(page)
            score = TransitionValidator.compute_transition_score(snap_before, snap_after)
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            success = score >= 0.15 or "search?q=" in page.url
            
            telemetry = {
                "event_type": "primitive_executed",
                "primitive": "google_search",
                "transition_score": score,
                "duration_ms": duration_ms,
                "success": success
            }
            logger.info(f"[PrimitiveActions] google_search completed: {telemetry}")
            return telemetry
            
        except Exception as e:
            logger.error(f"[PrimitiveActions] google_search failed: {e}")
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "event_type": "primitive_executed",
                "primitive": "google_search",
                "transition_score": 0.0,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def dismiss_overlay(page: Page, argument: str = "") -> dict:
        """Bypasses normal planning constraints to immediately dismiss popovers, modal covers, and blocking scrims."""
        start_time = time.perf_counter()
        logger.info("[PrimitiveActions] Launching dismiss_overlay primitive...")
        snap_before = TransitionValidator.take_snapshot(page)
        
        success = UIStateEngine.dismiss_overlay(page)
        
        snap_after = TransitionValidator.take_snapshot(page)
        score = TransitionValidator.compute_transition_score(snap_before, snap_after)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        telemetry = {
            "event_type": "primitive_executed",
            "primitive": "dismiss_overlay",
            "transition_score": score,
            "duration_ms": duration_ms,
            "success": success
        }
        logger.info(f"[PrimitiveActions] dismiss_overlay completed: {telemetry}")
        return telemetry

    @staticmethod
    def chatgpt_search(page: Page, query: str) -> dict:
        """Navigates to chatgpt.com, resiliently dismisses modals, focuses search field, and inputs query."""
        start_time = time.perf_counter()
        logger.info(f"[PrimitiveActions] Launching chatgpt_search primitive for: '{query}'")
        snap_before = TransitionValidator.take_snapshot(page)
        
        try:
            if "chatgpt.com" not in page.url:
                page.goto("https://chatgpt.com", timeout=12000, wait_until="load")
                page.wait_for_timeout(2000)

            # 1. Detect and Dismiss Guest Modal / Login Overlay / cookie walls if visible
            guest_selectors = [
                'button[aria-label="Close"]', 
                'button:has-text("Stay logged out")', 
                'button:has-text("Dismiss")', 
                '.modal button',
                '[role="dialog"] button'
            ]
            for sel in guest_selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        logger.info(f"[PrimitiveActions] Found overlay close button: '{sel}'. Clicking...")
                        loc.click(timeout=3000)
                        page.wait_for_timeout(500)
                except Exception:
                    pass

            # Also general dismiss if still overlay open
            if UIStateEngine.detect_overlay(page):
                UIStateEngine.dismiss_overlay(page)

            # 2. Locate and Focus Textarea
            textarea_selectors = [
                'textarea#prompt-textarea',
                'textarea[placeholder*="message" i]',
                'textarea[placeholder*="Ask" i]',
                'textarea',
                '[contenteditable="true"]'
            ]
            target_sel = None
            for sel in textarea_selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        target_sel = sel
                        break
                except Exception:
                    pass

            if not target_sel:
                target_sel = 'role=textbox'

            logger.info(f"[PrimitiveActions] ChatGPT prompt textarea resolved to '{target_sel}'. Typing query...")
            loc = page.locator(target_sel).first
            loc.click(timeout=5000)
            
            # Resilient clear and fill/type sequence
            loc.fill("")
            page.wait_for_timeout(100)
            loc.type(query)
            
            # 3. Press Enter / Click Send button
            try:
                loc.press("Enter")
            except Exception:
                page.keyboard.press("Enter")

            page.wait_for_timeout(1500)

            snap_after = TransitionValidator.take_snapshot(page)
            score = TransitionValidator.compute_transition_score(snap_before, snap_after)
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            
            success = score >= 0.15 or page.locator('button[data-testid="stop-button"]').count() > 0 or page.locator('button[aria-label="Stop generating"]').count() > 0
            
            telemetry = {
                "event_type": "primitive_executed",
                "primitive": "chatgpt_search",
                "transition_score": score,
                "duration_ms": duration_ms,
                "success": success
            }
            logger.info(f"[PrimitiveActions] chatgpt_search completed: {telemetry}")
            return telemetry

        except Exception as e:
            logger.error(f"[PrimitiveActions] chatgpt_search failed: {e}")
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "event_type": "primitive_executed",
                "primitive": "chatgpt_search",
                "transition_score": 0.0,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def focus_searchbox(page: Page, argument: str = "") -> dict:
        """Deterministically resolves and focuses the topmost prominent searchbox/input field."""
        start_time = time.perf_counter()
        logger.info("[PrimitiveActions] Launching focus_searchbox primitive...")
        snap_before = TransitionValidator.take_snapshot(page)

        try:
            selectors = [
                'input[type="search"]', 'input[placeholder*="Search" i]',
                'textarea[placeholder*="Search" i]', 'input[name="q"]',
                'textarea[name="q"]', 'input#search', 'role=searchbox'
            ]
            target_sel = None
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        target_sel = sel
                        break
                except Exception:
                    pass

            if not target_sel:
                target_sel = 'input'

            logger.info(f"[PrimitiveActions] Focus target resolved to '{target_sel}'. Focusing...")
            loc = page.locator(target_sel).first
            loc.click(timeout=5000)
            loc.focus()

            snap_after = TransitionValidator.take_snapshot(page)
            score = TransitionValidator.compute_transition_score(snap_before, snap_after)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            success = score >= 0.10 or page.evaluate("document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA'")

            telemetry = {
                "event_type": "primitive_executed",
                "primitive": "focus_searchbox",
                "transition_score": score,
                "duration_ms": duration_ms,
                "success": success
            }
            logger.info(f"[PrimitiveActions] focus_searchbox completed: {telemetry}")
            return telemetry

        except Exception as e:
            logger.error(f"[PrimitiveActions] focus_searchbox failed: {e}")
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "event_type": "primitive_executed",
                "primitive": "focus_searchbox",
                "transition_score": 0.0,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(e)
            }
