import os
import json
import time
import pytest
from dataclasses import asdict
from automation.execution_recorder import ExecutionRecorder, ExecutionFrame

def test_execution_frame_serialization():
    frame = ExecutionFrame(
        iteration=1,
        command="click",
        argument="submit-btn",
        observe_latency_ms=100,
        reasoning_latency_ms=150,
        execution_latency_ms=300,
        validation_latency_ms=50,
        transition_score=0.8,
        transition_type="navigation",
        action_success=True,
        before_state={"url": "http://test.com"},
        after_state={"url": "http://test.com/home"}
    )
    
    data = asdict(frame)
    assert data["iteration"] == 1
    assert data["command"] == "click"
    assert data["argument"] == "submit-btn"
    assert data["observe_latency_ms"] == 100
    assert data["transition_score"] == 0.8
    assert data["transition_type"] == "navigation"
    assert data["before_state"]["url"] == "http://test.com"
    assert data["after_state"]["url"] == "http://test.com/home"

def test_execution_recorder_async_writing(tmp_path):
    import automation.execution_recorder
    # Set the root dir to the temporary path for testing
    automation.execution_recorder.SESSIONS_DIR = str(tmp_path)
    
    recorder = ExecutionRecorder()
    session_id = recorder.start_session("Test Goal")
    
    # Session ID should be generated
    assert session_id is not None
    assert os.path.exists(recorder.session_dir)
    assert os.path.exists(recorder.screenshots_dir)
    assert os.path.exists(recorder.diffs_dir)
    
    # Record some frames
    for i in range(3):
        frame = ExecutionFrame(iteration=i, command=f"cmd_{i}", observe_latency_ms=10 * i)
        recorder.record_frame(frame)
        
    # Shutdown the recorder which joins the writer thread
    recorder.stop_session()
    
    # Check that timeline.jsonl is written correctly
    timeline_file = os.path.join(recorder.session_dir, "timeline.jsonl")
    assert os.path.exists(timeline_file)
    
    with open(timeline_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 3
        
        frame0 = json.loads(lines[0])
        assert frame0["iteration"] == 0
        assert frame0["command"] == "cmd_0"
        
        frame2 = json.loads(lines[2])
        assert frame2["iteration"] == 2
        assert frame2["command"] == "cmd_2"

def test_load_session(tmp_path):
    import automation.execution_recorder
    automation.execution_recorder.SESSIONS_DIR = str(tmp_path)
    
    recorder = ExecutionRecorder()
    session_id = recorder.start_session("Test Load")
    
    frame = ExecutionFrame(iteration=0, command="init")
    recorder.record_frame(frame)
    recorder.stop_session()
    
    data = ExecutionRecorder.load_session(session_id)
    assert data["session_id"] == session_id
    assert len(data["timeline"]) == 1
    assert data["timeline"][0]["command"] == "init"
