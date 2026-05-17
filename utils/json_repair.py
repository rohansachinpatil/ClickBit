"""
utils/json_repair.py
--------------------
Central Structured Output Reliability Pipeline.
Parses, repairs, validates, and persists malformed LLM JSON actions.
"""

import json
import os
import re
import hashlib
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

# Strict Command Registry (Execution ABI)
VALID_COMMANDS = {
    "observe",
    "open_url",
    "search",
    "click_text",
    "click_index",
    "click_first_result",
    "type_text",
    "task_complete"
}

def extract_json_block(text: str) -> str:
    """
    Extracts the first valid-looking JSON object from a text block.
    Strips markdown code fences and surrounding conversational prose.
    """
    if not text:
        return ""
    
    # Strip markdown code fences if present
    clean_text = text.strip()
    clean_text = re.sub(r"^```(?:json)?\n", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"\n```$", "", clean_text)
    
    # Locate first '{' and last '}'
    match = re.search(r"\{.*\}", clean_text, re.DOTALL)
    if match:
        return match.group().strip()
    
    return clean_text.strip()

def repair_pass_1(text: str) -> str:
    """
    Pass 1: Light cleanup
    Strips code fences, isolates block, resolves single-quotes, and fixes trailing commas.
    """
    block = extract_json_block(text)
    if not block:
        return ""

    # Fix trailing commas inside lists or objects before a closing bracket/brace
    # e.g., {"a": 1,} -> {"a": 1}
    block = re.sub(r",\s*([\}\]])", r"\1", block)
    
    # Coerce single quotes to double quotes around keys and values
    # Match single-quoted keys: 'key': -> "key":
    block = re.sub(r"([\{\,])\s*'([a-zA-Z0-9_-]+)'\s*:", r'\1"\2":', block)
    # Match single-quoted string values: : 'value' -> : "value"
    block = re.sub(r":\s*'([^']*)'\s*(?=[\,\}])", r': "\1"', block)
    
    return block

def repair_pass_2(text: str) -> str:
    """
    Pass 2: Structural fixes
    Resolves missing commas, duplicate commas, casing of booleans/nulls, unescaped newlines.
    """
    block = repair_pass_1(text)
    if not block:
        return ""

    # Fix missing commas between key-value pairs or consecutive fields
    # e.g., "reasoning": "thought" "confidence": 0.9 -> "reasoning": "thought", "confidence": 0.9
    # Match a primitive/string value followed by whitespace and a key
    block = re.sub(r'("[^"]*"|[0-9.]+|true|false|null)\s*(?=\s*"[a-zA-Z0-9_-]+"\s*:)', r'\1,', block)

    # Fix duplicate commas
    block = re.sub(r",\s*,+", ",", block)

    # Coerce Python booleans/None casing to JSON-valid booleans/null
    block = re.sub(r"\bTrue\b", "true", block)
    block = re.sub(r"\bFalse\b", "false", block)
    block = re.sub(r"\bNone\b", "null", block)

    # Escape literal newlines within double-quoted string values
    # Match double-quoted strings and replace internal newlines with escaped '\n'
    def escape_newlines(match):
        return match.group(0).replace('\n', '\\n').replace('\r', '\\r')
    block = re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', escape_newlines, block)

    return block

def repair_pass_3(text: str) -> str:
    """
    Pass 3: Aggressive fallback & reconstruction
    Leverages regex to isolate individual known keys and rebuilds a clean minimal JSON block.
    """
    # Try structural cleaning first
    block = repair_pass_2(text)
    
    # Regex search for the four target keys in any format (single/double quotes)
    reasoning_match = re.search(r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)"', block, re.IGNORECASE)
    if not reasoning_match:
        reasoning_match = re.search(r'"reasoning"\s*:\s*\'([^\']*)\'', block, re.IGNORECASE)
        
    confidence_match = re.search(r'"confidence"\s*:\s*([0-9.]+)', block, re.IGNORECASE)
    
    command_match = re.search(r'"command"\s*:\s*"([^"]+)"', block, re.IGNORECASE)
    if not command_match:
        command_match = re.search(r'"command"\s*:\s*\'([^\']+)\'', block, re.IGNORECASE)
        
    argument_match = re.search(r'"argument"\s*:\s*"((?:[^"\\]|\\.)*)"', block, re.IGNORECASE)
    if not argument_match:
        argument_match = re.search(r'"argument"\s*:\s*\'([^\']*)\'', block, re.IGNORECASE)

    # If none of the keys are found, do not salvage garbage
    if not (reasoning_match or confidence_match or command_match or argument_match):
        return ""

    # Salvage fields
    reasoning = reasoning_match.group(1) if reasoning_match else "Aggressive regex salvage"
    confidence = confidence_match.group(1) if confidence_match else "0.5"
    command = command_match.group(1) if command_match else "observe"
    argument = argument_match.group(1) if argument_match else ""

    # Programmatically rebuild valid JSON
    rebuilt = {
        "reasoning": reasoning,
        "confidence": float(confidence) if confidence.replace('.', '', 1).isdigit() else 0.5,
        "command": command,
        "argument": argument
    }
    return json.dumps(rebuilt)

