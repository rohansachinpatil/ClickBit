import pytest
import os
from agent.skill_memory import (
    SkillStep, LearnedSkill, WorkflowCompressionEngine,
    TFIDFEmbeddingBackend, SemanticRetrievalLayer
)

def test_workflow_compression():
    session_data = {
        "session_id": "test_session_123",
        "metadata": {"goal": "Search youtube for cats"},
        "timeline": [
            {
                "command": "observe",
                "action_success": True,
                "before_state": {"url": "https://www.youtube.com"}
            },
            {
                "command": "youtube_search",
                "argument": "funny cats 1080p",
                "action_success": True,
                "transition_type": "navigation"
            },
            {
                "command": "click", # retry that fails
                "argument": "some-btn",
                "action_success": False
            },
            {
                "command": "click",
                "argument": "video-title",
                "action_success": True,
                "transition_type": "playback_started"
            }
        ]
    }
    
    skill = WorkflowCompressionEngine.compress_trajectory(session_data)
    
    assert skill is not None
    assert skill.domain == "youtube.com"
    assert skill.name == "Search youtube for cats"
    assert skill.skill_generated_from_session_id == "test_session_123"
    assert len(skill.steps) == 3 # observe, youtube_search, click (failed retry is skipped)
    
    # Check expected keywords parsing
    assert "funny" in skill.steps[1].expected_keywords
    assert "cats" in skill.steps[1].expected_keywords
    
    # Fingerprint should be set
    assert skill.workflow_fingerprint != ""


def test_tfidf_backend():
    backend = TFIDFEmbeddingBackend()
    
    # Exact match
    assert backend.compute_similarity("search youtube", "search youtube") == 1.0
    
    # Partial match
    sim1 = backend.compute_similarity("search youtube for cats", "youtube search dogs")
    assert sim1 > 0.0
    
    # No match
    sim2 = backend.compute_similarity("google maps", "youtube search")
    assert sim2 == 0.0


def test_semantic_retrieval(tmp_path):
    import agent.skill_memory
    agent.skill_memory.SKILLS_DIR = str(tmp_path)
    
    memory = SemanticRetrievalLayer()
    
    # Create a skill
    skill1 = LearnedSkill(
        name="Navigate to GitHub repo",
        domain="github.com",
        skill_scope="strict_domain",
        success_rate=0.9
    )
    memory.store_skill(skill1)
    
    # Create another skill
    skill2 = LearnedSkill(
        name="Search YouTube for music",
        domain="youtube.com",
        skill_scope="strict_domain",
        success_rate=0.95
    )
    memory.store_skill(skill2)
    
    # Retrieve
    results = memory.retrieve_similar_skills("github repository", current_domain="github.com")
    assert len(results) >= 1
    assert results[0][0].skill_id == skill1.skill_id
    
    # Cross domain mismatch (should fail due to strict_domain)
    results2 = memory.retrieve_similar_skills("youtube music", current_domain="google.com")
    assert len(results2) == 0
    
    # Quarantine
    skill1.quarantined = True
    memory.store_skill(skill1)
    results3 = memory.retrieve_similar_skills("github repository", current_domain="github.com")
    assert len(results3) == 0
