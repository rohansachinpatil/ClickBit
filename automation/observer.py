import os
import json
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)

class BrowserObservation:
    """Structured representation of the page state."""
    def __init__(self, title: str, buttons: list[str], inputs: list[str], links: list[str], text_blocks: list[str]):
        self.title = title
        self.buttons = buttons
        self.inputs = inputs
        self.links = links
        self.text_blocks = text_blocks

    def to_dict(self):
        return {
            "title": self.title,
            "buttons": self.buttons[:15],
            "inputs": self.inputs[:15],
            "links": self.links[:15],
            "visible_text": self.text_blocks[:5]
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
                    
                return {
                    title: document.title,
                    buttons: [...new Set(buttons)],
                    inputs: [...new Set(inputs)],
                    links: [...new Set(links)],
                    text_blocks: [...new Set(text_blocks)]
                };
            }
            """
            
            data = page.evaluate(script)
            return BrowserObservation(
                title=data.get("title", ""),
                buttons=data.get("buttons", []),
                inputs=data.get("inputs", []),
                links=data.get("links", []),
                text_blocks=data.get("text_blocks", [])
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
