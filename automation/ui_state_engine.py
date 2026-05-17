"""
automation/ui_state_engine.py
------------------------------
Real-time page state tracking including modal presence, high z-index overlay blockages,
and pointer blockage detection. Exposes page interaction state snapshots.
"""

from playwright.sync_api import Page
from utils.logger import get_logger

logger = get_logger(__name__)

class UIState:
    """Holds a snapshot of the page's current UI layout state and blockages."""
    def __init__(self, overlay_open: bool, modal_visible: bool, active_element_type: str, 
                 pointer_blocked: bool, visible_inputs: list, clickable_regions: list, blocker_selector: str = "",
                 is_pointer_blocked: bool = False, blocking_element: str = "", overlay_zindex: int = 0,
                 viewport_coverage_percent: float = 0.0):
        self.overlay_open = overlay_open
        self.modal_visible = modal_visible
        self.active_element_type = active_element_type
        self.pointer_blocked = pointer_blocked
        self.visible_inputs = visible_inputs
        self.clickable_regions = clickable_regions
        self.blocker_selector = blocker_selector
        
        # New attributes required by the Semantic Grounding layer spec
        self.is_pointer_blocked = is_pointer_blocked
        self.blocking_element = blocking_element
        self.overlay_zindex = overlay_zindex
        self.viewport_coverage_percent = viewport_coverage_percent

    def to_dict(self) -> dict:
        return {
            "overlay_open": self.overlay_open,
            "modal_visible": self.modal_visible,
            "active_element_type": self.active_element_type,
            "pointer_blocked": self.pointer_blocked,
            "visible_inputs": self.visible_inputs,
            "clickable_regions": self.clickable_regions,
            "blocker_selector": self.blocker_selector,
            
            # New fields
            "is_pointer_blocked": self.is_pointer_blocked,
            "blocking_element": self.blocking_element,
            "overlay_zindex": self.overlay_zindex,
            "viewport_coverage_percent": self.viewport_coverage_percent
        }


