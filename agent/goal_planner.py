import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple
from mistralai.client import Mistral
from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class SubGoal:
    title: str
    description: str
    status: str = "pending"  # pending, executing, completed, failed, blocked
    steps: List[dict] = field(default_factory=list)
    verification_condition: dict = field(default_factory=dict)
    confidence: float = 1.0
    verification_confidence: float = 1.0
    retry_count: int = 0
    retry_stability: int = 3  # default stability score
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SubGoal":
        return cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=data.get("status", "pending"),
            steps=data.get("steps", []),
            verification_condition=data.get("verification_condition", {}),
            confidence=data.get("confidence", 1.0),
            verification_confidence=data.get("verification_confidence", 1.0),
            retry_count=data.get("retry_count", 0),
            retry_stability=data.get("retry_stability", 3),
            summary=data.get("summary", "")
        )

PLANNER_SYSTEM_PROMPT = """You are ClickBit's Hierarchical Goal Planner.
Your job is to break down a high-level user automation goal into a shallow list of 3 to 6 sequential executable subgoals.
Avoid deeply nested planning trees. Prioritize concrete, actionable objectives.

For each subgoal, you must provide:
1. "title": A brief, user-friendly title (e.g., "Navigate to python.org").
2. "description": A short explanation of the subgoal's objective.
3. "steps": A list of browser command dictionaries in sequence.
   Standard browser commands:
     - {"command": "open_url", "argument": "url"}
     - {"command": "search", "argument": "query"}
     - {"command": "click_text", "argument": "text"}
     - {"command": "click_index", "argument": "n"}
     - {"command": "click_first_result", "argument": ""}
     - {"command": "type_text", "argument": "text"}
     - {"command": "observe", "argument": ""}
4. "verification_condition": Environment anchors to verify completion of this subgoal:
     - "url_contains": substring expected in URL (or null)
     - "text_contains": substring expected on page (or null)
     - "min_buttons": minimum visible buttons expected (integer)
     - "min_inputs": minimum visible inputs expected (integer)
     - "title_contains": substring expected in page title (or null)
5. "confidence": Estimate of success probability (0.0 to 1.0).

You must respond ONLY with a valid JSON object containing a "subgoals" list. No prose or markdown.

Example: "Download Python 3.11"
{
  "subgoals": [
    {
      "title": "Navigate to python.org",
      "description": "Navigate to Python home page",
      "steps": [
        {"command": "open_url", "argument": "https://www.python.org"}
      ],
      "verification_condition": {
        "url_contains": "python.org",
        "text_contains": "Downloads",
        "min_buttons": 3,
        "min_inputs": 0,
        "title_contains": "Python"
      },
      "confidence": 0.95
    },
    {
      "title": "Locate downloads page",
      "description": "Click the downloads button to access download page",
      "steps": [
        {"command": "click_text", "argument": "Downloads"}
      ],
      "verification_condition": {
        "url_contains": "downloads",
        "text_contains": "Active Releases",
        "min_buttons": 5,
        "min_inputs": 0,
        "title_contains": "Download"
      },
      "confidence": 0.90
    },
    {
      "title": "Find Python 3.11 release page",
      "description": "Search or click Python 3.11 release version",
      "steps": [
        {"command": "click_text", "argument": "Python 3.11"}
      ],
      "verification_condition": {
        "url_contains": "3.11",
        "text_contains": "Release Notes",
        "min_buttons": 2,
        "min_inputs": 0,
        "title_contains": "3.11"
      },
      "confidence": 0.85
    }
  ]
}
"""

REPLAN_SYSTEM_PROMPT = """You are ClickBit's Hierarchical Goal Planner.
An existing execution roadmap has failed at a specific subgoal.
You must dynamically replan and repair the remaining branches of the workflow starting from the failed branch.
DO NOT regenerate completed subgoals. Preserve successful progress!

You are provided with:
1. The overall task goal.
2. The list of completed subgoals (as history).
3. The failed subgoal index, the page's current observation, and why it failed.
4. The remaining subgoals.

Regenerate and correct ONLY the failed subgoal and subsequent subgoals to bypass the obstacle.
Maintain the shallow 3-6 subgoal structure constraint.

You must respond ONLY with a valid JSON object containing a "subgoals" list matching the same schema as standard decomposition.
"""

