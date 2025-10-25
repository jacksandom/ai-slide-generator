"""LangGraph fan-out based HTML slide deck generator.

This module implements a fan-out/fan-in architecture using LangGraph's Send/Command
for true parallel processing of slide generation tasks.

Key improvements over the original:
- Native LangGraph parallelism using Send/Command
- Better error isolation and handling
- Cleaner state management
- More granular progress tracking
- Dynamic resource allocation
"""

from __future__ import annotations
import os
import json
import re
import time
import copy
import threading
import pandas as pd
from typing import List, Dict, Literal, Optional, Annotated, TypedDict, AsyncGenerator, Any
from pydantic import BaseModel, Field, conint
from dataclasses import dataclass, field

from bs4 import BeautifulSoup
from bs4.element import Tag
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, Command
from langgraph.config import get_stream_writer
from langchain.tools import tool
from databricks.sdk import WorkspaceClient
from operator import add

def merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Custom reducer for merging dictionaries in concurrent updates."""
    result = left.copy()
    result.update(right)
    return result

def merge_lists(left: List[str], right: List[str]) -> List[str]:
    """Custom reducer for merging lists in concurrent updates."""
    return left + right


# =========================
# Configuration and Constants
# =========================
HTML_CONSTRAINTS = """
You MUST return a single, complete HTML document for ONE slide. No markdown fences.

CDNs:
- Tailwind: <script src="https://cdn.tailwindcss.com"></script>
- Chart.js: <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
No other external JS.

CONTENT (strict):
- Exactly one <h1> title (≤ 55 characters), body text ≤ 40 words total.
- Professional, concise, scannable. One focal element.
- If you include data/metrics/trends, add ONE Chart.js chart.

CANVAS & LAYOUT:
- Slide size fixed to 1280x720 (720p), white #FFFFFF background.
- <body> styles: width:1280px; height:720px; margin:0; padding:0; overflow:hidden;
- Main container: max-width:1280px; max-height:720px; margin:0 auto;
- Content area: padding:16px; box-sizing:border-box;
- Use flex layout: column; justify-between; gap ≥ 12px; min-height:0 on flex children.
- All boxes/cards symmetrical; padding ≥16px; margin/gap ≥12px; border-radius 8–12px; shadow: 0 4px 6px rgba(0,0,0,.1); borders 1–2px #B2BAC0.
- Responsive within 1280x720; NO overflow or clipping. Wrap/ellipsize gracefully; never exceed viewport.

TYPOGRAPHY:
- Modern geometric sans (Inter/SF/Helvetica Now).
- H1 bold 40–52px; H2 28–36; H3 24–28; body 16–18; captions 12–14.
- Title color: Navy 900 #102025 ONLY (not gray). Subtitles: Navy 800 #2B3940. Body: #5D6D71; captions: #8D8E93.

BRAND PALETTE (hex):
Primary: Lava 600 #EB4A34; Lava 500 #EB6C53; Navy 900 #102025; Navy 800 #2B3940
Neutrals: Oat Light #F9FAFB; Oat Medium #E4E5E5; Gray-Text #5D6D71; Gray-Muted #8D8E93; Gray-Lines #B2BAC0; Gray-Nav #2B3940
Accents: Green 600 #4BA676; Yellow 600 #F2AE3D; Blue 600 #3C71AF; Maroon 600 #8C2330

USAGE RULES:
- Backgrounds: Oat Light; Oat Medium sparingly for bands/sidebars.
- Emphasis/callouts/buttons: Lava 600; hover/secondary: Lava 500.
- Status: Success=Green, Warning=Yellow, Info=Blue, Critical=Lava/Maroon (≤1 per slide).
- Maintain high contrast; ensure all colors visible on white.

CHART (only if needed):
- Types: bar/line/pie/doughnut/area/radar/scatter.
- Colors (brand): ['#EB4A34','#4BA676','#3C71AF','#F2AE3D'].
- Container with 12px outer margin; chart max-height 200px; maintainAspectRatio:false; labels, legend, tooltips enabled.
- Init example:
  new Chart(document.getElementById('chartCanvas'), {
    type: 'bar',
    data: { labels:[...], datasets:[{ label:'', data:[...], backgroundColor:['#EB4A34','#4BA676','#3C71AF','#F2AE3D'] }] },
    options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{display:true}, tooltip:{enabled:true} }, scales:{ x:{ ticks:{color:'#5D6D71'}}, y:{ ticks:{color:'#5D6D71'} } } }
  });

STRICT VALIDATION:
- One <h1> only, in Navy 900.
- No external deps beyond the two CDNs.
- No content overflow; nothing outside 1280x720; no horizontal scrollbars.
- Return ONLY the HTML document.
"""

ALLOWED_SCRIPT_SRC_SUBSTRINGS = ("tailwindcss.com", "chart.js")
ALLOWED_INLINE_SCRIPT_KEYWORDS = (
    "new chart",
    "chart.register",
    "chart.defaults",
    "chart.data",
    "chart.options",
    "chart.update",
    "tailwind.config",
)

# LLM Configuration
ws = WorkspaceClient(profile='logfood', product='slide-generator')
model_serving_client = ws.serving_endpoints.get_open_ai_client()

NLU_ENDPOINT = "databricks-gpt-oss-20b"
PLAN_ENDPOINT = "databricks-gpt-oss-20b" 
HTML_ENDPOINT = "databricks-claude-sonnet-4"

# Parallel Processing Configuration
DEFAULT_MAX_CONCURRENCY = 5  # Default max concurrent slide generations


# =========================
# Progress Tracking (Enhanced for Fan-out)
# =========================
class ProgressUpdate(BaseModel):
    """Progress update for streaming updates."""
    step: str
    progress_percent: int
    details: str = ""
    slides_completed: int = 0
    total_slides: int = 0
    elapsed_time: float = 0.0
    current_slide_title: str = ""
    error: Optional[str] = None
    branch_id: Optional[str] = None  # For tracking parallel branches

class FanOutProgressTracker:
    """Enhanced progress tracker for fan-out architecture."""
    
    def __init__(self, session_id: str, callback_func: Optional[callable] = None):
        self.session_id = session_id
        self.callback_func = callback_func
        self.start_time = time.time()
        self.current_step = ""
        self.progress_percent = 0
        self.slides_completed = 0
        self.total_slides = 0
        self.current_slide_title = ""
        self.last_update_time = 0
        self.pending_updates = []
        self._lock = threading.Lock()
        
        # Fan-out specific tracking
        self.branch_progress = {}  # branch_id -> progress info
        self.completed_branches = set()
        
    def update_progress(self, step: str, percent: int, details: str = "", 
                       slides_completed: int = None, total_slides: int = None,
                       current_slide_title: str = "", error: str = None, branch_id: str = None):
        """Update progress and send callback if available."""
        self.current_step = step
        self.progress_percent = percent
        self.current_slide_title = current_slide_title
        
        if slides_completed is not None:
            self.slides_completed = slides_completed
        if total_slides is not None:
            self.total_slides = total_slides
            
        elapsed_time = time.time() - self.start_time
        
        update = ProgressUpdate(
            step=step,
            progress_percent=percent,
            details=details,
            slides_completed=self.slides_completed,
            total_slides=self.total_slides,
            elapsed_time=elapsed_time,
            current_slide_title=current_slide_title,
            error=error,
            branch_id=branch_id
        )
        
        # Track branch progress for fan-out
        if branch_id:
            self.branch_progress[branch_id] = update
        
        # For async callbacks, always store updates (no throttling)
        import asyncio
        if self.callback_func and asyncio.iscoroutinefunction(self.callback_func):
            with self._lock:
                self.pending_updates.append(update)
                print(f"[PROGRESS] Stored pending update: {step} ({percent}%) - Branch: {branch_id}")
        elif self.callback_func and (time.time() - self.last_update_time > 1.0 or error):
            # For sync callbacks, throttle updates
            try:
                self.callback_func(update)
                self.last_update_time = time.time()
            except Exception as e:
                print(f"[PROGRESS] Error sending progress update: {e}")
    
    def set_total_slides(self, total: int):
        """Set the total number of slides to be generated."""
        self.total_slides = total
        print(f"[PROGRESS] Set total slides to {total}")
    
    def complete_slide(self, slide_title: str, branch_id: str = None):
        """Mark a slide as completed."""
        self.slides_completed += 1
        if branch_id:
            self.completed_branches.add(branch_id)
        
        self.update_progress(
            step=f"Completed slide {self.slides_completed}/{self.total_slides}",
            percent=int((self.slides_completed / max(self.total_slides, 1)) * 80) + 10,  # 10-90% range
            details=f"Finished: {slide_title}",
            current_slide_title=slide_title,
            branch_id=branch_id
        )
        print(f"[PROGRESS] Completed slide {self.slides_completed}/{self.total_slides}: {slide_title} (Branch: {branch_id})")
    
    def get_pending_updates(self):
        """Get and clear all pending updates."""
        with self._lock:
            updates = self.pending_updates.copy()
            self.pending_updates.clear()
            return updates
    
    def get_branch_progress(self, branch_id: str) -> Optional[ProgressUpdate]:
        """Get progress for a specific branch."""
        return self.branch_progress.get(branch_id)


# =========================
# Pydantic Models (Reused from original)
# =========================
class SlideTheme(BaseModel):
    """Theme configuration for slide decks."""
    bottom_right_logo_url: Optional[str] = None
    footer_text: Optional[str] = None

class SlideConfig(BaseModel):
    """Configuration for slide generation."""
    topic: Optional[str] = None
    style_hint: Optional[str] = None
    n_slides: Optional[conint(ge=1, le=40)] = None

class SlideChange(BaseModel):
    """Represents a change to be applied to a slide."""
    slide_id: Optional[int] = None
    operation: Literal[
        "REPLACE_TITLE", "REPLACE_BULLETS", "APPEND_BULLET", "DELETE_BULLET",
        "INSERT_IMAGE", "EDIT_RAW_HTML", "INSERT_SLIDE_AFTER", "DELETE_SLIDE",
        "REORDER_SLIDES"
    ]
    args: dict = Field(default_factory=dict)

class SlideTodo(BaseModel):
    """Represents a todo item for slide generation."""
    id: int
    action: Literal["WRITE_SLIDE", "FINALIZE_DECK"]
    title: str
    details: str = ""
    depends_on: List[int] = Field(default_factory=list)

class UserIntent(BaseModel):
    """Represents the user's intent from their message."""
    intent: Literal[
        "REQUEST_DECK", "REFINE_CONFIG", "ADD_CHANGES",
        "REGENERATE_TODOS", "FINALIZE", "SAVE", "SHOW_STATUS"
    ]
    config_delta: SlideConfig = SlideConfig()
    changes: List[SlideChange] = Field(default_factory=list)
    notes: Optional[str] = None

