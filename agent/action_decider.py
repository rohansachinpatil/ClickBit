"""
agent/action_decider.py
-----------------------
The "Think" phase of the Observe→Think→Act loop.

Given the current ExecutionState (goal, history, live observation),
it calls Mistral to generate exactly ONE next action as a structured JSON object.

Output contract:
{
  "reasoning":  str,   # Internal monologue explaining WHY this action was chosen
  "confidence": float, # 0.0–1.0, agent's certainty this action moves toward the goal
  "command":    str,   # One of the known BrowserAgent commands, or "task_complete"
  "argument":   str    # Argument for the command
}
"""

import json
import os
import re
from agent.execution_state import ExecutionState
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Safety: forbidden domains and commands ────────────────────────────────────
FORBIDDEN_DOMAINS = [
    "bank", "paypal", "wallet", "payment", "checkout", "signin",
    "admin", "root", "ssh", "localhost",
]
FORBIDDEN_COMMANDS = ["delete", "rm", "format", "shutdown", "kill"]

KNOWN_COMMANDS = [
    "open_url", "search", "click_text", "click_index",
    "click_first_result", "type_text", "observe", "task_complete",
    "youtube_search", "google_search", "play_first_video", "dismiss_overlay", "close_modal"
]

DECIDER_SYSTEM_PROMPT = """You are the reasoning core of an autonomous AI browser agent.
You receive the agent's current goal, what it has done so far, and what it currently sees on screen.
You must decide the single BEST next action to take.

Return ONLY a valid JSON object with these exact keys:
{
  "reasoning":  "<your internal thought process, 1-2 sentences>",
  "confidence": <float 0.0 to 1.0>,
  "command":    "<one of: open_url, search, click_text, click_index, click_first_result, type_text, observe, task_complete, youtube_search, google_search, play_first_video, dismiss_overlay>",
  "argument":   "<argument for the command, or empty string>"
}

Valid Commands:
- "open_url": navigates to a URL (e.g. argument "youtube.com")
- "search": types and searches query in active page input
- "click_text": clicks an element matching specific text
- "click_index": clicks an element by its index number
- "type_text": types text into an input box
- "observe": re-inspects active page state
- "task_complete": goal fully achieved
- "youtube_search": deterministically searches youtube for query (argument: query)
- "google_search": deterministically searches google for query (argument: query)
- "play_first_video": plays the first video in the results view
- "dismiss_overlay": resiliently dismisses any blocking popup, cookie manager, modal, or scrim

Rules:
- Prefer deterministic high-level commands like "youtube_search", "google_search", "play_first_video", and "dismiss_overlay" when relevant to speed up and stabilize workflows.
- Do NOT choose any action listed under the ACTIVE COOLDOWN blacklist.
- Do NOT repeat the exact same failed action from history.
- Keep "argument" concise and precise.
"""


