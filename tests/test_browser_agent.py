import pytest
from unittest.mock import patch, MagicMock
from automation.browser_agent import BrowserAgent

def test_action_normalization(mock_playwright, qtbot):
    agent = BrowserAgent(headless=True)
    
    # We pass legacy string steps
    steps = [
        "open_url:https://google.com",
        "search:test"
    ]
    
    # Because execute() emits signals and is a slot, we don't necessarily want to run it fully 
    # without isolating the wait. But we can patch _run_with_retry to see what arguments it gets.
    with patch.object(agent, '_run_with_retry', return_value=True) as mock_retry:
        agent.execute(steps)
        
        # It should have called _run_with_retry with the parsed JSON keys
        assert mock_retry.call_count == 2
        mock_retry.assert_any_call("open_url", "https://google.com")
        mock_retry.assert_any_call("search", "test")

def test_retry_wrapper_success(mock_playwright):
    agent = BrowserAgent(headless=True)
    
    # We patch a specific command to fail on the first try but succeed on the second
    mock_click = MagicMock(side_effect=[Exception("Element not found"), None])
    
    with patch.object(agent, '_click_first_result', mock_click):
        # Temporarily mock time.sleep so we don't actually wait during the test
        with patch("time.sleep", return_value=None):
            # Also mock recover state so we don't get stuck
            with patch.object(agent, '_recover_state'):
                success = agent._run_with_retry("click_first_result", "")
                
                assert success is True
                assert mock_click.call_count == 2

def test_recovery_system_epipe(mock_playwright):
    agent = BrowserAgent(headless=True)
    
    # Inject the mock Playwright components so the agent believes it has a running session
    agent._playwright = mock_playwright["playwright"]
    agent._browser = mock_playwright["browser"]
    
    # Simulate an EPIPE disconnect by making is_connected return False
    mock_playwright["browser"].is_connected.return_value = False
    
    # We patch _teardown_browser and _ensure_browser to verify they are called during recovery
    with patch.object(agent, '_teardown_browser') as mock_teardown, \
         patch.object(agent, '_ensure_browser') as mock_ensure:
         
        agent._recover_state()
        
        mock_teardown.assert_called_once()
        mock_ensure.assert_called_once()