class SlideStatus(BaseModel):
    """Status of a slide in the deck."""
    id: int  # Artifact ID (internal)
    position: int  # User-visible slide number (1, 2, 3...)
    title: str
    html: str  # Complete HTML document
    is_generated: bool = False
    is_valid: bool = False


# =========================
# Fan-out State Management
# =========================
class FanOutSlideState(TypedDict):
    """State for the fan-out slide generation agent."""
    # Core configuration
    config: SlideConfig
    config_version: int
    
    # User interaction
    messages: List[Dict[str, str]]
    last_intent: Optional[str]
    
    # Generation state
    todos: List[SlideTodo]
    artifacts: Dict[int, str]  # slide_id -> HTML content
    pending_changes: List[SlideChange]
    
    # Status and metadata
    status: List[SlideStatus]
    errors: List[str]
    metrics: Dict[str, float]
    run_id: str
    
    # Progress tracking
    progress_tracker: Optional[FanOutProgressTracker]
    
    # Fan-out specific - use Annotated for concurrent list updates
    parallel_results: Annotated[List[Dict[str, Any]], add]  # Results from parallel branches


# =========================
# Utility Functions (Reused from original)
# =========================
def _is_allowed_inline_script(tag: Tag) -> bool:
    """Check if an inline script is allowed."""
    text = (tag.get_text() or "").strip().lower()
    if not text:
        return False
    return any(keyword in text for keyword in ALLOWED_INLINE_SCRIPT_KEYWORDS)

def _extract_text_from_response(content) -> str:
    """Extract text content from various response formats."""
    if isinstance(content, str):
        return content
    
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                return item.get('text', '')
            elif isinstance(item, dict) and 'text' in item:
                return item['text']
    
    return str(content)

def _clean_markdown_fences(content: str) -> str:
    """Remove markdown code fences from content."""
    content = content.strip()
    
    # Remove opening fence
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```html"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    
    # Remove closing fence (strip again after removing opening fence)
    content = content.strip()
    if content.endswith("```"):
        content = content[:-3]
    
    return content.strip()


# =========================
# Data Integration (Reused from original)
# =========================
def query_genie_space(question: str, space_id: str = "01effebcc2781b6bbb749077a55d31e3", workspace_client: WorkspaceClient = ws) -> str:
    """Query Genie space for data and return as JSON."""
    try:
        response = workspace_client.genie.start_conversation_and_wait(
            space_id=space_id,
            content=question
        )

        conversation_id = response.conversation_id
        message_id = response.message_id
        attachment_ids = [_.attachment_id for _ in response.attachments]

        response = workspace_client.genie.get_message_attachment_query_result(
            space_id=space_id,
            conversation_id=conversation_id,
            message_id=message_id,
            attachment_id=attachment_ids[0]
        )
        response = response.as_dict()['statement_response']
        columns = [_['name'] for _ in response['manifest']['schema']['columns']]
        data = response['result']['data_array']
        df = pd.DataFrame(data, columns=columns)
        output = df.to_json(orient='records')
        
        print(f"[GENIE] Successfully fetched data: {len(data)} rows")
        return output
    except Exception as e:
        print(f"[GENIE] Error querying Genie space: {e}")
        return "[]"

def _detect_data_need(title: str, outline: str) -> Optional[str]:
    """Use LLM to detect if slide needs data and construct an optimized Genie query."""
    
    system_prompt = """You are a data needs analyzer for presentation slides. Your job is to determine if a slide requires actual data from a database and, if so, create a natural language query for Databricks Genie.

                        DECISION CRITERIA:
                        - Slides with charts, graphs, tables, metrics, KPIs, statistics → NEED DATA
                        - Slides with rankings (top 10, bottom 5), comparisons, trends → NEED DATA  
                        - Slides with business metrics (revenue, sales, customers, etc.) → NEED DATA
                        - Slides with questions (how many, what are, etc.) → NEED DATA
                        - Slides with only text, concepts, mission statements, strategies → NO DATA

                        QUERY CONSTRUCTION:
                        - Keep queries concise and clear (under 200 characters)
                        - Use natural language that Genie can understand
                        - Examples: "show top 10 products by revenue", "get customer count by region", "revenue trend over last 12 months"

                        OUTPUT FORMAT:
                        Return ONLY a JSON object:
                        {"needs_data": true/false, "query": "your query here or null"}

                        Examples:
                        Input: Title="Revenue Analysis", Outline="Show revenue by product category"
                        Output: {"needs_data": true, "query": "show revenue by product category"}

                        Input: Title="Company Mission", Outline="Our vision and values"  
                        Output: {"needs_data": false, "query": null}

                        Input: Title="Top Performers", Outline="top 5 sales reps this quarter"
                        Output: {"needs_data": true, "query": "show top 5 sales representatives by sales this quarter"}"""

    user_prompt = f"""Slide Title: {title}
                        Slide Outline: {outline}

                        Determine if this slide needs data and create a query if needed."""

    try:
        response = model_serving_client.chat.completions.create(
            model=NLU_ENDPOINT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0  # Deterministic output
        )
        
        content = _extract_text_from_response(response.choices[0].message.content)
        content = _clean_markdown_fences(content)
        
        # Parse the JSON response
        result = json.loads(content)
        
        if result.get("needs_data") and result.get("query"):
            query = result["query"].strip()
            print(f"[DATA_DETECTION] Data needed - Query: '{query}'")
            return query
        else:
            print(f"[DATA_DETECTION] No data needed for slide: {title}")
            return None
            
    except json.JSONDecodeError as e:
        print(f"[DATA_DETECTION] JSON parse error: {e}, content: {content[:200]}")
        return None
    except Exception as e:
        print(f"[DATA_DETECTION] Error: {e}")
        return None