def safe_parse_json(text: str, prompt: str = "") -> tuple[dict | None, bool, str]:
    """
    Iterative 3-pass JSON repair escalation loop.
    Returns (parsed_dict, was_repaired, repaired_string). Never throws.
    """
    if not text:
        return None, False, ""

    repaired_str = text
    was_repaired = False

    # Attempt 1: Light cleanup
    try:
        repaired_str = repair_pass_1(text)
        parsed = json.loads(repaired_str)
        return parsed, was_repaired, repaired_str
    except Exception:
        was_repaired = True

    # Attempt 2: Structural fixes
    try:
        repaired_str = repair_pass_2(text)
        parsed = json.loads(repaired_str)
        return parsed, was_repaired, repaired_str
    except Exception:
        pass

    # Attempt 3: Aggressive salvage fallback
    try:
        repaired_str = repair_pass_3(text)
        parsed = json.loads(repaired_str)
        return parsed, was_repaired, repaired_str
    except Exception:
        pass

    return None, was_repaired, ""

def validate_action_schema(data: dict) -> tuple[dict, list[str]]:
    """
    Strictly validates the parsed action against the required ClickBit Execution ABI.
    Returns (validated_action_dict, warning_messages_list).
    """
    warnings = []
    
    if not isinstance(data, dict):
        data = {}

    # Extract & coerce fields
    reasoning = str(data.get("reasoning", "")).strip()
    argument = str(data.get("argument", "")).strip()
    
    # 1. Normalise command
    command = str(data.get("command", "")).strip().lower()
    
    # 2. Strict Command Registry Validation
    if not command:
        warnings.append("Missing command property.")
        command = "observe"
    elif command not in VALID_COMMANDS:
        warnings.append(f"Rejected unknown command '{command}' violating Execution ABI.")
        command = "observe"

    # 3. Confidence Clamping
    try:
        confidence = float(data.get("confidence", 0.5))
    except (ValueError, TypeError):
        warnings.append("Non-numeric confidence normalized to 0.5.")
        confidence = 0.5
        
    if confidence < 0.0:
        warnings.append(f"Clamped negative confidence {confidence} to 0.0.")
        confidence = 0.0
    elif confidence > 1.0:
        warnings.append(f"Clamped confidence {confidence} exceeding maximum to 1.0.")
        confidence = 1.0

    validated = {
        "reasoning": reasoning if reasoning else "Validated action structure",
        "confidence": confidence,
        "command": command,
        "argument": argument
    }
    
    return validated, warnings

def persist_malformed_output(prompt: str, raw_output: str, repaired_output: str | None, final_result: dict) -> str:
    """
    Persists malformed LLM response metadata to the local filesystem for auditing.
    Saves to tmp/malformed_outputs/
    """
    try:
        out_dir = "tmp/malformed_outputs"
        os.makedirs(out_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        hashed = hashlib.md5(raw_output.encode("utf-8", errors="ignore")).hexdigest()[:8]
        filename = f"{timestamp}_{hashed}.json"
        filepath = os.path.join(out_dir, filename)

        payload = {
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "raw_output": raw_output,
            "repaired_output": repaired_output,
            "final_fallback_result": final_result
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            
        logger.info(f"[StructuredOutputPipeline] Persisted malformed transaction record to: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"[StructuredOutputPipeline] Failed to persist malformed output transaction: {e}")
        return ""
