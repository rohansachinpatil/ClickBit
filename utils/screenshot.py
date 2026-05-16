"""
utils/screenshot.py
--------------------
Screen capture helper using PyAutoGUI.
"""

import os
import time
import pyautogui
from utils.logger import get_logger

logger = get_logger(__name__)

# Default directory for saved screenshots
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots")


def take_screenshot(path: str = None) -> str:
    """
    Captures the entire screen and saves it to `path`.
    If no path is given, auto-generates a timestamped filename in ./screenshots/.
    Returns the absolute path of the saved file.
    """
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    if path is None:
        filename = f"screenshot_{int(time.time())}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)

    logger.debug(f"Taking screenshot → {path}")
    screenshot = pyautogui.screenshot()
    screenshot.save(path)
    logger.info(f"Screenshot saved: {path}")
    return path
