"""
automation/element_classifier.py
---------------------------------
Determines the semantic type of a page element before attempting interactions,
preventing invalid interactions (like typing into link nodes).
"""

from enum import Enum
from playwright.sync_api import Locator
from utils.logger import get_logger

logger = get_logger(__name__)

class ElementType(Enum):
    INPUT = "INPUT"
    BUTTON = "BUTTON"
    LINK = "LINK"
    SEARCHBOX = "SEARCHBOX"
    MENU = "MENU"
    UNKNOWN = "UNKNOWN"

class ElementClassifier:
    """Classifies visible page elements to ensure interaction safety and element compatibility."""
    
    @staticmethod
    def classify(locator: Locator) -> ElementType:
        """Inspects tag properties, attributes, and roles via browser execution."""
        try:
            info = locator.evaluate("""(el) => {
                return {
                    tagName: el.tagName.toUpperCase(),
                    type: (el.getAttribute('type') || '').toUpperCase(),
                    role: (el.getAttribute('role') || '').toUpperCase(),
                    contentEditable: el.contentEditable === 'true' || el.isContentEditable,
                    placeholder: el.getAttribute('placeholder') || ''
                };
            }""")
            
            tag = info.get("tagName", "")
            typ = info.get("type", "")
            role = info.get("role", "")
            editable = info.get("contentEditable", False)
            placeholder = info.get("placeholder", "").lower()
            
            # 1. Searchbox checks (role, type, or placeholder text)
            if role == "SEARCHBOX" or typ == "SEARCH" or "search" in placeholder:
                return ElementType.SEARCHBOX
                
            # 2. Input / Textarea / ContentEditable checks
            if tag in ("INPUT", "TEXTAREA") or editable or role in ("TEXTBOX", "COMBOBOX"):
                return ElementType.INPUT
                
            # 3. Button checks
            if tag == "BUTTON" or role == "BUTTON" or (tag == "INPUT" and typ in ("BUTTON", "SUBMIT", "RESET")):
                return ElementType.BUTTON
                
            # 4. Link checks
            if tag == "A" or role == "LINK":
                return ElementType.LINK
                
            # 5. Menu / Dropdown checks
            if role in ("MENUITEM", "OPTION", "LISTBOX", "SELECT", "MENU"):
                return ElementType.MENU
                
            return ElementType.UNKNOWN
        except Exception as e:
            logger.debug(f"Element classification failed: {e}")
            return ElementType.UNKNOWN

    @classmethod
    def is_input(cls, locator: Locator) -> bool:
        t = cls.classify(locator)
        return t in (ElementType.INPUT, ElementType.SEARCHBOX)

    @classmethod
    def is_clickable(cls, locator: Locator) -> bool:
        t = cls.classify(locator)
        return t in (ElementType.BUTTON, ElementType.LINK, ElementType.MENU)

    @classmethod
    def supports_typing(cls, locator: Locator) -> bool:
        return cls.is_input(locator)
