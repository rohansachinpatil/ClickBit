import pytest
from unittest.mock import patch, MagicMock
from agent.execution_state import ExecutionState, ActionRecord
from agent.action_decider import ActionDecider

def test_detect_stall_observes():
    state = ExecutionState(goal="search for hindi music")
    
    # 2 observes - not stalled yet
    state.action_history = [
        ActionRecord(iteration=1, observation="A", reasoning="thinking", command="observe", argument="", confidence=0.8, success=True),
        ActionRecord(iteration=2, observation="B", reasoning="thinking", command="observe", argument="", confidence=0.8, success=True),
    ]
    assert not state.detect_stall()
    
    # 3 observes - stalled!
    state.action_history.append(
        ActionRecord(iteration=3, observation="C", reasoning="thinking", command="observe", argument="", confidence=0.8, success=True)
    )
    assert state.detect_stall()

def test_detect_stall_repeats():
    state = ExecutionState(goal="search for hindi music")
    
    # 3 different commands - not stalled
    state.action_history = [
        ActionRecord(iteration=1, observation="A", reasoning="thinking", command="click_text", argument="first", confidence=0.8, success=True),
        ActionRecord(iteration=2, observation="B", reasoning="thinking", command="click_text", argument="second", confidence=0.8, success=True),
        ActionRecord(iteration=3, observation="C", reasoning="thinking", command="click_text", argument="first", confidence=0.8, success=True),
    ]
    assert not state.detect_stall()
    
    # 3 consecutive identical commands + arguments - stalled!
    state.action_history = [
        ActionRecord(iteration=1, observation="A", reasoning="thinking", command="click_text", argument="first", confidence=0.8, success=True),
        ActionRecord(iteration=2, observation="B", reasoning="thinking", command="click_text", argument="first", confidence=0.8, success=True),
        ActionRecord(iteration=3, observation="C", reasoning="thinking", command="click_text", argument="first", confidence=0.8, success=True),
    ]
    assert state.detect_stall()

@patch("httpx.post")
def test_empty_observation_skip_llm(mock_post):
    decider = ActionDecider()
    state = ExecutionState(goal="search for hindi music")
    state.latest_observation = "   " # empty observation
    state.iteration = 2 # not first iteration
    
    res = decider.decide(state)
    
    # Decider should bypass LLM call and return observe directly
    assert res["command"] == "observe"
    mock_post.assert_not_called()
