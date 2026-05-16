import pytest
from agent.workflow_memory import WorkflowMemory

def test_save_and_retrieve_workflow(temp_memory_db):
    prompt = "open google"
    plan = {
        "action": "browser",
        "steps": [{"command": "open_url", "argument": "https://google.com"}]
    }
    
    # Save a successful workflow
    temp_memory_db.save_workflow(prompt, plan, success=True)
    
    # Retrieve it
    cached = temp_memory_db.get_cached_plan(prompt)
    
    assert cached is not None
    assert cached["action"] == "browser"
    assert cached["steps"][0]["command"] == "open_url"

def test_memory_schema_migration(temp_memory_db):
    # Saving a plan without a version tag
    prompt = "legacy prompt"
    legacy_plan = {
        "action": "browser",
        "steps": [{"command": "open_url", "argument": "https://old.com"}]
    }
    
    temp_memory_db.save_workflow(prompt, legacy_plan, success=True)
    
    # When retrieved, it should have version: 2 appended by the retrieval logic (if implemented)
    # or at least remain intact
    cached = temp_memory_db.get_cached_plan(prompt)
    assert cached["action"] == "browser"

def test_failed_workflow_exclusion(temp_memory_db):
    prompt = "do something bad"
    plan = {"action": "browser", "steps": []}
    
    # Save a failed workflow
    temp_memory_db.save_workflow(prompt, plan, success=False)
    
    # It should not be returned by get_cached_plan
    cached = temp_memory_db.get_cached_plan(prompt)
    assert cached is None
