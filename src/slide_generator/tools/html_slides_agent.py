"""LangGraph-based HTML slide deck generator with proper agent architecture.

This module provides a clean, modular approach to generating HTML slides using LangGraph:
- Proper separation of concerns with individual nodes
- Clean state management with Pydantic models
- Modular tools for different operations
- Clear routing and conditional edges
- Better error handling and validation
"""

from __future__ import annotations
import os
import json
import re
import time
import copy
import pandas as pd
from typing import List, Dict, Literal, Optional, Annotated, TypedDict
from pydantic import BaseModel, Field, conint
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from bs4 import BeautifulSoup
from bs4.element import Tag
from langgraph.graph import StateGraph, END
from langchain.tools import tool
from databricks.sdk import WorkspaceClient


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
MAX_WORKERS = 5  # Maximum number of concurrent slide generations


# =========================
# Pydantic Models
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


@dataclass
class SlideAdapter:
    """Adapter to convert SlideStatus to Slide-like object for PPTX export.
    
    This bridges the new SlideDeckAgent architecture with the legacy
    HtmlToPptxConverter which expects the old Slide format from html_slides.py.
    
    The HtmlToPptxConverter was designed for the old architecture where slides
    had explicit types (title, agenda, content). In the new architecture, all
    slides are custom HTML, so we default to slide_type="custom".
    
    Attributes:
        slide_type: Type of slide (always "custom" for new architecture)
        html: Complete HTML document for the slide
        content: HTML content (same as html, for compatibility)
        title: Slide title extracted from HTML or metadata
        subtitle: Slide subtitle (empty for custom HTML slides)
        bullets: List of bullet points (empty for custom HTML slides)
        metadata: Additional metadata (empty dict for custom HTML slides)
    """
    slide_type: str = "custom"  # All new slides are custom HTML
    html: str = ""
    content: str = ""  # Same as html, for compatibility with HtmlToPptxConverter
    title: str = ""
    subtitle: str = ""  # Empty for custom HTML slides
    bullets: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # Empty for custom HTML slides
    
    @classmethod
    def from_slide_status(cls, status: SlideStatus) -> 'SlideAdapter':
        """Create SlideAdapter from SlideStatus.
        
        Args:
            status: SlideStatus object from SlideDeckAgent
            
        Returns:
            SlideAdapter object compatible with HtmlToPptxConverter
        """
        return cls(
            slide_type="custom",  # All slides are custom HTML in new architecture
            html=status.html,
            content=status.html,  # content and html are the same
            title=status.title,
            subtitle="",  # No separate subtitle in new architecture
            bullets=[],  # Bullets are embedded in HTML, not separate
            metadata={}  # No additional metadata
        )


class SlideDeckState(TypedDict):
    """State for the slide deck generation agent."""
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


# =========================
# Utility Functions
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
    """Remove markdown code fences from content.
    
    Handles various markdown fence formats:
    - ```json ... ```
    - ```html ... ```
    - ``` ... ```
    """
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
# Intent Parsing Helpers
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


def _generate_single_slide(todo: SlideTodo, style_hint: str, space_id: str) -> tuple[int, str, Optional[str]]:
    """
    Generate a single slide (used for parallel processing).
    
    Returns:
        tuple: (slide_id, html_content, error_message)
    """
    try:
        print(f"[PARALLEL] Generating slide {todo.id}: {todo.title}")
        
        # Generate HTML with automatic data fetching
        raw_html = generate_slide_html.invoke({
            "title": todo.title,
            "outline": todo.details,
            "style_hint": style_hint,
            "space_id": space_id
        })
        
        # Validate and repair if needed
        if not validate_slide_html.invoke({"html": raw_html}):
            print(f"[PARALLEL] Slide {todo.id} failed validation, attempting repair")
            raw_html = apply_slide_change.invoke({
                "slide_html": raw_html,
                "change": SlideChange(operation="EDIT_RAW_HTML", args={"fix": "structure"}),
                "style_hint": style_hint
            })
        
        # Sanitize
        sanitized_html = sanitize_slide_html.invoke({"html": raw_html})
        
        print(f"[PARALLEL] Slide {todo.id} generated successfully")
        return (todo.id, sanitized_html, None)
        
    except Exception as e:
        error_msg = f"Generation error for slide {todo.id}: {str(e)}"
        print(f"[PARALLEL] Error generating slide {todo.id}: {e}")
        
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
        
        return (todo.id, placeholder_html, error_msg)

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
# LangGraph Tools
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
# LangGraph Nodes
# =========================
def nlu_node(state: SlideDeckState) -> SlideDeckState:
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

