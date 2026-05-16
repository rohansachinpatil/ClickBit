import pytest
from unittest.mock import patch, MagicMock
from PyQt5.QtCore import Qt

def test_memory_hit_path(qtbot, temp_memory_db, mock_playwright):
    # Important: executor imports instantiate PyQt QTimer and threads
    from agent.executor import Executor
    
    # Pre-populate memory
    temp_memory_db.save_workflow("open google", {"steps": [{"command": "open_url", "argument": "https://google.com"}]}, success=True)
    
    executor = Executor()
    # Inject our temp db
    executor._wf_memory = temp_memory_db
    
    # Use QSignalSpy from pytest-qt to wait for the signal
    with qtbot.waitSignal(executor.confirmation_required, timeout=2000) as blocker:
        executor.handle_task("open google")
        
    # Check that the signal was emitted with the cached plan
    plan_arg = blocker.args[0]
    assert plan_arg is not None
    assert plan_arg["steps"][0]["command"] == "open_url"

@pytest.mark.skip(reason="QThread teardown with PyTorch mocked causes access violations on Windows test runner")
def test_task_lifecycle_cloud_fallback(qtbot, temp_memory_db, mock_playwright, mock_mistral, mock_ollama):
    from agent.executor import Executor
    
    # Ensure Ollama returns None so it falls back to Mistral
    mock_ollama.return_value = MagicMock(status_code=500)
    
    executor = Executor()
    executor._wf_memory = temp_memory_db
    
    # Wait for the planning thread to finish and emit the confirmation
    with qtbot.waitSignal(executor.confirmation_required, timeout=3000) as blocker:
        with patch('agent.workflow_memory.WorkflowMemory.get_cached_plan', return_value=None):
            executor.handle_task("Do something complex")
        
    plan_arg = blocker.args[0]
    assert plan_arg["action"] == "browser"
    
    # Now simulate user approving the plan
    with qtbot.waitSignal(executor.task_finished, timeout=5000):
        with patch("time.sleep", return_value=None), \
             patch('agent.workflow_memory.WorkflowMemory.save_workflow'):
            # Set the pending plan explicitly since we might not have triggered the full UI flow
            executor._pending_plan = plan_arg
            executor.approve_plan()
