import pytest
from unittest.mock import patch, MagicMock
from PyQt5.QtCore import Qt

def test_memory_hit_path(qtbot, temp_memory_db, mock_playwright):
    from agent.executor import Executor
    
    # Pre-populate memory
    temp_memory_db.save_workflow("open google", {"action": "autonomous", "goal": "open google", "steps": []}, success=True)
    
    executor = Executor()
    executor._wf_memory = temp_memory_db
    
    # Verify that handling the task triggers high-level goal confirmation immediately
    with qtbot.waitSignal(executor.confirmation_required, timeout=2000) as blocker:
        executor.handle_task("open google")
        
    plan_arg = blocker.args[0]
    assert plan_arg is not None
    assert plan_arg["action"] == "autonomous"
    assert "open google" in plan_arg["goal"]
    
    executor.shutdown()
