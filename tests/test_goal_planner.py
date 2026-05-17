import pytest
import os
import shutil
from unittest.mock import patch, MagicMock
from agent.goal_planner import GoalPlanner, SubGoal

@pytest.fixture(autouse=True)
def cleanup_tmp_snapshots():
    # Setup
    yield
    # Teardown
    if os.path.exists("tmp/roadmaps"):
        shutil.rmtree("tmp/roadmaps", ignore_errors=True)

@patch("agent.goal_planner.Mistral")
def test_goal_decomposition(mock_mistral_class):
    mock_client = MagicMock()
    mock_mistral_class.return_value = mock_client
    
    # Mock decomposition API response
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="""
        {
          "subgoals": [
            {
              "title": "Navigate to python.org",
              "description": "Open python home page",
              "steps": [{"command": "open_url", "argument": "https://www.python.org"}],
              "verification_condition": {
                "url_contains": "python.org",
                "text_contains": "Downloads",
                "min_buttons": 3,
                "title_contains": "Python"
              },
              "confidence": 0.95
            },
            {
              "title": "Locate downloads",
              "description": "Click the downloads button",
              "steps": [{"command": "click_text", "argument": "Downloads"}],
              "verification_condition": {
                "url_contains": "downloads"
              },
              "confidence": 0.90
            }
          ]
        }
        """))
    ]
    mock_client.chat.complete.return_value = mock_response
    
    planner = GoalPlanner()
    subgoals = planner.decompose("Download Python")
    
    assert len(subgoals) == 2
    assert subgoals[0].title == "Navigate to python.org"
    assert subgoals[0].confidence == 0.95
    assert subgoals[0].verification_condition["url_contains"] == "python.org"
    assert subgoals[1].title == "Locate downloads"
    assert subgoals[1].steps[0]["command"] == "click_text"

def test_subgoal_progression_verification():
    planner = GoalPlanner()
    subgoal = SubGoal(
        title="Navigate to google.com",
        description="Verify navigation page homepage",
        verification_condition={
            "url_contains": "google.com",
            "text_contains": "Search",
            "min_buttons": 2
        }
    )
    
    # Test case 1: Perfect verification match (3/3 matched -> 1.0)
    obs_perfect = {
        "url": "https://www.google.com/?gws_rd=ssl",
        "text": "Google Search bar here",
        "button_count": 4,
        "input_count": 1,
        "title": "Google"
    }
    verified, score = planner.verify_subgoal(subgoal, obs_perfect)
    assert verified is True
    assert score == 1.0
    
    # Test case 2: Partial verified match (2/3 matched -> 0.67 < 0.75 -> Verified False)
    obs_partial = {
        "url": "https://www.google.com/?gws_rd=ssl",
        "text": "Google Search homepage",  # matches "Search"
        "button_count": 0,  # Fails min_buttons (0 < 2)
        "input_count": 1,
        "title": "Google"
    }
    verified, score = planner.verify_subgoal(subgoal, obs_partial)
    assert verified is False
    assert score == pytest.approx(0.667, abs=0.01)

@patch("agent.goal_planner.Mistral")
def test_replanning_logic(mock_mistral_class):
    mock_client = MagicMock()
    mock_mistral_class.return_value = mock_client
    
    # Mock replanning API response to return regenerated remaining subgoals
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="""
        {
          "subgoals": [
            {
              "title": "Bypass navigation failure",
              "description": "Go to alternate search URL",
              "steps": [{"command": "open_url", "argument": "https://google.com/search"}],
              "verification_condition": {"url_contains": "google.com/search"},
              "confidence": 0.88
            }
          ]
        }
        """))
    ]
    mock_client.chat.complete.return_value = mock_response
    
    current_subgoals = [
        SubGoal(title="Completed Subgoal", status="completed", description="First step"),
        SubGoal(title="Failed Subgoal", status="executing", description="Second step")
    ]
    
    planner = GoalPlanner()
    new_subgoals = planner.replan(
        goal="Search query",
        current_subgoals=current_subgoals,
        failed_index=1,
        last_observation="Page failed to open downloads button"
    )
    
    # Assert completed subgoal was preserved
    assert len(new_subgoals) == 2
    assert new_subgoals[0].title == "Completed Subgoal"
    assert new_subgoals[0].status == "completed"
    
    # Assert remaining branches were replaced
    assert new_subgoals[1].title == "Bypass navigation failure"
    assert new_subgoals[1].confidence == 0.88

def test_interrupted_task_resume():
    planner = GoalPlanner()
    subgoals = [
        SubGoal(title="Completed Subgoal", status="completed", description="Task 1"),
        SubGoal(title="Pending Subgoal", status="pending", description="Task 2")
    ]
    
    # Save progress snapshot
    planner.save_snapshot(
        session_id="test_interrupt",
        subgoals=subgoals,
        current_index=1,
        goal="Long horizon goal"
    )
    
    # Retrieve/Resume from snapshot
    recovered = planner.load_snapshot("test_interrupt")
    
    assert recovered is not None
    assert recovered["goal"] == "Long horizon goal"
    assert recovered["current_subgoal_index"] == 1
    assert len(recovered["subgoals"]) == 2
    assert recovered["subgoals"][0].title == "Completed Subgoal"
    assert recovered["subgoals"][0].status == "completed"
    assert recovered["subgoals"][1].title == "Pending Subgoal"
