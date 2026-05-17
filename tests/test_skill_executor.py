import pytest
import sys
from unittest.mock import MagicMock, patch

# Mock out PyQt5 to avoid UI import errors in headless tests
try:
    import PyQt5
except ImportError:
    sys.modules['PyQt5'] = MagicMock()
    sys.modules['PyQt5.QtCore'] = MagicMock()

# Mock out browser agent
mock_browser_module = MagicMock()
sys.modules['automation.browser_agent'] = mock_browser_module

from agent.skill_executor import SkillExecutor, SkillExecutionError
from agent.skill_memory import LearnedSkill, SkillStep

def test_skill_executor_success():
    mock_browser = MagicMock()
    mock_browser.execute_command.return_value = True
    
    # Mock snapshot logic to avoid deep playwright dependencies
    import agent.transition_validator
    mock_snapshot = MagicMock()
    mock_snapshot.modal_state = False
    
    with patch.object(agent.transition_validator.TransitionValidator, "take_snapshot", return_value=mock_snapshot), \
         patch.object(agent.transition_validator.TransitionValidator, "compute_transition_score", return_value=(0.9, "navigation")):
         
        mock_memory = MagicMock()
        
        executor = SkillExecutor(mock_browser, mock_memory)
        
        skill = LearnedSkill(name="Test Skill")
        skill.steps = [
            SkillStep(action_type="click", argument="btn"),
            SkillStep(action_type="type", argument="text")
        ]
        
        success, reason = executor.execute_skill(skill)
        
        assert success is True
        assert mock_browser.execute_command.call_count == 2
        assert mock_memory.store_skill.called


def test_skill_executor_fallback_and_failure():
    mock_browser = MagicMock()
    
    # First command fails, fallback fails too
    mock_browser.execute_command.return_value = False
    mock_memory = MagicMock()
    
    executor = SkillExecutor(mock_browser, mock_memory)
    
    skill = LearnedSkill(name="Failing Skill")
    skill.steps = [
        SkillStep(action_type="click", argument="btn", fallback_actions=["fallback-btn"])
    ]
    
    success, reason = executor.execute_skill(skill)
    
    assert success is False
    assert "Action and fallback failed" in reason
    assert mock_browser.execute_command.call_count == 2 # Tried original, then fallback
    assert mock_memory.store_skill.called # Still stores the decayed confidence
