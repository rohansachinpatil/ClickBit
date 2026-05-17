"""
agent/executor.py
------------------
The central coordinator between the UI, the Autonomous Agent Loop,
and the BrowserAgent.

Architecture (v2 — Autonomous Loop):
  UI                →  Executor.handle_task(goal)
  Executor          →  shows one-shot high-level approval dialog
  User approves     →  Executor.approve_task()
  Executor          →  spins up AgentLoopWorker in _browser_thread
                        (SAME thread as BrowserAgent for Playwright safety)
  AgentLoopWorker   →  Observe → Think → Act continuously
  BrowserAgent      →  executes single actions synchronously in its thread
  Executor          →  forwards all signals to the UI / Debug Panel
"""

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from agent.action_decider  import ActionDecider
from agent.agent_loop      import AgentLoopWorker
from agent.memory          import Memory
from agent.planner         import Planner, SYSTEM_PROMPT
from agent.router          import Router
from agent.workflow_memory import WorkflowMemory
from automation.browser_agent  import BrowserAgent
from automation.desktop_agent  import DesktopAgent
from utils.logger import get_logger

logger = get_logger(__name__)


class Executor(QObject):
    # ── Signals consumed by the UI ─────────────────────────────────────────────
    task_started          = pyqtSignal(str)          # (goal) — update prompt status
    confirmation_required = pyqtSignal(dict)         # (goal_dict) — show approval dialog
    task_finished         = pyqtSignal(str)          # (message) — hide prompt
    task_error            = pyqtSignal(str)          # (message) — show error state
    clarification_needed  = pyqtSignal(str)          # (reasoning) — ask user for hint
    agent_event           = pyqtSignal(str, str, str) # (type, message, status) → Debug Panel

    def __init__(self, parent=None):
        super().__init__(parent)

        # Core sub-systems (stateless helpers)
        self._memory     = Memory()
        self._router     = Router()
        self._planner    = Planner(memory=self._memory)
        self._wf_memory  = WorkflowMemory()

        # BrowserAgent lives in a dedicated thread — ALL Playwright ops run here
        self._browser_thread = QThread()
        self._browser_agent  = BrowserAgent(headless=False)
        self._browser_agent.moveToThread(self._browser_thread)
        self._browser_thread.start()

        # Forward BrowserAgent status messages to the Debug Panel
        self._browser_agent.status_message.connect(
            lambda msg: self.agent_event.emit("action", msg, "info")
        )
        self._browser_agent.observation_ready.connect(self._on_observation)

        self._desktop_agent = DesktopAgent()

        # Agent loop bookkeeping
        self._agent_thread:  QThread = None
        self._agent_worker:  AgentLoopWorker = None
        self._pending_goal:  str = None
        self._current_goal:  str = None

        logger.info("Executor ready (Autonomous Agent Loop Enabled)")

    # ── Public API called by UI ────────────────────────────────────────────────

    @pyqtSlot(str)
    def handle_task(self, prompt: str):
        """Called when user presses Enter in the floating prompt."""
        if self._agent_thread and self._agent_thread.isRunning():
            self.task_error.emit("An agent task is already running. Stop it first.")
            return

        self._pending_goal = prompt
        self._current_goal = prompt
        self.task_started.emit(prompt)
        self.agent_event.emit("info", f"📋 New goal received: {prompt}", "info")

        # Emit the one-shot high-level approval dialog
        # We reuse the existing confirmation_required signal;
        # the confirmation dialog renders the goal as a plain text description.
        goal_dict = {
            "action": "autonomous",
            "goal": prompt,
            "steps": [f"Autonomously complete: {prompt}"],
        }
        self.confirmation_required.emit(goal_dict)

    @pyqtSlot()
    def approve_plan(self):
        """Called when the user approves the high-level goal. Starts the agent loop."""
        if not self._pending_goal:
            return
        goal = self._pending_goal
        self._pending_goal = None

        self.agent_event.emit("planning", f"🚀 Launching autonomous agent for: {goal}", "info")
        self._start_agent_loop(goal)

    @pyqtSlot()
    def reject_plan(self):
        """User rejected the high-level goal approval."""
        self._pending_goal = None
        self.task_finished.emit("Task cancelled by user.")

    @pyqtSlot()
    def emergency_stop(self):
        """Immediately signals the running agent loop to halt."""
        if self._agent_worker:
            self._agent_worker.request_stop()
            self.agent_event.emit("error", "🛑 Emergency stop requested!", "error")

    @pyqtSlot(str)
    def provide_clarification(self, hint: str):
        """Resume the loop after the user answered a clarification request."""
        if self._agent_worker:
            self._agent_worker.resume_after_clarification(hint)

    @pyqtSlot()
    def resume_intervention(self):
        """Called when the user clicks Resume on the intervention card."""
        if self._agent_worker:
            self._agent_worker.resume_intervention()

    @pyqtSlot()
    def abort_intervention(self):
        """Called when the user clicks Abort on the intervention card."""
        self.emergency_stop()

    # ── Internal: Agent Loop Lifecycle ────────────────────────────────────────

    def _start_agent_loop(self, goal: str):
        """
        Spins up the AgentLoopWorker on the SAME thread as BrowserAgent.
        This is the critical design choice: both workers share the Playwright
        thread, so the loop can call browser_agent methods synchronously
        without cross-thread Playwright access.
        """
        # Create the worker but move it to the existing browser thread
        self._agent_worker = AgentLoopWorker(goal=goal, browser_agent=self._browser_agent)
        self._agent_worker.moveToThread(self._browser_thread)

        # Wire signals
        self._agent_worker.loop_event.connect(self.agent_event)
        self._agent_worker.loop_finished.connect(self._on_loop_finished)
        self._agent_worker.loop_error.connect(self._on_loop_error)
        self._agent_worker.clarification_needed.connect(self.clarification_needed)

        # Start via QMetaObject.invokeMethod so it runs on _browser_thread's event loop
        from PyQt5.QtCore import QMetaObject, Qt
        QMetaObject.invokeMethod(self._agent_worker, "run", Qt.QueuedConnection)

    # ── Slot handlers ─────────────────────────────────────────────────────────

    def _on_loop_finished(self, goal: str):
        self.agent_event.emit("success", f"✅ Autonomous task completed: {goal}", "success")
        # Save success to workflow memory for future semantic retrieval
        if self._current_goal:
            plan = {"action": "autonomous", "goal": goal, "steps": []}
            self._wf_memory.save_workflow(self._current_goal, plan, success=True)
        self.task_finished.emit("Task completed autonomously!")
        self._agent_worker = None

    def _on_loop_error(self, error_msg: str):
        self.agent_event.emit("error", f"❌ Agent loop failed: {error_msg}", "error")
        self.task_error.emit(error_msg)
        self._agent_worker = None

    def _on_observation(self, obs):
        msg = (
            f"👁 Seen: {len(obs.buttons)} buttons, "
            f"{len(obs.inputs)} inputs. "
            f"Title: '{obs.title}'"
        )
        self.agent_event.emit("observation", msg, "info")

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def shutdown(self):
        if self._agent_worker:
            self._agent_worker.request_stop()
        self._browser_agent.close()
        self._browser_thread.quit()
        self._browser_thread.wait(3000)