class GoalPlanner:
    def __init__(self, model: str = "mistral-small-latest"):
        self._api_key = os.getenv("MISTRAL_API_KEY", "")
        self._client = Mistral(api_key=self._api_key)
        self._model = os.getenv("MISTRAL_MODEL", model)

    def decompose(self, goal: str) -> List[SubGoal]:
        """Decomposes the high-level user goal into 3-6 shallow subgoals."""
        logger.info(f"[GoalPlanner] Decomposing goal: {goal!r}")
        try:
            messages = [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": f"Decompose this goal into 3-6 subgoals: {goal}"}
            ]
            response = self._client.chat.complete(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            subgoals_data = data.get("subgoals", [])
            
            # Enforce 3-6 subgoals count cap
            subgoals_data = subgoals_data[:6]
            if len(subgoals_data) < 3:
                # pad or keep as is if short but at least 1
                pass
                
            subgoals = [SubGoal.from_dict(s) for s in subgoals_data]
            logger.info(f"[GoalPlanner] Created roadmap with {len(subgoals)} subgoals.")
            return subgoals
        except Exception as e:
            logger.error(f"[GoalPlanner] Decomposition failed: {e}. Falling back to default plan.")
            # Resilient fallback plan
            return [
                SubGoal(
                    title=f"Complete: {goal}",
                    description=goal,
                    steps=[{"command": "observe", "argument": ""}],
                    verification_condition={"text_contains": goal}
                )
            ]

    def replan(self, goal: str, current_subgoals: List[SubGoal], failed_index: int, last_observation: str) -> List[SubGoal]:
        """Regenerates remaining plan branches starting from failed_index, preserving completed subgoals."""
        logger.warning(f"[GoalPlanner] Replanning triggered at subgoal index {failed_index} for goal: {goal}")
        
        # 1. Split completed vs remaining
        completed_list = current_subgoals[:failed_index]
        failed_subgoal = current_subgoals[failed_index]
        
        history_desc = "\n".join([f"- [COMPLETED] {s.title}: {s.description}" for s in completed_list])
        remaining_desc = "\n".join([f"- [PENDING] {s.title}: {s.description}" for s in current_subgoals[failed_index:]])
        
        prompt = f"""
Overall Goal: {goal}
Completed Steps History:
{history_desc or "None"}

Failed Subgoal (Index {failed_index}): {failed_subgoal.title}
Failed Subgoal Description: {failed_subgoal.description}
Page Observation on Failure: {last_observation[:1000]}

Remaining Unfinished Subgoals Roadmap:
{remaining_desc}

Regenerate a new workflow starting from index {failed_index} to bypass this failure. Return ONLY valid JSON format.
"""
        try:
            messages = [
                {"role": "system", "content": REPLAN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            response = self._client.chat.complete(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            new_subgoals_data = data.get("subgoals", [])
            new_subgoals = [SubGoal.from_dict(s) for s in new_subgoals_data]
            
            # Combine completed + newly replanned remaining subgoals
            combined = completed_list + new_subgoals
            # Ensure shallow subgoal hierarchy cap
            combined = combined[:6]
            
            logger.info(f"[GoalPlanner] Replan complete. New total subgoals: {len(combined)}")
            return combined
        except Exception as e:
            logger.error(f"[GoalPlanner] Replanning failed: {e}. Reverting to original remaining roadmap.")
            # Recover by just resetting retry count of failed subgoal
            failed_subgoal.retry_count = 0
            return current_subgoals

    def verify_subgoal(self, subgoal: SubGoal, obs: dict) -> Tuple[bool, float]:
        """Evaluates environment anchors against current browser page state observation."""
        cond = subgoal.verification_condition
        if not cond:
            return True, 1.0

        total_anchors = 0
        matched_anchors = 0

        # Anchor 1: URL expectation
        url_target = cond.get("url_contains")
        if url_target:
            total_anchors += 1
            if url_target.lower() in obs.get("url", "").lower():
                matched_anchors += 1

        # Anchor 2: Visible text expectation
        text_target = cond.get("text_contains")
        if text_target:
            total_anchors += 1
            if text_target.lower() in obs.get("text", "").lower():
                matched_anchors += 1

        # Anchor 3: Expected interactive buttons count
        min_btn = cond.get("min_buttons")
        if min_btn is not None:
            total_anchors += 1
            if obs.get("button_count", 0) >= int(min_btn):
                matched_anchors += 1

        # Anchor 4: Expected interactive inputs count
        min_inp = cond.get("min_inputs")
        if min_inp is not None:
            total_anchors += 1
            if obs.get("input_count", 0) >= int(min_inp):
                matched_anchors += 1

        # Anchor 5: Page-title hints
        title_target = cond.get("title_contains")
        if title_target:
            total_anchors += 1
            if title_target.lower() in obs.get("title", "").lower():
                matched_anchors += 1

        if total_anchors == 0:
            return True, 1.0

        score = matched_anchors / total_anchors
        # Verify if 75% or more anchors are met
        verified = (score >= 0.75)
        
        logger.info(f"[GoalPlanner] Verification anchor check for '{subgoal.title}': {matched_anchors}/{total_anchors} matched. Verified={verified}")
        return verified, score

    def compress_roadmap(self, subgoals: List[SubGoal]) -> str:
        """Compresses completed subgoals into a compact historical string for the decider context."""
        compressed = []
        for i, s in enumerate(subgoals):
            if s.status == "completed":
                summary_text = s.summary if s.summary else s.description
                compressed.append(f"✅ Subgoal {i+1} [{s.title}]: Completed successfully. ({summary_text})")
            elif s.status == "executing":
                compressed.append(f"⚡ Subgoal {i+1} [{s.title}]: ACTIVE - {s.description}")
            else:
                compressed.append(f"⏳ Subgoal {i+1} [{s.title}]: Pending - {s.description}")
        return "\n".join(compressed)

    def save_snapshot(self, session_id: str, subgoals: List[SubGoal], current_index: int, goal: str):
        """Saves a progress snapshot to tmp/roadmaps/{session_id}.json for crash-safe resume."""
        try:
            os.makedirs("tmp/roadmaps", exist_ok=True)
            path = f"tmp/roadmaps/{session_id}.json"
            snapshot = {
                "goal": goal,
                "current_subgoal_index": current_index,
                "subgoals": [s.to_dict() for s in subgoals]
            }
            with open(path, "w") as f:
                json.dump(snapshot, f, indent=2)
            logger.info(f"[GoalPlanner] Saved progress snapshot to {path}")
        except Exception as e:
            logger.error(f"[GoalPlanner] Snapshot saving failed: {e}")

    def load_snapshot(self, session_id: str) -> Optional[dict]:
        """Loads a progress snapshot from tmp/roadmaps/{session_id}.json."""
        path = f"tmp/roadmaps/{session_id}.json"
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            subgoals_list = [SubGoal.from_dict(s) for s in data.get("subgoals", [])]
            return {
                "goal": data.get("goal", ""),
                "current_subgoal_index": data.get("current_subgoal_index", 0),
                "subgoals": subgoals_list
            }
        except Exception as e:
            logger.error(f"[GoalPlanner] Failed to load snapshot: {e}")
            return None
