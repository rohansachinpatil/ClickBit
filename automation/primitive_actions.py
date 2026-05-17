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
