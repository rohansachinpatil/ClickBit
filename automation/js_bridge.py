"""
automation/js_bridge.py
-----------------------
Playwright JS bridge helper. Forces safe, single-payload evaluate calls.
"""

import json
from utils.logger import get_logger

logger = get_logger(__name__)

def safe_evaluate(page, script: str, payload: dict | None = None):
    """
    Safely executes a page.evaluate() script with at most one serializable payload.
    Prevents positional multi-argument Playwright evaluate issues.
    """
    if payload is None:
        payload = {}
        
    # Validate payload serializability
    try:
        serialized = json.dumps(payload)
        payload_size = len(serialized)
    except (TypeError, OverflowError) as e:
        logger.error(f"[JSBridge] Payload serialization failed: {e}")
        # Telemetry on serialization failure
        logger.info(json.dumps({
            "event": "js_bridge_failure",
            "exception": f"SerializationError: {e}"
        }))
        raise ValueError(f"Payload not JSON serializable: {e}")

    # Deduce script name or brief representation
    script_lines = [line.strip() for line in script.strip().split("\n") if line.strip()]
    script_name = script_lines[0][:60] if script_lines else "anonymous"

    # Telemetry before call
    logger.info(json.dumps({
        "event": "js_bridge_call",
        "script": script_name,
        "payload_size": payload_size
    }))

    try:
        # Perform the actual Playwright evaluate call with ONE payload argument
        result = page.evaluate(script, payload)
        return result
    except Exception as e:
        # Telemetry on Playwright error
        logger.error(json.dumps({
            "event": "js_bridge_failure",
            "exception": str(e)
        }))
        raise e
