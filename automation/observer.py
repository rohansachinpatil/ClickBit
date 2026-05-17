import os
import json
from pathlib import Path
from utils.logger import get_logger
from automation.js_bridge import safe_evaluate

logger = get_logger(__name__)

class BrowserObservation:
    """Structured representation of the page state."""
    def __init__(self, title: str, buttons: list[str], inputs: list[str], links: list[str], text_blocks: list[str],
                 captcha_detected: bool = False, auth_required: bool = False, permission_popup: bool = False, modal_blocking_flow: bool = False, intervention_reason: str = None):
        self.title = title
        self.buttons = buttons
        self.inputs = inputs
        self.links = links
        self.text_blocks = text_blocks
        self.captcha_detected = captcha_detected
        self.auth_required = auth_required
        self.permission_popup = permission_popup
        self.modal_blocking_flow = modal_blocking_flow
        self.intervention_reason = intervention_reason

    def to_dict(self):
        return {
            "title": self.title,
            "buttons": self.buttons[:15],
            "inputs": self.inputs[:15],
            "links": self.links[:15],
            "visible_text": self.text_blocks[:5],
            "captcha_detected": self.captcha_detected,
            "auth_required": self.auth_required,
            "permission_popup": self.permission_popup,
            "modal_blocking_flow": self.modal_blocking_flow,
            "intervention_reason": self.intervention_reason
        }

class Observer:
    """
    Vision and Observation Layer.
    Extracts structured DOM data, takes screenshots, and performs OCR.
    """
    def __init__(self):
        self.tmp_dir = Path("tmp")
        self.tmp_dir.mkdir(exist_ok=True)
        self.screenshot_path = self.tmp_dir / "last_state.png"

    def get_page_state(self, page) -> BrowserObservation:
        """Dynamically extracts visible elements from the DOM."""
        try:
            # We use an injected script to get truly visible elements
            # Playwright's innerText sometimes includes hidden elements or misses layout
            script = """
            () => {
                function isVisible(el) {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && 
                           style.visibility !== 'hidden' && style.opacity !== '0';
                }
                
                const buttons = Array.from(document.querySelectorAll('button, [role="button"]'))
                    .filter(isVisible)
                    .map(b => b.innerText.trim() || b.getAttribute('aria-label') || b.value || "")
                    .filter(t => t.length > 0);
                    
                const inputs = Array.from(document.querySelectorAll('input, textarea'))
                    .filter(isVisible)
                    .map(i => i.placeholder || i.name || i.id || "")
                    .filter(t => t.length > 0);
                    
                const links = Array.from(document.querySelectorAll('a'))
                    .filter(isVisible)
                    .map(a => a.innerText.trim() || a.getAttribute('aria-label') || "")
                    .filter(t => t.length > 0);
                    
                // Grab some main text blocks (h1, h2, p)
                const text_blocks = Array.from(document.querySelectorAll('h1, h2, h3, p'))
                    .filter(isVisible)
                    .map(el => el.innerText.trim())
                    .filter(t => t.length > 0);
                    
                // Heuristics for human intervention
                let captcha_detected = false;
                let auth_required = false;
                let permission_popup = false;
                let modal_blocking_flow = false;
                let intervention_reason = null;

                if (document.querySelector('iframe[src*="recaptcha"]') || document.querySelector('iframe[src*="cloudflare"]') || document.querySelector('.cf-turnstile') || document.body.innerText.includes('Verify you are human')) {
                    captcha_detected = true;
                    intervention_reason = 'CAPTCHA_DETECTED';
                } else if (document.querySelector('input[type="password"]')) {
                    auth_required = true;
                    intervention_reason = 'AUTH_REQUIRED';
                } else if (document.querySelector('div[id*="cookie"]') || document.querySelector('div[role="dialog"]')) {
                    modal_blocking_flow = true;
                    intervention_reason = 'MODAL_BLOCKING_FLOW';
                }
                    
                return {
                    title: document.title,
                    buttons: [...new Set(buttons)],
                    inputs: [...new Set(inputs)],
                    links: [...new Set(links)],
                    text_blocks: [...new Set(text_blocks)],
                    captcha_detected: captcha_detected,
                    auth_required: auth_required,
                    permission_popup: permission_popup,
                    modal_blocking_flow: modal_blocking_flow,
                    intervention_reason: intervention_reason
                };
            }
            """
            
            data = safe_evaluate(page, script)
            return BrowserObservation(
                title=data.get("title", ""),
                buttons=data.get("buttons", []),
                inputs=data.get("inputs", []),
                links=data.get("links", []),
                text_blocks=data.get("text_blocks", []),
                captcha_detected=data.get("captcha_detected", False),
                auth_required=data.get("auth_required", False),
                permission_popup=data.get("permission_popup", False),
                modal_blocking_flow=data.get("modal_blocking_flow", False),
                intervention_reason=data.get("intervention_reason", None)
            )
            
        except Exception as e:
            logger.error(f"DOM extraction failed: {e}")
            # Fallback to empty observation, then attempt OCR if needed
            return BrowserObservation("Unknown", [], [], [], [])

    def capture_screen(self, page) -> str:
        """Captures a screenshot of the current viewport to the tmp folder."""
        try:
            path_str = str(self.screenshot_path)
            page.screenshot(path=path_str, full_page=False)
            logger.debug(f"Screenshot saved to {path_str}")
            return path_str
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return ""

    def ocr_fallback(self, image_path: str) -> str:
        """Uses pytesseract to read text from an image if DOM is obscured."""
        try:
            import pytesseract
            from PIL import Image
            
            if not os.path.exists(image_path):
                return ""
                
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img)
            logger.info("OCR fallback successful")
            return text.strip()
        except ImportError:
            logger.warning("pytesseract or PIL not installed, skipping OCR fallback.")
            return ""
        except Exception as e:
            logger.warning(f"OCR fallback failed (Tesseract may not be installed): {e}")
            return ""
