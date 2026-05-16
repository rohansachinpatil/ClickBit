"""
main.py
--------
ClickBit entry point.

Startup sequence:
  1. Load .env (MISTRAL_API_KEY etc.)
  2. Create QApplication (hidden system-tray icon keeps app alive)
  3. Create FloatingPrompt overlay (hidden initially)
  4. Create Executor (owns Planner, BrowserAgent, DesktopAgent)
  5. Start pynput mouse listener in a background thread
  6. When left+right click detected simultaneously → show FloatingPrompt at cursor
  7. FloatingPrompt.task_submitted → Executor.handle_task

Triggering the overlay:
  Hold LEFT MOUSE + RIGHT MOUSE at the same time (either order).
  The overlay will appear near your cursor.
"""

import sys
import threading
import signal

from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon, QPixmap, QColor
from PyQt5.QtCore import QObject, pyqtSignal, QMetaObject, Qt, Q_ARG, QTimer
from dotenv import load_dotenv

from overlay.floating_prompt import FloatingPrompt
from overlay.confirmation import ConfirmationDialog
from overlay.debug_panel import DebugPanel
from agent.executor import Executor
from utils.logger import get_logger

# ── Load environment variables from .env before anything else ─────────────────
load_dotenv()

logger = get_logger(__name__)


# ── Thread-safe bridge: pynput → Qt ──────────────────────────────────────────

class MouseBridge(QObject):
    """
    [BEGINNER GUIDE]
    What is this?
    This is a "Bridge" between two different worlds: the background mouse listener (pynput)
    and the main user interface (PyQt5). 
    
    Why do we need it?
    PyQt5 expects all UI updates to happen on the "Main Thread". But our mouse listener 
    runs constantly in the background on a "Daemon Thread". If the background thread 
    tried to open the UI directly, the app would crash.
    
    How does it work?
    This class creates a Qt Signal (`trigger`). When the background thread detects a click, 
    it "emits" this signal. PyQt safely catches this signal and opens the UI on the main thread.
    """
    trigger = pyqtSignal(int, int)   # x, y coordinates of the cursor when triggered


class MouseListener:
    """
    Global mouse listener using pynput.
    Tracks which buttons are currently pressed and fires the bridge signal
    when BOTH left and right are held simultaneously.
    """

    def __init__(self, bridge: MouseBridge):
        self._bridge   = bridge
        self._pressed  = set()          # Currently held buttons
        self._fired    = False          # Prevent repeated fires on hold
        self._lock     = threading.Lock()
        self._listener = None

    def start(self) -> None:
        """Starts listening to your mouse clicks in the background."""
        from pynput import mouse as m

        def on_click(x, y, button, pressed):
            """This function is called by your computer every single time you click your mouse."""
            with self._lock: # We use a lock to prevent multiple threads from confusing each other
                if pressed:
                    self._pressed.add(button) # Remember which button is being held down
                    
                    # Fire only when both left AND right are held together
                    if (
                        m.Button.left  in self._pressed
                        and m.Button.right in self._pressed
                        and not self._fired # Make sure we don't fire 100 times per second!
                    ):
                        self._fired = True
                        logger.debug(f"L+R click detected at ({x}, {y})")
                        
                        # Tell the bridge to send a signal to the main app to wake up!
                        self._bridge.trigger.emit(x, y)
                else:
                    self._pressed.discard(button) # Forget the button once you let go
                    
                    # Reset the 'fired' lock once you let go of all buttons
                    if not self._pressed:
                        self._fired = False

        # Create the listener and tell it to run in the background (daemon)
        self._listener = m.Listener(on_click=on_click)
        self._listener.daemon = True
        self._listener.start()
        logger.info("Global mouse listener started (L+R click to show overlay)")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()


# ── Main application ──────────────────────────────────────────────────────────

