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

from playwright.sync_api import Error as PlaywrightError
from automation.browser_agent import BrowserSessionState, TransportError
import threading

def test_transport_recovery_epipe(mock_playwright):
    agent = BrowserAgent(headless=True)
    
    # Inject the mock Playwright components
    agent._playwright = mock_playwright["playwright"]
    agent._browser = mock_playwright["browser"]
    agent._page = mock_playwright["page"]
    agent._session_state = BrowserSessionState.READY
    
    # Simulate an EPIPE disconnect
    mock_playwright["browser"].is_connected.return_value = False
    
    with patch.object(agent, '_safe_teardown') as mock_teardown, \
         patch.object(agent, '_ensure_browser') as mock_ensure:
         
        with pytest.raises(TransportError):
            agent.execute_single_action("observe", "")
            
        mock_teardown.assert_called_once()
        mock_ensure.assert_called_once()
        assert agent._session_state == BrowserSessionState.READY
        assert agent._session_generation == 1

def test_safe_teardown_concurrency():
    agent = BrowserAgent(headless=True)
    agent._session_state = BrowserSessionState.READY
    
    def teardown_worker():
        agent._safe_teardown()

    threads = [threading.Thread(target=teardown_worker) for _ in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()

    # The state should be DEAD and no exceptions should have escaped
    assert agent._session_state == BrowserSessionState.DEAD

def test_emergency_stop_lifecycle():
    agent = BrowserAgent(headless=True)
    agent._session_state = BrowserSessionState.READY
    
    agent.close()
    
    assert agent._session_state == BrowserSessionState.DEAD
