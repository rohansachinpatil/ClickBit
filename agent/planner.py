"""
agent/planner.py
-----------------
Parses natural language into structured JSON plans with a standardized action schema.
"""

import json
import os
from mistralai.client import Mistral
from agent.memory import Memory
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Standardized Action Schema in System Prompt ──────────────────────────────
SYSTEM_PROMPT = """You are ClickBit, a desktop automation assistant.
The user will give you a task. You must respond ONLY with valid JSON — no prose, no markdown.

JSON schema:
{
  "action": "browser" | "desktop" | "unknown",
  "steps": [
    {"command": "string", "argument": "string"},
    ...
  ]
}

Browser commands:
  - command: "open_url", argument: "url"
  - command: "search", argument: "query"
  - command: "click_text", argument: "text"
  - command: "click_index", argument: "n"
  - command: "click_first_result", argument: ""
  - command: "type_text", argument: "text"
  - command: "observe", argument: ""

CRITICAL RULES:
1. Steps MUST be objects with "command" and "argument" keys.
2. If the user says "play", "watch", or "listen", follow search with {"command": "click_first_result", "argument": ""}.
3. ALWAYS navigate to the site first using open_url.

Example: "Play trending Hindi songs on YouTube"
{
  "action": "browser",
  "steps": [
    {"command": "open_url", "argument": "https://www.youtube.com"},
    {"command": "search", "argument": "trending Hindi songs"},
    {"command": "click_first_result", "argument": ""}
  ]
}
"""

class Planner:
    def __init__(self, model: str = "mistral-small-latest", memory: Memory = None):
        self._api_key = os.getenv("MISTRAL_API_KEY")
        self._client = Mistral(api_key=self._api_key)
        self._model = os.getenv("MISTRAL_MODEL", model)
        logger.info(f"Planner ready (Structured Schema Enabled)")

    def plan(self, prompt: str) -> dict:
        """Calls Mistral AI and then validates/fixes the resulting plan."""
        logger.info(f"Planning (Structured): {prompt!r}")
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        response = self._client.chat.complete(
            model=self._model,
            messages=messages,
            response_format={"type": "json_object"}
        )
        
        plan = json.loads(response.choices[0].message.content)
        plan["version"] = 2  # Current schema version
        
        # Phase 2: Validation & Auto-Correction
        plan = self.validate_and_fix(prompt, plan)
        
        logger.info(f"Final Plan: {plan}")
        return plan

    def validate_and_fix(self, prompt: str, plan: dict) -> dict:
        """Detects and fixes missing steps using the structured schema."""
        if plan.get("action") != "browser": return plan
        steps = plan.get("steps", [])
        p_lower = prompt.lower()
        
        # 1. Normalize steps (convert any legacy strings to objects)
        normalized_steps = []
        for s in steps:
            if isinstance(s, str):
                cmd_part, _, arg_part = s.partition(":")
                normalized_steps.append({"command": cmd_part.strip().lower(), "argument": arg_part.strip()})
            else:
                normalized_steps.append(s)

        # 2. Playback Auto-Fix Logic
        playback_keywords = ["play", "watch", "listen"]
        if any(kw in p_lower for kw in playback_keywords):
            # Check if search exists but result selection is missing
            has_search = any(s.get("command") == "search" for s in normalized_steps)
            has_click = any(s.get("command", "").startswith("click_") for s in normalized_steps)
            
            if has_search and not has_click:
                logger.info(f"Auto-Fix: Adding missing 'click_first_result' for prompt '{prompt}'")
                normalized_steps.append({"command": "click_first_result", "argument": None})
        
        plan["steps"] = normalized_steps
        return plan