def planning_node(state: SlideDeckState) -> SlideDeckState:
    """Planning node - creates todos for slide generation."""
    print(f"[PLANNING] Creating todos for topic: {state['config'].topic}")
    
    try:
        if (state["config"].topic and 
            state["config"].n_slides and 
            not state["todos"]):
            
            todos = create_slide_todos.invoke({
                "topic": state["config"].topic,
                "style_hint": state["config"].style_hint or "professional clean",
                "n_slides": state["config"].n_slides
            })
            
            state["todos"] = todos
            print(f"[PLANNING] Created {len(todos)} todos")
            print(f"[PLANNING] Todo IDs: {[t.id for t in todos if t.action == 'WRITE_SLIDE']}")
        
    except Exception as e:
        print(f"[PLANNING] Error: {e}")
        state["errors"].append(f"Planning error: {str(e)}")
    
    return state

def generation_node(state: SlideDeckState) -> SlideDeckState:
    """Generation node - generates HTML for slides using parallel processing."""
    print(f"[GENERATION] Generating slides")
    
    slide_todos = [t for t in state["todos"] if t.action == "WRITE_SLIDE"]
    
    # Filter out slides that already exist
    todos_to_generate = [t for t in slide_todos if t.id not in state["artifacts"]]
    
    if not todos_to_generate:
        print(f"[GENERATION] All slides already generated")
        return state
    
    print(f"[GENERATION] Generating {len(todos_to_generate)} slides in parallel (max {MAX_WORKERS} workers)")
    start_time = time.time()
    
    style_hint = state["config"].style_hint or "professional clean"
    space_id = "01effebcc2781b6bbb749077a55d31e3"
    
    # Use ThreadPoolExecutor for parallel generation
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all slide generation tasks
        future_to_todo = {
            executor.submit(_generate_single_slide, todo, style_hint, space_id): todo
            for todo in todos_to_generate
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_todo):
            todo = future_to_todo[future]
            try:
                slide_id, html_content, error_msg = future.result()
                
                # Store the generated slide
                state["artifacts"][slide_id] = html_content
                
                # Log any errors
                if error_msg:
                    state["errors"].append(error_msg)
                    
            except Exception as e:
                error_msg = f"Unexpected error for slide {todo.id}: {str(e)}"
                print(f"[GENERATION] {error_msg}")
                state["errors"].append(error_msg)
                
                # Create placeholder for failed slide
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
                state["artifacts"][todo.id] = placeholder_html
    
    elapsed_time = time.time() - start_time
    print(f"[GENERATION] Completed {len(todos_to_generate)} slides in {elapsed_time:.2f}s (avg {elapsed_time/len(todos_to_generate):.2f}s per slide)")
    
    # Optimized todo management: Keep todos but mark as completed (immutably)
    # Create new todo instances instead of mutating existing ones
    remaining_todos = []
    for todo in state["todos"]:
        if todo.action == "WRITE_SLIDE":
            # Create new todo instance with COMPLETED marker (don't mutate original)
            if not todo.details.startswith("[COMPLETED]"):
                new_todo = SlideTodo(
                    id=todo.id,
                    action=todo.action,
                    title=todo.title,
                    details=f"[COMPLETED] {todo.details}",
                    depends_on=todo.depends_on
                )
                remaining_todos.append(new_todo)
            else:
                remaining_todos.append(todo)
        else:
            # Keep non-WRITE_SLIDE todos
            remaining_todos.append(todo)
    
    state["todos"] = remaining_todos
    print(f"[GENERATION] Processed {len(todos_to_generate)} slides, kept {len(remaining_todos)} todos for reference")
    
    return state

