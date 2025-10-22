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
import time
from typing import List, Dict, Literal, Optional, Annotated, TypedDict
from pydantic import BaseModel, Field, conint

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
ws = WorkspaceClient(profile='e2-demo', product='slide-generator')
model_serving_client = ws.serving_endpoints.get_open_ai_client()

NLU_ENDPOINT = "databricks-gpt-oss-120b"
PLAN_ENDPOINT = "databricks-gpt-oss-120b" 
HTML_ENDPOINT = "databricks-claude-sonnet-4"


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
    id: int
    title: str
    html: str  # Complete HTML document
    is_generated: bool = False
    is_valid: bool = False

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
    """Remove markdown code fences from content."""
    if content.startswith("```html"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


# =========================
# LangGraph Tools
# =========================
@tool("interpret_user_intent", return_direct=False)
def interpret_user_intent(messages: List[Dict[str, str]], current_config: SlideConfig) -> UserIntent:
    """Interpret user messages and extract intent, config changes, and slide modifications."""
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
        "\nExamples:\n"
        "- 'create 2 slides on AI and Machine Learning' → REQUEST_DECK, topic='AI and Machine Learning', n_slides=2\n"
        "- 'Slide 2 title: KEY BENEFITS...' → ADD_CHANGES, no config changes\n"
        "- 'change the title to Machine Learning' → ADD_CHANGES, no config changes\n"
        "\nReturn JSON with intent, config_delta (with topic/style_hint/n_slides), and changes array."
    )
    # Check if there are existing slides by looking at the current config
    has_existing_slides = current_config.topic is not None and current_config.topic.strip() != ""
    
    user = f"""Messages (recent last):
{json.dumps(messages[-12:], ensure_ascii=False, indent=2)}

Current config: {current_config.model_dump()}
Has existing slides: {has_existing_slides}

IMPORTANT: If the user is requesting 'Slide 2', 'Slide 3', etc. AND there are existing slides (has_existing_slides=True), 
then classify as ADD_CHANGES, not REQUEST_DECK."""
    
    response = model_serving_client.chat.completions.create(
        model=NLU_ENDPOINT,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": user}
        ]
    )
    
    print("current_config", current_config)
    content = _extract_text_from_response(response.choices[0].message.content)
    content = _clean_markdown_fences(content)
    
    try:
        data = json.loads(content)
        
        # Validate and fix intent if needed
        valid_intents = ["REQUEST_DECK", "REFINE_CONFIG", "ADD_CHANGES", "REGENERATE_TODOS", "FINALIZE", "SAVE", "SHOW_STATUS"]
        if data.get("intent") not in valid_intents:
            data["intent"] = "REQUEST_DECK"
        
        # Handle config_deltas -> config_delta
        if "config_deltas" in data and "config_delta" not in data:
            data["config_delta"] = data.pop("config_deltas")
        
        # Parse changes
        if "changes" in data:
            parsed_changes = []
            if isinstance(data["changes"], dict):
                if "slide" in data["changes"] and "actions" in data["changes"]:
                    slide_id = data["changes"]["slide"]
                    actions = data["changes"]["actions"]
                    if isinstance(actions, list):
                        for action in actions:
                            parsed_changes.append({
                                "slide_id": slide_id,
                                "operation": "EDIT_RAW_HTML",
                                "args": {"description": action}
                            })
            elif isinstance(data["changes"], list):
                for change_item in data["changes"]:
                    if isinstance(change_item, str):
                        parsed_changes.append({
                            "slide_id": 1,
                            "operation": "EDIT_RAW_HTML",
                            "args": {"description": change_item}
                        })
                    elif isinstance(change_item, dict):
                        if "slide_number" in change_item and "description" in change_item:
                            parsed_changes.append({
                                "slide_id": change_item["slide_number"],
                                "operation": "EDIT_RAW_HTML",
                                "args": {"description": change_item["description"]}
                            })
                        elif "slide_id" in change_item and "operation" in change_item:
                            parsed_changes.append(change_item)
            
            data["changes"] = parsed_changes
        
        # Special handling for ADD_CHANGES intent - if no changes parsed but intent is ADD_CHANGES,
        # create a slide addition change from the user message
        if data.get("intent") == "ADD_CHANGES" and not data.get("changes"):
            # Extract the latest user message
            latest_message = messages[-1]["content"] if messages else ""
            if latest_message.strip():
                # Determine slide ID - look for "Slide X" pattern
                import re
                slide_match = re.search(r'Slide\s+(\d+)', latest_message)
                slide_id = int(slide_match.group(1)) if slide_match else 2  # Default to slide 2
                
                parsed_changes.append({
                    "slide_id": slide_id,
                    "operation": "INSERT_SLIDE_AFTER",
                    "args": {
                        "title": f"Slide {slide_id}",
                        "content": latest_message,
                        "bullets": []
                    }
                })
                data["changes"] = parsed_changes
        
        # Enhanced slide ID handling for ADD_CHANGES
        if data.get("intent") == "ADD_CHANGES" and data.get("changes"):
            latest_message = messages[-1]["content"] if messages else ""
            import re
            
            # Look for slide references in various formats
            slide_patterns = [
                r'Slide\s+(\d+)',  # "Slide 2"
                r'slide\s+(\d+)',  # "slide 2"
                r'for\s+slide\s+(\d+)',  # "for slide 2"
                r'to\s+slide\s+(\d+)',  # "to slide 2"
            ]
            
            target_slide_id = None
            for pattern in slide_patterns:
                slide_match = re.search(pattern, latest_message, re.IGNORECASE)
                if slide_match:
                    target_slide_id = int(slide_match.group(1))
                    break
            
            if target_slide_id:
                # Update the change to use correct slide ID
                for change in data["changes"]:
                    if change.get("operation") == "EDIT_RAW_HTML":
                        # Check if this is a slide addition or modification
                        if "Slide" in latest_message and ("title:" in latest_message or "bullets:" in latest_message):
                            change["operation"] = "INSERT_SLIDE_AFTER"
                            change["slide_id"] = target_slide_id
                            change["args"] = {
                                "title": f"Slide {target_slide_id}",
                                "content": latest_message,
                                "bullets": []
                            }
                        else:
                            # This is a modification to existing slide
                            change["slide_id"] = target_slide_id
        
        return UserIntent(**data)
    
    except Exception as e:
        print(f"Error parsing intent: {e}")
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
def generate_slide_html(title: str, outline: str, style_hint: str) -> str:
    """Generate complete HTML document for a single slide."""
    sys = "Create a complete HTML document for a single slide." + HTML_CONSTRAINTS
    user = f"""TITLE: {title}
OUTLINE: {outline}
STYLE: {style_hint}

CRITICAL INSTRUCTIONS:
- Use ONLY the content provided above - do not add, modify, or hallucinate any data
- If specific metrics, numbers, or data points are provided, use them exactly as given
- If bullet points are specified, include them exactly as listed
- If section headings are provided, use them exactly as specified
- If company names, logos, or branding are mentioned, include them as specified
- Do not create fictional data, statistics, or content not explicitly provided
- Maintain the exact structure and content hierarchy as specified in the outline
- Use Tailwind CSS with the brand colors and styling specified in the constraints

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
    print(f"[NLU] Processing {len(state['messages'])} messages")
    
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
        
    except Exception as e:
        print(f"[PLANNING] Error: {e}")
        state["errors"].append(f"Planning error: {str(e)}")
    
    return state

def generation_node(state: SlideDeckState) -> SlideDeckState:
    """Generation node - generates HTML for slides."""
    print(f"[GENERATION] Generating slides")
    
    slide_todos = [t for t in state["todos"] if t.action == "WRITE_SLIDE"]
    processed_todos = []
    
    for todo in slide_todos:
        if todo.id in state["artifacts"]:
            print(f"[GENERATION] Slide {todo.id} already exists, skipping")
            processed_todos.append(todo)
            continue
        
        try:
            print(f"[GENERATION] Generating slide {todo.id}: {todo.title}")
            
            # Generate HTML
            raw_html = generate_slide_html.invoke({
                "title": todo.title,
                "outline": todo.details,
                "style_hint": state["config"].style_hint or "professional clean"
            })
            
            # Validate and repair if needed
            if not validate_slide_html.invoke({"html": raw_html}):
                print(f"[GENERATION] Slide {todo.id} failed validation, attempting repair")
                # Try one repair attempt
                raw_html = apply_slide_change.invoke({
                    "slide_html": raw_html,
                    "change": SlideChange(operation="EDIT_RAW_HTML", args={"fix": "structure"}),
                    "style_hint": state["config"].style_hint or "professional clean"
                })
            
            # Sanitize and store
            sanitized_html = sanitize_slide_html.invoke({"html": raw_html})
            state["artifacts"][todo.id] = sanitized_html
            
            print(f"[GENERATION] Slide {todo.id} generated successfully")
            processed_todos.append(todo)
            
        except Exception as e:
            print(f"[GENERATION] Error generating slide {todo.id}: {e}")
            state["errors"].append(f"Generation error for slide {todo.id}: {str(e)}")
            
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
            state["artifacts"][todo.id] = placeholder_html
            processed_todos.append(todo)
    
    # Optimized todo management: Only remove todos that are fully processed
    # Keep todos for slides that might need modifications
    remaining_todos = []
    for todo in state["todos"]:
        if todo.action == "WRITE_SLIDE":
            # Keep the todo if it was processed (for potential future modifications)
            # Mark it as completed but keep it for reference
            todo.details = f"[COMPLETED] {todo.details}"
            remaining_todos.append(todo)
        else:
            # Keep non-WRITE_SLIDE todos
            remaining_todos.append(todo)
    
    state["todos"] = remaining_todos
    print(f"[GENERATION] Processed {len(processed_todos)} slides, kept {len(remaining_todos)} todos for reference")
    
    return state

def modification_node(state: SlideDeckState) -> SlideDeckState:
    """Modification node - applies changes to slides."""
    print(f"[MODIFICATION] Processing {len(state['pending_changes'])} changes")
    
    # Create a mapping of user-visible slide numbers to actual artifact IDs
    artifact_ids = sorted(state["artifacts"].keys())
    slide_number_to_id = {i+1: artifact_ids[i] for i in range(len(artifact_ids))}
    print(f"[MODIFICATION] Slide mapping: {slide_number_to_id}")
    
    for change in state["pending_changes"]:
        try:
            print(f"[MODIFICATION] Applying change: {change.operation}")
            
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
                    state["artifacts"].pop(actual_id, None)
                else:
                    state["artifacts"].pop(slide_id, None)
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
                        "style_hint": state["config"].style_hint or "professional clean"
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
    # Look at artifacts directly since WRITE_SLIDE todos may have been removed
    for slide_id, html in state["artifacts"].items():
        is_generated = bool(html)
        is_valid = validate_slide_html.invoke({"html": html}) if html else False
        
        # Try to extract title from HTML or use a default
        title = f"Slide {slide_id}"
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
            title=title,
            html=html,
            is_generated=is_generated,
            is_valid=is_valid
        ))
    
    state["status"] = status_list
    print(f"[STATUS] Updated status for {len(status_list)} slides")
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
        
        # Add message to state
        current_state = self.initial_state.copy()
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
    
    def process_message_streaming(self, message: str, run_id: str = None, callback=None) -> Dict:
        """Process a user message with streaming updates via callback."""
        if run_id is None:
            run_id = f"run_{int(time.time())}"
        
        current_state = self.initial_state.copy()
        current_state["messages"].append({"role": "user", "content": message})
        current_state["run_id"] = run_id
        
        try:
            if callback:
                callback("nlu", "Analyzing your request and extracting intent...")
            current_state = nlu_node(current_state)
            if callback:
                intent = current_state.get("last_intent", "unknown")
                callback("nlu", f"Intent identified: {intent}")
            
            if callback and current_state.get("config").topic and current_state.get("config").style_hint and current_state.get("config").n_slides:
                callback("planning", f"Creating plan for {current_state['config'].n_slides} slides on '{current_state['config'].topic}'...")
            current_state = planning_node(current_state)
            if callback and current_state.get("todos"):
                callback("planning", f"Plan created with {len([t for t in current_state['todos'] if t.action == 'WRITE_SLIDE'])} slides")
            
            slide_todos = [t for t in current_state["todos"] if t.action == "WRITE_SLIDE"]
            if callback and slide_todos:
                callback("generation", f"Generating {len(slide_todos)} slides...")
            
            for i, todo in enumerate(slide_todos):
                if todo.id in current_state["artifacts"]:
                    continue
                if callback:
                    callback("generation", f"Generating slide {i+1}/{len(slide_todos)}: {todo.title}")
                
                try:
                    # Generate HTML
                    raw_html = generate_slide_html.invoke({
                        "title": todo.title,
                        "outline": todo.details,
                        "style_hint": current_state["config"].style_hint or "professional clean"
                    })
                    
                    # Validate and repair if needed
                    if not validate_slide_html.invoke({"html": raw_html}):
                        if callback:
                            callback("generation", f"Repairing slide {i+1}...")
                        raw_html = apply_slide_change.invoke({
                            "slide_html": raw_html,
                            "change": SlideChange(operation="EDIT_RAW_HTML", args={"fix": "structure"}),
                            "style_hint": current_state["config"].style_hint or "professional clean"
                        })
                    
                    # Sanitize and store
                    sanitized_html = sanitize_slide_html.invoke({"html": raw_html})
                    current_state["artifacts"][todo.id] = sanitized_html
                    
                    if callback:
                        callback("generation", f"✅ Slide {i+1} completed: {todo.title}")
                        
                except Exception as e:
                    if callback:
                        callback("generation", f"❌ Error generating slide {i+1}: {str(e)}")
                    current_state["errors"].append(f"Generation error for slide {todo.id}: {str(e)}")
            
            # Remove processed WRITE_SLIDE todos, keep FINALIZE_DECK todos
            remaining_todos = [t for t in current_state["todos"] if t.action != "WRITE_SLIDE"]
            current_state["todos"] = remaining_todos
            if callback:
                callback("generation", f"Cleaned up {len(slide_todos)} processed todos")
            
            if callback and current_state.get("pending_changes"):
                callback("modification", f"Applying {len(current_state['pending_changes'])} changes...")
            current_state = modification_node(current_state)
            
            if callback:
                callback("status", "Finalizing slide status...")
            current_state = status_node(current_state)
            
            if callback:
                slides_generated = len([s for s in current_state["status"] if s.is_generated])
                callback("status", f"✅ All done! Generated {slides_generated} slides successfully")
            
            # Update the agent's state with the result
            self.initial_state = current_state
            
            return {
                "success": True,
                "slides": [slide.html for slide in current_state["status"] if slide.is_generated],
                "status": current_state["status"],
                "errors": current_state["errors"]
            }
        except Exception as e:
            if callback:
                callback("error", f"❌ Processing failed: {str(e)}")
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
