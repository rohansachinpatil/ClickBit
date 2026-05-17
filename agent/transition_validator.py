"""
agent/transition_validator.py
------------------------------
Lightweight, ultra-fast (sub-5ms) DOM and layout state hashing validator.
Compares page-state snapshots before and after actions to verify transition success.
"""

import hashlib
import time
from playwright.sync_api import Page
from utils.logger import get_logger

logger = get_logger(__name__)

class TransitionSnapshot:
    """Compact descriptor of page state for lightweight delta checks."""
    def __init__(self, url: str, title: str, active_element: str, text_hash: str, elements_hash: str, modal_state: bool):
        self.url = url
        self.title = title
        self.active_element = active_element
        self.text_hash = text_hash
        self.elements_hash = elements_hash
        self.modal_state = modal_state


class TransitionValidator:
    """Computes high-speed transition scores based on page state deltas."""
    
    @staticmethod
    def take_snapshot(page: Page) -> TransitionSnapshot:
        """Captures lightweight markers under 5ms, avoiding expensive full DOM serialization."""
        start_time = time.perf_counter()
        try:
            # Sub-5ms JS extractor targeting visible headers, clickable boundaries, active focus, and modal indicators
            js_script = """
            () => {
                const vw = window.innerWidth;
                const vh = window.innerHeight;
                
                function isElementVisible(el) {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && 
                           style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                }
                
                // Extract visible layout-relevant text fragments (limit to top 40 for speed)
                const textElems = Array.from(document.querySelectorAll('h1, h2, h3, p, span'))
                    .filter(isElementVisible)
                    .map(el => el.innerText.trim())
                    .filter(t => t.length > 0)
                    .slice(0, 40);
                    
                // Extract visible clickable landmarks (limit to top 40)
                const clickableElems = Array.from(document.querySelectorAll('button, a, [role="button"], [role="link"]'))
                    .filter(isElementVisible)
                    .map(el => (el.innerText.trim() || el.getAttribute('aria-label') || el.id || ''))
                    .filter(t => t.length > 0)
                    .slice(0, 40);
                    
                // Active focus identity
                let active = "NONE";
                if (document.activeElement) {
                    active = document.activeElement.tagName + (document.activeElement.id ? "#" + document.activeElement.id : "");
                }
                
                // Alert / Dialog visible state
                const hasModal = !!document.querySelector('[role="dialog"], .modal, .dialog');
                
                return {
                    url: window.location.href,
                    title: document.title,
                    active_element: active,
                    visible_text: textElems.join("|"),
                    clickable_labels: clickableElems.join("|"),
                    modal_state: hasModal
                };
            }
            """
            data = page.evaluate(js_script)
            
            # Lightweight MD5 hashing for rapid comparison
            text_hash = hashlib.md5(data["visible_text"].encode("utf-8", errors="ignore")).hexdigest()
            elems_hash = hashlib.md5(data["clickable_labels"].encode("utf-8", errors="ignore")).hexdigest()
            
            snapshot = TransitionSnapshot(
                url=data["url"],
                title=data["title"],
                active_element=data["active_element"],
                text_hash=text_hash,
                elements_hash=elems_hash,
                modal_state=data["modal_state"]
            )
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.debug(f"[TransitionValidator] Lightweight snapshot completed in {duration_ms:.2f}ms.")
            return snapshot
        except Exception as e:
            logger.error(f"[TransitionValidator] Failed to take page state snapshot: {e}")
            return TransitionSnapshot("", "", "", "", "", False)

    @staticmethod
    def compute_transition_score(before: TransitionSnapshot, after: TransitionSnapshot) -> float:
        """
        Computes the delta magnitude between two snapshots, returning a score from 0.0 to 1.0.
        A score >= 0.15 indicates a successful, meaningful state transition.
        """
        score = 0.0
        
        # 1. URL change is a highly significant transition
        if before.url != after.url:
            score += 0.8
            
        # 2. Page Title change is highly meaningful
        if before.title != after.title:
            score += 0.4
            
        # 3. DOM Text structural mutation
        if before.text_hash != after.text_hash:
            score += 0.3
            
        # 4. Clickable structures layout mutation
        if before.elements_hash != after.elements_hash:
            score += 0.3
            
        # 5. Focus pointer movement
        if before.active_element != after.active_element:
            score += 0.2
            
        # 6. Modal / Overlay visibility state change
        if before.modal_state != after.modal_state:
            score += 0.4
            
        return min(1.0, score)