class ActionDecider:
    """
    Calls Mistral to reason about the ExecutionState and return one structured action.
    Thread-safe: stateless — all context is passed in via ExecutionState.
    """

    def __init__(self):
        self._api_key = os.getenv("MISTRAL_API_KEY", "")
        self._model = "mistral-small-latest"  # Fast model for tight reasoning loops
        self._cache = {}  # LRU reasoning cache

    def decide(self, state: ExecutionState) -> dict:
        """
        Core reasoning call. Returns a parsed action dict.
        Applies heuristics, checks cache, then falls back to LLM with 8s hard timeout.
        """
        # 1. Heuristic Fast-Path
        heuristic = self._apply_heuristics(state)
        if heuristic:
            logger.info("[ActionDecider] Heuristic triggered. Bypassing LLM.")
            return heuristic

        # 1.5 Avoid reasoning on empty observations
        obs_clean = state.latest_observation.strip()
        if not obs_clean or obs_clean == "Page is empty.":
            logger.info("[ActionDecider] Empty observation detected. Skipping LLM call and observing.")
            return {
                "reasoning": "Page content is empty. Observing page to reload content.",
                "confidence": 0.9,
                "command": "observe",
                "argument": ""
            }

        # 2. Stall check & cache management
        is_stalled = state.detect_stall()
        if is_stalled:
            logger.warning("[ActionDecider] Stall detected! Clearing reasoning cache to force new actions.")
            self._cache.clear()

        # Cache Check (if not stalled)
        cache_key = hash(f"{state.goal}_{state.page_title}_{state.latest_observation}")
        if not is_stalled and cache_key in self._cache:
            logger.info("[ActionDecider] Reasoning cache HIT. Bypassing LLM.")
            return self._cache[cache_key]

        # 3. LLM Call
        try:
            import httpx

            user_message = self._build_user_message(state)
            logger.debug(f"[ActionDecider] Calling Mistral for iteration {state.iteration}...")

            response = httpx.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": DECIDER_SYSTEM_PROMPT},
                        {"role": "user",   "content": user_message},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 150, # Reduced max tokens for faster TTFB
                },
                timeout=8.0, # Hard timeout at 8 seconds
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"].strip()
            
            parsed = self._parse_and_validate(raw, state, prompt=user_message)
            
            # Save successful reasoning to cache
            if parsed["command"] != "observe":
                self._cache[cache_key] = parsed
            return parsed

        except httpx.ReadTimeout:
            logger.warning("[ActionDecider] Mistral 8s hard timeout reached. Falling back to deterministic heuristic.")
            return {
                "reasoning": "LLM timeout. Observing to refresh state.",
                "confidence": 0.4,
                "command": "observe",
                "argument": "",
            }
        except Exception as e:
            logger.error(f"[ActionDecider] Mistral call failed: {e}")
            return {
                "reasoning": f"API error. Observing.",
                "confidence": 0.3,
                "command": "observe",
                "argument": "",
            }

    # ── Private Helpers ────────────────────────────────────────────────────────
    
    def _apply_heuristics(self, state: ExecutionState) -> dict:
        """Lightweight rules to bypass the LLM for obvious situations."""
        goal_lower = state.goal.lower()
        obs_lower = state.latest_observation.lower()
        
        # Heuristic 1: If searching and a search input is visible
        if "search" in goal_lower and "q" in obs_lower:
            # Extract the actual query (naive extraction)
            query = state.goal.split("search for", 1)[-1].strip() if "search for" in goal_lower else state.goal
            if "on " in query: query = query.split("on ")[0].strip()
            
            # Avoid repeating exactly
            if f"type_text({query})" not in state.failed_actions[-3:]:
                return {
                    "reasoning": "Search bar detected. Fast-pathing query typing.",
                    "confidence": 0.95,
                    "command": "search",
                    "argument": query
                }
                
        # Heuristic 2: If starting fresh on a blank page
        if not state.page_title and not state.latest_observation.strip() and state.iteration == 1:
            if "youtube" in goal_lower:
                return {"reasoning": "Goal implies YouTube. Fast-pathing navigation.", "confidence": 0.99, "command": "open_url", "argument": "youtube.com"}
            elif "chatgpt" in goal_lower:
                return {"reasoning": "Goal implies ChatGPT. Fast-pathing navigation.", "confidence": 0.99, "command": "open_url", "argument": "chatgpt.com"}
            elif "google" in goal_lower:
                return {"reasoning": "Goal implies Google. Fast-pathing navigation.", "confidence": 0.99, "command": "open_url", "argument": "google.com"}

        return None

    def _build_user_message(self, state: ExecutionState) -> str:
        """Ultra-compact prompt containing ONLY strictly necessary context."""
        history = state.get_history_summary(last_n=3) # Limit to 3 actions
        
        warning_msg = ""
        if state.detect_stall():
            last_action = state.action_history[-1]
            warning_msg = (
                f"\n⚠️ SYSTEM WARNING: You are stuck in a stalled loop repeating the action '{last_action.command}({last_action.argument})'. "
                "Your previous actions failed to advance the page state. You MUST choose a DIFFERENT action, a different text selector, "
                "or navigate/search differently. DO NOT repeat your last action!\n"
            )
            
        blacklist_msg = ""
        if getattr(state, "recent_failed_actions", None):
            import time
            now = time.time()
            cooling_down = []
            for act_key, data in state.recent_failed_actions.items():
                if now < data.get("cooldown_until", 0.0):
                    cooling_down.append(act_key)
            if cooling_down:
                blacklist_msg = f"\n⚠️ ACTIVE BLACKLIST COOLDOWN (DO NOT CHOOSE ANY OF THESE ACTIONS):\n" + "\n".join(f"- {act}" for act in cooling_down) + "\n"
            
        roadmap_context = ""
        if getattr(state, "compressed_history", ""):
            roadmap_context = f"ROADMAP STATUS:\n{state.compressed_history}\n\n"

        return (
            f"GOAL: {state.goal}\n"
            f"{roadmap_context}"
            f"PAGE TITLE: {state.page_title}\n\n"
            f"WHAT I SEE NOW:\n{state.latest_observation}\n\n"
            f"{warning_msg}"
            f"{blacklist_msg}"
            f"LAST 3 ACTIONS:\n{history}\n\n"
            "Respond with JSON only."
        )

    def _parse_and_validate(self, raw: str, state: ExecutionState, prompt: str = "") -> dict:
        """Extracts, parses, and safety-validates the JSON returned by Mistral."""
        logger.info(f"[StructuredOutputPipeline] [RAW LLM OUTPUT]:\n{raw}")
        
        from utils.json_repair import safe_parse_json, validate_action_schema, persist_malformed_output
        
        parsed_dict, was_repaired, repaired_str = safe_parse_json(raw, prompt=prompt)
        
        if parsed_dict is not None:
            logger.info(f"[StructuredOutputPipeline] [EXTRACTED JSON]:\n{repaired_str}")
            if was_repaired:
                logger.info(f"[StructuredOutputPipeline] [REPAIRED JSON]:\n{repaired_str}")
                
            validated, warnings = validate_action_schema(parsed_dict)
            
            validated["has_warnings"] = bool(warnings)
            validated["warnings"] = warnings
            validated["was_repaired"] = was_repaired
            validated["raw_output"] = raw
            
            # Persist if repaired or has schema warnings
            if was_repaired or warnings:
                persist_malformed_output(prompt, raw, repaired_str, validated)
                
            logger.info(f"[StructuredOutputPipeline] [VALIDATED ACTION]:\n{json.dumps(validated)}")
            
            # Safety: block forbidden domains in URLs
            if validated["command"] == "open_url":
                for blocked in FORBIDDEN_DOMAINS:
                    if blocked in validated["argument"].lower():
                        logger.warning(f"[ActionDecider] Forbidden domain blocked: {validated['argument']}")
                        validated["command"] = "observe"
                        validated["reasoning"] = f"Blocked navigation to forbidden domain: {validated['argument']}"
                        
            # Blacklist Cooldown enforcement
            action_sig = f"{validated['command']}({validated['argument']})"
            action_key = f"{validated['command']}:{validated['argument']}"
            if state.is_action_blacklisted(action_key):
                logger.warning(f"[ActionDecider] Blacklist cooldown hit: blocking {action_key}")
                validated["command"]   = "observe"
                validated["argument"]  = ""
                validated["reasoning"] = f"Blacklist protection: action '{action_sig}' is currently cooling down. Observing instead."
                validated["confidence"] = 0.2
            elif action_sig in state.failed_actions[-3:]:
                # Loop protection fallback
                logger.warning(f"[ActionDecider] Loop protection: blocking repeated failed action {action_sig}")
                validated["command"]   = "observe"
                validated["argument"]  = ""
                validated["reasoning"] = f"Loop guard: avoiding repeated failure of {action_sig}. Observing instead."
                validated["confidence"] = 0.3
                
            return validated
        else:
            # Complete parse failure!
            logger.error("[StructuredOutputPipeline] All repair passes failed. Activating safe fallback.")
            fallback = {
                "reasoning": "Structured output repair failed",
                "command": "observe",
                "argument": "",
                "confidence": 0.0,
                "has_warnings": True,
                "warnings": ["Complete JSON parse failure."],
                "was_repaired": False,
                "raw_output": raw
            }
            persist_malformed_output(prompt, raw, None, fallback)
            return fallback
