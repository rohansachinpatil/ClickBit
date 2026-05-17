"""
agent/skill_memory.py
---------------------
Autonomous Skill Memory & Workflow Learning Engine.
Compresses successful trajectories into reusable semantic procedural memory.
Implements lazy-loading hybrid retrieval.
"""

import os
import json
import time
import math
import uuid
import hashlib
from typing import List, Dict, Any, Optional, Protocol, Tuple
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse

from utils.logger import get_logger

logger = get_logger(__name__)

SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")

# ── Data Models ────────────────────────────────────────────────────────────────

@dataclass
class SkillStep:
    action_type: str
    argument: str
    transition_type: str = "no_change"
    expected_keywords: List[str] = field(default_factory=list)
    fallback_actions: List[str] = field(default_factory=list)
    confidence: float = 1.0
    primitive_used: bool = False

@dataclass
class LearnedSkill:
    skill_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    domain: str = ""
    skill_scope: str = "strict_domain" # strict_domain, related_domains, global
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    
    # Traceability
    skill_generated_from_session_id: str = ""
    workflow_fingerprint: str = ""
    
    # Analytics & Reinforcement
    usage_count: int = 0
    success_rate: float = 1.0
    confidence: float = 1.0
    avg_execution_time: float = 0.0
    
    # Failure & Quarantine
    failure_count: int = 0
    failure_streak: int = 0
    last_failure_at: float = 0.0
    quarantined: bool = False
    
    # Semantic Matchers
    trigger_phrases: List[str] = field(default_factory=list)
    
    # Workflow
    steps: List[SkillStep] = field(default_factory=list)
    recovery_patterns: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def evolve_confidence(self, success: bool):
        """Adaptive evolution based on RL rule: (old * 0.8) + (latest * 0.2)"""
        latest_result = 1.0 if success else 0.0
        self.confidence = (self.confidence * 0.8) + (latest_result * 0.2)
        
        self.usage_count += 1
        
        if success:
            self.failure_streak = 0
            # Success rate moving average
            self.success_rate = ((self.success_rate * (self.usage_count - 1)) + 1.0) / self.usage_count
        else:
            self.failure_count += 1
            self.failure_streak += 1
            self.last_failure_at = time.time()
            self.success_rate = ((self.success_rate * (self.usage_count - 1)) + 0.0) / self.usage_count
            
            if self.failure_streak >= 3 or self.success_rate < 0.2:
                self.quarantined = True
                logger.warning(f"[SkillMemory] Quarantined skill {self.name} due to failure streak.")


# ── Workflow Compression Engine ────────────────────────────────────────────────

class WorkflowCompressionEngine:
    @staticmethod
    def compress_trajectory(session_data: Dict[str, Any]) -> Optional[LearnedSkill]:
        """
        Parses execution frames, removes retries/stalls, merges repetitive actions,
        and translates raw events into semantic procedural memory steps.
        """
        timeline = session_data.get("timeline", [])
        if not timeline: return None
        
        goal = session_data.get("metadata", {}).get("goal", "")
        session_id = session_data.get("session_id", "")
        if not goal: return None
        
        domain = ""
        steps: List[SkillStep] = []
        
        for idx, frame in enumerate(timeline):
            cmd = frame.get("command")
            arg = frame.get("argument", "")
            success = frame.get("action_success", False)
            t_type = frame.get("transition_type", "no_change")
            
            # Skip failed actions (compression deduplication)
            if not success: continue
            
            # Determine domain from first successful action URL
            if not domain and frame.get("before_state", {}).get("url"):
                parsed = urlparse(frame["before_state"]["url"])
                domain = parsed.netloc.replace("www.", "")
            
            # Skip redundant consecutive observes
            if cmd == "observe" and len(steps) > 0 and steps[-1].action_type == "observe":
                continue
                
            step = SkillStep(
                action_type=cmd,
                argument=arg,
                transition_type=t_type,
                confidence=frame.get("confidence", 1.0),
                primitive_used=frame.get("primitive_used", False)
            )
            
            # Extract expected keywords for semantic anchoring instead of raw selectors
            if cmd in ["click", "type", "youtube_search", "google_search"]:
                # Clean argument to act as anchor keyword
                clean_arg = "".join(c if c.isalnum() else " " for c in arg).strip().lower()
                if clean_arg:
                    step.expected_keywords = [w for w in clean_arg.split() if len(w) > 2]
            
            steps.append(step)
            
        if len(steps) < 2: 
            return None # Not a meaningful workflow
            
        # Generate Deterministic Fingerprint
        chain_str = "|".join([f"{s.action_type}:{s.transition_type}:{s.primitive_used}" for s in steps])
        fingerprint = hashlib.md5(chain_str.encode("utf-8")).hexdigest()
        
        skill = LearnedSkill(
            name=goal,
            domain=domain,
            skill_generated_from_session_id=session_id,
            workflow_fingerprint=fingerprint,
            trigger_phrases=[goal.lower()]
        )
        skill.steps = steps
        
        return skill


# ── Semantic Embedding Protocols ───────────────────────────────────────────────

class EmbeddingBackend(Protocol):
    def compute_similarity(self, query: str, document: str) -> float:
        ...