def create_tray_icon(app: QApplication, prompt: FloatingPrompt, executor: Executor) -> QSystemTrayIcon:
    """
    Creates a minimal system-tray icon so the app stays alive when
    the overlay is hidden and doesn't appear in the taskbar.
    """
    # Generate a simple coloured icon programmatically (no image file needed)
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(80, 100, 255))
    icon = QIcon(pixmap)

    tray = QSystemTrayIcon(icon, parent=app)
    tray.setToolTip("ClickBit — L+R click to activate")

    menu = QMenu()

    show_action = QAction("Show Prompt", menu)
    show_action.triggered.connect(lambda: prompt.show_at(200, 200))
    menu.addAction(show_action)

    menu.addSeparator()

    quit_action = QAction("Quit ClickBit", menu)
    quit_action.triggered.connect(lambda: _quit(app, executor))
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.show()
    logger.info("System tray icon created")
    return tray


def _quit(app: QApplication, executor: Executor) -> None:
    """Graceful shutdown."""
    logger.info("Shutting down ClickBit…")
    executor.shutdown()
    app.quit()


def main():
    """
    [BEGINNER GUIDE]
    This is the STARTING POINT of the entire ClickBit application.
    When you run `python main.py`, this function is what actually gets executed.
    """
    logger.info("=" * 60)
    logger.info("ClickBit starting…")
    logger.info("=" * 60)

    # 1. Start the GUI Application Engine (PyQt5)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # Don't close the app just because the floating prompt is hidden

    # ── Build components ───────────────────────────────────────────────────
    # 2. Create the "Pieces" of our app
    prompt   = FloatingPrompt()     # The text box you type into
    executor = Executor()           # The "Brain" that decides what to do
    debug_panel = DebugPanel()      # The timeline window on the side
    bridge   = MouseBridge()        # The thread-safe signal sender
    listener = MouseListener(bridge)# The background ear listening for clicks

    # ── Signal Handling (Ctrl+C) ──────────────────────────────────────────
    # 3. Allow stopping the app from the terminal safely
    def signal_handler(sig, frame):
        logger.info("Interrupt received, shutting down...")
        _quit(app, executor)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # 4. Qt usually ignores terminal signals. A timer forces Qt to check for them.
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    # ── Wire signals ───────────────────────────────────────────────────────
    # [BEGINNER GUIDE] - What is Wiring Signals?
    # Think of signals like "Text Messages". One part of the app sends a message, 
    # and another part is listening and reacts to it.
    
    # When the mouse listener hears L+R click -> Tell the prompt to show itself
    bridge.trigger.connect(prompt.show_at)

    # When you press Enter in the prompt -> Tell the Executor to handle the task
    prompt.task_submitted.connect(executor.handle_task)

    # As the Executor thinks -> Tell the prompt to update its text (e.g. "🧠 Planning...")
    executor.task_started.connect(prompt.on_task_started)
    executor.task_finished.connect(prompt.on_task_finished)
    executor.task_error.connect(prompt.on_task_error)
    
    # When the Executor does literally anything -> Send a text message to the Debug Panel to display
    executor.agent_event.connect(debug_panel.add_event)

    # ── Confirmation Logic ────────────────────────────────────────────────
    def show_confirmation(plan: dict):
        steps = plan.get("steps", [])
        dialog = ConfirmationDialog(steps)
        # Connect dialog buttons to executor slots
        dialog.approved.connect(executor.approve_plan)
        dialog.rejected.connect(executor.reject_plan)
        dialog.exec_()

    executor.confirmation_required.connect(show_confirmation)

    # ── System tray ────────────────────────────────────────────────────────
    tray = create_tray_icon(app, prompt, executor)

    # ── Start mouse listener ───────────────────────────────────────────────
    listener.start()

    logger.info("ClickBit is running. Hold LEFT + RIGHT mouse button to open the prompt.")
    logger.info("Right-click the system tray icon to quit.")

    exit_code = app.exec_()
    listener.stop()
    executor.shutdown()
    logger.info(f"ClickBit exited with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
