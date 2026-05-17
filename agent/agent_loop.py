"""
agent/agent_loop.py
-------------------
The autonomous Observe → Think → Act orchestration engine.

Runs in a background QThread.  On each iteration it:
  1. OBSERVE  – asks BrowserAgent for a live DOM + page snapshot
  2. THINK    – calls ActionDecider to produce one structured next action
  3. EMIT     – broadcasts reasoning / confidence to the Debug Panel in real time
  4. ACT      – executes the chosen action via BrowserAgent
  5. REPEAT   – loops until task_complete, max iterations, or emergency stop

Safety guards built in:
  - MAX_ITERATIONS        hard cap on loop cycles
  - MAX_CONSECUTIVE_FAILS hard cap on back-to-back failures
  - CONFIDENCE_THRESHOLD  pauses loop and asks for clarification if too uncertain
  - Emergency stop flag   can be set from any thread via request_stop()
"""

import time
import os

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from agent.execution_state import ExecutionState, AgentStatus
from automation.browser_agent import TransportError
from .intervention import InterventionReason
from datetime import datetime
from agent.action_decider   import ActionDecider
from agent.goal_planner     import GoalPlanner, SubGoal
from utils.logger           import get_logger

logger = get_logger(__name__)

# ── Safety Tuning ─────────────────────────────────────────────────────────────
MAX_ITERATIONS        = int(os.getenv("AGENT_MAX_ITERATIONS",        "30"))
MAX_CONSECUTIVE_FAILS = int(os.getenv("AGENT_MAX_CONSECUTIVE_FAILS", "4"))
CONFIDENCE_THRESHOLD  = float(os.getenv("AGENT_CONFIDENCE_THRESHOLD", "0.40"))
ACTION_DELAY_SEC      = float(os.getenv("AGENT_ACTION_DELAY_SEC",     "1.5"))


