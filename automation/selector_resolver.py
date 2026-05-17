import os
import sqlite3
import time
import difflib
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)


class ResolverExecutionError(Exception):
    """Custom exception raised when SelectorResolver execution signature is invalid or fails."""
    pass


@dataclass
class CandidateElement:
    index: int
    tag_name: str
    element_type: str
    text: str
    placeholder: str
    aria_label: str
    name: str
    element_id: str
    class_name: str
    role: str
    is_visible: bool
    rect: Dict[str, float]
    css_selector: str
    is_disabled: bool = False
    is_tiny: bool = False
    is_offscreen: bool = False
    is_overlay_blocked: bool = False
    confidence: float = 0.0
    text_similarity_score: float = 0.0
    visibility_score: float = 0.0
    interaction_score: float = 0.0
    spatial_relevance_score: float = 0.0
    memory_boost: float = 0.0


class SelectorResolver:
    """
    Adaptive Selector Intelligence Engine.
    Scrapes interactive DOM nodes, ranks them using multi-factor heuristics,
    caches successful resolutions per-domain, and executes fallback chains on failure.
    """

    def __init__(self, db_path: str = "tmp/selector_memory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initializes the lightweight SQLite cache database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS selector_history (
                        domain TEXT,
                        semantic_query TEXT,
                        selector TEXT,
                        selector_type TEXT,
                        success_count INTEGER DEFAULT 1,
                        confidence REAL,
                        last_success_time REAL,
                        PRIMARY KEY (domain, semantic_query, selector)
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize selector database: {e}")

    def _get_domain(self, url: str) -> str:
        """Extracts base domain from a URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            if domain.startswith("www."):
                domain = domain[4:]
            return domain or "local"
        except:
            return "unknown"

    def gather_candidates(self, page) -> List[CandidateElement]:
        """Scrapes interactive nodes in the DOM using a fast JavaScript evaluator."""
        js_script = """
        () => {
            function getUniqueSelector(el) {
                if (el.id) {
                    return "#" + CSS.escape(el.id);
                }
                if (el.name && el.tagName === 'INPUT') {
                    return `input[name="${CSS.escape(el.name)}"]`;
                }
                if (el.tagName === 'BODY') return 'body';
                
                let path = [];
                let current = el;
                while (current && current.nodeType === Node.ELEMENT_NODE) {
                    let selector = current.nodeName.toLowerCase();
                    if (current.id) {
                        selector += '#' + CSS.escape(current.id);
                        path.unshift(selector);
                        break;
                    } else {
                        let sib = current, count = 1;
                        while (sib = sib.previousElementSibling) {
                            if (sib.nodeName.toLowerCase() == selector) count++;
                        }
                        if (count > 1 || current.nextElementSibling) {
                            selector += `:nth-of-type(${count})`;
                        }
                    }
                    path.unshift(selector);
                    current = current.parentNode;
                }
                return path.join(' > ');
            }

            const vw = window.innerWidth;
            const vh = window.innerHeight;
            
            // Locate active blocker modal/overlay if any
            let blockerEl = null;
            const blockerSelectors = [
                '[role="dialog"]', '.modal', '.dialog', '.scrim', '.overlay', '.backdrop',
                '[class*="modal" i]', '[class*="dialog" i]', '[class*="scrim" i]', '[class*="overlay" i]'
            ];
            for (const selector of blockerSelectors) {
                const el = document.querySelector(selector);
                if (el) {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (rect.width > 50 && rect.height > 50 && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                        const zIndex = parseInt(style.zIndex, 10);
                        if ((!isNaN(zIndex) && zIndex >= 10) || style.position === 'fixed' || style.position === 'absolute') {
                            blockerEl = el;
                            break;
                        }
                    }
                }
            }

            function isVisible(el) {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && 
                       style.visibility !== 'hidden' && style.opacity !== '0';
            }

            const query = 'button, input, textarea, a, [role="button"], [role="link"], [onclick]';
            const elements = Array.from(document.querySelectorAll(query));
            
            return elements.map((el, idx) => {
                const rect = el.getBoundingClientRect();
                const is_disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
                const is_tiny = rect.width < 4 || rect.height < 4;
                const is_offscreen = rect.right < 0 || rect.bottom < 0 || rect.left > vw || rect.top > vh;
                
                let is_blocked = false;
                if (blockerEl && blockerEl !== el && !blockerEl.contains(el)) {
                    is_blocked = true;
                }
                
                return {
                    index: idx,
                    tag_name: el.tagName.toLowerCase(),
                    element_type: el.getAttribute('type') || '',
                    text: el.innerText.trim() || '',
                    placeholder: el.placeholder || '',
                    aria_label: el.getAttribute('aria-label') || '',
                    name: el.getAttribute('name') || '',
                    element_id: el.id || '',
                    class_name: el.className || '',
                    role: el.getAttribute('role') || '',
                    is_visible: isVisible(el),
                    is_disabled: is_disabled,
                    is_tiny: is_tiny,
                    is_offscreen: is_offscreen,
                    is_overlay_blocked: is_blocked,
                    rect: {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    },
                    css_selector: getUniqueSelector(el)
                };
            });
        }
        """
        try:
            raw_nodes = page.evaluate(js_script)
            candidates = []
            for node in raw_nodes:
                candidates.append(CandidateElement(
                    index=node["index"],
                    tag_name=node["tag_name"],
                    element_type=node["element_type"],
                    text=node["text"],
                    placeholder=node["placeholder"],
                    aria_label=node["aria_label"],
                    name=node["name"],
                    element_id=node["element_id"],
                    class_name=node["class_name"],
                    role=node["role"],
                    is_visible=node["is_visible"],
                    is_disabled=node.get("is_disabled", False),
                    is_tiny=node.get("is_tiny", False),
                    is_offscreen=node.get("is_offscreen", False),
                    is_overlay_blocked=node.get("is_overlay_blocked", False),
                    rect=node["rect"],
                    css_selector=node["css_selector"]
                ))
            return candidates
        except Exception as e:
            logger.error(f"Failed to gather candidates: {e}")
            return []

    def _calculate_similarity(self, query: str, field_val: str) -> float:
        """Helper to calculate normalized similarity ratio."""
        if not field_val:
            return 0.0
        query_lower = query.lower().strip()
        field_lower = field_val.lower().strip()
        
        # Exact match boost
        if query_lower == field_lower:
            return 1.0
        
        # Substring containment
        if query_lower in field_lower:
            return 0.85
        
        if field_lower in query_lower:
            return 0.70

        # Fuzzy sequence matcher fallback
        return difflib.SequenceMatcher(None, query_lower, field_lower).ratio()

    def resolve_best_candidate(self, page, query: str, action_type: str, context: Optional[Dict[str, Any]] = None) -> Tuple[Optional[CandidateElement], float, str]:
        """
        Ranks gathered candidate elements using multi-factor scores,
        combines them with historical memory boosts, and returns the top resolution.
        """
        domain = self._get_domain(page.url)
        candidates = self.gather_candidates(page)
        
        if not candidates:
            return None, 0.0, "No candidates found"

        top_candidate = None
        highest_score = -1.0
        match_reason = "No match"

        # Apply memory boost mappings
        memory_boosts = self._get_memory_boosts(domain, query)

        for cand in candidates:
            # 1. Text Similarity Score
            # Evaluate all relevant semantic attributes
            text_sim = max(
                self._calculate_similarity(query, cand.text),
                self._calculate_similarity(query, cand.placeholder),
                self._calculate_similarity(query, cand.aria_label),
                self._calculate_similarity(query, cand.name),
                self._calculate_similarity(query, cand.element_id)
            )
            cand.text_similarity_score = text_sim

            # 2. Visibility Score
            cand.visibility_score = 1.0 if cand.is_visible else 0.0

            # 3. Interaction Score
            # Ensure candidate aligns with the type of actions being taken
            interaction = 0.2
            tag = cand.tag_name
            role = cand.role
            
            if action_type in ("click", "click_text", "click_index", "click_first_result"):
                if tag in ("button", "a") or role in ("button", "link"):
                    interaction = 1.0
                elif tag == "input" and cand.element_type in ("submit", "button"):
                    interaction = 1.0
            elif action_type in ("type", "fill", "search"):
                if tag in ("input", "textarea") or role in ("textbox", "searchbox"):
                    interaction = 1.0
            cand.interaction_score = interaction

            # 4. Spatial Relevance Score
            # Prioritize elements based on viewport prominence (more toward center is better)
            spatial = 0.5
            r = cand.rect
            if r["width"] > 0 and r["height"] > 0:
                # Prefer elements higher or centered
                viewport_center_y = 400
                distance_to_center = abs(r["y"] + (r["height"] / 2) - viewport_center_y)
                # Max center distance ~ 400
                spatial = max(0.1, 1.0 - (distance_to_center / 600))
            cand.spatial_relevance_score = spatial

            # 5. Domain Memory Boost
            boost = 0.0
            if cand.css_selector in memory_boosts:
                boost = memory_boosts[cand.css_selector]
                cand.memory_boost = boost

            # Compute combined weighted confidence
            # Text similarity and visibility are primary weights, interaction is structural, spatial is fallback
            weighted_score = (
                (cand.text_similarity_score * 0.45) +
                (cand.visibility_score * 0.25) +
                (cand.interaction_score * 0.20) +
                (cand.spatial_relevance_score * 0.10)
            )
            
            # Interaction Safety Penalties (If candidate is hidden, disabled, tiny, offscreen, or overlay-blocked, decay confidence sharply)
            safety_penalty = 1.0
            if not cand.is_visible:
                safety_penalty *= 0.1
            if cand.is_disabled:
                safety_penalty *= 0.05
            if cand.is_tiny:
                safety_penalty *= 0.1
            if cand.is_offscreen:
                safety_penalty *= 0.1
            if cand.is_overlay_blocked:
                safety_penalty *= 0.05
                
            # Combine boost and safety penalty (cap total confidence at 1.0)
            cand.confidence = min(1.0, (weighted_score + boost) * safety_penalty)

            if cand.confidence > highest_score:
                highest_score = cand.confidence
                top_candidate = cand
                
                # Deduce reasoning details
                if boost > 0.0:
                    match_reason = f"Memory-assisted match (+{boost:.2f} boost)"
                elif text_sim > 0.8:
                    match_reason = f"High semantic similarity text match: '{cand.text or cand.placeholder}'"
                elif cand.is_visible:
                    match_reason = "Best structural visible candidate"
                else:
                    match_reason = "Best matching candidate"

        return top_candidate, highest_score, match_reason

    def _get_memory_boosts(self, domain: str, query: str) -> Dict[str, float]:
        """Queries the SQLite database for successful selectors on the active domain/query."""
        boosts = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT selector, success_count, confidence 
                    FROM selector_history 
                    WHERE domain = ? AND semantic_query = ?
                """, (domain, query))
                rows = cursor.fetchall()
                for row in rows:
                    selector, count, conf = row
                    # Boost is proportional to historical success frequency and confidence, capped at 0.35 max
                    boost = min(0.35, 0.15 + (count * 0.02) + (conf * 0.10))
                    boosts[selector] = boost
        except Exception as e:
            logger.error(f"Failed to query selector memory: {e}")
        return boosts

    def remember_success(self, domain: str, query: str, selector: str, selector_type: str, confidence: float):
        """Records a successful element resolution inside the domain interaction memory."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO selector_history (domain, semantic_query, selector, selector_type, success_count, confidence, last_success_time)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(domain, semantic_query, selector) DO UPDATE SET
                        success_count = success_count + 1,
                        confidence = MAX(confidence, EXCLUDED.confidence),
                        last_success_time = EXCLUDED.last_success_time
                """, (domain, query, selector, selector_type, confidence, time.time()))
                conn.commit()
                logger.info(f"Interaction Memory: Logged resolution success on {domain} -> '{query}' using {selector}")
        except Exception as e:
            logger.error(f"Failed to record selector success in SQLite: {e}")

    def decay_selector(self, domain: str, query: str, selector: str):
        """Decrements confidence of a cached selector when it fails to yield a successful action (Self-Healing)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT success_count, confidence FROM selector_history
                    WHERE domain = ? AND semantic_query = ? AND selector = ?
                """, (domain, query, selector))
                row = cursor.fetchone()
                if row:
                    count, conf = row
                    new_count = max(0, count - 1)
                    new_conf = max(0.0, conf - 0.15)
                    
                    if new_count == 0 and new_conf <= 0.1:
                        # Purge stale/broken selectors entirely
                        cursor.execute("""
                            DELETE FROM selector_history
                            WHERE domain = ? AND semantic_query = ? AND selector = ?
                        """, (domain, query, selector))
                        logger.info(f"Interaction Memory: Purged decayed stale selector {selector} on {domain}")
                    else:
                        cursor.execute("""
                            UPDATE selector_history 
                            SET success_count = ?, confidence = ?
                            WHERE domain = ? AND semantic_query = ? AND selector = ?
                        """, (new_count, new_conf, domain, query, selector))
                        logger.info(f"Interaction Memory: Decayed selector {selector} on {domain} (New Count: {new_count}, New Conf: {new_conf:.2f})")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to decay selector in SQLite: {e}")

    def execute_fallback_chain(self, page, top_candidate: Optional[CandidateElement], query: str, action_type: str = None, argument: str = "") -> Tuple[bool, str, str]:
        """
        Attempts interaction with the top candidate using its CSS selector,
        and if it fails, falls back sequentially to alternative candidates or fuzzy text matches.
        """
        if not action_type:
            raise ResolverExecutionError("action_type is missing or empty in execute_fallback_chain")
            
        domain = self._get_domain(page.url)
        tried_selectors = []

        # 1. Primary Attempt (Top candidate)
        if top_candidate:
            sel = top_candidate.css_selector
            tried_selectors.append(sel)
            try:
                logger.info(f"SelectorResolver: Resolving primary target selector '{sel}'")
                self._perform_action(page, sel, action_type, argument)
                # Successful! Cache in interaction memory
                self.remember_success(domain, query, sel, "css", top_candidate.confidence)
                return True, sel, f"Success via primary selector: {sel}"
            except Exception as e:
                logger.warning(f"SelectorResolver: Primary selector '{sel}' failed: {e}. Executing decay & fallbacks...")
                self.decay_selector(domain, query, sel)

        # 2. Fallback Attempt (Ranked Semantic Candidates)
        # Gather all visible elements of correct role/type and matching text
        candidates = self.gather_candidates(page)
        # Filter and sort by basic similarity
        fallback_candidates = [
            c for c in candidates 
            if c.is_visible and c.css_selector not in tried_selectors and
            (self._calculate_similarity(query, c.text) > 0.4 or self._calculate_similarity(query, c.placeholder) > 0.4)
        ]
        fallback_candidates.sort(key=lambda x: self._calculate_similarity(query, x.text), reverse=True)

        for c in fallback_candidates[:2]:
            sel = c.css_selector
            tried_selectors.append(sel)
            try:
                logger.info(f"SelectorResolver Fallback: Trying alternative candidate CSS '{sel}'")
                self._perform_action(page, sel, action_type, argument)
                self.remember_success(domain, query, sel, "css", 0.5)
                return True, sel, f"Success via alternative candidate: {sel}"
            except Exception as e:
                logger.debug(f"SelectorResolver Fallback: Alternative CSS '{sel}' failed: {e}")

        # 3. Fuzzy Text Matching Fallback
        # Query Playwright's native get_by_text search
        try:
            logger.info(f"SelectorResolver Fallback: Trying Playwright native get_by_text('{query}')")
            locator = page.get_by_text(query, exact=False).first
            if locator.count() > 0 and locator.is_visible():
                # We can perform action directly
                if action_type in ("click", "click_text", "click_index", "click_first_result"):
                    locator.click(timeout=5000)
                else:
                    locator.fill(argument)
                return True, f"get_by_text({query})", "Success via fuzzy native text locator"
        except Exception as e:
            logger.warning(f"SelectorResolver Fallback: Fuzzy text locator failed: {e}")

        # 4. Proximity / Native Role Fallback
        # E.g. find any button containing parts of the text query
        try:
            logger.info(f"SelectorResolver Fallback: Trying native button role matching")
            loc = page.get_by_role("button", name=query, exact=False).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=5000)
                return True, f"get_by_role(button, {query})", "Success via native button role fallback"
        except Exception as e:
            logger.warning(f"SelectorResolver Fallback: Button role locator failed: {e}")

        return False, "", "All fallback selectors failed"

    def _perform_action(self, page, selector: str, action_type: str, argument: str):
        """Helper to invoke Playwright action using selector."""
        from automation.element_classifier import ElementClassifier
        from automation.ui_state_engine import UIStateEngine
        
        locator = page.locator(selector).first
        locator.wait_for(state="visible", timeout=5000)
        
        # 1. Overlay Blocking check
        ui_state = UIStateEngine.inspect_page(page)
        if ui_state.pointer_blocked and ui_state.blocker_selector:
            # Check if selector element is nested under the blocking overlay
            try:
                is_nested = page.evaluate(f"""(sel, blocker) => {{
                    const el = document.querySelector(sel);
                    const bl = document.querySelector(blocker);
                    return bl && el && (bl === el || bl.contains(el));
                }}""", selector, ui_state.blocker_selector)
                if not is_nested:
                    raise ResolverExecutionError(f"Target element '{selector}' is blocked/obscured by overlay '{ui_state.blocker_selector}'.")
            except Exception as e:
                if isinstance(e, ResolverExecutionError):
                    raise
                pass

        # 2. Type / Fill safety verification
        if action_type in ("type", "fill", "search"):
            if not ElementClassifier.supports_typing(locator):
                # Raise clean exception to prevent typing into elements that don't support it
                raise ResolverExecutionError(f"Cannot type/fill into non-editable target element '{selector}' (type: {ElementClassifier.classify(locator).value}).")
            locator.fill(argument)
            if action_type == "search":
                locator.press("Enter")
        elif action_type in ("click", "click_text", "click_index", "click_first_result"):
            locator.click(timeout=5000)
        else:
            raise ValueError(f"Unknown action type: {action_type}")
