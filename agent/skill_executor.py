"""
agent/skill_executor.py
-----------------------
Executes learned procedural skills deterministically.
Bypasses Mistral for rapid execution, but validates transitions strictly.
"""

import time
from typing import Tuple
from utils.logger import get_logger
from automation.browser_agent import BrowserAgent
from agent.skill_memory import LearnedSkill, SemanticRetrievalLayer
from agent.transition_validator import TransitionValidator

logger = get_logger(__name__)

class SkillExecutionError(Exception):
    pass

class SkillExecutor:
    def __init__(self, browser_agent: BrowserAgent, memory_layer: SemanticRetrievalLayer):
        self.browser_agent = browser_agent
        self.memory = memory_layer
        
    def execute_skill(self, skill: LearnedSkill) -> Tuple[bool, str]:
        """
        Executes a workflow deterministically.
        Returns (success: bool, failure_reason: str)
        """
        if not skill.steps:
            return False, "Skill has no steps."
            
        logger.info(f"[SkillExecutor] Starting execution of skill: {skill.name} [{skill.skill_id}]")
        
        start_time = time.perf_counter()
        success = True
        reason = ""
        
        try:
            for i, step in enumerate(skill.steps):
                logger.info(f"  [Step {i+1}/{len(skill.steps)}] {step.action_type}({step.argument})")
                
                # Snapshot before
                page = self.browser_agent._page
                before_snapshot = None
                if page and not page.is_closed():
                    before_snapshot = TransitionValidator.take_snapshot(page)
                
                # Execute action
                step_success = self.browser_agent.execute_command(step.action_type, step.argument)
                if not step_success:
                    # Attempt fallback if available
                    if step.fallback_actions:
                        logger.warning(f"  [Step {i+1}] Failed. Attempting fallback: {step.fallback_actions[0]}")
                        # Very simple fallback logic for V1: just try the first fallback
                        fallback_success = self.browser_agent.execute_command(step.action_type, step.fallback_actions[0])
                        if not fallback_success:
                            raise SkillExecutionError(f"Action and fallback failed at step {i+1}")
                    else:
                        raise SkillExecutionError(f"Action failed at step {i+1}")
                
                # Validate transition
                time.sleep(1.0) # Wait for network/DOM
                if page and not page.is_closed() and before_snapshot:
                    after_snapshot = TransitionValidator.take_snapshot(page)
                    t_score, t_type = TransitionValidator.compute_transition_score(before_snapshot, after_snapshot)
                    
                    # Log transition, could be used for strict validation
                    logger.debug(f"  [Step {i+1}] Transition verified. Score: {t_score:.2f}, Type: {t_type}")
                    
                    # Adaptation: if overlay detected unexpectedly
                    if after_snapshot.modal_state and not before_snapshot.modal_state and step.transition_type != "modal_open":
                        logger.warning(f"  [Step {i+1}] Unexpected overlay detected during skill execution. Aborting for safety.")
                        raise SkillExecutionError(f"Unexpected modal overlay at step {i+1}")
                        
        except SkillExecutionError as e:
            logger.error(f"[SkillExecutor] Skill aborted: {e}")
            success = False
            reason = str(e)
        except Exception as e:
            logger.error(f"[SkillExecutor] Unexpected error during skill execution: {e}")
            success = False
            reason = f"Exception: {e}"
            
        # ── Reinforcement Signal ───────────────────────────────────────────────
        duration = time.perf_counter() - start_time
        
        # Update rolling average execution time
        if success:
            n = skill.usage_count
            if n == 0:
                skill.avg_execution_time = duration
            else:
                skill.avg_execution_time = ((skill.avg_execution_time * n) + duration) / (n + 1)
                
        skill.evolve_confidence(success)
        
        # Persist updated skill metrics
        self.memory.store_skill(skill)
        
        if success:
            logger.info(f"[SkillExecutor] Skill '{skill.name}' completed successfully in {duration:.2f}s.")
        
        return success, reason
