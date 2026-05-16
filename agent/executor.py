"""
agent/executor.py
------------------
[BEGINNER GUIDE]
What is this file?
This is the "Brain Stem" of ClickBit. It connects all the pieces together.
When you type a command, the UI sends it here. This file then:
  1. Asks the Planner (AI) for a plan.
  2. Shows you the plan to get your approval.
  3. Sends the approved plan to the BrowserAgent (the Hands) to actually click buttons.

Why is this file so big?
Because it handles "Threads". If we did all the heavy AI thinking and web browsing
on the main thread, the app would freeze and stop responding to your clicks.
So, the Executor creates "Worker Threads" that run in the background.
"""

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from agent.planner import Planner, SYSTEM_PROMPT
from agent.router import Router
from agent.memory import Memory
from agent.workflow_memory import WorkflowMemory
from automation.browser_agent import BrowserAgent
from automation.desktop_agent import DesktopAgent
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Planning Worker ───────────────────────────────────────────────────────────

class PlanningWorker(QObject):
    """
    [BEGINNER GUIDE]
    A "Worker" is like a mini-program that runs in the background.
    This specific worker's only job is to talk to the AI (Mistral) and get a plan.
    It uses "Signals" (finished, error) to tell the main program when it's done.
    """
    finished = pyqtSignal(dict) # Sent when a plan is successfully created
    error = pyqtSignal(str)     # Sent if something goes wrong (no internet, API error)

    def __init__(self, prompt: str, router: Router, planner: Planner, wf_memory: WorkflowMemory):
        super().__init__()
        self.prompt = prompt
        self.router = router
        self.planner = planner
        self.wf_memory = wf_memory

    @pyqtSlot()
    def run(self):
        """This runs automatically when the background thread starts."""
        try:
            # 1. Check Memory First (Did we already solve this problem before?)
            cached_plan = self.wf_memory.get_cached_plan(self.prompt)
            if cached_plan:
                logger.info(f"Memory HIT for '{self.prompt}'. Validating cached workflow...")
                
                # REPAIR LAYER: Check if our old memory is still a good plan
                repaired_plan = self.planner.validate_and_fix(self.prompt, cached_plan)
                
                # If we fixed it, save the better version!
                if repaired_plan != cached_plan:
                    logger.info("Cache Auto-Fix applied to legacy workflow. Updating memory.")
                    self.wf_memory.save_workflow(self.prompt, repaired_plan, success=True)
                
                # Tell the main program: "Hey, I have a plan ready!"
                self.finished.emit(repaired_plan)
                return

            # 2. Decide route (Local AI vs Cloud AI)
            decision = self.router.get_routing_decision(self.prompt)
            plan = None
            if decision == "local":
                plan = self.router.get_local_plan(self.prompt, SYSTEM_PROMPT)
            
            # 3. Fallback to Cloud AI (Mistral) if local fails or isn't used
            if not plan:
                logger.info("Using CLOUD (Mistral) for new plan...")
                plan = self.planner.plan(self.prompt)
            
            # Tell the main program: "Hey, I have a new plan ready!"
            self.finished.emit(plan)
        except Exception as e:
            # Tell the main program: "Oops, something broke."
            self.error.emit(str(e))

# ── Execution Worker ──────────────────────────────────────────────────────────

class ExecutionWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, prompt: str, plan: dict, browser_agent: BrowserAgent, desktop_agent: DesktopAgent, wf_memory: WorkflowMemory):
        super().__init__()
        self.prompt = prompt
        self.plan = plan
        self.browser_agent = browser_agent
        self.desktop_agent = desktop_agent
        self.wf_memory = wf_memory

    @pyqtSlot()
    def run(self):
        action = self.plan.get("action", "unknown")
        steps = self.plan.get("steps", [])
        try:
            if action == "browser":
                self.browser_agent.execute(steps)
            elif action == "desktop":
                self.desktop_agent.execute(steps)
            else:
                self.error.emit(f"Unknown action: {action}")
                return
            
            # Save successful workflow to memory
            self.wf_memory.save_workflow(self.prompt, self.plan, success=True)
            self.finished.emit("Task completed successfully")
        except Exception as e:
            self.error.emit(str(e))

# ── Executor ──────────────────────────────────────────────────────────────────