class AgentLoopWorker(QObject):
    """
    Runs in a dedicated QThread (created by Executor).

    Signals (all consumed by Executor → forwarded to UI):
      loop_event    (event_type, message, status)   – live feed for Debug Panel
      loop_finished (goal)                           – task completed successfully
      loop_error    (error_message)                  – unrecoverable failure
      clarification_needed (reasoning)               – confidence too low, ask user
      action_ready  (command, argument)              – a single action to execute
                                                       (picked up by BrowserAgent)
    """

    loop_event           = pyqtSignal(str, str, str)   # (type, message, status)
    loop_finished        = pyqtSignal(str)
    loop_error           = pyqtSignal(str)
    clarification_needed = pyqtSignal(str)
    action_ready         = pyqtSignal(str, str)        # (command, argument)

    def __init__(self, goal: str, browser_agent, parent=None):
        super().__init__(parent)
        self._goal           = goal
        self._browser_agent  = browser_agent
        self._browser_agent.status_message.connect(self._handle_status_message)
        self._decider        = ActionDecider()
        self._state          = ExecutionState(goal=goal)
        self._goal_planner   = GoalPlanner()
        self._waiting        = False   # True while waiting for clarification reply
        self._waiting_intervention = False # True while waiting for human intervention

    # ── Public API ─────────────────────────────────────────────────────────────

    def request_stop(self):
        """Thread-safe stop request. Can be called from the main thread."""
        self._state.emergency_stop = True
        logger.warning("[AgentLoop] Emergency stop requested.")

    def resume_after_clarification(self, user_hint: str = ""):
        """Resume the loop after the user answered a clarification prompt."""
        if user_hint:
            # Inject user's hint as an extra context note
            self._state.latest_observation += f"\n\n[User hint]: {user_hint}"
        self._state.consecutive_failures = 0
        self._waiting = False

    def resume_intervention(self):
        """Resume loop after human intervention is resolved."""
        self._state.human_intervention_needed = False
        self._state.intervention_reason = None
        if self._state.state_snapshot:
            # Restore context to ensure smooth continuation
            self._state.iteration = self._state.state_snapshot.get("iteration", self._state.iteration)
            self._state.latest_confidence = self._state.state_snapshot.get("confidence", self._state.latest_confidence)
            self._state.latest_reasoning = self._state.state_snapshot.get("reasoning", self._state.latest_reasoning)
            self._state.latest_command = self._state.state_snapshot.get("command", self._state.latest_command)
        self._waiting_intervention = False

    # ── Main Loop ──────────────────────────────────────────────────────────────

    @pyqtSlot()
    def run(self):
        """Entry point — called when the QThread starts."""
        self._state.status = AgentStatus.OBSERVING
        self._emit("info", f"🚀 Starting autonomous task: {self._goal}", "info")

        # Initialize/Resume Goal Planning Roadmap
        snapshot = self._goal_planner.load_snapshot(self._state.session_id)
        if snapshot:
            self._state.goal = snapshot["goal"]
            self._state.subgoals = snapshot["subgoals"]
            self._state.current_subgoal_index = snapshot["current_subgoal_index"]
            self._emit("info", "🔄 Resumed unfinished task from progress snapshot.", "info")
        else:
            self._emit("planning", "📋 Decomposing goal into hierarchical subgoals...", "info")
            self._state.subgoals = self._goal_planner.decompose(self._goal)
            self._state.current_subgoal_index = 0

        self._update_progress()
        self._emit_roadmap()

        while True:
            # Check if we just recovered from a transport failure
            if getattr(self, "_transport_recovered", False):
                self._transport_recovered = False
                self._state.consecutive_failures = 0
                self._emit("info", "🔄 Restoring snapshot and performing fresh observation...", "info")
                # Go straight to OBSERVE without recording failure
                pass
            # ── Guard: emergency stop ─────────────────────────────────────────
            if self._state.emergency_stop:
                self._state.status = AgentStatus.STOPPED
                self._emit("info", "🛑 Emergency stop received.", "error")
                self.loop_error.emit("Emergency stop.")
                return

            # ── Guard: max iterations ─────────────────────────────────────────
            if self._state.iteration >= MAX_ITERATIONS:
                self._state.status = AgentStatus.FAILED
                self._emit("error", f"⚠️ Max iterations ({MAX_ITERATIONS}) reached.", "error")
                self.loop_error.emit(f"Exceeded maximum of {MAX_ITERATIONS} iterations.")
                return

            # ── Guard: too many consecutive failures ──────────────────────────
            if self._state.consecutive_failures >= MAX_CONSECUTIVE_FAILS:
                self._state.status = AgentStatus.FAILED
                msg = f"❌ {MAX_CONSECUTIVE_FAILS} consecutive failures. Aborting."
                self._emit("error", msg, "error")
                self.loop_error.emit(msg)
                return

            # ── Guard: check if all subgoals completed ──────────────────────────
            if self._state.current_subgoal_index >= len(self._state.subgoals):
                self._state.status = AgentStatus.COMPLETED
                self._emit("success", "✅ All planned subgoals achieved! Task complete.", "success")
                self.loop_finished.emit(self._goal)
                return

            subgoal = self._state.subgoals[self._state.current_subgoal_index]
            subgoal.status = "executing"
            self._emit_roadmap()

            self._state.iteration += 1
            self._emit("info", f"── Iteration {self._state.iteration} ──", "info")

            # ════════════════════════════════════════════════════════════════════
            # PHASE 1: OBSERVE
            # ════════════════════════════════════════════════════════════════════
            self._state.status = AgentStatus.OBSERVING
            self._emit("observation", "👁 Observing page...", "info")

            obs = self._get_observation()
            if getattr(self, "_transport_recovered", False):
                continue
            self._state.latest_observation = obs.get("text", "")
            self._state.page_title         = obs.get("title", "")
            self._state.current_url        = obs.get("url", "")

            obs_summary = (
                f"Title: '{self._state.page_title}' | "
                f"URL: {self._state.current_url} | "
                f"Buttons: {obs.get('button_count', 0)} | "
                f"Inputs: {obs.get('input_count', 0)}"
            )
            self._emit("observation", obs_summary, "info")

            # ── Guard: Human Intervention ─────────────────────────────────────
            if (obs.get("captcha_detected") or obs.get("auth_required") or 
                obs.get("permission_popup") or obs.get("modal_blocking_flow")):
                
                reason = obs.get("intervention_reason", "unknown")
                self._state.human_intervention_needed = True
                self._state.intervention_reason = reason
                self._state.intervention_attempts += 1
                
                if self._state.intervention_attempts > 3:
                    self._state.status = AgentStatus.FAILED
                    msg = f"❌ Max intervention attempts (3) exceeded for {reason}. Aborting."
                    self._emit("error", msg, "error")
                    self.loop_error.emit(msg)
                    return
                
                # Snapshot state
                self._state.state_snapshot = {
                    "iteration": self._state.iteration,
                    "confidence": self._state.latest_confidence,
                    "reasoning": self._state.latest_reasoning,
                    "command": self._state.latest_command
                }
                
                self._state.status = AgentStatus.PAUSED_HUMAN_INTERVENTION
                self._emit("human_intervention", f"🛑 Human verification required: {reason}", "error")
                self._state.record_intervention(reason)
                
                self._waiting_intervention = True
                while self._waiting_intervention and not self._state.emergency_stop:
                    time.sleep(0.5)
                
                if self._state.emergency_stop:
                    self._state.status = AgentStatus.STOPPED
                    self._emit("info", "🛑 Emergency stop received.", "error")
                    self.loop_error.emit("Emergency stop.")
                    return
                
                # User clicked Resume:
                self._state.status = AgentStatus.RECOVERING
                self._emit("info", "👤 User resumed task. 🔄 Re-observing...", "info")
                continue # Go back to start of loop to do a fresh observation

            # ════════════════════════════════════════════════════════════════════
            # PHASE 2: THINK
            # ════════════════════════════════════════════════════════════════════
            self._state.status = AgentStatus.THINKING
            
            # If subgoal has prepopulated/queued steps, pop and execute!
            if subgoal.steps:
                next_step = subgoal.steps.pop(0)
                cmd = next_step.get("command", "observe")
                arg = next_step.get("argument") or ""
                self._state.latest_command = cmd
                self._state.latest_argument = arg
                self._state.latest_reasoning = f"Executing planned step for subgoal: {subgoal.title}"
                self._state.latest_confidence = subgoal.confidence
                
                self._emit(
                    "planning",
                    f"💭 Executing planned step for subgoal: {subgoal.title} -> {cmd}({arg})",
                    "info"
                )
            else:
                # Ask Decider (Mistral) for the next action to accomplish the subgoal
                self._state.compressed_history = self._goal_planner.compress_roadmap(self._state.subgoals)
                
                if self._state.detect_stall():
                    self._emit("warning", "⚠️ Loop stall warning: Agent is repeating identical steps without progress.", "warning")
                self._emit("planning", f"🧠 Reasoning how to complete subgoal: {subgoal.title}...", "info")

                action = self._decider.decide(self._state)

                # Process Structured Output Reliability Pipeline Telemetry & Events
                if action.get("was_repaired"):
                    self._emit("json_repair", "🛠 Repaired malformed LLM JSON block.", "info")
                    
                if action.get("has_warnings"):
                    warnings = action.get("warnings", [])
                    if "Complete JSON parse failure." in warnings:
                        self._emit("malformed_output", "🧩 Complete parse failure! Safe fallback to observe.", "warning")
                        self._state.consecutive_malformed += 1
                        if self._state.consecutive_malformed >= 2:
                            self._emit("warning", f"⚠️ Consecutive malformed outputs ({self._state.consecutive_malformed}). Clearing reasoning cache.", "warning")
                            self._decider._cache.clear()
                    else:
                        for warn in warnings:
                            self._emit("schema_warning", f"⚠️ Schema Warning: {warn}", "warning")
                        self._state.consecutive_malformed = 0
                else:
                    self._state.consecutive_malformed = 0

                self._state.latest_reasoning  = action.get("reasoning",  "")
                self._state.latest_confidence = action.get("confidence", 0.5)
                self._state.latest_command    = action.get("command",    "observe")
                self._state.latest_argument   = action.get("argument",   "")

                self._emit(
                    "planning",
                    f"💭 {self._state.latest_reasoning} [conf={self._state.latest_confidence:.2f}]",
                    "info",
                )

            # ── Guard: low confidence ─────────────────────────────────────────
            if self._state.latest_confidence < CONFIDENCE_THRESHOLD:
                self._state.status = AgentStatus.WAITING
                msg = (
                    f"Confidence too low ({self._state.latest_confidence:.2f}). "
                    f"Reasoning: {self._state.latest_reasoning}"
                )
                self._emit("info", f"❓ Requesting clarification: {msg}", "info")
                self.clarification_needed.emit(msg)
                # Spin-wait (loop polls every 500ms) until resume_after_clarification() is called
                self._waiting = True
                while self._waiting and not self._state.emergency_stop:
                    time.sleep(0.5)
                continue

            # ════════════════════════════════════════════════════════════════════
            # PHASE 3: TERMINAL CHECK (task_complete)
            # ════════════════════════════════════════════════════════════════════
            if self._state.latest_command == "task_complete":
                self._run_verification_phase(subgoal, obs)
                time.sleep(ACTION_DELAY_SEC)
                continue

            # ════════════════════════════════════════════════════════════════════
            # PHASE 4: ACT
            # ════════════════════════════════════════════════════════════════════
            # Snapshot state right before action in case of transport failure
            self._state.state_snapshot = {
                "iteration": self._state.iteration,
                "confidence": self._state.latest_confidence,
                "reasoning": self._state.latest_reasoning,
                "command": self._state.latest_command
            }
            
            self._state.status = AgentStatus.ACTING
            cmd = self._state.latest_command
            arg = self._state.latest_argument
            self._emit("action", f"⚡ Executing: {cmd}({arg})", "info")

            success = self._execute_action(cmd, arg)
            
            if getattr(self, "_transport_recovered", False):
                # We crashed and recovered during the action phase. Do not record this action.
                continue

            self._state.record_action(success=success)

            if not success:
                self._emit("retry", f"⚠️ Action failed ({self._state.consecutive_failures}/{MAX_CONSECUTIVE_FAILS})", "error")
            
            # Throttle between iterations to behave human-like
            time.sleep(ACTION_DELAY_SEC)

    def _update_progress(self):
        total = len(self._state.subgoals)
        if total == 0:
            self._state.progress_percentage = 0.0
            return
        completed = sum(1 for s in self._state.subgoals if s.status == "completed")
        self._state.progress_percentage = (completed / total) * 100.0

    def _emit_roadmap(self):
        roadmap_str = self._goal_planner.compress_roadmap(self._state.subgoals)
        self._emit("plan_update", f"ROADMAP:{self._state.progress_percentage:.1f}%|{roadmap_str}", "info")

    def _run_verification_phase(self, subgoal, obs):
        self._emit("info", f"🔍 Verifying subgoal: {subgoal.title} against environment anchors...", "info")
        obs_dict = {
            "url": self._state.current_url,
            "title": self._state.page_title,
            "text": self._state.latest_observation,
            "button_count": obs.get("button_count", 0),
            "input_count": obs.get("input_count", 0)
        }
        verified, conf = self._goal_planner.verify_subgoal(subgoal, obs_dict)
        subgoal.verification_confidence = conf
        
        if verified:
            subgoal.status = "completed"
            subgoal.summary = f"Verified at {self._state.current_url} with confidence {conf:.2f}"
            self._emit("success", f"✅ Subgoal '{subgoal.title}' verified successfully!", "success")
            self._state.current_subgoal_index += 1
            self._state.consecutive_failures = 0
            
            # Save progress snapshot
            self._goal_planner.save_snapshot(
                self._state.session_id, 
                self._state.subgoals, 
                self._state.current_subgoal_index, 
                self._state.goal
            )
            
            self._update_progress()
            self._emit_roadmap()
        else:
            subgoal.retry_count += 1
            subgoal.retry_stability = max(0, subgoal.retry_stability - 1)
            self._emit("warning", f"⚠️ Subgoal '{subgoal.title}' verification failed (retry {subgoal.retry_count}/2)", "warning")
            
            # Deterministic recovery cascade before LLM replanning
            if subgoal.retry_count >= 2:
                subgoal.status = "failed"
                self._emit("warning", f"🔄 Subgoal repeatedly failed. Triggering dynamic replanning...", "warning")
                new_subgoals = self._goal_planner.replan(
                    self._state.goal, 
                    self._state.subgoals, 
                    self._state.current_subgoal_index, 
                    self._state.latest_observation
                )
                self._state.subgoals = new_subgoals
                self._update_progress()
                self._emit_roadmap()
            else:
                self._emit("info", "🔄 Running deterministic recovery: fresh observation & step retry...", "info")
                subgoal.steps = [{"command": "observe", "argument": ""}]

    # ── Internal Helpers ───────────────────────────────────────────────────────

    def _get_observation(self) -> dict:
        """Calls BrowserAgent synchronously to grab the live page state."""
        try:
            raw = self._browser_agent.get_current_observation()
            if raw is None:
                return {}
            # BrowserObservation → dict
            return {
                "title":        getattr(raw, "title", ""),
                "url":          getattr(raw, "url", ""),
                "text":         self._format_observation(raw),
                "button_count": len(getattr(raw, "buttons", [])),
                "input_count":  len(getattr(raw, "inputs", [])),
            }
        except TransportError as e:
            logger.warning(f"[AgentLoop] Transport recovery triggered during observation: {e}")
            self._handle_transport_recovery()
            return {"text": "Recovering transport layer...", "title": "", "url": ""}
        except Exception as e:
            logger.error(f"[AgentLoop] Observation failed: {e}")
            return {"text": f"Observation error: {e}", "title": "", "url": ""}

    def _format_observation(self, obs) -> str:
        """Aggressively compressed observation summary for low-latency LLM reasoning."""
        lines = []
        if getattr(obs, "buttons", []):
            btn_labels = [str(b) for b in obs.buttons[:5]] # Max 5 buttons
            lines.append(f"Buttons: {', '.join(btn_labels)}")
        if getattr(obs, "inputs", []):
            inp_labels = [str(i) for i in obs.inputs[:3]]  # Max 3 inputs
            lines.append(f"Inputs: {', '.join(inp_labels)}")
        return "\n".join(lines) if lines else "Page is empty."

    def _execute_action(self, command: str, argument: str) -> bool:
        """Delegates a single action to BrowserAgent and returns success/fail."""
        import json
        from agent.primitive_router import PrimitiveRouter
        from agent.transition_validator import TransitionValidator
        from automation.ui_state_engine import UIStateEngine

        # 0. Active Cooldown Check
        action_key = f"{command}:{argument}"
        if self._state.is_action_blacklisted(action_key):
            telemetry = {
                "event_type": "action_blacklisted",
                "payload": {
                    "action": f"{command}({argument})",
                    "reason": "Action is currently cooling down on the blacklist."
                }
            }
            self._emit("action_blacklisted", json.dumps(telemetry), "error")
            return False

        # 1. Overlay Detection & Automatic Recovery Cascade
        page = self._browser_agent.page
        if page:
            try:
                ui_state = UIStateEngine.inspect_page(page)
                if ui_state.overlay_open or ui_state.is_pointer_blocked:
                    telemetry = {
                        "event_type": "overlay_detected",
                        "payload": {
                            "blocking_element": ui_state.blocking_element,
                            "overlay_zindex": ui_state.overlay_zindex,
                            "viewport_coverage_percent": ui_state.viewport_coverage_percent
                        }
                    }
                    self._emit("overlay_detected", json.dumps(telemetry), "warning")
                    
                    # Attempt automatic recovery dismissals
                    recovered = UIStateEngine.dismiss_overlay(page)
                    if recovered:
                        telemetry_rec = {
                            "event_type": "overlay_recovered",
                            "payload": {
                                "method": "dismiss_overlay_cascade"
                            }
                        }
                        self._emit("overlay_recovered", json.dumps(telemetry_rec), "success")
                    else:
                        # If a standard action is about to run but pointer is blocked by overlay, fail/abort early
                        if not PrimitiveRouter.is_primitive(command) and command not in ("observe", "open_url"):
                            telemetry_block = {
                                "event_type": "blocked_interaction",
                                "payload": {
                                    "reason": f"Overlay '{ui_state.blocking_element}' could not be dismissed"
                                }
                            }
                            self._emit("blocked_interaction", json.dumps(telemetry_block), "error")
                            self._state.record_failed_action(action_key, cooldown_duration_sec=30)
                            return False
            except Exception as e:
                logger.error(f"[AgentLoop] Overlay detection/recovery failed: {e}")

        # 2. Deterministic Primitive Workflow routing
        if PrimitiveRouter.is_primitive(command):
            self._emit("primitive_intent", f"Executing deterministic primitive: {command}({argument})", "info")
            if not page:
                logger.error("[AgentLoop] Primitive execution failed: Playwright Page is inactive.")
                self._emit("primitive_failure", "Playwright page not ready.", "error")
                return False
            try:
                res = PrimitiveRouter.execute(page, command, argument)
                success = res.get("success", False)
                msg = res.get("message", "No message provided")
                if success:
                    self._emit("primitive_success", f"✅ {command} successful: {msg}", "success")
                    
                    # Emit primitive_executed structured telemetry
                    telemetry = {
                        "event_type": "primitive_executed",
                        "payload": {
                            "primitive": command,
                            "argument": argument,
                            "transition_score": 1.0,
                            "message": msg
                        }
                    }
                    self._emit("primitive_executed", json.dumps(telemetry), "success")
                else:
                    self._emit("primitive_failure", f"❌ {command} failed: {msg}", "error")
                return success
            except Exception as e:
                logger.error(f"[AgentLoop] Primitive action [{command}({argument})] crashed: {e}")
                self._emit("primitive_failure", f"Crash in primitive action: {e}", "error")
                return False

        # 3. Standard Action execution with Transition Validation
        try:
            before_snapshot = None
            if page:
                before_snapshot = TransitionValidator.take_snapshot(page)
                
            gen = self._browser_agent.get_session_generation()
            
            # Pointer safety check before performing standard interaction
            if page and command in ("click_text", "click_index", "click_first_result", "type_text", "search"):
                # We inspect pointer blockage again dynamically just in case
                ui_state_before = UIStateEngine.inspect_page(page)
                if ui_state_before.is_pointer_blocked and ui_state_before.blocking_element:
                    # Unless it's inside the overlay, it's blocked
                    is_safe = UIStateEngine.validate_interaction_safe(page, ui_state_before.blocker_selector or "body")
                    if not is_safe:
                        telemetry_block = {
                            "event_type": "blocked_interaction",
                            "payload": {
                                "reason": f"Pointer event for {command}({argument}) would be intercepted by '{ui_state_before.blocking_element}'"
                            }
                        }
                        self._emit("blocked_interaction", json.dumps(telemetry_block), "error")
                        self._state.record_failed_action(action_key, cooldown_duration_sec=30)
                        return False

            no_exception = self._browser_agent.execute_single_action(command, argument, expected_generation=gen)
            
            if getattr(self, "_transport_recovered", False):
                return False
                
            transition_score = 0.0
            if no_exception and page:
                after_snapshot = TransitionValidator.take_snapshot(page)
                if before_snapshot and after_snapshot:
                    transition_score = TransitionValidator.compute_transition_score(before_snapshot, after_snapshot)
                    self._emit("transition_score", f"Transition score: {transition_score:.2f} (command: {command})", "info")
            
            # success contract rule: meaningful state change for interaction elements
            is_interaction = command in ("click_text", "click_index", "click_first_result", "type_text", "search")
            if is_interaction:
                success = no_exception and (transition_score >= 0.15)
                
                # Interaction memory safety updates
                if success:
                    # Enforce transition_verified event
                    telemetry_verified = {
                        "event_type": "transition_verified",
                        "payload": {
                            "action": f"{command}({argument})",
                            "transition_score": transition_score
                        }
                    }
                    self._emit("transition_verified", json.dumps(telemetry_verified), "success")
                    
                    if self._browser_agent.selector_resolver:
                        logger.info("[AgentLoop] Transition verified! Reinforcing selector resolution.")
                        self._browser_agent.selector_resolver.reinforce_last_successful_resolution()
                else:
                    if self._browser_agent.selector_resolver:
                        logger.warning("[AgentLoop] Transition score below threshold! Purging selector resolution.")
                        self._browser_agent.selector_resolver.decay_last_successful_resolution()
                        
                    telemetry_ineffective = {
                        "event_type": "ineffective_action",
                        "payload": {
                            "action": f"{command}({argument})",
                            "transition_score": transition_score
                        }
                    }
                    self._emit("ineffective_action", json.dumps(telemetry_ineffective), "warning")
                    self._state.record_failed_action(action_key, cooldown_duration_sec=30)
            else:
                success = no_exception
                
            return success
            
        except TransportError as e:
            logger.warning(f"[AgentLoop] Transport recovery triggered during action: {e}")
            self._handle_transport_recovery()
            return False
        except Exception as e:
            logger.error(f"[AgentLoop] Action [{command}({argument})] failed: {e}")
            # If standard resolver execution or exception is thrown, also decay last successful resolution
            if self._browser_agent.selector_resolver:
                self._browser_agent.selector_resolver.decay_last_successful_resolution()
            return False

    def _handle_transport_recovery(self):
        """Restores context after a BrowserAgent transport failure to force a fresh cycle."""
        self._emit("info", "🔄 Transport recovered. Agent state rolling back...", "info")
        prev_url = self._state.current_url
        if self._state.state_snapshot:
            self._state.iteration = self._state.state_snapshot.get("iteration", self._state.iteration)
            self._state.latest_confidence = self._state.state_snapshot.get("confidence", self._state.latest_confidence)
            self._state.latest_reasoning = self._state.state_snapshot.get("reasoning", self._state.latest_reasoning)
            self._state.latest_command = self._state.state_snapshot.get("command", self._state.latest_command)
        
        # Restore navigation if we had a previous URL
        if prev_url and prev_url != "about:blank" and not prev_url.startswith("data:"):
            self._emit("info", f"🌐 Restoring navigation to previous URL: {prev_url}", "info")
            try:
                self._browser_agent.restore_url(prev_url)
            except Exception as e:
                logger.error(f"[AgentLoop] Failed to restore previous URL {prev_url}: {e}")
                
        self._state.status = AgentStatus.RECOVERING
        self._transport_recovered = True

    def _emit(self, event_type: str, message: str, status: str):
        """Convenience wrapper for the loop_event signal."""
        self.loop_event.emit(event_type, message, status)

    def _handle_status_message(self, msg: str):
        if msg.startswith("SELECTOR_RESOLUTION:"):
            clean_msg = msg.replace("SELECTOR_RESOLUTION:", "").strip()
            self._emit("selector_resolution", clean_msg, "info")
        else:
            self._emit("info", msg, "info")