# =========================
# LangGraph Tools (Reused from original)
# =========================
@tool("interpret_user_intent", return_direct=False)
def interpret_user_intent(messages: List[Dict[str, str]], current_config: SlideConfig) -> UserIntent:
    """Interpret user messages and extract intent, config changes, and slide modifications."""
    # System prompt (unchanged as per requirements)
    sys = (
        "You are an intent recognizer for a slides agent. "
        "From chat messages, extract intent + config deltas (topic/style/n_slides) and changes. "
        "Valid intents: REQUEST_DECK, REFINE_CONFIG, ADD_CHANGES, REGENERATE_TODOS, FINALIZE, SAVE, SHOW_STATUS. "
        "\n\nINTENT CLASSIFICATION RULES:\n"
        "- REQUEST_DECK: User wants to create a NEW slide deck (first slide or completely new topic)\n"
        "  Examples: 'create slides on...', 'make a presentation about...', 'Slide 1 title:...' (when no existing deck)\n"
        "- ADD_CHANGES: User wants to ADD slides to existing deck or MODIFY existing slides\n"
        "  Examples: 'Slide 2 title:...', 'add another slide...', 'change the title to...', 'update slide 2...'\n"
        "\nCRITICAL CLASSIFICATION LOGIC:\n"
        "- If user mentions 'Slide 2', 'Slide 3', etc. AND there are existing slides → ADD_CHANGES\n"
        "- If user says 'add', 'another', 'next slide' → ADD_CHANGES\n"
        "- If user provides detailed content for a slide numbered 2+ → ADD_CHANGES\n"
        "- Only use REQUEST_DECK for Slide 1 or completely new topics\n"
        "\nIMPORTANT: When user requests slide creation (REQUEST_DECK), extract:\n"
        "- topic: The main subject/topic of the presentation\n"
        "- style_hint: The style description (professional, clean, modern, etc.)\n"
        "- n_slides: Number of slides requested (default to 1 if not specified)\n"
        "\nCRITICAL FOR DETAILED REQUESTS:\n"
        "- If user provides specific slide content, titles, bullet points, metrics, data, etc., "
        "capture ALL of this information in the topic field\n"
        "- Preserve exact wording, numbers, company names, section headings, and specifications\n"
        "- Do not summarize or modify the user's detailed instructions\n"
        "- The topic field should contain the complete user specification for slide generation\n"
        "\nMULTI-SLIDE DETECTION:\n"
        "- If user mentions 'first slide' and 'second slide' or 'create a second slide', "
        "this indicates multiple distinct slides with different content\n"
        "- Extract the complete specification for each slide in the topic field\n"
        "- Count the number of distinct slide requests to determine n_slides\n"
        "- Example: 'create first slide about X, create a second slide about Y' → n_slides=2, topic='first slide about X, second slide about Y'"
        "\n**CRITICAL: OPERATION TYPE DETECTION**\n"
        "For ADD_CHANGES intent, you MUST correctly identify the operation:\n\n"
        "USE INSERT_SLIDE_AFTER when user says:\n"
        "- 'add another slide', 'add a new slide', 'create another slide'\n"
        "- 'insert slide', 'add slide 4', 'create slide about X'\n"
        "- 'make a slide showing', 'add a slide to show'\n"
        "Format: {\"operation\": \"INSERT_SLIDE_AFTER\", \"slide_id\": N, \"args\": {\"title\": \"...\", \"content\": \"user's full request\"}}\n"
        "**IMPORTANT: For INSERT_SLIDE_AFTER, slide_id determines position:**\n"
        "  - slide_id = 0: Insert at the beginning (before slide 1)\n"
        "  - slide_id = N: Insert after slide N (e.g., slide_id=1 inserts after slide 1, becoming new slide 2)\n"
        "  - slide_id = current_n_slides: Append at the end (most common for 'add another slide')\n"
        "  - If user says 'add another slide' or 'create another slide', use slide_id = current_n_slides to append\n\n"
        "USE EDIT_RAW_HTML when user says:\n"
        "- 'change slide 1', 'update the title', 'modify slide 2'\n"
        "- 'in slide 1 add', 'on slide 2 change', 'fix slide 3'\n"
        "Format: {\"operation\": \"EDIT_RAW_HTML\", \"slide_id\": N, \"args\": {\"description\": \"change description\"}}\n\n"
        "USE DELETE_SLIDE when user says:\n"
        "- 'delete slide 5', 'remove slide 3', 'delete the last slide'\n"
        "- 'remove the slide about X', 'get rid of slide 2'\n"
        "Format: {\"operation\": \"DELETE_SLIDE\", \"slide_id\": N, \"args\": {}}\n"
        "\nExamples:\n"
        "- 'create 2 slides on AI and Machine Learning' → REQUEST_DECK, topic='AI and Machine Learning', n_slides=2\n"
        "- 'add another slide to show revenue trends' (when current_n_slides=3) → ADD_CHANGES, INSERT_SLIDE_AFTER with slide_id=3\n"
        "- 'insert a slide after slide 1 about benefits' → ADD_CHANGES, INSERT_SLIDE_AFTER with slide_id=1\n"
        "- 'Slide 2 title: KEY BENEFITS...' → ADD_CHANGES, INSERT_SLIDE_AFTER with slide_id=1\n"
        "- 'change the title to Machine Learning' → ADD_CHANGES, EDIT_RAW_HTML\n"
        "- 'in slide 1 add icons' → ADD_CHANGES, EDIT_RAW_HTML for slide_id=1\n"
        "- 'delete slide 5' → ADD_CHANGES, DELETE_SLIDE with slide_id=5\n"
        "\nReturn JSON with intent, config_delta (with topic/style_hint/n_slides), and changes array."
    )
    
    # Check if there are existing slides
    has_existing_slides = bool(current_config.topic and current_config.topic.strip())
    
    # Get current number of slides for the LLM
    current_n_slides = current_config.n_slides or 0
    
    # Build user prompt
    user = f"""Messages (recent last):
            {json.dumps(messages[-12:], ensure_ascii=False, indent=2)}

            Current config: {current_config.model_dump()}
            Has existing slides: {has_existing_slides}
            Current number of slides (current_n_slides): {current_n_slides}

            CRITICAL INSTRUCTIONS:
            1. ONLY extract intent and changes from the LAST (most recent) user message
            2. DO NOT include changes from previous messages in the conversation history
            3. If the user is requesting 'Slide 2', 'Slide 3', etc. AND has_existing_slides=True, classify as ADD_CHANGES
            4. For simple edits like "In slide 1 change X", return ONLY ONE change with operation=EDIT_RAW_HTML
            5. For new slide requests like "add another slide", return ONLY ONE change with operation=INSERT_SLIDE_AFTER
            6. For INSERT_SLIDE_AFTER with "add another slide", use slide_id = current_n_slides (to append at end)"""
                    
    # Call LLM
    response = model_serving_client.chat.completions.create(
        model=NLU_ENDPOINT,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": user}
        ]
    )
    
    print(f"[NLU] Current config: {current_config}")
    content = _extract_text_from_response(response.choices[0].message.content)
    content = _clean_markdown_fences(content)
    
    print(f"[NLU] Raw LLM response: {content[:500]}")  # Debug: show first 500 chars
    
    try:
        data = json.loads(content)
        print(f"[NLU] Parsed JSON: intent={data.get('intent')}, changes={data.get('changes')}")
        
        # 1. Validate and fix intent
        valid_intents = ["REQUEST_DECK", "REFINE_CONFIG", "ADD_CHANGES", "REGENERATE_TODOS", "FINALIZE", "SAVE", "SHOW_STATUS"]
        if data.get("intent") not in valid_intents:
            print(f"[NLU] Invalid intent '{data.get('intent')}', defaulting to REQUEST_DECK")
            data["intent"] = "REQUEST_DECK"
        
        # 2. Normalize config_delta field name
        if "config_deltas" in data and "config_delta" not in data:
            data["config_delta"] = data.pop("config_deltas")
        
        # 3. Parse changes using helper functions
        parsed_changes = []
        if "changes" in data:
            if isinstance(data["changes"], dict):
                parsed_changes = _parse_change_from_dict(data["changes"])
            elif isinstance(data["changes"], list):
                parsed_changes = _parse_change_from_list(data["changes"])
        
        # 4. Fallback: Create change from user message if ADD_CHANGES but no changes parsed
        if data.get("intent") == "ADD_CHANGES" and not parsed_changes:
            latest_message = messages[-1]["content"] if messages else ""
            if latest_message.strip():
                # Check if this is a new slide request
                is_new_slide = _is_new_slide_indicator(latest_message, 0)  # Use 0 as placeholder
                
                # For new slides, default to adding after the last slide (use current n_slides)
                if is_new_slide:
                    # Get the current number of slides from config
                    current_n_slides = current_config.n_slides or 0
                    slide_id = current_n_slides  # Will insert AFTER this slide
                else:
                    # For edits, extract the specific slide ID or default to 1
                    slide_id = _extract_slide_id_from_message(latest_message, default=1)
                
                fallback_change = _create_fallback_change(latest_message, slide_id, is_new_slide)
                parsed_changes.append(fallback_change)
                print(f"[NLU] Fallback change created: operation={fallback_change['operation']}, slide_id={slide_id}")
        
        # 5. Enhanced slide ID handling: Update changes with correct slide IDs (ONLY if needed)
        # IMPORTANT: Only apply this fix if changes are missing slide_ids or operations
        # If the LLM returned well-formed changes, don't modify them!
        if data.get("intent") == "ADD_CHANGES" and parsed_changes:
            # Check if any changes need fixing (missing slide_id or operation)
            needs_fixing = any(
                change.get("slide_id") is None or change.get("operation") is None
                for change in parsed_changes
            )
            
            if needs_fixing:
                latest_message = messages[-1]["content"] if messages else ""
                target_slide_id = _extract_slide_id_from_message(latest_message, default=None)
                
                if target_slide_id:
                    for change in parsed_changes:
                        # Only update if the change doesn't already have a slide_id
                        # This prevents overwriting correctly parsed changes
                        if change.get("slide_id") is None:
                            _update_change_with_slide_id(change, target_slide_id, latest_message)
        
        data["changes"] = parsed_changes
        
        print(f"[NLU] Parsed - intent: {data.get('intent')}, changes: {len(parsed_changes)}")
        for i, change in enumerate(parsed_changes):
            print(f"[NLU]   Change {i+1}: operation={change.get('operation')}, slide_id={change.get('slide_id')}")
        return UserIntent(**data)
    
    except json.JSONDecodeError as e:
        print(f"[NLU] JSON parse error: {e}, content preview: {content[:200]}")
        return UserIntent(intent="REQUEST_DECK")
    except Exception as e:
        print(f"[NLU] Unexpected error: {e}")
        return UserIntent(intent="REQUEST_DECK")

@tool("create_slide_todos", return_direct=False)
def create_slide_todos(topic: str, style_hint: str, n_slides: int) -> List[SlideTodo]:
    """Create a list of todos for slide generation."""
    sys = (
        "Return ordered JSON TODOs as an array. Each todo must have: "
        "id (integer), action (WRITE_SLIDE or FINALIZE_DECK), title (string), "
        "details (string), depends_on (array of integers). "
        "First N: WRITE_SLIDE; last: FINALIZE_DECK depending on prior ids. "
        "Titles <= 8 words; bullets concise. Return only JSON."
        "\n\nCRITICAL: Preserve ALL user-provided content in the details field. "
        "Include exact specifications, bullet points, metrics, data, section headings, "
        "company names, and any other specific instructions provided by the user. "
        "Do not summarize or modify the user's content - capture it completely."
        "\n\nMULTI-SLIDE REQUESTS:"
        "If the user provides detailed specifications for multiple slides, "
        "create separate todos for each slide with distinct titles and content. "
        "Each slide should have its own unique title and detailed specifications."
    )
    user = f"Topic: {topic}\nStyle: {style_hint}\nSlides requested: {n_slides}\nReturn EXACTLY {n_slides+1} items."
    
    response = model_serving_client.chat.completions.create(
        model=PLAN_ENDPOINT,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": user}
        ]
    )
    
    content = _extract_text_from_response(response.choices[0].message.content)
    content = _clean_markdown_fences(content)
    
    try:
        data = json.loads(content)
        if not isinstance(data, list):
            data = [data]
        
        # Validate and fix each todo
        valid_actions = ["WRITE_SLIDE", "FINALIZE_DECK"]
        for i, item in enumerate(data):
            if i < n_slides:
                item["action"] = "WRITE_SLIDE"
            else:
                item["action"] = "FINALIZE_DECK"
            item["id"] = item.get("id") if isinstance(item.get("id"), int) else i + 1
            item["depends_on"] = item.get("depends_on") if isinstance(item.get("depends_on"), list) else []
        
        return [SlideTodo(**item) for item in data]
    
    except Exception as e:
        print(f"Error creating todos: {e}")
        return []

