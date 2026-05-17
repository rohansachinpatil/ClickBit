import pytest
import os
import json
from unittest.mock import MagicMock, patch

# -- WorkflowMemory In-Memory DB Fixture --
@pytest.fixture
def temp_memory_db(tmp_path):
    """
    Provides a WorkflowMemory instance connected to a temporary SQLite file.
    This prevents tests from polluting the real workflows.db.
    Also mocks the SemanticMemoryEngine to prevent heavy PyTorch DLL loads during tests.
    """
    from agent.workflow_memory import WorkflowMemory
    db_file = tmp_path / "test_workflows.db"
    import sys
    from unittest.mock import MagicMock
    
    with patch('agent.semantic_memory.SemanticMemoryEngine.encode') as mock_encode:
        # Provide a dummy normalized vector as standard list
        mock_encode.return_value = [1.0, 0.0]
        memory = WorkflowMemory(db_path=str(db_file))
        yield memory

# -- Mistral API Mock Fixture --
@pytest.fixture
def mock_mistral(mocker):
    # Mock the Mistral client to prevent network calls
    mock_client_class = mocker.patch("agent.planner.Mistral")
    mock_instance = mock_client_class.return_value
    
    # Setup a default dummy response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "action": "browser",
        "steps": [
            {"command": "open_url", "argument": "https://example.com"}
        ]
    })
    mock_instance.chat.complete.return_value = mock_response
    
    return mock_instance

# -- Playwright Mock Fixture --
@pytest.fixture
def mock_playwright(mocker):
    # Mock sync_playwright to prevent actual chromium launches
    mock_sync_pw = mocker.patch("automation.browser_agent.sync_playwright")
    
    mock_pw_context = MagicMock()
    mock_sync_pw.return_value = mock_pw_context
    
    mock_pw_instance = mock_pw_context.start.return_value
    mock_browser = mock_pw_instance.chromium.launch.return_value
    mock_context = mock_browser.new_context.return_value
    mock_page = mock_context.new_page.return_value
    
    # By default, pretend everything is connected and alive
    mock_browser.is_connected.return_value = True
    mock_page.is_closed.return_value = False
    
    return {
        "sync_pw": mock_sync_pw,
        "playwright": mock_pw_instance,
        "browser": mock_browser,
        "context": mock_context,
        "page": mock_page
    }

# -- Ollama/Router Mock Fixture --
@pytest.fixture
def mock_ollama(mocker):
    # Mock httpx.post for the Router's local ollama calls
    mock_post = mocker.patch("agent.router.httpx.post")
    
    # Default to a successful mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "response": json.dumps({
            "action": "browser",
            "steps": [{"command": "open_url", "argument": "https://google.com"}]
        })
    }
    mock_post.return_value = mock_response
    
    return mock_post