class UIStateEngine:
    """Orchestrates UI layout inspection, blockage safety checks, and resilient overlays recovery."""
    
    @staticmethod
    def inspect_page(page: Page) -> UIState:
        """Analyzes active overlays, z-index hierarchy, viewport coverage %, and input systems."""
        try:
            # High-performance JS analyzer evaluating z-indices, fixed elements, and overlap area
            js_script = """
            () => {
                const vw = window.innerWidth;
                const vh = window.innerHeight;
                const viewportArea = vw * vh;
                
                const all = Array.from(document.querySelectorAll('*'));
                let overlayOpen = false;
                let modalVisible = false;
                let pointerBlocked = false;
                let blockerSelector = "";
                let overlayZindex = 0;
                let viewportCoveragePercent = 0.0;
                
                // 1. Precise Modal / Dialog Detection
                const modalSelectors = [
                    '[role="dialog"]', '[role="alertdialog"]', 
                    '.modal', '.dialog', '.popup',
                    '[class*="modal" i]', '[class*="dialog" i]', '[class*="popup" i]'
                ];
                for (const selector of modalSelectors) {
                    const el = document.querySelector(selector);
                    if (el) {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        if (rect.width > 50 && rect.height > 50 && 
                            style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                            modalVisible = true;
                            overlayOpen = true;
                            blockerSelector = selector;
                            const zIndexVal = parseInt(style.zIndex, 10);
                            overlayZindex = isNaN(zIndexVal) ? 0 : zIndexVal;
                            
                            const overlapX = Math.max(0, Math.min(rect.right, vw) - Math.max(rect.left, 0));
                            const overlapY = Math.max(0, Math.min(rect.bottom, vh) - Math.max(rect.top, 0));
                            const overlapArea = overlapX * overlapY;
                            viewportCoveragePercent = (overlapArea / viewportArea) * 100.0;
                            break;
                        }
                    }
                }
                
                // 2. High Z-Index & Viewport Coverage Interception Analysis
                if (!overlayOpen) {
                    for (const el of all) {
                        if (!el.getBoundingClientRect) continue;
                        const rect = el.getBoundingClientRect();
                        if (rect.width <= 10 || rect.height <= 10) continue;
                        
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
                        
                        // Viewport intersection bounds
                        const overlapX = Math.max(0, Math.min(rect.right, vw) - Math.max(rect.left, 0));
                        const overlapY = Math.max(0, Math.min(rect.bottom, vh) - Math.max(rect.top, 0));
                        const overlapArea = overlapX * overlapY;
                        const coverage = overlapArea / viewportArea;
                        
                        const zIndexVal = parseInt(style.zIndex, 10);
                        const hasHighZ = !isNaN(zIndexVal) && zIndexVal >= 10;
                        
                        // Custom overlay naming patterns (banners, scrims, cookie consent managers)
                        const isOverlayClass = /[_-]?(overlay|scrim|backdrop|drawer|banner|cookie|popover|dialog)[_-]?/i.test(el.className || "") || 
                                               /[_-]?(overlay|scrim|backdrop|drawer|banner|cookie|popover|dialog)[_-]?/i.test(el.id || "");
                        
                        const isFixedAbs = style.position === 'fixed' || style.position === 'absolute';
                        
                        // If fixed/absolute, has high z-index or overlay marker, and covers >= 40% viewport
                        if (isFixedAbs && (hasHighZ || isOverlayClass) && coverage >= 0.40) {
                            overlayOpen = true;
                            pointerBlocked = true;
                            blockerSelector = el.tagName + (el.id ? '#' + el.id : '') + 
                                              (el.className ? '.' + el.className.split(' ').join('.') : '');
                            overlayZindex = isNaN(zIndexVal) ? 0 : zIndexVal;
                            viewportCoveragePercent = coverage * 100.0;
                            break;
                        }
                    }
                }
                
                // 3. Helper to determine visibility
                function isElementVisible(el) {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && 
                           style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                }
                
                const visibleInputs = Array.from(document.querySelectorAll('input, textarea'))
                    .filter(isElementVisible)
                    .map(i => i.placeholder || i.name || i.id || "")
                    .filter(x => x.length > 0);
                    
                const clickableRegions = Array.from(document.querySelectorAll('button, a, [role="button"], [role="link"]'))
                    .filter(isElementVisible)
                    .map(c => c.innerText.trim() || c.getAttribute('aria-label') || "")
                    .filter(x => x.length > 0);
                    
                let activeElemType = "UNKNOWN";
                if (document.activeElement) {
                    activeElemType = document.activeElement.tagName;
                    const r = document.activeElement.getAttribute('role');
                    if (r) {
                        activeElemType += `:${r.toUpperCase()}`;
                    }
                }
                
                return {
                    overlay_open: overlayOpen,
                    modal_visible: modalVisible,
                    pointer_blocked: pointerBlocked,
                    active_element_type: activeElemType,
                    visible_inputs: [...new Set(visibleInputs)].slice(0, 15),
                    clickable_regions: [...new Set(clickableRegions)].slice(0, 15),
                    blocker_selector: blockerSelector,
                    overlay_zindex: overlayZindex,
                    viewport_coverage_percent: viewportCoveragePercent
                };
            }
            """
            data = page.evaluate(js_script)
            return UIState(
                overlay_open=data.get("overlay_open", False),
                modal_visible=data.get("modal_visible", False),
                active_element_type=data.get("active_element_type", "UNKNOWN"),
                pointer_blocked=data.get("pointer_blocked", False),
                visible_inputs=data.get("visible_inputs", []),
                clickable_regions=data.get("clickable_regions", []),
                blocker_selector=data.get("blocker_selector", ""),
                is_pointer_blocked=data.get("pointer_blocked", False),
                blocking_element=data.get("blocker_selector", ""),
                overlay_zindex=data.get("overlay_zindex", 0),
                viewport_coverage_percent=data.get("viewport_coverage_percent", 0.0)
            )
        except Exception as e:
            logger.error(f"UIStateEngine inspection failed: {e}")
            return UIState(False, False, "UNKNOWN", False, [], [])

    @classmethod
    def detect_overlay(cls, page: Page) -> bool:
        state = cls.inspect_page(page)
        return state.overlay_open or state.pointer_blocked or state.is_pointer_blocked

    @classmethod
    def attempt_escape_recovery(cls, page: Page) -> bool:
        """Attempts to recover by pressing the Escape key to dismiss active overlays."""
        try:
            logger.info("[UIStateEngine] Attempting Escape key recovery...")
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            return not cls.detect_overlay(page)
        except Exception as e:
            logger.error(f"[UIStateEngine] Escape recovery failed: {e}")
            return False

    @classmethod
    def scrim_click_recovery(cls, page: Page) -> bool:
        """Attempts to recover by clicking a neutral viewport area (scrim/backdrop)."""
        try:
            logger.info("[UIStateEngine] Attempting outer scrim click recovery...")
            page.mouse.click(10, 10)
            page.wait_for_timeout(500)
            return not cls.detect_overlay(page)
        except Exception as e:
            logger.error(f"[UIStateEngine] Scrim click recovery failed: {e}")
            return False

    @classmethod
    def dismiss_overlay(cls, page: Page) -> bool:
        """Resiliently attempts modal / overlay dismissal via keyboard and target click strategies."""
        logger.info("[UIStateEngine] Attempting overlay / modal dismissal recovery cascade...")
        try:
            # 1. Escape key recovery
            if cls.attempt_escape_recovery(page):
                logger.info("[UIStateEngine] Overlay dismissed successfully via Escape key.")
                return True
                
            # 2. Click outside the modal center (scrim/backdrop click)
            if cls.scrim_click_recovery(page):
                logger.info("[UIStateEngine] Overlay dismissed successfully via outer scrim-click.")
                return True
                
            # 3. Dynamic lookup of common closing selectors
            closing_selectors = [
                '[aria-label*="close" i]', '.close', '#close', 
                '[class*="close" i]', 'button:has-text("Close")', 
                'button:has-text("✕")', 'button:has-text("X")'
            ]
            for selector in closing_selectors:
                try:
                    loc = page.locator(selector).first
                    if loc.count() > 0 and loc.is_visible():
                        loc.click(timeout=1000)
                        page.wait_for_timeout(500)
                        if not cls.detect_overlay(page):
                            logger.info(f"[UIStateEngine] Overlay dismissed via closing button '{selector}'.")
                            return True
                except Exception:
                    pass
                    
            logger.warning("[UIStateEngine] Overlay dismissal cascade finished without complete resolution.")
            return False
        except Exception as e:
            logger.error(f"[UIStateEngine] Error during dismiss_overlay: {e}")
            return False

    @classmethod
    def validate_interaction_safe(cls, page: Page, selector: str) -> bool:
        """Verifies if the selector target is visible, enabled, and not overlay-blocked."""
        try:
            loc = page.locator(selector).first
            if not loc.is_visible() or not loc.is_enabled():
                return False
                
            # Pointer interception verify
            state = cls.inspect_page(page)
            if state.pointer_blocked and state.blocker_selector:
                # If element is inside the overlay itself, it is safe to interact with!
                # We check if the element is nested under the blocker selector.
                try:
                    is_nested = page.evaluate(f"""(sel, blocker) => {{
                        const el = document.querySelector(sel);
                        const bl = document.querySelector(blocker);
                        return bl && el && (bl === el || bl.contains(el));
                    }}""", selector, state.blocker_selector)
                    if is_nested:
                        return True
                except Exception:
                    pass
                return False
            return True
        except Exception:
            return False