class Executor(QObject):
    task_started = pyqtSignal(str)
    confirmation_required = pyqtSignal(dict)
    task_finished = pyqtSignal(str)
    task_error = pyqtSignal(str)
    
    # Dashboard Signal: event_type, message, status
    agent_event = pyqtSignal(str, str, str)

    request_browser_execution = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._memory = Memory()
        self._router = Router()
        self._planner = Planner(memory=self._memory)
        self._wf_memory = WorkflowMemory()
        
        self._browser_thread = QThread()
        self._browser_agent = BrowserAgent(headless=False)
        self._browser_agent.moveToThread(self._browser_thread)
        self._browser_thread.start()
        
        self.request_browser_execution.connect(self._browser_agent.execute)
        self._browser_agent.action_finished.connect(self._on_execution_finished)
        self._browser_agent.action_error.connect(self._on_execution_error)
        self._browser_agent.status_message.connect(lambda msg: self.agent_event.emit("action", msg, "info"))
        
        self._desktop_agent = DesktopAgent()
        
        self._planning_thread = None
        self._execution_thread = None
        self._pending_plan = None
        self._current_prompt = None
        logger.info("Executor ready (Timeline Enabled)")

    @pyqtSlot(str)
    def handle_task(self, prompt: str):
        """
        [BEGINNER GUIDE]
        This is called the moment you press "Enter" in the UI.
        It starts the whole process.
        """
        # Make sure we aren't already busy thinking about another task
        if (self._planning_thread and self._planning_thread.isRunning()):
            self.task_error.emit("A task is already running.")
            return

        self._current_prompt = prompt
        self.task_started.emit(prompt) # Tell the UI to show "Planning..."
        self.agent_event.emit("info", f"New Task: {prompt}", "info")
        
        # Check Memory First
        cached = self._wf_memory.get_cached_plan(prompt)
        if cached:
            self.agent_event.emit("memory", "Cache HIT: Validating workflow...", "success")
            
        # ── CREATE A BACKGROUND THREAD ──
        # We put the "Planner" into a background thread so the app doesn't freeze
        self._planning_thread = QThread()
        self._planner_worker = PlanningWorker(prompt, self._router, self._planner, self._wf_memory)
        
        # Move the worker into the new thread
        self._planner_worker.moveToThread(self._planning_thread)
        
        # Connect the "wires": when thread starts, run the worker
        self._planning_thread.started.connect(self._planner_worker.run)
        # When worker finishes, call _on_plan_ready
        self._planner_worker.finished.connect(self._on_plan_ready)
        self._planner_worker.error.connect(self.task_error)
        
        self.agent_event.emit("planning", "🧠 Planning workflow...", "info")
        
        # Cleanup: when thread finishes, delete it from memory to prevent leaks
        self._planning_thread.finished.connect(lambda: setattr(self, "_planning_thread", None))
        self._planning_thread.finished.connect(self._planning_thread.deleteLater)
        
        # Finally, press the "Start" button on the thread!
        self._planning_thread.start()

    def _on_plan_ready(self, plan: dict):
        self._pending_plan = plan
        steps_count = len(plan.get("steps", []))
        self.agent_event.emit("success", f"Plan Ready: {steps_count} steps.", "success")
        self.confirmation_required.emit(plan)
        if self._planning_thread:
            self._planning_thread.quit()

    @pyqtSlot()
    def approve_plan(self):
        if not self._pending_plan: return

        action = self._pending_plan.get("action", "unknown")
        steps = self._pending_plan.get("steps", [])
        self._active_plan = self._pending_plan # Capture for memory save

        self.agent_event.emit("action", f"Executing {action} workflow...", "info")

        if action == "browser":
            self.request_browser_execution.emit(steps)
        elif action == "desktop":
            # For desktop, we still use a small worker to ensure memory is saved
            self._execution_thread = QThread()
            self._exec_worker = ExecutionWorker(self._current_prompt, self._pending_plan, self._browser_agent, self._desktop_agent, self._wf_memory)
            self._exec_worker.moveToThread(self._execution_thread)
            self._execution_thread.started.connect(self._exec_worker.run)
            self._exec_worker.finished.connect(self.task_finished)
            self._exec_worker.error.connect(self.task_error)
            self._execution_thread.finished.connect(lambda: setattr(self, "_execution_thread", None))
            self._execution_thread.finished.connect(self._execution_thread.deleteLater)
            self._execution_thread.start()
        else:
            self.task_error.emit(f"Unknown action: {action}")
            self.agent_event.emit("error", f"Unknown action: {action}", "error")
        
        self._pending_plan = None

    def _on_execution_finished(self, msg: str):
        """Called when BrowserAgent finishes successfully."""
        self.agent_event.emit("success", "Workflow completed successfully! ✅", "success")
        if self._current_prompt and hasattr(self, "_active_plan") and self._active_plan:
            self._wf_memory.save_workflow(self._current_prompt, self._active_plan, success=True)
            self._active_plan = None
        self.task_finished.emit(msg)

    def _on_execution_error(self, err_msg: str):
        self.agent_event.emit("error", f"Execution Failed: {err_msg}", "error")
        self.task_error.emit(err_msg)

    @pyqtSlot()
    def reject_plan(self):
        self._pending_plan = None
        self.task_finished.emit("Task cancelled")

    def shutdown(self):
        if self._planning_thread:
            self._planning_thread.quit()
            self._planning_thread.wait(1000)
        self._browser_agent.close()
        self._browser_thread.quit()
        self._browser_thread.wait(2000)