@tool("generate_slide_html", return_direct=False)
def generate_slide_html(title: str, outline: str, style_hint: str, space_id: Optional[str] = "01effebcc2781b6bbb749077a55d31e3") -> str:
    """Generate complete HTML document for a single slide, fetching data from Genie if needed."""
    
    # Check if slide needs data
    data_query = _detect_data_need(title, outline)
    fetched_data = None
    
    if data_query:
        print(f"[GENERATION] Data needed for slide '{title}', querying Genie...")
        print(f"[GENERATION] Query: {data_query}")
        fetched_data = query_genie_space(data_query, space_id=space_id)
        if fetched_data and fetched_data != "[]":
            print(f"[GENERATION] Data fetched successfully")
            outline = f"{outline}\n\nDATA (use this actual data):\n{fetched_data}"
        else:
            print(f"[GENERATION] No data returned from Genie, proceeding without data")
    
    sys = "Create a complete HTML document for a single slide." + HTML_CONSTRAINTS
    
    user = f"""TITLE: {title}
                OUTLINE: {outline}
                STYLE: {style_hint}

                CRITICAL INSTRUCTIONS:
                - Use ONLY the content provided above - do not add, modify, or hallucinate any data
                - If specific metrics, numbers, or data points are provided, use them exactly as given
                - If DATA section is provided above, use that ACTUAL data - do not create fictional data
                - If bullet points are specified, include them exactly as listed
                - If section headings are provided, use them exactly as specified
                - If company names, logos, or branding are mentioned, include them as specified
                - Do not create fictional data, statistics, or content not explicitly provided
                - Maintain the exact structure and content hierarchy as specified in the outline
                - Use Tailwind CSS with the brand colors and styling specified in the constraints
                - If data is provided, visualize it using Chart.js with appropriate chart type

                Create a beautiful, modern slide using Tailwind CSS with the exact brand colors and spacing specified. Ensure all content fits within 1280x720 pixels with proper contrast and visibility. Use white background and symmetrical layout. IMPORTANT: Use Navy 900 (#102025) for the main title, NOT gray colors."""
    
    response = model_serving_client.chat.completions.create(
        model=HTML_ENDPOINT,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": user}
        ]
    )
    
    content = _extract_text_from_response(response.choices[0].message.content)
    return _clean_markdown_fences(content)

@tool("validate_slide_html", return_direct=False)
def validate_slide_html(html: str) -> bool:
    """Validate HTML content for a slide."""
    soup = BeautifulSoup(html, "lxml")
    
    # Check for complete HTML document structure
    if not soup.find("html") or not soup.find("head") or not soup.find("body"):
        return False
    
    # Check for main heading
    if len(soup.find_all("h1")) != 1:
        return False
    
    # Check for content
    if not (soup.select("ul li") or soup.select("p") or soup.select("div")):
        return False
    
    # Check for required scripts
    if not soup.find("script", src=lambda x: x and "tailwindcss.com" in x):
        return False
    if not soup.find("script", src=lambda x: x and "chart.js" in x):
        return False
    
    # Check for proper viewport constraints
    body = soup.find("body")
    if body:
        style = body.get("style", "")
        if not ("width: 1280px" in style or "width:1280px" in style):
            return False
        if not ("height: 720px" in style or "height:720px" in style):
            return False
        if not ("overflow: hidden" in style or "overflow:hidden" in style):
            return False
    
    # Security checks
    for tag in soup(True):
        for attr in list(tag.attrs.keys()):
            if attr.lower().startswith("on"):
                return False
            if attr.lower() in {"href", "src"} and str(tag.attrs[attr]).strip().lower().startswith("javascript:"):
                return False
    
    return True

@tool("sanitize_slide_html", return_direct=False)
def sanitize_slide_html(html: str) -> str:
    """Sanitize HTML content by removing dangerous attributes."""
    soup = BeautifulSoup(html, "lxml")
    
    # Keep allowed scripts, remove others
    for script in soup.find_all("script"):
        src = script.get("src")
        if src:
            if not any(needle in src for needle in ALLOWED_SCRIPT_SRC_SUBSTRINGS):
                script.decompose()
        elif not _is_allowed_inline_script(script):
            script.decompose()
    
    # Remove dangerous attributes
    for tag in soup(True):
        for attr in list(tag.attrs.keys()):
            if attr.lower().startswith("on"):
                del tag.attrs[attr]
            if attr.lower() in {"href", "src"} and isinstance(tag.attrs[attr], str) and tag.attrs[attr].strip().lower().startswith("javascript:"):
                del tag.attrs[attr]
    
    return str(soup)

@tool("apply_slide_change", return_direct=False)
def apply_slide_change(slide_html: str, change: SlideChange, style_hint: str) -> str:
    """Apply a change to a slide using LLM."""
    sys = "Apply a slide change while maintaining beautiful Tailwind CSS design." + HTML_CONSTRAINTS
    user = f"""CURRENT SLIDE:
            {slide_html}

            CHANGE: {change.model_dump_json()}
            STYLE: {style_hint}

            CRITICAL INSTRUCTIONS:
            - Apply ONLY the specific change requested - do not add, modify, or hallucinate any data
            - If the change specifies exact content, use it exactly as provided
            - If metrics, numbers, or data points are specified, use them exactly as given
            - If bullet points are specified, include them exactly as listed
            - If section headings are provided, use them exactly as specified
            - Do not create fictional data, statistics, or content not explicitly provided
            - Maintain the exact structure and content hierarchy as specified in the change
            - Use Tailwind CSS with the brand colors and styling specified in the constraints

            Apply the change while keeping the modern Tailwind CSS styling and design."""
    
    response = model_serving_client.chat.completions.create(
        model=HTML_ENDPOINT,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": user}
        ]
    )
    
    content = _extract_text_from_response(response.choices[0].message.content)
    return _clean_markdown_fences(content)


