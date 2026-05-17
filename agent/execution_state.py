"""
agent/execution_state.py
------------------------
Tracks the full live state of a running autonomous agent session.
Each field is updated as the Observe→Think→Act loop progresses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Any
from enum import Enum
from .intervention import InterventionReason

class AgentStatus(Enum):
    IDLE                     = "idle"
    OBSERVING                = "observing"
    THINKING                 = "thinking"
    ACTING                   = "acting"
    WAITING                  = "waiting_for_clarification"
    PAUSED_HUMAN_INTERVENTION = "paused_human_intervention"
    RECOVERING               = "recovering"
    BLOCKED                  = "blocked"
    COMPLETED                = "completed"
    FAILED                   = "failed"
    STOPPED                  = "stopped"


@dataclass
class ActionRecord:
    """Immutable snapshot of one completed Observe→Think→Act cycle."""
    iteration:   int
    observation: str
    reasoning:   str
    command:     str
    argument:    str
    confidence:  float
    success:     bool
    timestamp:   str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ExecutionState:
    """
    Single source of truth for an active agent task.
    Passed into the AgentLoop and ActionDecider on every iteration.
    """
    # ── Core Goal ──────────────────────────────────────────────────────────────
    goal: str

    # ── Progress Tracking ──────────────────────────────────────────────────────
    status: AgentStatus = AgentStatus.IDLE
    iteration: int = 0
    consecutive_failures: int = 0
    subgoals: list = field(default_factory=list)
    current_subgoal_index: int = 0
    progress_percentage: float = 0.0
    session_id: str = "default_session"
    compressed_history: str = ""
    consecutive_malformed: int = 0

    # ── Latest Perception ──────────────────────────────────────────────────────
    latest_observation: str = ""
    page_title: str = ""
    current_url: str = ""

    # ── Latest Reasoning ───────────────────────────────────────────────────────
    latest_reasoning: str = ""
    latest_confidence: float = 1.0
    latest_command: str = ""
    latest_argument: str = ""

    # ── Human Intervention Flags ───────────────────────────────────────────────
    human_intervention_needed: bool = False
    intervention_reason: Optional[InterventionReason] = None
    intervention_timestamp: Optional[datetime] = None
    intervention_attempts: int = 0
    state_snapshot: Optional[dict] = None

    # ── Full History ───────────────────────────────────────────────────────────
    action_history: List[ActionRecord] = field(default_factory=list)
    failed_actions: List[str] = field(default_factory=list)
    recent_failed_actions: dict = field(default_factory=dict)

    # ── Safety ─────────────────────────────────────────────────────────────────
    emergency_stop: bool = False

    def record_failed_action(self, action_key: str, cooldown_duration_sec: int = 30):
        """Logs a failed action and schedules a cooldown timestamp."""
        now = datetime.utcnow().timestamp()
        if action_key not in self.recent_failed_actions:
            self.recent_failed_actions[action_key] = {
                "failures": 0,
                "cooldown_until": 0.0
            }
        self.recent_failed_actions[action_key]["failures"] += 1
        self.recent_failed_actions[action_key]["cooldown_until"] = now + cooldown_duration_sec

    def is_action_blacklisted(self, action_key: str) -> bool:
        """Determines if the action is currently under active cooling down blacklist."""
        if action_key not in self.recent_failed_actions:
            return False
        now = datetime.utcnow().timestamp()
        cooldown_until = self.recent_failed_actions[action_key].get("cooldown_until", 0.0)
        return now < cooldown_until

    def record_action(self, success: bool):
        """Commits the current Think result to history."""
        record = ActionRecord(
            iteration=self.iteration,
            observation=self.latest_observation,
            reasoning=self.latest_reasoning,
            command=self.latest_command,
            argument=self.latest_argument,
            confidence=self.latest_confidence,
            success=success,
        )
        self.action_history.append(record)
        if not success:
            self.consecutive_failures += 1
            self.failed_actions.append(f"{self.latest_command}({self.latest_argument})")
        else:
            self.consecutive_failures = 0

    def record_intervention(self, reason: str):
        """Commits the intervention block to history so the agent learns about the interruption."""
        record = ActionRecord(
            iteration=self.iteration,
            observation=self.latest_observation,
            reasoning=f"Agent loop paused for human intervention. Reason: {reason}",
            command="pause_for_intervention",
            argument=reason,
            confidence=self.latest_confidence,
            success=False,
        )
        self.action_history.append(record)

    def get_history_summary(self, last_n: int = 5) -> str:
        """Returns a compact text summary of the most recent actions for the LLM context window."""
        recent = self.action_history[-last_n:]
        if not recent:
            return "No actions taken yet."
        lines = []
        for r in recent:
            status_icon = "✅" if r.success else "❌"
            lines.append(
                f"{status_icon} [{r.iteration}] {r.command}({r.argument}) "
                f"[conf={r.confidence:.2f}] — {r.reasoning[:80]}"
            )
        return "\n".join(lines)

    def detect_stall(self) -> bool:
        """
        Detects if the agent is stuck in a stalled loop.
        A stall is defined as:
        - The last 3 actions are all 'observe', or
        - The exact same non-observe command + argument is repeated 3 times in a row.
        """
        if len(self.action_history) < 3:
            return False
        
        last_three = self.action_history[-3:]
        # Check for 3 consecutive observes
        if all(r.command == "observe" for r in last_three):
            return True
            
        # Check for 3 consecutive identical commands + arguments
        first = last_three[0]
        if all(r.command == first.command and r.argument == first.argument for r in last_three):
            return True
            
        return False