class TFIDFEmbeddingBackend:
    """
    Lightweight, zero-dependency local embedding matcher using BM25-style
    Jaccard overlap + TF weighting.
    """
    def __init__(self):
        # We can implement IDF later as skills grow, but Jaccard overlap + TF is solid for V1
        pass
        
    def _tokenize(self, text: str) -> set:
        clean = "".join(c if c.isalnum() else " " for c in text.lower())
        return set(w for w in clean.split() if len(w) > 2)

    def compute_similarity(self, query: str, document: str) -> float:
        q_tokens = self._tokenize(query)
        d_tokens = self._tokenize(document)
        
        if not q_tokens or not d_tokens:
            return 0.0
            
        intersection = q_tokens.intersection(d_tokens)
        union = q_tokens.union(d_tokens)
        
        # Jaccard
        jaccard = len(intersection) / len(union)
        
        # Recall-focused subset matching (if query is fully present in document)
        recall = len(intersection) / len(q_tokens)
        
        return (jaccard * 0.4) + (recall * 0.6)


# ── Semantic Retrieval Layer ───────────────────────────────────────────────────

class SemanticRetrievalLayer:
    def __init__(self, backend: EmbeddingBackend = None):
        self.backend = backend or TFIDFEmbeddingBackend()
        os.makedirs(SKILLS_DIR, exist_ok=True)
        self._index_path = os.path.join(SKILLS_DIR, "index.json")
        self._ensure_index()
        
    def _ensure_index(self):
        if not os.path.exists(self._index_path):
            with open(self._index_path, "w", encoding="utf-8") as f:
                json.dump({"skills": []}, f, indent=2)
                
    def _load_index(self) -> List[Dict[str, Any]]:
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("skills", [])
        except Exception:
            return []
            
    def _save_index(self, skills_meta: List[Dict[str, Any]]):
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump({"skills": skills_meta}, f, indent=2)

    def store_skill(self, skill: LearnedSkill):
        """Saves skill body to disk and updates lightweight index."""
        # Save full body
        skill_path = os.path.join(SKILLS_DIR, f"{skill.skill_id}.json")
        with open(skill_path, "w", encoding="utf-8") as f:
            json.dump(asdict(skill), f, indent=2)
            
        # Update index
        index = self._load_index()
        # Remove existing if same ID
        index = [s for s in index if s["skill_id"] != skill.skill_id]
        
        # Add lightweight metadata
        meta = {
            "skill_id": skill.skill_id,
            "name": skill.name,
            "domain": skill.domain,
            "skill_scope": skill.skill_scope,
            "success_rate": skill.success_rate,
            "confidence": skill.confidence,
            "quarantined": skill.quarantined,
            "workflow_fingerprint": skill.workflow_fingerprint,
            "created_at_timestamp": time.time()
        }
        index.append(meta)
        self._save_index(index)
        logger.info(f"[SkillMemory] Stored learned skill: {skill.name} [{skill.skill_id}]")

    def load_skill_body(self, skill_id: str) -> Optional[LearnedSkill]:
        """Lazy loads full skill body."""
        skill_path = os.path.join(SKILLS_DIR, f"{skill_id}.json")
        if not os.path.exists(skill_path): return None
        try:
            with open(skill_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Reconstruct step dataclasses
                steps_data = data.pop("steps", [])
                steps = [SkillStep(**s) for s in steps_data]
                skill = LearnedSkill(**data)
                skill.steps = steps
                return skill
        except Exception as e:
            logger.error(f"[SkillMemory] Failed to load skill {skill_id}: {e}")
            return None

    def retrieve_similar_skills(self, goal: str, current_domain: str, top_k: int = 3) -> List[Tuple[LearnedSkill, float]]:
        """
        Implements lightweight hybrid ranking without loading all skill bodies into RAM.
        Final Score = Semantic (0.45) + Domain (0.20) + Success (0.25) + Recency (0.10)
        """
        index = self._load_index()
        if not index: return []
        
        scored = []
        now = time.time()
        
        for meta in index:
            if meta.get("quarantined", False): continue
            
            # 1. Semantic Score (0.45 weight)
            semantic = self.backend.compute_similarity(goal, meta["name"])
            
            # 2. Domain Score (0.20 weight)
            domain_score = 0.0
            if meta["domain"] and current_domain:
                if meta["domain"] in current_domain or current_domain in meta["domain"]:
                    domain_score = 1.0
                elif meta["skill_scope"] == "global":
                    domain_score = 0.5
            elif meta["skill_scope"] == "global":
                domain_score = 0.8
                
            # If strict domain and mismatch, heavy penalty
            if meta["skill_scope"] == "strict_domain" and domain_score == 0.0 and current_domain:
                continue
                
            # 3. Success / Confidence (0.25 weight)
            success = meta.get("confidence", meta.get("success_rate", 0.5))
            
            # 4. Recency (0.10 weight)
            age_days = (now - meta.get("created_at_timestamp", now)) / (60 * 60 * 24)
            recency = max(0.0, 1.0 - (age_days / 30.0)) # 30 day decay
            
            final_score = (semantic * 0.45) + (domain_score * 0.20) + (success * 0.25) + (recency * 0.10)
            
            if final_score > 0.35: # Minimum threshold to consider
                scored.append((meta["skill_id"], final_score))
                
        # Sort descending
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Lazy load bodies for top K
        results = []
        for sid, score in scored[:top_k]:
            skill = self.load_skill_body(sid)
            if skill:
                results.append((skill, score))
                
        return results
