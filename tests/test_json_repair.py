import os
import shutil
import json
import pytest
from unittest.mock import patch, MagicMock
from utils.json_repair import (
    VALID_COMMANDS,
    extract_json_block,
    repair_pass_1,
    repair_pass_2,
    repair_pass_3,
    safe_parse_json,
    validate_action_schema,
    persist_malformed_output
)
from agent.execution_state import ExecutionState
from agent.action_decider import ActionDecider

def test_extract_json_block():
    # Surrounding prose and code fences
    raw = "Here is the response:\n```json\n{\n  \"command\": \"observe\"\n}\n```\nHope this helps!"
    assert extract_json_block(raw) == "{\n  \"command\": \"observe\"\n}"
    
    # Just fences
    raw2 = "```\n{\"a\": 1}\n```"
    assert extract_json_block(raw2) == "{\"a\": 1}"

    # Plain JSON
    raw3 = "{\"a\": 1}"
    assert extract_json_block(raw3) == "{\"a\": 1}"

def test_repair_pass_1():
    # Trailing commas in objects and arrays
    text = '{"a": 1, "b": [2, 3,],}'
    repaired = repair_pass_1(text)
    assert "1" in repaired
    assert ",]" not in repaired
    assert ",}" not in repaired

    # Single quotes to double quotes
    text_quotes = "{'command': 'open_url', 'argument': 'http://test.com'}"
    repaired_quotes = repair_pass_1(text_quotes)
    parsed = json.loads(repaired_quotes)
    assert parsed["command"] == "open_url"
    assert parsed["argument"] == "http://test.com"

def test_repair_pass_2():
    # Missing commas between key-value pairs
    text_missing_commas = '{"reasoning": "checking page" "confidence": 0.95 "command": "click_text" "argument": "login"}'
    repaired = repair_pass_2(text_missing_commas)
    parsed = json.loads(repaired)
    assert parsed["reasoning"] == "checking page"
    assert parsed["confidence"] == 0.95
    assert parsed["command"] == "click_text"
    assert parsed["argument"] == "login"

    # Duplicate commas
    text_dup_commas = '{"a": 1,, "b": 2}'
    repaired_dup = repair_pass_2(text_dup_commas)
    parsed_dup = json.loads(repaired_dup)
    assert parsed_dup["a"] == 1
    assert parsed_dup["b"] == 2

    # Malformed Python boolean/None casing
    text_casing = '{"a": True, "b": False, "c": None}'
    repaired_casing = repair_pass_2(text_casing)
    parsed_casing = json.loads(repaired_casing)
    assert parsed_casing["a"] is True
    assert parsed_casing["b"] is False
    assert parsed_casing["c"] is None

    # Unescaped raw newlines inside strings
    text_newlines = '{\n  "reasoning": "Line 1\nLine 2",\n  "command": "observe"\n}'
    repaired_newlines = repair_pass_2(text_newlines)
    parsed_newlines = json.loads(repaired_newlines)
    assert "Line 1\\nLine 2" in repaired_newlines or "Line 1\nLine 2" in parsed_newlines["reasoning"]

def test_repair_pass_3():
    # Aggressively salvage fields from totally cut off / malformed text
    fragment = '{"reasoning": "We need to go to Python site", "confidence": 0.88, "command": "open_url", "arg'
    repaired = repair_pass_3(fragment)
    parsed = json.loads(repaired)
    assert parsed["reasoning"] == "We need to go to Python site"
    assert parsed["confidence"] == 0.88
    assert parsed["command"] == "open_url"
    assert parsed["argument"] == "" # default fallback for cut off field

def test_safe_parse_json():
    # Pass 1 success
    raw = '{"command": "observe", "confidence": 0.9,}'
    res, was_rep, rep_str = safe_parse_json(raw)
    assert res is not None
    assert res["command"] == "observe"
    assert res["confidence"] == 0.9

    # Pass 2 success
    raw2 = '{"command": "open_url" "argument": "google.com" "confidence": True}'
    res2, was_rep2, rep_str2 = safe_parse_json(raw2)
    assert res2 is not None
    assert res2["command"] == "open_url"
    assert res2["argument"] == "google.com"
    assert res2["confidence"] is True

    # Complete fail
    raw_bad = "totally random text without any keys"
    res_bad, was_rep_bad, rep_str_bad = safe_parse_json(raw_bad)
    assert res_bad is None

def test_validate_action_schema():
    # Valid schema - no warnings
    data = {
        "reasoning": "Valid reasoning",
        "confidence": 0.8,
        "command": "click_text",
        "argument": "Submit"
    }
    validated, warnings = validate_action_schema(data)
    assert not warnings
    assert validated["command"] == "click_text"
    assert validated["confidence"] == 0.8

    # Unknown command rejection -> observe + emit warning
    data_unknown = {
        "reasoning": "Test",
        "confidence": 0.9,
        "command": "hallucinated_command",
        "argument": "argument"
    }
    validated_unknown, warnings_unknown = validate_action_schema(data_unknown)
    assert warnings_unknown
    assert any("violating Execution ABI" in w for w in warnings_unknown)
    assert validated_unknown["command"] == "observe"

    # Confidence clamping
    data_clamp = {
        "confidence": 2.5,
        "command": "observe"
    }
    validated_clamp, warnings_clamp = validate_action_schema(data_clamp)
    assert warnings_clamp
    assert validated_clamp["confidence"] == 1.0

    data_clamp_neg = {
        "confidence": -0.5,
        "command": "observe"
    }
    validated_clamp_neg, warnings_clamp_neg = validate_action_schema(data_clamp_neg)
    assert warnings_clamp_neg
    assert validated_clamp_neg["confidence"] == 0.0

    # Auto-fill missing fields
    data_empty = {}
    validated_empty, warnings_empty = validate_action_schema(data_empty)
    assert validated_empty["command"] == "observe"
    assert validated_empty["confidence"] == 0.5
    assert validated_empty["argument"] == ""

    # Primitive commands survival
    data_primitive = {
        "reasoning": "Searching...",
        "confidence": 0.9,
        "command": "youtube_search",
        "argument": "lo-fi coding music"
    }
    validated_prim, warnings_prim = validate_action_schema(data_primitive)
    assert not warnings_prim
    assert validated_prim["command"] == "youtube_search"
    assert validated_prim["argument"] == "lo-fi coding music"

def test_persist_malformed_output():
    out_dir = "tmp/malformed_outputs"
    # Ensure dir cleaned up initially
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)

    prompt = "Test prompt context"
    raw = "Bad unparseable {"
    repaired = None
    final_res = {"command": "observe", "confidence": 0.0}

    filepath = persist_malformed_output(prompt, raw, repaired, final_res)
    assert filepath
    assert os.path.exists(filepath)

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["prompt"] == prompt
        assert data["raw_output"] == raw
        assert data["repaired_output"] is None
        assert data["final_fallback_result"] == final_res

    # Cleanup
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)

@patch("httpx.post")
def test_action_decider_integration(mock_post):
    # Mock Mistral returning malformed JSON with missing comma and trailing comma
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": '{"reasoning": "Mistral forgot commas" "command": "open_url" "argument": "google.com", "confidence": 0.9,}'
            }
        }]
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    decider = ActionDecider()
    state = ExecutionState(goal="navigate to google")
    state.latest_observation = "Some non-empty page content"
    
    res = decider.decide(state)
    assert res["command"] == "open_url"
    assert res["argument"] == "google.com"
    assert res["confidence"] == 0.9
    assert res["was_repaired"] is True
