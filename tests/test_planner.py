import pytest
import json
from agent.planner import Planner

def test_structured_action_generation(mock_mistral):
    planner = Planner()
    
    # Mistral is mocked to return {"action": "browser", "steps": [{"command": "open_url", "argument": "https://example.com"}]}
    plan = planner.plan("Open example.com")
    
    assert plan["action"] == "browser"
    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["command"] == "open_url"
    assert plan["steps"][0]["argument"] == "https://example.com"
    assert plan["version"] == 2

def test_validation_auto_fix():
    planner = Planner()
    
    # Create a plan that is missing a click for a playback prompt
    initial_plan = {
        "action": "browser",
        "steps": [
            {"command": "open_url", "argument": "https://youtube.com"},
            {"command": "search", "argument": "trending songs"}
        ]
    }
    
    # The prompt contains the keyword "play"
    fixed_plan = planner.validate_and_fix("Play trending songs", initial_plan)
    
    assert len(fixed_plan["steps"]) == 3
    assert fixed_plan["steps"][-1]["command"] == "click_first_result"
    assert fixed_plan["steps"][-1]["argument"] is None

def test_legacy_string_normalization():
    planner = Planner()
    
    # Create a plan with old string-based steps
    legacy_plan = {
        "action": "browser",
        "steps": [
            "open_url:https://google.com",
            "search:cats"
        ]
    }
    
    # Run through validation
    normalized_plan = planner.validate_and_fix("Search for cats", legacy_plan)
    
    assert normalized_plan["steps"][0]["command"] == "open_url"
    assert normalized_plan["steps"][0]["argument"] == "https://google.com"
    assert normalized_plan["steps"][1]["command"] == "search"
    assert normalized_plan["steps"][1]["argument"] == "cats"
