"""
automation/desktop_agent.py
-----------------------------
PyAutoGUI-based desktop automation.

Supported step commands:
  type:<text>             — type text with the keyboard
  hotkey:<k1>+<k2>+…     — press a keyboard shortcut
  click:<x>,<y>           — left-click at screen coordinates
  screenshot              — save a screenshot (via utils.screenshot)
"""

import time
import pyautogui
from utils.screenshot import take_screenshot
from utils.logger import get_logger

logger = get_logger(__name__)

# PyAutoGUI safety: abort if mouse moves to corner (fail-safe)
pyautogui.FAILSAFE = True
# Small pause between each PyAutoGUI call to avoid flooding the OS
pyautogui.PAUSE = 0.1

# Delay between steps (seconds)
ACTION_DELAY = 0.5


class DesktopAgent:
    """
    Executes a list of desktop automation steps using PyAutoGUI.
    """

    def execute(self, steps: list[str]) -> None:
        """
        Execute a list of step strings.
        Each string is "command:argument" (e.g. "hotkey:win+r").
        """
        for step in steps:
            logger.info(f"DesktopAgent step: {step!r}")

            if ":" in step:
                cmd, _, arg = step.partition(":")
            else:
                cmd, arg = step, ""

            cmd = cmd.strip().lower()
            arg = arg.strip()

            try:
                if cmd == "type":
                    self._type(arg)
                elif cmd == "hotkey":
                    self._hotkey(arg)
                elif cmd == "click":
                    self._click(arg)
                elif cmd == "screenshot":
                    path = take_screenshot()
                    logger.info(f"Screenshot saved: {path}")
                else:
                    logger.warning(f"Unknown desktop command: {cmd!r}")

                time.sleep(ACTION_DELAY)

            except Exception as e:
                logger.error(f"DesktopAgent error on step '{step}': {e}")
                raise

    # ── Individual actions ────────────────────────────────────────────────────

    def _type(self, text: str) -> None:
        """Type text using the keyboard (supports unicode via typewrite interval)."""
        logger.debug(f"Typing: {text!r}")
        pyautogui.write(text, interval=0.05)

    def _hotkey(self, combo: str) -> None:
        """
        Press a keyboard shortcut.
        combo format: "win+r" or "ctrl+shift+esc" etc.
        """
        keys = [k.strip() for k in combo.split("+")]
        logger.debug(f"Hotkey: {keys}")
        pyautogui.hotkey(*keys)

    def _click(self, coords: str) -> None:
        """
        Left-click at x,y screen coordinates.
        coords format: "960,540"
        """
        try:
            x_str, y_str = coords.split(",")
            x, y = int(x_str.strip()), int(y_str.strip())
            logger.debug(f"Clicking at ({x}, {y})")
            pyautogui.click(x, y)
        except ValueError:
            logger.error(f"Invalid click coordinates: {coords!r}")