# =========================
# Helper Functions (Reused from original)
# =========================
def _extract_slide_id_from_message(message: str, default: int = 1) -> int:
    """Extract slide ID from message using various patterns."""
    patterns = [
        r'(?:in\s+)?slide\s+(\d+)',   # "slide 1", "in slide 1"
        r'for\s+slide\s+(\d+)',        # "for slide 2"
        r'to\s+slide\s+(\d+)',         # "to slide 3"
        r'on\s+slide\s+(\d+)',         # "on slide 4"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return default

def _is_new_slide_indicator(message: str, slide_id: int) -> bool:
    """Check if message contains indicators of new slide creation."""
    message_lower = message.lower()
    
    # Strong indicators that this is a new slide, not an edit
    new_slide_keywords = [
        "title:",
        "bullets:",
        "new slide",
        "add slide",
        "add another slide",
        "add a slide",
        "create slide",
        "create another slide",
        "insert slide",
        "make a slide",
        "make another slide",
        f"slide {slide_id} title:",
        f"slide {slide_id} —",
        f"slide {slide_id}:",
    ]
    
    return any(keyword in message_lower for keyword in new_slide_keywords)

def _parse_change_from_dict(changes_dict: dict) -> List[dict]:
    """Parse changes from dict format: {"slide": N, "actions": [...]}."""
    parsed = []
    
    if "slide" in changes_dict and "actions" in changes_dict:
        slide_id = changes_dict["slide"]
        actions = changes_dict["actions"]
        if isinstance(actions, list):
            for action in actions:
                parsed.append({
                    "slide_id": slide_id,
                    "operation": "EDIT_RAW_HTML",
                    "args": {"description": action}
                })
    
    return parsed

def _parse_change_from_list(changes_list: list) -> List[dict]:
    """Parse changes from list format with various item types."""
    parsed = []
    
    for item in changes_list:
        # String format: convert to EDIT_RAW_HTML on slide 1
        if isinstance(item, str):
            parsed.append({
                "slide_id": 1,
                "operation": "EDIT_RAW_HTML",
                "args": {"description": item}
            })
        
        # Dict format: multiple sub-formats
        elif isinstance(item, dict):
            # {"slide_number": N, "description": "..."}
            if "slide_number" in item and "description" in item:
                parsed.append({
                    "slide_id": item["slide_number"],
                    "operation": "EDIT_RAW_HTML",
                    "args": {"description": item["description"]}
                })
            
            # {"slide_id": N, "operation": "...", "args": {...}}
            elif "slide_id" in item and "operation" in item:
                parsed.append(item)
    
    return parsed

def _create_fallback_change(message: str, slide_id: int, is_new_slide: bool) -> dict:
    """Create a fallback change when LLM doesn't provide structured changes."""
    if is_new_slide:
        return {
            "slide_id": slide_id,
            "operation": "INSERT_SLIDE_AFTER",
            "args": {
                "title": f"Slide {slide_id}",
                "content": message,
                "bullets": []
            }
        }
    else:
        return {
            "slide_id": slide_id,
            "operation": "EDIT_RAW_HTML",
            "args": {"description": message}
        }

def _update_change_with_slide_id(change: dict, target_slide_id: int, message: str) -> None:
    """Update a change dict with correct slide ID and operation in-place."""
    if change.get("operation") != "EDIT_RAW_HTML":
        return
    
    # Check if this is actually a new slide request
    if _is_new_slide_indicator(message, target_slide_id):
        change["operation"] = "INSERT_SLIDE_AFTER"
        change["slide_id"] = target_slide_id
        change["args"] = {
            "title": f"Slide {target_slide_id}",
            "content": message,
            "bullets": []
        }
    else:
        # Just update the slide ID for editing
        change["slide_id"] = target_slide_id


# =========================
# Fan-out LangGraph Nodes
# =========================
def nlu_node(state: FanOutSlideState) -> FanOutSlideState:
    """Natural Language Understanding node - interprets user intent."""
    last_message = state['messages'][-1]['content'] if state['messages'] else ""
    print(f"[NLU] Processing last message: '{last_message[:80]}...'") if len(last_message) > 80 else print(f"[NLU] Processing last message: '{last_message}'")
    
    try:
        intent = interpret_user_intent.invoke({
            "messages": state["messages"],
            "current_config": state["config"]
        })
        
        state["last_intent"] = intent.intent
        
        # Update config if changed
        config_changed = False
        if intent.config_delta.topic and intent.config_delta.topic != state["config"].topic:
            state["config"].topic = intent.config_delta.topic
            config_changed = True
        if intent.config_delta.style_hint and intent.config_delta.style_hint != state["config"].style_hint:
            state["config"].style_hint = intent.config_delta.style_hint
            config_changed = True
        if intent.config_delta.n_slides and intent.config_delta.n_slides != state["config"].n_slides:
            state["config"].n_slides = intent.config_delta.n_slides
            config_changed = True
        
        # Ensure style_hint has a default value
        if state["config"].style_hint is None:
            state["config"].style_hint = "professional clean"
            config_changed = True
        
        if config_changed:
            state["config_version"] += 1
            state["todos"] = []
            state["artifacts"] = {}
        
        state["pending_changes"] = intent.changes
        
        print(f"[NLU] Intent: {intent.intent}, Config changed: {config_changed}, Changes: {len(intent.changes)}")
        
    except Exception as e:
        print(f"[NLU] Error: {e}")
        state["errors"].append(f"NLU error: {str(e)}")
    
    return state

def planning_node(state: FanOutSlideState) -> FanOutSlideState:
    """Planning node - creates todos for slide generation."""
    print(f"[PLANNING] Creating todos for topic: {state['config'].topic}")
    
    try:
        if (state["config"].topic and 
            state["config"].n_slides and 
            not state["todos"]):
            
            # Get progress tracker from state if available
            progress_tracker = state.get("progress_tracker")
            if progress_tracker:
                progress_tracker.update_progress(
                    step="Planning slides",
                    percent=10,
                    details=f"Creating plan for {state['config'].n_slides} slides about {state['config'].topic}"
                )
            
            todos = create_slide_todos.invoke({
                "topic": state["config"].topic,
                "style_hint": state["config"].style_hint or "professional clean",
                "n_slides": state["config"].n_slides
            })
            
            state["todos"] = todos
            
            # Set total slides for progress tracking
            if progress_tracker:
                slide_todos = [t for t in todos if t.action == "WRITE_SLIDE"]
                progress_tracker.set_total_slides(len(slide_todos))
                progress_tracker.update_progress(
                    step="Planning complete",
                    percent=15,
                    details=f"Created plan for {len(slide_todos)} slides"
                )
            
            print(f"[PLANNING] Created {len(todos)} todos")
            print(f"[PLANNING] Todo IDs: {[t.id for t in todos if t.action == 'WRITE_SLIDE']}")
        
    except Exception as e:
        print(f"[PLANNING] Error: {e}")
        state["errors"].append(f"Planning error: {str(e)}")
        
        # Update progress with error
        progress_tracker = state.get("progress_tracker")
        if progress_tracker:
            progress_tracker.update_progress(
                step="Planning failed",
                percent=0,
                details=f"Error creating plan: {str(e)}",
                error=str(e)
            )
    
    return state

def fan_out_generation(state: FanOutSlideState) -> Command:
    """Fan-out node: creates parallel slide generation tasks using Send/Command."""
    print(f"[FAN-OUT] Starting fan-out generation")
    
    slide_todos = [t for t in state["todos"] if t.action == "WRITE_SLIDE"]
    
    # Filter out slides that already exist
    todos_to_generate = [t for t in slide_todos if t.id not in state["artifacts"]]
    
    if not todos_to_generate:
        print(f"[FAN-OUT] All slides already generated")
        return Command(goto="join_results")
    
    # Get progress tracker from state if available
    progress_tracker = state.get("progress_tracker")
    
    print(f"[FAN-OUT] Fanning out {len(todos_to_generate)} slides for parallel generation")
    
    # Update progress for generation start
    if progress_tracker:
        progress_tracker.update_progress(
            step="Starting parallel generation",
            percent=20,
            details=f"Fanning out {len(todos_to_generate)} slides for parallel processing"
        )
    
    # Create Send commands for each slide
    sends = []
    for todo in todos_to_generate:
        # Create isolated state slice for each parallel branch
        branch_state = {
            "todo": todo,
            "config": state["config"],
            "progress_tracker": progress_tracker,
            "branch_id": f"slide_{todo.id}"
        }
        sends.append(Send("generate_slide", branch_state))
    
    print(f"[FAN-OUT] Created {len(sends)} parallel branches")
    return Command(goto=sends)

def generate_slide(state: FanOutSlideState) -> Command:
    """Worker node: generates a single slide with parallel Genie calls."""
    todo = state["todo"]
    branch_id = state.get("branch_id", f"slide_{todo.id}")
    progress_tracker = state.get("progress_tracker")
    
    print(f"[GENERATE_SLIDE] Generating slide {todo.id}: {todo.title} (Branch: {branch_id})")
    
    try:
        # Get stream writer for real-time updates
        try:
            writer = get_stream_writer()
            if writer:
                writer(f"Starting generation of slide: {todo.title}")
                print(f"[GENERATE_SLIDE] Stream writer: Starting generation of slide: {todo.title}")
        except Exception as e:
            writer = None
            print(f"[GENERATE_SLIDE] Stream writer failed: {e}")
        
        # Check if data is needed and create parallel Genie calls
        print(f"[GENERATE_SLIDE] Detecting data need for slide: {todo.title}")
        data_query = _detect_data_need(todo.title, todo.details)
        print(f"[GENERATE_SLIDE] Data query result: {data_query}")
        
        if data_query:
            # Create parallel Genie calls using Send/Command
            print(f"[GENERATE_SLIDE] Creating parallel Genie calls for slide: {todo.title}")
            
            # Create state for Genie query
            genie_state = {
                "todo": todo,
                "data_query": data_query,
                "config": state["config"],
                "progress_tracker": progress_tracker,
                "branch_id": branch_id,
                "writer": writer
            }
            
            # Send to Genie query node
            return Command(goto=[Send("query_genie", genie_state)])
        else:
            # No data needed, proceed directly to HTML generation
            print(f"[GENERATE_SLIDE] No data needed, proceeding to HTML generation")
            
            # Create state for HTML generation
            html_state = {
                "todo": todo,
                "config": state["config"],
                "progress_tracker": progress_tracker,
                "branch_id": branch_id,
                "writer": writer,
                "genie_data": None  # No data from Genie
            }
            
            return Command(goto=[Send("generate_html", html_state)])
        
    except Exception as e:
        error_msg = f"Generation error for slide {todo.id}: {str(e)}"
        print(f"[GENERATE_SLIDE] Error generating slide {todo.id}: {e}")
        
        # Return error result
        return Command(goto=[Send("handle_generation_error", {
            "todo": todo,
            "error": error_msg,
            "branch_id": branch_id
        })])

def query_genie(state: FanOutSlideState) -> Command:
    """Query Genie for data needed by a slide."""
    todo = state["todo"]
    data_query = state["data_query"]
    branch_id = state.get("branch_id", f"slide_{todo.id}")
    progress_tracker = state.get("progress_tracker")
    writer = state.get("writer")
    
    print(f"[QUERY_GENIE] Querying Genie for slide {todo.id}: {data_query[:50]}...")
    
    try:
        # Send progress update
        if writer:
            writer(f"Querying Genie for slide: {todo.title}")
            writer(f"Fetching data: {data_query[:50]}...")
        elif progress_tracker:
            progress_tracker.update_progress(
                step=f"Querying Genie for slide: {todo.title}",
                percent=progress_tracker.progress_percent,
                details=f"Fetching data: {data_query[:50]}...",
                current_slide_title=todo.title,
                branch_id=branch_id
            )
        
        # Query Genie
        genie_data = query_genie_space(data_query, "01effebcc2781b6bbb749077a55d31e3")
        
        print(f"[QUERY_GENIE] Genie query completed for slide {todo.id}")
        
        # Proceed to HTML generation with Genie data
        html_state = {
            "todo": todo,
            "config": state["config"],
            "progress_tracker": progress_tracker,
            "branch_id": branch_id,
            "writer": writer,
            "genie_data": genie_data
        }
        
        return Command(goto=[Send("generate_html", html_state)])
        
    except Exception as e:
        error_msg = f"Genie query error for slide {todo.id}: {str(e)}"
        print(f"[QUERY_GENIE] Error querying Genie for slide {todo.id}: {e}")
        
        # Proceed to HTML generation without Genie data
        html_state = {
            "todo": todo,
            "config": state["config"],
            "progress_tracker": progress_tracker,
            "branch_id": branch_id,
            "writer": writer,
            "genie_data": None,
            "genie_error": error_msg
        }
        
        return Command(goto=[Send("generate_html", html_state)])

def generate_html(state: FanOutSlideState) -> Dict[str, Any]:
    """Generate HTML for a slide with optional Genie data."""
    todo = state["todo"]
    branch_id = state.get("branch_id", f"slide_{todo.id}")
    progress_tracker = state.get("progress_tracker")
    writer = state.get("writer")
    genie_data = state.get("genie_data")
    genie_error = state.get("genie_error")
    
    print(f"[GENERATE_HTML] Generating HTML for slide {todo.id}: {todo.title}")
    
    try:
        # Prepare generation parameters
        generation_params = {
            "title": todo.title,
            "outline": todo.details,
            "style_hint": state["config"].style_hint or "professional clean",
            "space_id": "01effebcc2781b6bbb749077a55d31e3"
        }
        
        # Add Genie data if available
        if genie_data:
            generation_params["genie_data"] = genie_data
            print(f"[GENERATE_HTML] Using Genie data for slide {todo.id}")
        elif genie_error:
            print(f"[GENERATE_HTML] Genie query failed for slide {todo.id}: {genie_error}")
        
        # Generate HTML
        raw_html = generate_slide_html.invoke(generation_params)
        
        # Validate and repair if needed
        if not validate_slide_html.invoke({"html": raw_html}):
            print(f"[GENERATE_HTML] Slide {todo.id} failed validation, attempting repair")
            if writer:
                writer(f"Repairing slide: {todo.title}")
            raw_html = apply_slide_change.invoke({
                "slide_html": raw_html,
                "change": SlideChange(operation="EDIT_RAW_HTML", args={"fix": "structure"}),
                "style_hint": state["config"].style_hint or "professional clean"
            })
        
        # Sanitize
        sanitized_html = sanitize_slide_html.invoke({"html": raw_html})
        
        # Send completion update
        if writer:
            writer(f"Completed slide: {todo.title}")
        elif progress_tracker:
            progress_tracker.complete_slide(todo.title, branch_id)
        
        print(f"[GENERATE_HTML] Slide {todo.id} generated successfully")
        
        # Return result for collection
        return {
            "parallel_results": [{
                "slide_id": todo.id,
                "html": sanitized_html,
                "branch_id": branch_id,
                "success": True,
                "title": todo.title,
                "genie_data_used": genie_data is not None
            }]
        }
        
    except Exception as e:
        error_msg = f"HTML generation error for slide {todo.id}: {str(e)}"
        print(f"[GENERATE_HTML] Error generating HTML for slide {todo.id}: {e}")
        
        # Create placeholder slide
        placeholder_html = f"""<!DOCTYPE html>
                                <html lang="en">
                                <head>
                                    <meta charset="UTF-8">
                                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                                    <title>{todo.title}</title>
                                    <script src="https://cdn.tailwindcss.com"></script>
                                    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
                                </head>
                                <body style="width: 1280px; height: 720px; margin: 0; padding: 0; overflow: hidden; background: white;">
                                    <div style="max-width: 1280px; max-height: 720px; margin: 0 auto; padding: 32px; box-sizing: border-box;">
                                        <h1 style="color: #102025; font-size: 48px; font-weight: bold; margin-bottom: 24px;">{todo.title}</h1>
                                        <p style="color: #5D6D71; font-size: 18px;">Error generating slide content. Please try again.</p>
                                    </div>
                                </body>
                            </html>"""
        
        return {
            "parallel_results": [{
                "slide_id": todo.id,
                "html": placeholder_html,
                "branch_id": branch_id,
                "success": False,
                "title": todo.title,
                "error": error_msg
            }],
            "errors": [error_msg]
        }

def handle_generation_error(state: FanOutSlideState) -> Dict[str, Any]:
    """Handle generation errors."""
    todo = state["todo"]
    error = state["error"]
    branch_id = state.get("branch_id", f"slide_{todo.id}")
    
    print(f"[HANDLE_ERROR] Handling error for slide {todo.id}: {error}")
    
    # Create placeholder slide
    placeholder_html = f"""<!DOCTYPE html>
                            <html lang="en">
                            <head>
                                <meta charset="UTF-8">
                                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                                <title>{todo.title}</title>
                                <script src="https://cdn.tailwindcss.com"></script>
                                <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
                            </head>
                            <body style="width: 1280px; height: 720px; margin: 0; padding: 0; overflow: hidden; background: white;">
                                <div style="max-width: 1280px; max-height: 720px; margin: 0 auto; padding: 32px; box-sizing: border-box;">
                                    <h1 style="color: #102025; font-size: 48px; font-weight: bold; margin-bottom: 24px;">{todo.title}</h1>
                                    <p style="color: #5D6D71; font-size: 18px;">Error generating slide content. Please try again.</p>
                                </div>
                            </body>
                    </html>"""
    
    return {
        "parallel_results": [{
            "slide_id": todo.id,
            "html": placeholder_html,
            "branch_id": branch_id,
            "success": False,
            "title": todo.title,
            "error": error
        }],
        "errors": [error]
    }

def join_results(state: FanOutSlideState) -> FanOutSlideState:
    """Fan-in node: merges results from all parallel branches."""
    print(f"[JOIN] 🔥 JOIN_RESULTS CALLED - Merging results from parallel branches")
    
    # Process results from parallel branches
    parallel_results = state.get("parallel_results", [])
    print(f"[JOIN] Processing {len(parallel_results)} parallel results")
    
    # Initialize artifacts if not present
    if "artifacts" not in state:
        state["artifacts"] = {}
    
    # Process each result
    for result in parallel_results:
        slide_id = result.get("slide_id")
        html = result.get("html")
        success = result.get("success", False)
        title = result.get("title", f"Slide {slide_id}")
        error = result.get("error")
        
        # Only add if not already present (avoid duplicates)
        if slide_id not in state["artifacts"]:
            if success and html:
                state["artifacts"][slide_id] = html
                print(f"[JOIN] ✅ Added slide {slide_id}: {title}")
            else:
                # Create placeholder for failed slide
                placeholder_html = f"""<!DOCTYPE html>
                                        <html lang="en">
                                        <head>
                                            <meta charset="UTF-8">
                                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                                            <title>{title}</title>
                                            <script src="https://cdn.tailwindcss.com"></script>
                                            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
                                        </head>
                                        <body style="width: 1280px; height: 720px; margin: 0; padding: 0; overflow: hidden; background: white;">
                                            <div style="max-width: 1280px; max-height: 720px; margin: 0 auto; padding: 32px; box-sizing: border-box;">
                                                <h1 style="color: #102025; font-size: 48px; font-weight: bold; margin-bottom: 24px;">{title}</h1>
                                                <p style="color: #5D6D71; font-size: 18px;">Error generating slide content. Please try again.</p>
                                            </div>
                                        </body>
                                        </html>"""
                state["artifacts"][slide_id] = placeholder_html
                print(f"[JOIN] ⚠️ Added placeholder for slide {slide_id}: {title}")
                
                if error:
                    if "errors" not in state:
                        state["errors"] = []
                    state["errors"].append(error)
        else:
            print(f"[JOIN] ⏭️ Skipping duplicate slide {slide_id}: {title}")
    
    # Clear parallel_results to prevent re-processing
    state["parallel_results"] = []
    
    # Update progress for completion
    progress_tracker = state.get("progress_tracker")
    if progress_tracker:
        artifacts = state.get("artifacts", {})
        completed_slides = len(artifacts)
        progress_tracker.update_progress(
            step="Generation complete",
            percent=90,
            details=f"Successfully generated {completed_slides} slides"
        )
    
    print(f"[JOIN] Merged results: {len(state.get('artifacts', {}))} slides generated")
    return state

def modification_node(state: FanOutSlideState) -> FanOutSlideState:
    """Modification node - applies changes to slides."""
    print(f"[MODIFICATION] Processing {len(state['pending_changes'])} changes")
    
    # Create a mapping of user-visible slide numbers to actual artifact IDs
    slide_todos = [t for t in state["todos"] if t.action == "WRITE_SLIDE"]
    slide_number_to_id = {i+1: slide_todos[i].id for i in range(len(slide_todos))}
    print(f"[MODIFICATION] Slide mapping (based on todo order): {slide_number_to_id}")
    
    for change in state["pending_changes"]:
        try:
            print(f"[MODIFICATION] Applying change: {change.operation}, slide_id={change.slide_id}, args={change.args}")
            
            if change.operation == "REORDER_SLIDES":
                order = change.args.get("order", [])
                slides = [t for t in state["todos"] if t.action == "WRITE_SLIDE"]
                id2t = {t.id: t for t in slides}
                new_slides = [id2t[i] for i in order if i in id2t]
                others = [t for t in state["todos"] if t.action != "WRITE_SLIDE"]
                state["todos"] = new_slides + others
                continue
            
            if change.operation == "DELETE_SLIDE":
                slide_id = change.slide_id
                
                # Map user slide number to actual artifact ID if needed
                if slide_id in slide_number_to_id:
                    actual_id = slide_number_to_id[slide_id]
                else:
                    actual_id = slide_id
                
                # Remove from artifacts
                removed_artifact = state["artifacts"].pop(actual_id, None)
                
                # Also remove from todos
                slide_todos = [t for t in state["todos"] if t.action == "WRITE_SLIDE"]
                other_todos = [t for t in state["todos"] if t.action != "WRITE_SLIDE"]
                updated_slides = [t for t in slide_todos if t.id != actual_id]
                state["todos"] = updated_slides + other_todos
                
                if removed_artifact:
                    print(f"[MODIFICATION] ✅ Deleted slide {slide_id} (artifact ID {actual_id})")
                else:
                    print(f"[MODIFICATION] ⚠️ Slide {slide_id} not found for deletion")
                continue
            
            if change.operation == "INSERT_SLIDE_AFTER":
                after_id = change.slide_id or 0
                title = change.args.get("title", "New Slide")
                bullets = change.args.get("bullets", [])
                content = change.args.get("content", "")
                
                # Use the detailed content if available, otherwise use bullets
                if content:
                    outline = content
                else:
                    outline = "\n".join(f"- {b}" for b in bullets)
                
                # Generate new slide with error handling
                try:
                    new_html = generate_slide_html.invoke({
                        "title": title,
                        "outline": outline,
                        "style_hint": state["config"].style_hint or "professional clean",
                        "space_id": "01effebcc2781b6bbb749077a55d31e3"
                    })
                    
                    if not validate_slide_html.invoke({"html": new_html}):
                        new_html = apply_slide_change.invoke({
                            "slide_html": new_html,
                            "change": SlideChange(operation="EDIT_RAW_HTML", args={"fix": "structure"}),
                            "style_hint": state["config"].style_hint or "professional clean"
                        })
                    
                    new_id = max([t.id for t in state["todos"]], default=0) + 1
                    state["artifacts"][new_id] = sanitize_slide_html.invoke({"html": new_html})
                    
                except Exception as e:
                    print(f"[MODIFICATION] Error generating slide: {e}")
                    # Create a placeholder slide
                    new_id = max([t.id for t in state["todos"]], default=0) + 1
                    placeholder_html = f"""<!DOCTYPE html>
                                        <html lang="en">
                                        <head>
                                            <meta charset="UTF-8">
                                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                                            <title>{title}</title>
                                            <script src="https://cdn.tailwindcss.com"></script>
                                            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
                                        </head>
                                        <body style="width: 1280px; height: 720px; margin: 0; padding: 0; overflow: hidden; background: white;">
                                            <div style="max-width: 1280px; max-height: 720px; margin: 0 auto; padding: 32px; box-sizing: border-box;">
                                                <h1 style="color: #102025; font-size: 48px; font-weight: bold; margin-bottom: 24px;">{title}</h1>
                                                <div style="color: #5D6D71; font-size: 18px; line-height: 1.6;">
                                                    <pre style="white-space: pre-wrap; font-family: inherit;">{outline}</pre>
                                                </div>
                                            </div>
                                        </body>
                                        </html>"""
                    state["artifacts"][new_id] = placeholder_html
                    state["errors"].append(f"Slide generation error: {str(e)}")
                
                # Insert into todos
                slides = [t for t in state["todos"] if t.action == "WRITE_SLIDE"]
                others = [t for t in state["todos"] if t.action != "WRITE_SLIDE"]
                inserted = []
                for t in slides:
                    inserted.append(t)
                    if t.id == after_id:
                        inserted.append(SlideTodo(id=new_id, action="WRITE_SLIDE", title=title, details="", depends_on=[]))
                if after_id == 0:
                    inserted = [SlideTodo(id=new_id, action="WRITE_SLIDE", title=title, details="", depends_on=[])] + inserted
                state["todos"] = inserted + others
                print(f"[MODIFICATION] After INSERT_SLIDE_AFTER: Todo order now {[t.id for t in inserted]}")
                continue
            
            # Apply content changes to existing slides
            slide_id = change.slide_id
            if slide_id is None:
                print(f"[MODIFICATION] Skipping change - no slide ID specified")
                continue
            
            # Map user slide number to actual artifact ID
            actual_id = slide_number_to_id.get(slide_id, slide_id)
            
            if actual_id not in state["artifacts"]:
                print(f"[MODIFICATION] Skipping change for slide {slide_id} (mapped to {actual_id}, not found)")
                continue
            
            print(f"[MODIFICATION] Applying change to slide {slide_id} (artifact {actual_id})")
            
            updated_html = apply_slide_change.invoke({
                "slide_html": state["artifacts"][actual_id],
                "change": change,
                "style_hint": state["config"].style_hint or "professional clean"
            })
            
            state["artifacts"][actual_id] = sanitize_slide_html.invoke({"html": updated_html})
            print(f"[MODIFICATION] Applied change to slide {slide_id} (artifact {actual_id})")
            
        except Exception as e:
            print(f"[MODIFICATION] Error applying change: {e}")
            state["errors"].append(f"Modification error: {str(e)}")
    
    # Clear pending changes
    state["pending_changes"] = []
    return state

def status_node(state: FanOutSlideState) -> FanOutSlideState:
    """Status node - updates slide status."""
    print(f"[STATUS] Updating slide status")
    
    status_list = []
    # Use todo order to preserve slide sequence
    slide_todos = [t for t in state["todos"] if t.action == "WRITE_SLIDE"]
    print(f"[STATUS] Todo order: {[t.id for t in slide_todos]}")
    
    for position, todo in enumerate(slide_todos, start=1):
        slide_id = todo.id
        html = state["artifacts"].get(slide_id, "")
        is_generated = bool(html)
        is_valid = validate_slide_html.invoke({"html": html}) if html else False
        
        # Try to extract title from HTML or use todo title as fallback
        title = todo.title or f"Slide {position}"
        if html:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                h1 = soup.find("h1")
                if h1:
                    title = h1.get_text().strip()
            except:
                pass
        
        status_list.append(SlideStatus(
            id=slide_id,
            position=position,  # User-visible position (1, 2, 3...)
            title=title,
            html=html,
            is_generated=is_generated,
            is_valid=is_valid
        ))
    
    state["status"] = status_list
    print(f"[STATUS] Updated status for {len(status_list)} slides")
    print(f"[STATUS] Status list order: {[(s.position, s.id, s.title[:30]) for s in status_list]}")
    return state


# =========================
# Routing Functions
# =========================
def should_continue(state: FanOutSlideState) -> str:
    """Determine the next node based on current state."""
    intent = state.get("last_intent")
    
    if intent in ["FINALIZE", "SAVE"]:
        return "status"
    elif intent == "ADD_CHANGES" and state.get("pending_changes"):
        # For ADD_CHANGES, go directly to modification
        return "modification"
    elif intent == "REQUEST_DECK":
        # For REQUEST_DECK, check if we need planning or generation
        if state.get("config").topic and state.get("config").style_hint and state.get("config").n_slides:
            if not state.get("todos"):
                return "planning"
            elif any(todo.id not in state.get("artifacts", {}) for todo in state.get("todos", []) if todo.action == "WRITE_SLIDE"):
                return "fan_out_generation"
            else:
                return "status"
        else:
            return "status"
    else:
        return "status"


# =========================
# Graph Construction
# =========================
def create_fanout_slide_agent() -> StateGraph:
    """Create the fan-out slide generation agent graph."""
    
    # Create the graph
    graph = StateGraph(FanOutSlideState)
    
    # Add nodes
    graph.add_node("nlu", nlu_node)
    graph.add_node("planning", planning_node)
    graph.add_node("fan_out_generation", fan_out_generation)
    graph.add_node("generate_slide", generate_slide)
    graph.add_node("query_genie", query_genie)
    graph.add_node("generate_html", generate_html)
    graph.add_node("handle_generation_error", handle_generation_error)
    graph.add_node("join_results", join_results)
    graph.add_node("modification", modification_node)
    graph.add_node("status", status_node)
    
    # Set entry point
    graph.set_entry_point("nlu")
    
    # Add edges with conditional routing
    graph.add_conditional_edges(
        "nlu",
        should_continue,
        {
            "planning": "planning",
            "modification": "modification",
            "status": "status"
        }
    )
    graph.add_edge("planning", "fan_out_generation")
    # Note: fan_out_generation -> generate_slide is handled by Send commands
    # Note: generate_slide -> query_genie/generate_html/handle_generation_error is handled by Send commands
    # Note: query_genie -> generate_html is handled by Send commands
    # Note: generate_html/handle_generation_error -> join_results is handled by Send commands
    graph.add_edge("generate_html", "join_results")
    graph.add_edge("handle_generation_error", "join_results")
    graph.add_edge("join_results", "modification")
    graph.add_conditional_edges(
        "modification",
        should_continue,
        {
            "status": "status",
            "planning": "planning",
            "fan_out_generation": "fan_out_generation",
            "modification": "modification"
        }
    )
    graph.add_edge("status", END)
    
    return graph


# =========================
# Main Agent Class
# =========================
class FanOutSlideDeckAgent:
    """Fan-out based slide deck generation agent using LangGraph Send/Command."""
    
    def __init__(self, theme: Optional[SlideTheme] = None, progress_tracker: Optional[FanOutProgressTracker] = None):
        self.theme = theme or SlideTheme()
        self.graph = create_fanout_slide_agent().compile()
        self.progress_tracker = progress_tracker
        
        # Initialize state
        self.initial_state: FanOutSlideState = {
            "config": SlideConfig(),
            "config_version": 0,
            "messages": [],
            "last_intent": None,
            "todos": [],
            "artifacts": {},
            "pending_changes": [],
            "status": [],
            "errors": [],
            "metrics": {},
            "run_id": "",
            "progress_tracker": progress_tracker,
            "parallel_results": []
        }
    
    def process_message(self, message: str, run_id: str = None, max_concurrency: int = DEFAULT_MAX_CONCURRENCY) -> Dict:
        """Process a user message and return the result."""
        if run_id is None:
            run_id = f"run_{int(time.time())}"
        
        # Add message to state (shallow copy to avoid threading lock issues)
        current_state = self.initial_state.copy()
        current_state["messages"] = self.initial_state["messages"].copy()
        current_state["messages"].append({"role": "user", "content": message})
        current_state["run_id"] = run_id
        
        # Run the agent with configurable concurrency
        try:
            result = self.graph.invoke(
                current_state, 
                config={
                    "run_id": run_id,
                    "max_concurrency": max_concurrency
                }
            )
            
            # Update the agent's state with the result
            self.initial_state = result
            
            return {
                "success": True,
                "slides": [slide.html for slide in result["status"] if slide.is_generated],
                "status": result["status"],
                "errors": result["errors"]
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "slides": [],
                "status": [],
                "errors": [str(e)]
            }
    
    async def process_message_streaming_async(self, message: str, run_id: str = None, max_concurrency: int = DEFAULT_MAX_CONCURRENCY) -> AsyncGenerator[Dict, None]:
        """Process a user message with real-time streaming using LangGraph's astream method."""
        if run_id is None:
            run_id = f"run_{int(time.time())}"
        
        # Initialize progress tracking
        if self.progress_tracker:
            self.progress_tracker.update_progress(
                step="Starting slide generation",
                percent=0,
                details="Analyzing request and initializing..."
            )
        
        # Add message to state (shallow copy to avoid threading lock issues)
        current_state = self.initial_state.copy()
        current_state["messages"] = self.initial_state["messages"].copy()
        current_state["messages"].append({"role": "user", "content": message})
        current_state["run_id"] = run_id
        current_state["progress_tracker"] = self.progress_tracker
        
        try:
            # Use LangGraph's streaming capability
            final_state = current_state
            async for chunk in self.graph.astream(
                current_state, 
                config={
                    "run_id": run_id,
                    "max_concurrency": max_concurrency
                }, 
                stream_mode="updates"
            ):
                # Handle None or invalid chunks
                if chunk is None or not isinstance(chunk, dict):
                    print(f"[STREAM] Skipping invalid chunk: {chunk}")
                    continue
                
                # Extract the node name and state from the chunk
                for node_name, node_state in chunk.items():
                    print(f"[STREAM] Node '{node_name}' completed")
                    
                    # Update final state with the latest state
                    if node_state and isinstance(node_state, dict):
                        final_state.update(node_state)
                    
                    # Send progress updates based on which node completed
                    if self.progress_tracker:
                        if node_name == "nlu":
                            self.progress_tracker.update_progress(
                                step="Understanding request",
                                percent=5,
                                details="Analyzed user intent and extracted requirements"
                            )
                        elif node_name == "planning":
                            todos = node_state.get("todos", [])
                            slide_todos = [t for t in todos if t.action == "WRITE_SLIDE"]
                            self.progress_tracker.set_total_slides(len(slide_todos))
                            self.progress_tracker.update_progress(
                                step="Planning complete",
                                percent=15,
                                details=f"Created plan for {len(slide_todos)} slides"
                            )
                        elif node_name == "fan_out_generation":
                            self.progress_tracker.update_progress(
                                step="Starting parallel generation",
                                percent=20,
                                details="Fanning out slides for parallel processing"
                            )
                        elif node_name == "generate_slide":
                            # Individual slide completion (now returns Command, not state)
                            self.progress_tracker.update_progress(
                                step="Starting slide generation",
                                percent=25,
                                details="Analyzing slide requirements and data needs"
                            )
                        elif node_name == "query_genie":
                            # Genie query completion
                            self.progress_tracker.update_progress(
                                step="Querying data sources",
                                percent=35,
                                details="Fetching data from Genie"
                            )
                        elif node_name == "generate_html":
                            # HTML generation completion
                            artifacts = node_state.get("artifacts", {})
                            if artifacts:
                                completed_slides = len(artifacts)
                                total_slides = self.progress_tracker.total_slides or completed_slides
                                progress = int((completed_slides / max(total_slides, 1)) * 80) + 10
                                self.progress_tracker.update_progress(
                                    step=f"Generated {completed_slides}/{total_slides} slides",
                                    percent=progress,
                                    details=f"Completed slide generation"
                                )
                        elif node_name == "handle_generation_error":
                            # Error handling completion
                            self.progress_tracker.update_progress(
                                step="Handling generation error",
                                percent=50,
                                details="Creating placeholder slide"
                            )
                        elif node_name == "join_results":
                            slides_generated = len([slide for slide in node_state.get("status", []) if slide.is_generated])
                            self.progress_tracker.update_progress(
                                step="Generation complete",
                                percent=100,
                                details=f"Successfully generated {slides_generated} slides"
                            )
                    
                    # Yield the chunk for real-time processing
                    yield {
                        "node": node_name,
                        "state": node_state,
                        "progress": self.progress_tracker.progress_percent if self.progress_tracker else 0
                    }
            
            # Update the agent's state with the final result
            self.initial_state = final_state
            
            # Final result - handle case where status might not be populated
            slides = []
            status_list = []
            
            # Get slides from artifacts if status is empty
            if "artifacts" in final_state and final_state["artifacts"]:
                slides = list(final_state["artifacts"].values())
                print(f"[STREAM] Using artifacts for slides: {len(slides)} slides")
            
            # Get status from final_state if available
            if "status" in final_state and final_state["status"]:
                status_list = final_state["status"]
                slides = [slide.html for slide in status_list if slide.is_generated]
                print(f"[STREAM] Using status for slides: {len(slides)} slides")
            
            # If no slides found, try to get from initial_state
            if not slides and hasattr(self, 'initial_state'):
                if "artifacts" in self.initial_state and self.initial_state["artifacts"]:
                    slides = list(self.initial_state["artifacts"].values())
                    print(f"[STREAM] Using initial_state artifacts: {len(slides)} slides")
                elif "status" in self.initial_state and self.initial_state["status"]:
                    status_list = self.initial_state["status"]
                    slides = [slide.html for slide in status_list if slide.is_generated]
                    print(f"[STREAM] Using initial_state status: {len(slides)} slides")
            
            print(f"[STREAM] Final slides count: {len(slides)}")
            
            # Final result
            yield {
                "node": "complete",
                "result": {
                    "success": len(slides) > 0,
                    "slides": slides,
                    "status": status_list,
                    "errors": final_state.get("errors", [])
                },
                "progress": 100
            }
            
        except Exception as e:
            # Error handling
            if self.progress_tracker:
                self.progress_tracker.update_progress(
                    step="Error occurred",
                    percent=0,
                    details=f"Generation failed: {str(e)}",
                    error=str(e)
                )
            
            yield {
                "node": "error",
                "result": {
                    "success": False,
                    "error": str(e),
                    "slides": [],
                    "status": [],
                    "errors": [str(e)]
                },
                "progress": 0
            }
    
    def get_slides(self) -> List[str]:
        """Get the generated slides as HTML strings."""
        print(f"[DEBUG] get_slides - initial_state keys: {list(self.initial_state.keys())}")
        
        # Check status field
        if "status" in self.initial_state:
            status_slides = [slide.html for slide in self.initial_state["status"] if slide.is_generated]
            print(f"[DEBUG] get_slides - status slides: {len(status_slides)}")
            if status_slides:
                return status_slides
        
        # Check artifacts field
        if "artifacts" in self.initial_state:
            artifact_slides = list(self.initial_state["artifacts"].values())
            print(f"[DEBUG] get_slides - artifact slides: {len(artifact_slides)}")
            if artifact_slides:
                return artifact_slides
        
        print(f"[DEBUG] get_slides - no slides found")
        return []
    
    def get_status(self) -> List[SlideStatus]:
        """Get the current status of all slides."""
        return self.initial_state["status"]
    
    def save_slides(self, output_dir: str = "output") -> List[str]:
        """Save slides to individual HTML files."""
        os.makedirs(output_dir, exist_ok=True)
        saved_files = []
        
        for slide in self.initial_state["status"]:
            if slide.is_generated:
                file_path = os.path.join(output_dir, f"slide_{slide.id}.html")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(slide.html)
                saved_files.append(file_path)
        
        return saved_files


# =========================
# Demo and Testing
# =========================
if __name__ == "__main__":
    print("Fan-out LangGraph Slide Deck Agent")
    print("=" * 40)
    
    # Create agent
    agent = FanOutSlideDeckAgent()
    
    # Test with a simple message
    result = agent.process_message(
        "Create a 3-slide presentation about AI and Machine Learning with a professional, clean style",
        max_concurrency=3
    )
    
    print(f"Generation result: {result['success']}")
    print(f"Generated {len(result['slides'])} slides")
    
    if result["success"]:
        # Save slides
        saved_files = agent.save_slides()
        print(f"Saved slides to: {saved_files}")
        
        # Show status
        status = agent.get_status()
        for slide in status:
            print(f"Slide {slide.id}: {slide.title} (Generated: {slide.is_generated}, Valid: {slide.is_valid})")
    else:
        print(f"Error: {result['error']}")