def modification_node(state: SlideDeckState) -> SlideDeckState:
    """Modification node - applies changes to slides."""
    print(f"[MODIFICATION] Processing {len(state['pending_changes'])} changes")
    
    # Create a mapping of user-visible slide numbers to actual artifact IDs
    # IMPORTANT: Use todo order (not sorted artifact keys) to preserve slide sequence
    # This is critical after INSERT_SLIDE_AFTER operations which reorder todos
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
                
                # CRITICAL: Also remove from todos (this was missing!)
                slide_todos = [t for t in state["todos"] if t.action == "WRITE_SLIDE"]
                other_todos = [t for t in state["todos"] if t.action != "WRITE_SLIDE"]
                updated_slides = [t for t in slide_todos if t.id != actual_id]
                state["todos"] = updated_slides + other_todos
                
                if removed_artifact:
                    print(f"[MODIFICATION] ✅ Deleted slide {slide_id} (artifact ID {actual_id})")
                    print(f"[MODIFICATION] After DELETE_SLIDE: Todo order now {[t.id for t in updated_slides]}")
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
                
                # Generate new slide with error handling (with automatic data fetching)
                try:
                    new_html = generate_slide_html.invoke({
                        "title": title,
                        "outline": outline,
                        "style_hint": state["config"].style_hint or "professional clean",
                        "space_id": "01effebcc2781b6bbb749077a55d31e3"  # Genie space ID
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
                    # Create a placeholder slide with the user's content
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

def status_node(state: SlideDeckState) -> SlideDeckState:
    """Status node - updates slide status."""
    print(f"[STATUS] Updating slide status")
    
    status_list = []
    # IMPORTANT: Use todo order to preserve slide sequence (not artifact dict order)
    # This ensures slides are displayed in the correct order after INSERT_SLIDE_AFTER
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
def should_continue(state: SlideDeckState) -> str:
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
                return "generation"
            else:
                return "status"
        else:
            return "status"
    else:
        return "status"


# =========================
# Graph Construction
# =========================
def create_slide_agent() -> StateGraph:
    """Create the slide generation agent graph."""
    
    # Create the graph
    graph = StateGraph(SlideDeckState)
    
    # Add nodes
    graph.add_node("nlu", nlu_node)
    graph.add_node("planning", planning_node)
    graph.add_node("generation", generation_node)
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
    graph.add_edge("planning", "generation")
    graph.add_edge("generation", "modification")
    graph.add_conditional_edges(
        "modification",
        should_continue,
        {
            "status": "status",
            "planning": "planning",
            "generation": "generation",
            "modification": "modification"
        }
    )
    graph.add_edge("status", END)
    
    return graph


# =========================
# Main Agent Class
# =========================
class SlideDeckAgent:
    """LangGraph-based slide deck generation agent."""
    
    def __init__(self, theme: Optional[SlideTheme] = None):
        self.theme = theme or SlideTheme()
        self.graph = create_slide_agent().compile()
        
        # Initialize state
        self.initial_state: SlideDeckState = {
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
            "run_id": ""
        }
    
    def process_message(self, message: str, run_id: str = None) -> Dict:
        """Process a user message and return the result."""
        if run_id is None:
            run_id = f"run_{int(time.time())}"
        
        # Add message to state (deep copy to prevent mutations affecting original state)
        current_state = copy.deepcopy(self.initial_state)
        current_state["messages"].append({"role": "user", "content": message})
        current_state["run_id"] = run_id
        
        # Run the agent
        try:
            result = self.graph.invoke(current_state, config={"run_id": run_id})
            
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
    
    
    def get_slides(self) -> List[str]:
        """Get the generated slides as HTML strings."""
        return [slide.html for slide in self.initial_state["status"] if slide.is_generated]
    
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


class SlideDeckAgentAdapter:
    """Adapter to make SlideDeckAgent compatible with HtmlToPptxConverter.
    
    The HtmlToPptxConverter was designed for the old HtmlDeck architecture
    from html_slides.py. This adapter provides the interface that 
    HtmlToPptxConverter expects while using the new SlideDeckAgent internally.
    
    This enables PPTX export functionality without refactoring the entire
    HtmlToPptxConverter, which would be a significant effort.
    
    Usage:
        >>> agent = SlideDeckAgent()
        >>> agent.process_message("Create 3 slides about AI")
        >>> adapter = SlideDeckAgentAdapter(agent)
        >>> converter = HtmlToPptxConverter(adapter)
        >>> await converter.convert_to_pptx("output.pptx")
    
    Attributes:
        agent: The SlideDeckAgent instance being adapted
        theme: SlideTheme from the agent (required by HtmlToPptxConverter)
    """
    
    def __init__(self, agent: SlideDeckAgent):
        """Initialize adapter with a SlideDeckAgent instance.
        
        Args:
            agent: The SlideDeckAgent instance to adapt
        """
        self.agent = agent
        self.theme = agent.theme
    
    @property
    def _slides(self) -> List[SlideAdapter]:
        """Convert SlideStatus objects to Slide-like objects.
        
        This property mimics the old HtmlDeck._slides attribute that
        HtmlToPptxConverter expects. It converts the new SlideStatus
        objects to SlideAdapter objects that have the same interface
        as the old Slide class.
        
        Returns:
            List of SlideAdapter objects that mimic the old Slide interface
        """
        slides = []
        for status in self.agent.get_status():
            if status.is_generated:
                slides.append(SlideAdapter.from_slide_status(status))
        return slides
    
    def to_html(self) -> str:
        """Generate combined HTML for all slides.
        
        This method mimics the old HtmlDeck.to_html() that HtmlToPptxConverter
        expects. It combines all slide HTML into a single document.
        
        Returns:
            Combined HTML string with all slides
        """
        slides_html = []
        for status in self.agent.get_status():
            if status.is_generated:
                slides_html.append(status.html)
        
        # If no slides, return empty HTML
        if not slides_html:
            return "<html><body><h1>No slides generated</h1></body></html>"
        
        # For now, just concatenate slides (HtmlToPptxConverter processes them individually)
        # The converter actually doesn't use this combined HTML for rendering,
        # it accesses individual slides via _slides property
        return "\n".join(slides_html)
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"SlideDeckAgentAdapter(slides={len(self._slides)}, theme={self.theme})"


# =========================
# Demo and Testing
# =========================
if __name__ == "__main__":
    print("LangGraph Slide Deck Agent")
    print("=" * 40)
    
    # Create agent
    agent = SlideDeckAgent()
    
    # Test with a simple message
    result = agent.process_message(
        "Create a 3-slide presentation about AI and Machine Learning with a professional, clean style"
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
