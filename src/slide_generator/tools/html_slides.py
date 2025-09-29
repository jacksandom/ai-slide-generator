"""Generate HTML slide decks with LLM-based generation and validation.

This module provides an LLM-driven approach to generating HTML slides with:
- LLM-based slide generation with constraints
- HTML validation and sanitization
- State management for slide decks
- Tool functions for slide manipulation

Slides are generated as `<section class="slide">` elements with strict validation.
"""

from __future__ import annotations
import os, json
from typing import List, Dict, Literal, Optional, TypedDict
from pydantic import BaseModel, Field, conint

from bs4 import BeautifulSoup
from bs4.element import Tag
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
from langgraph.graph import StateGraph
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain.tools import tool
from databricks.sdk import WorkspaceClient


# =========================
# Global constraints (LLM)
# =========================
HTML_CONSTRAINTS = """
You MUST return a complete, self-contained HTML document for a single slide.
Requirements:
- Use Tailwind CSS via CDN: <script src="https://cdn.tailwindcss.com"></script>
- Use Chart.js via CDN: <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
- Create a beautiful, modern slide design with proper typography and spacing
- Include exactly one main heading (h1) and supporting content
- Make it visually appealing with proper color schemes and layouts it has white-background so choose accordingly
- Male all boxes symmetrical and beautiful.
- Keep content concise and scannable
- No external JavaScript dependencies beyond Tailwind and Chart.js
- Responsive design that works on different screen sizes
- Professional appearance suitable for business presentations
- Constrain slide dimensions to 720p (1280x720 pixels)
- Return ONLY the HTML document, no markdown code fences (```html or ```)

STYLING GUIDE:
Brand palette
-Primary: Lava 600 #EB4A34, Lava 500 #EB6C53, Navy 900 #102025, Navy 800 #2B3940
-Neutrals: Oat Light #F9FAFB, Oat Medium #E4E5E5, Gray-Text #5D6D71, Gray-Muted #8D8E93, Gray-Lines #B2BAC0, Gray-Navigation #2B3940
-Accents: Green 600 #4BA676, Yellow 600 #F2AE3D, Blue 600 #3C71AF, Maroon 600 #8C2330
Usage rules
-Backgrounds: Oat Light; use Oat Medium sparingly for content bands or sidebars.
-Primary emphasis: Lava 600 (buttons, key numbers, callouts). Hover/secondary: Lava 500.
-Headlines & nav: Navy 900 (#102025) for main titles, Navy 800 (#2B3940) for subtitles. Body: Gray-Text (#5D6D71); captions/notes: Gray-Muted (#8D8E93).
-Dividers/borders: Gray-Lines, 1–2 px.
-Status: Success Green, Warning Yellow, Info Blue, Critical Lava/Maroon (use once per slide).

Typography
-Typeface: modern geometric sans (e.g., Inter, SF Pro, Helvetica Now). Consistent across deck.
-Weights: Headings semibold/bold; body regular/medium.
-Sizes (min): H1 48–64, H2 36–44, H3 28–32, body 18–22, captions 14–16.
-Line length target: 45–75 characters. Avoid paragraphs >3 lines.

Layout & spacing
-Grid: 12-column with 24 px gutters; base spacing unit 8 px.
Max text per slide: ≤40 words (exceptions: appendix).
Visual hierarchy: one focal element per slide.

CRITICAL SLIDE CONSTRAINTS:
- Slide dimensions: 1280x720 pixels (720p)
- White background (#FFFFFF) for main slide area
- All content boxes must be symmetrical and properly spaced
- Ensure all colors are visible and not hidden by background
- Maintain proper contrast ratios for accessibility
- Box shadows: subtle (0 4px 6px rgba(0, 0, 0, 0.1))
- Border radius: 8-12px for cards and boxes
- Padding: minimum 24px inside all content boxes
- Margins: minimum 16px between elements
- Text must not overflow slide boundaries
- All elements must fit within 1280x720 viewport

MANDATORY CSS STRUCTURE:
- Body must have: width: 1280px; height: 720px; margin: 0; padding: 0; overflow: hidden;
- Main container must have: max-width: 1280px; max-height: 720px; margin: 0 auto;
- Content area must have: padding: 32px; box-sizing: border-box;
- Use fixed positioning or flexbox to ensure content stays within bounds

HEADER/TITLE SPECIFIC RULES:
- Main title (H1): Use Navy 900 (#102025) color, NOT gray
- Title text: Bold, 48-64px font size, high contrast
- DO NOT use gray colors for main titles - use Navy 900 for visibility
- Ensure title text is clearly visible against white background

CHART INTEGRATION RULES:
- Use Chart.js for data visualization when content includes data, metrics, or trends
- Chart types: bar, line, pie, doughnut, area, radar, scatter
- Chart colors: Use brand palette (Lava 600 #EB4A34, Green 600 #4BA676, Blue 600 #3C71AF, Yellow 600 #F2AE3D)
- Chart sizing: Fit within slide content area, maintain 16px margins
- Chart responsiveness: Use responsive: true in Chart.js config
- Chart accessibility: Include proper labels, legends, and tooltips
- Chart examples: Market growth, performance metrics, survey results, comparisons

CHART.JS IMPLEMENTATION REQUIREMENTS:
- ALWAYS include Chart.js CDN: <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
- Initialize chart in script: new Chart(document.getElementById('chartCanvas'), { type: 'bar', data: {...}, options: {...} })
- Use brand colors: backgroundColor: ['#EB4A34', '#4BA676', '#3C71AF', '#F2AE3D']
- Set responsive: true and maintainAspectRatio: false in options
- Include proper labels, datasets, and data arrays
- Place chart in a container div with proper Tailwind classes
"""

# Allow inline scripts that initialize Tailwind tweaks or Chart.js without exposing other arbitrary JS.
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


def _is_allowed_inline_script(tag: Tag) -> bool:
    """Permit known-safe inline scripts required for Tailwind styling or Chart.js rendering."""
    text = (tag.get_text() or "").strip().lower()
    if not text:
        return False
    return any(keyword in text for keyword in ALLOWED_INLINE_SCRIPT_KEYWORDS)


# =========================
# Models
# =========================
class SlideTheme(BaseModel):
    """Theme configuration for slide decks."""
    bottom_right_logo_url: Optional[str] = None
    footer_text: Optional[str] = None

class ExtractedConfig(BaseModel):
    topic: Optional[str] = None
    style_hint: Optional[str] = None
    n_slides: Optional[conint(ge=1, le=40)] = None

class Change(BaseModel):
    slide_id: Optional[int] = None
    op: Literal[
        "REPLACE_TITLE","REPLACE_BULLETS","APPEND_BULLET","DELETE_BULLET",
        "INSERT_IMAGE","EDIT_RAW_HTML","INSERT_SLIDE_AFTER","DELETE_SLIDE",
        "REORDER_SLIDES"
    ]
    args: dict = Field(default_factory=dict)

class Todo(BaseModel):
    id: int
    action: Literal["WRITE_SLIDE", "FINALIZE_DECK"]
    title: str
    details: str = ""
    depends_on: List[int] = Field(default_factory=list)

class UtteranceIntent(BaseModel):
    intent: Literal[
        "REQUEST_DECK","REFINE_CONFIG","ADD_CHANGES",
        "REGENERATE_TODOS","FINALIZE","SAVE","SHOW_STATUS"
    ]
    config_delta: ExtractedConfig = ExtractedConfig()
    changes: List[Change] = Field(default_factory=list)
    notes: Optional[str] = None

class SlideStatus(BaseModel):
    id: int
    title: str
    html: str  # sanitized <section class="slide">…</section> ("" if not generated)


# =========================
# State
# =========================
class AgentState(TypedDict):
    messages: List[Dict[str, str]]      # chat history
    topic: Optional[str]
    style_hint: Optional[str]
    n_slides: Optional[int]
    config_version: int
    todos: List[Todo]
    cursor: int
    artifacts: Dict[int, str]           # slideId -> sanitized HTML
    deck_html: str
    pending_changes: List[Change]
    run_id: str
    errors: List[str]
    metrics: Dict[str, float]
    last_intent: Optional[str]
    status: List[SlideStatus] | None

# =========================
# LLMs
# =========================
# Initialize Databricks client
ws = WorkspaceClient(profile='e2-demo', product='slide-generator')
model_serving_client = ws.serving_endpoints.get_open_ai_client()

# LLM endpoint names
NLU_ENDPOINT = "databricks-claude-sonnet-4"
PLAN_ENDPOINT = "databricks-claude-sonnet-4" 
HTML_ENDPOINT = "databricks-claude-sonnet-4"

# =========================
# Tools
# =========================
@tool("interpret_utterance", return_direct=False)
def interpret_utterance(messages: List[Dict[str, str]], current_config: ExtractedConfig) -> UtteranceIntent:
    """Interpret user messages and extract intent, config changes, and slide modifications."""
    sys = (
        "You are an intent recognizer for a slides agent. "
        "From chat messages, return intent + any config deltas (topic/style/n_slides) and changes. "
        "Valid intents: REQUEST_DECK, REFINE_CONFIG, ADD_CHANGES, REGENERATE_TODOS, FINALIZE, SAVE, SHOW_STATUS. "
        "Return only JSON."
    )
    user = f"Messages (recent last):\n{json.dumps(messages[-12:], ensure_ascii=False, indent=2)}\n\nCurrent config: {current_config.model_dump()}"
    
    response = model_serving_client.chat.completions.create(
        model=NLU_ENDPOINT,
        messages=[
            {"role":"system","content":sys},
            {"role":"user","content":user}
        ]
    )
    
    # Parse the response and create UtteranceIntent
    content = response.choices[0].message.content
    print(f"NLU response: {content}")
    
    # Strip markdown code fences if present
    if content.startswith("```json"):
        content = content[7:]  # Remove ```json
    if content.startswith("```"):
        content = content[3:]   # Remove ```
    if content.endswith("```"):
        content = content[:-3]  # Remove trailing ```
    content = content.strip()
    
    data = json.loads(content)
    
    # Validate and fix intent if needed
    valid_intents = ["REQUEST_DECK", "REFINE_CONFIG", "ADD_CHANGES", "REGENERATE_TODOS", "FINALIZE", "SAVE", "SHOW_STATUS"]
    if data.get("intent") not in valid_intents:
        data["intent"] = "REQUEST_DECK"  # Default fallback
    
    return UtteranceIntent(**data)

@tool("create_todos", return_direct=False)
def create_todos(topic: str, style_hint: str, n_slides: int) -> List[Todo]:
    """Create a list of todos for slide generation based on topic, style, and number of slides."""
    
    sys = ("Return ordered JSON TODOs as an array. Each todo must have: id (integer), action (WRITE_SLIDE or FINALIZE_DECK), title (string), details (string), depends_on (array of integers). "
           "First N: WRITE_SLIDE; last: FINALIZE_DECK depending on prior ids. "
           "Titles <= 8 words; bullets concise. Return only JSON.")
    user = f"Topic: {topic}\nStyle: {style_hint}\nSlides requested: {n_slides}\nReturn EXACTLY {n_slides+1} items."
    
    response = model_serving_client.chat.completions.create(
        model=PLAN_ENDPOINT,
        messages=[
            {"role":"system","content":sys},
            {"role":"user","content":user}
        ]
    )
    
    content = response.choices[0].message.content
    
    # Strip markdown code fences if present
    if content.startswith("```json"):
        content = content[7:]  # Remove ```json
    if content.startswith("```"):
        content = content[3:]   # Remove ```
    if content.endswith("```"):
        content = content[:-3]  # Remove trailing ```
    content = content.strip()
    
    data = json.loads(content)
    
    # Ensure data is a list
    if not isinstance(data, list):
        data = [data]
    
    # Validate and fix each todo
    valid_actions = ["WRITE_SLIDE"]
    for item in data:
        item["action"] = item.get("action") if item.get("action") in valid_actions else "WRITE_SLIDE"
        item["id"] = item.get("id") if isinstance(item.get("id"), int) else len(data)
        item["depends_on"] = item.get("depends_on") if isinstance(item.get("depends_on"), list) else []
    
    return [Todo(**item) for item in data]

@tool("write_slide_html", return_direct=False)
def write_slide_html(title: str, outline: str, style_hint: str) -> str:
    """Generate complete HTML document for a single slide with Tailwind CSS."""
    print(f"[DEBUG] write_slide_html - title: {title}")
    print(f"[DEBUG] write_slide_html - outline: {outline}")
    print(f"[DEBUG] write_slide_html - style_hint: {style_hint}")
    
    sys = "Create a complete HTML document for a single slide." + HTML_CONSTRAINTS
    user = f"TITLE: {title}\nOUTLINE: {outline}\nSTYLE: {style_hint}\n\nCreate a beautiful, modern slide using Tailwind CSS with the exact brand colors and spacing specified. Ensure all content fits within 1280x720 pixels with proper contrast and visibility. Use white background and symmetrical layout. IMPORTANT: Use Navy 900 (#102025) for the main title, NOT gray colors. If the content includes data, metrics, or trends, add a Chart.js visualization using the brand colors. CRITICAL: Include Chart.js CDN, create canvas element, and initialize chart with proper JavaScript code."
    
    print(f"[DEBUG] write_slide_html - calling LLM with endpoint: {HTML_ENDPOINT}")
    response = model_serving_client.chat.completions.create(
        model=HTML_ENDPOINT,
        messages=[
            {"role":"system","content":sys},
            {"role":"user","content":user}
        ]
    )
    
    raw_content = response.choices[0].message.content.strip()
    print(f"[DEBUG] write_slide_html - raw LLM response length: {len(raw_content)}")
    print(f"[DEBUG] write_slide_html - raw LLM response preview: {raw_content[:200]}...")
    
    # Remove markdown code fences if present
    if raw_content.startswith("```html"):
        raw_content = raw_content[7:]  # Remove ```html
        print(f"[DEBUG] write_slide_html - removed ```html prefix")
    if raw_content.startswith("```"):
        raw_content = raw_content[3:]   # Remove ```
        print(f"[DEBUG] write_slide_html - removed ``` prefix")
    if raw_content.endswith("```"):
        raw_content = raw_content[:-3]  # Remove trailing ```
        print(f"[DEBUG] write_slide_html - removed ``` suffix")
    
    cleaned_content = raw_content.strip()
    print(f"[DEBUG] write_slide_html - final content length: {len(cleaned_content)}")
    print(f"[DEBUG] write_slide_html - final content preview: {cleaned_content[:200]}...")
    
    return cleaned_content

@tool("create_slide_from_spec", return_direct=False)
def create_slide_from_spec(title: str, bullets: List[str], style_hint: str) -> str:
    """Create a complete HTML document for a slide from a specification with title and bullet points."""
    print(f"[DEBUG] create_slide_from_spec - title: {title}")
    print(f"[DEBUG] create_slide_from_spec - bullets count: {len(bullets)}")
    print(f"[DEBUG] create_slide_from_spec - style_hint: {style_hint}")
    
    sys = "Create a complete HTML document for a single slide from specification." + HTML_CONSTRAINTS
    bullet_text = "\n".join(f"- {b}" for b in bullets)
    user = f"TITLE: {title}\nBULLETS: {bullet_text}\nSTYLE: {style_hint}\n\nCreate a beautiful, modern slide using Tailwind CSS with the exact brand colors and spacing specified."
    
    print(f"[DEBUG] create_slide_from_spec - calling LLM with endpoint: {HTML_ENDPOINT}")
    response = model_serving_client.chat.completions.create(
        model=HTML_ENDPOINT,
        messages=[
            {"role":"system","content":sys},
            {"role":"user","content":user}
        ]
    )
    
    raw_content = response.choices[0].message.content.strip()
    print(f"[DEBUG] create_slide_from_spec - raw LLM response length: {len(raw_content)}")
    print(f"[DEBUG] create_slide_from_spec - raw LLM response preview: {raw_content[:200]}...")
    
    # Remove markdown code fences if present
    if raw_content.startswith("```html"):
        raw_content = raw_content[7:]  # Remove ```html
        print(f"[DEBUG] create_slide_from_spec - removed ```html prefix")
    if raw_content.startswith("```"):
        raw_content = raw_content[3:]   # Remove ```
        print(f"[DEBUG] create_slide_from_spec - removed ``` prefix")
    if raw_content.endswith("```"):
        raw_content = raw_content[:-3]  # Remove trailing ```
        print(f"[DEBUG] create_slide_from_spec - removed ``` suffix")
    
    cleaned_content = raw_content.strip()
    print(f"[DEBUG] create_slide_from_spec - final content length: {len(cleaned_content)}")
    print(f"[DEBUG] create_slide_from_spec - final content preview: {cleaned_content[:200]}...")
    
    return cleaned_content

@tool("patch_slide_html", return_direct=False)
def patch_slide_html(slide_html: str, change: Change, style_hint: str) -> str:
    """LLM-only patch. Validates & self-repairs up to 2 retries."""
    def _llm_edit(src_html: str, ch: Change) -> str:
        print(f"[DEBUG] _llm_edit - change: {ch.model_dump_json()}")
        print(f"[DEBUG] _llm_edit - style_hint: {style_hint}")
        
        sys = "Apply a slide change while maintaining beautiful Tailwind CSS design." + HTML_CONSTRAINTS
        user = f"CURRENT SLIDE:\n{src_html}\nCHANGE: {ch.model_dump_json()}\nSTYLE: {style_hint}\n\nApply the change while keeping the modern Tailwind CSS styling and design."
        
        print(f"[DEBUG] _llm_edit - calling LLM with endpoint: {HTML_ENDPOINT}")
        response = model_serving_client.chat.completions.create(
            model=HTML_ENDPOINT,
            messages=[
                {"role":"system","content":sys},
                {"role":"user","content":user}
            ]
        )
        
        raw_content = response.choices[0].message.content.strip()
        print(f"[DEBUG] _llm_edit - raw LLM response length: {len(raw_content)}")
        
        # Remove markdown code fences if present
        if raw_content.startswith("```html"):
            raw_content = raw_content[7:]  # Remove ```html
            print(f"[DEBUG] _llm_edit - removed ```html prefix")
        if raw_content.startswith("```"):
            raw_content = raw_content[3:]   # Remove ```
            print(f"[DEBUG] _llm_edit - removed ``` prefix")
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]  # Remove trailing ```
            print(f"[DEBUG] _llm_edit - removed ``` suffix")
        
        return raw_content.strip()
    
    def _validate_html_direct(html: str, kind: str) -> bool:
        """Direct validation without LangGraph tool wrapper"""
        soup = BeautifulSoup(html, "lxml")
        if kind == "slide":
            # Check for complete HTML document structure
            if not soup.find("html"): return False
            if not soup.find("head"): return False
            if not soup.find("body"): return False
            
            # Check for main heading
            if len(soup.find_all("h1")) != 1: return False
            
            # Check for content (ul, p, div, etc.)
            if not (soup.select("ul li") or soup.select("p") or soup.select("div")):
                return False
                
            # Check for Tailwind CSS and Chart.js
            if not soup.find("script", src=lambda x: x and "tailwindcss.com" in x):
                return False
            if not soup.find("script", src=lambda x: x and "chart.js" in x):
                return False
            
            # Check for proper viewport constraints
            body = soup.find("body")
            if body:
                style = body.get("style", "")
                # Check for width: 1280px and height: 720px in body style
                if "width: 1280px" not in style and "width:1280px" not in style:
                    return False
                if "height: 720px" not in style and "height:720px" not in style:
                    return False
                if "overflow: hidden" not in style and "overflow:hidden" not in style:
                    return False
                
            # Check for main container with proper constraints
            main_container = soup.find("div", class_=lambda x: x and ("container" in x or "main" in x or "slide" in x))
            if main_container:
                style = main_container.get("style", "")
                # Check for max-width and max-height constraints
                if "max-width: 1280px" not in style and "max-width:1280px" not in style:
                    return False
                if "max-height: 720px" not in style and "max-height:720px" not in style:
                    return False
                
            # Basic security checks
            for tag in soup(True):
                for a in list(tag.attrs.keys()):
                    if a.lower().startswith("on"): return False
                    if a.lower() in {"href","src"} and str(tag.attrs[a]).strip().lower().startswith("javascript:"):
                        return False
            return True
        else:
            return bool(soup.find("html") and soup.find("head") and soup.find("body"))
    
    def _sanitize_html_direct(html: str, level: str) -> str:
        """Direct sanitization without LangGraph tool wrapper"""
        soup = BeautifulSoup(html, "lxml")
        
        # Keep Tailwind CSS and Chart.js scripts but remove other scripts
        for s in soup.find_all("script"):
            src = s.get("src")
            if src:
                if not any(needle in src for needle in ALLOWED_SCRIPT_SRC_SUBSTRINGS):
                    s.decompose()
            elif not _is_allowed_inline_script(s):
                s.decompose()
        
        # strip events + javascript: URLs
        for tag in soup(True):
            for a in list(tag.attrs.keys()):
                if a.lower().startswith("on"):
                    del tag.attrs[a]
                if a.lower() in {"href","src"} and isinstance(tag.attrs[a], str) and tag.attrs[a].strip().lower().startswith("javascript:"):
                    del tag.attrs[a]
        return str(soup)
    
    print(f"[DEBUG] patch_slide_html - starting patch operation")
    edited = _llm_edit(slide_html, change)
    print(f"[DEBUG] patch_slide_html - initial edit completed, length: {len(edited)}")
    
    if _validate_html_direct(edited, "slide"):
        print(f"[DEBUG] patch_slide_html - initial edit passed validation")
        return _sanitize_html_direct(edited, "conservative")
    
    print(f"[DEBUG] patch_slide_html - initial edit failed validation, attempting repairs")
    for attempt in range(2):
        print(f"[DEBUG] patch_slide_html - repair attempt {attempt + 1}/2")
        sys = "Self-correct invalid slide to pass validation while maintaining Tailwind CSS design." + HTML_CONSTRAINTS
        user = f"INVALID:\n---\n{edited}\n---\nORIGINAL:\n---\n{slide_html}\n---\nCHANGE JSON:\n{change.model_dump_json()}\nSTYLE: {style_hint}\n\nFix the slide while keeping beautiful Tailwind CSS styling. CRITICAL: The slide MUST be exactly 1280x720 pixels with body width: 1280px; height: 720px; margin: 0; padding: 0; overflow: hidden; and a main container with max-width: 1280px; max-height: 720px; margin: 0 auto; padding: 32px; box-sizing: border-box;. Ensure all content fits within these dimensions with proper contrast and visibility."
        
        response = model_serving_client.chat.completions.create(
            model=HTML_ENDPOINT,
            messages=[
                {"role":"system","content":sys},
                {"role":"user","content":user}
            ]
        )
        edited = response.choices[0].message.content.strip()
        
        # Remove markdown code fences if present
        if edited.startswith("```html"):
            edited = edited[7:]  # Remove ```html
        if edited.startswith("```"):
            edited = edited[3:]   # Remove ```
        if edited.endswith("```"):
            edited = edited[:-3]  # Remove trailing ```
        edited = edited.strip()
        
        print(f"[DEBUG] patch_slide_html - repair attempt {attempt + 1} completed, length: {len(edited)}")
        if _validate_html_direct(edited, "slide"):
            print(f"[DEBUG] patch_slide_html - repair attempt {attempt + 1} passed validation")
            return _sanitize_html_direct(edited, "conservative")
    
    print(f"[DEBUG] patch_slide_html - all repair attempts failed, returning sanitized content")
    return _sanitize_html_direct(edited, "conservative")




@tool("save_file", return_direct=False)
def save_file(path: str, content: str) -> str:
    """Save content to a file at the specified path."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return os.path.abspath(path)

@tool("validate_html", return_direct=False)
def validate_html(html: str, kind: Literal["slide","deck"]) -> bool:
    """Validate HTML content for slides or complete decks."""
    soup = BeautifulSoup(html, "lxml")
    if kind == "slide":
        # Check for complete HTML document structure
        if not soup.find("html"): return False
        if not soup.find("head"): return False
        if not soup.find("body"): return False
        
        # Check for main heading
        if len(soup.find_all("h1")) != 1: return False
        
        # Check for content (ul, p, div, etc.)
        if not (soup.select("ul li") or soup.select("p") or soup.select("div")):
            return False
            
        # Check for Tailwind CSS and Chart.js
        if not soup.find("script", src=lambda x: x and "tailwindcss.com" in x):
            return False
        if not soup.find("script", src=lambda x: x and "chart.js" in x):
            return False
        
        # Check for proper viewport constraints
        body = soup.find("body")
        if body:
            style = body.get("style", "")
            # Check for width: 1280px and height: 720px in body style
            if "width: 1280px" not in style and "width:1280px" not in style:
                return False
            if "height: 720px" not in style and "height:720px" not in style:
                return False
            if "overflow: hidden" not in style and "overflow:hidden" not in style:
                return False
            
        # Check for main container with proper constraints
        main_container = soup.find("div", class_=lambda x: x and ("container" in x or "main" in x or "slide" in x))
        if main_container:
            style = main_container.get("style", "")
            # Check for max-width and max-height constraints
            if "max-width: 1280px" not in style and "max-width:1280px" not in style:
                return False
            if "max-height: 720px" not in style and "max-height:720px" not in style:
                return False
            
        # Basic security checks
        for tag in soup(True):
            for a in list(tag.attrs.keys()):
                if a.lower().startswith("on"): return False
                if a.lower() in {"href","src"} and str(tag.attrs[a]).strip().lower().startswith("javascript:"):
                    return False
        return True
    else:
        return bool(soup.find("html") and soup.find("head") and soup.find("body"))

@tool("sanitize_html", return_direct=False)
def sanitize_html(html: str, level: Literal["conservative","deck"]) -> str:
    """Sanitize HTML content by removing dangerous attributes while preserving Tailwind CSS."""
    soup = BeautifulSoup(html, "lxml")
    
    # Keep Tailwind CSS and Chart.js scripts but remove other scripts
    for s in soup.find_all("script"):
        src = s.get("src")
        if src:
            if not any(needle in src for needle in ALLOWED_SCRIPT_SRC_SUBSTRINGS):
                s.decompose()
        elif not _is_allowed_inline_script(s):
            s.decompose()
    
    # strip events + javascript: URLs
    for tag in soup(True):
        for a in list(tag.attrs.keys()):
            if a.lower().startswith("on"):
                del tag.attrs[a]
            if a.lower() in {"href","src"} and isinstance(tag.attrs[a], str) and tag.attrs[a].strip().lower().startswith("javascript:"):
                del tag.attrs[a]
    return str(soup)

@tool("summarize_status", return_direct=False)
def summarize_status(todos: List[Todo], artifacts: Dict[int, str]) -> List[SlideStatus]:
    """Summarize the current status of all slides in the deck."""
    slides: List[SlideStatus] = []
    for t in todos:
        if t.action == "WRITE_SLIDE":
            slides.append(SlideStatus(id=t.id, title=t.title, html=artifacts.get(t.id, "")))
    return slides

# =========================
# Run-to-completion node
# =========================
def run_to_completion_node(s: AgentState) -> AgentState:
    # 1) NLU + config merge
    cfg = ExtractedConfig(topic=s.get("topic"), style_hint=s.get("style_hint"), n_slides=s.get("n_slides"))
    ui = interpret_utterance.invoke({"messages": s["messages"], "current_config": cfg}, config={"run_id": s.get("run_id", "default")})
    s["last_intent"] = ui.intent
    changed = False
    if ui.config_delta.topic and ui.config_delta.topic != s.get("topic"):
        s["topic"] = ui.config_delta.topic; changed = True
    if ui.config_delta.style_hint and ui.config_delta.style_hint != s.get("style_hint"):
        s["style_hint"] = ui.config_delta.style_hint; changed = True
    if ui.config_delta.n_slides and ui.config_delta.n_slides != s.get("n_slides"):
        s["n_slides"] = int(ui.config_delta.n_slides); changed = True
    if changed:
        s["config_version"] = (s.get("config_version") or 0) + 1
        s.update(todos=[], cursor=0, artifacts={}, deck_html="")

    # 2) Plan if needed
    if (s.get("topic") and s.get("style_hint") and s.get("n_slides")) and not s["todos"]:
        s["todos"] = create_todos.invoke({"topic": s["topic"], "style_hint": s["style_hint"], "n_slides": s["n_slides"]}, config={"run_id": s.get("run_id", "default")})
        s["cursor"] = 0

    # 3) Generate ALL slides
    slide_todos = [t for t in s["todos"] if t.action == "WRITE_SLIDE"]
    print(f"[DEBUG] run_to_completion_node - generating {len(slide_todos)} slides")
    for i, t in enumerate(slide_todos):
        print(f"[DEBUG] run_to_completion_node - generating slide {i+1}/{len(slide_todos)}: {t.title}")
        if t.id in s["artifacts"]:
            print(f"[DEBUG] run_to_completion_node - slide {t.id} already exists, skipping")
            continue
        raw = write_slide_html.invoke({"title": t.title, "outline": t.details, "style_hint": s["style_hint"]}, config={"run_id": s.get("run_id", "default")})
        print(f"[DEBUG] run_to_completion_node - slide {t.id} generated, length: {len(raw)}")
        if not validate_html.invoke({"html": raw, "kind":"slide"}, config={"run_id": s.get("run_id", "default")}):
            print(f"[DEBUG] run_to_completion_node - slide {t.id} failed validation, attempting repair")
            # attempt one repair pass using constraints
            raw = patch_slide_html.invoke({"slide_html": raw, "change": Change(op="EDIT_RAW_HTML", args={"fix":"structure"}), "style_hint": s["style_hint"]}, config={"run_id": s.get("run_id", "default")})
            print(f"[DEBUG] run_to_completion_node - slide {t.id} repair completed, length: {len(raw)}")
        s["artifacts"][t.id] = sanitize_html.invoke({"html": raw, "level":"conservative"}, config={"run_id": s.get("run_id", "default")})
        print(f"[DEBUG] run_to_completion_node - slide {t.id} sanitized and stored")

    # 4) Apply any user changes (LLM-only tools)
    s["pending_changes"] = ui.changes or []
    for ch in s["pending_changes"]:
        if ch.op == "REORDER_SLIDES":
            order = ch.args.get("order", [])
            slides = [t for t in s["todos"] if t.action=="WRITE_SLIDE"]
            id2t = {t.id: t for t in slides}
            new_slides = [id2t[i] for i in order if i in id2t]
            others = [t for t in s["todos"] if t.action!="WRITE_SLIDE"]
            s["todos"] = new_slides + others
            continue
        if ch.op == "DELETE_SLIDE":
            sid = ch.slide_id
            s["todos"] = [t for t in s["todos"] if not (t.action=="WRITE_SLIDE" and t.id==sid)]
            s["artifacts"].pop(sid, None)
            continue
        if ch.op == "INSERT_SLIDE_AFTER":
            after = ch.slide_id or 0
            title = ch.args.get("title","New Slide")
            bullets = ch.args.get("bullets",[])
            new_html = create_slide_from_spec.invoke({"title": title, "bullets": bullets, "style_hint": s["style_hint"]}, config={"run_id": s.get("run_id", "default")})
            if not validate_html.invoke({"html": new_html, "kind":"slide"}, config={"run_id": s.get("run_id", "default")}):
                new_html = patch_slide_html.invoke({"slide_html": new_html, "change": Change(op="EDIT_RAW_HTML", args={"fix":"structure"}), "style_hint": s["style_hint"]}, config={"run_id": s.get("run_id", "default")})
            new_id = max([t.id for t in s["todos"]], default=0) + 1
            s["artifacts"][new_id] = sanitize_html.invoke({"html": new_html, "level":"conservative"}, config={"run_id": s.get("run_id", "default")})
            slides = [t for t in s["todos"] if t.action=="WRITE_SLIDE"]
            others = [t for t in s["todos"] if t.action!="WRITE_SLIDE"]
            inserted: List[Todo] = []
            for t in slides:
                inserted.append(t)
                if t.id == after:
                    inserted.append(Todo(id=new_id, action="WRITE_SLIDE", title=title, details="", depends_on=[]))
            if after == 0:
                inserted = [Todo(id=new_id, action="WRITE_SLIDE", title=title, details="", depends_on=[])] + inserted
            s["todos"] = inserted + others
            continue
        # Per-slide content edits
        sid = ch.slide_id
        if sid is None or sid not in s["artifacts"]:
            continue
        updated = patch_slide_html.invoke({"slide_html": s["artifacts"][sid], "change": ch, "style_hint": s["style_hint"]}, config={"run_id": s.get("run_id", "default")})
        s["artifacts"][sid] = updated
    s["pending_changes"] = []

    # 5) FINALIZE (individual slides are already complete HTML documents)
    if s["todos"]:
        slide_ids = [t.id for t in s["todos"] if t.action=="WRITE_SLIDE"]
        slides = [s["artifacts"].get(i,"") for i in slide_ids if s["artifacts"].get(i,"")]
        print(f"[DEBUG] run_to_completion_node - slide_ids: {slide_ids}")
        print(f"[DEBUG] run_to_completion_node - slides count: {len(slides)}")
        if slides:
            print(f"[DEBUG] run_to_completion_node - slides are complete HTML documents")
            # Each slide is already a complete HTML document with Tailwind CSS
            s["deck_html"] = ""  # Not needed since we return individual slides
            print(f"[DEBUG] run_to_completion_node - individual slides ready")
        else:
            print(f"[DEBUG] run_to_completion_node - no slides to process")

    # 6) SAVE (auto) - save individual slides
    if s["artifacts"]:
        for slide_id, slide_html in s["artifacts"].items():
            save_file.invoke({"path": f"slide_{slide_id}.html", "content": slide_html}, config={"run_id": s.get("run_id", "default")})

    # 7) Status list with slide HTML
    s["status"] = summarize_status.invoke({"todos": s["todos"], "artifacts": s["artifacts"]}, config={"run_id": s.get("run_id", "default")})
    return s

# =========================
# Graph wiring (single hop)
# =========================
g = StateGraph(AgentState)
g.add_node("run", run_to_completion_node)
g.set_entry_point("run")
app_graph = g.compile(checkpointer=SqliteSaver("slides_agent.db"))

class HtmlDeck:
    """LLM-based HTML slide deck generator with state management."""

    def __init__(self, theme: Optional[SlideTheme] = None) -> None:
        self.theme = theme or SlideTheme()
        self.state: AgentState = {
            "messages": [],
            "topic": None,
            "style_hint": None,
            "n_slides": None,
            "config_version": 0,
            "todos": [],
            "cursor": 0,
            "artifacts": {},
            "deck_html": "",
            "pending_changes": [],
            "run_id": "",
            "errors": [],
            "metrics": {},
            "last_intent": None,
            "status": None
        }
        self.TOOLS = [
  {
    "type": "function",
    "function": {
                    "name": "tool_generate_deck",
                    "description": "Generate a complete slide deck from topic, style, and number of slides",
      "parameters": {
        "type": "object",
        "properties": {
                            "topic": {"type": "string"},
                            "style_hint": {"type": "string"},
                            "n_slides": {"type": "integer", "minimum": 1, "maximum": 40}
                        },
                        "required": ["topic", "style_hint", "n_slides"],
        "additionalProperties": False
      }
    }
  },
  {
    "type": "function",
    "function": {
                    "name": "tool_modify_slide",
                    "description": "Modify a specific slide with various operations",
      "parameters": {
        "type": "object",
        "properties": {
                            "slide_id": {"type": "integer"},
                            "operation": {
                                "type": "string",
                                "enum": ["REPLACE_TITLE", "REPLACE_BULLETS", "APPEND_BULLET", "DELETE_BULLET", "EDIT_RAW_HTML"]
        },
                            "args": {"type": "object"}
                        },
                        "required": ["slide_id", "operation", "args"],
        "additionalProperties": False
      }
    }
  },
  {
    "type": "function",
    "function": {
                    "name": "tool_reorder_slides",
                    "description": "Reorder slides in the deck",
      "parameters": {
        "type": "object",
        "properties": {
                            "order": {"type": "array", "items": {"type": "integer"}}
                        },
                        "required": ["order"],
        "additionalProperties": False
      }
    }
  },
  {
    "type": "function",
    "function": {
                    "name": "tool_delete_slide",
                    "description": "Delete a slide from the deck",
      "parameters": {
        "type": "object",
        "properties": {
                            "slide_id": {"type": "integer"}
        },
                        "required": ["slide_id"],
        "additionalProperties": False
      }
    }
  },
  {
    "type": "function",
    "function": {
                    "name": "tool_insert_slide",
                    "description": "Insert a new slide after a specific slide",
      "parameters": {
        "type": "object",
        "properties": {
                            "after_slide_id": {"type": "integer"},
                            "title": {"type": "string"},
                            "bullets": {"type": "array", "items": {"type": "string"}}
        },
                        "required": ["after_slide_id", "title", "bullets"],
        "additionalProperties": False
      }
    }
  },
  {
    "type": "function",
    "function": {
                    "name": "tool_get_status",
                    "description": "Get current status of all slides",
      "parameters": {
        "type": "object",
                        "properties": {},
                        "required": [],
        "additionalProperties": False
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "tool_get_html",
                    "description": "Get the complete HTML deck",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False
      }
    }
  },
  {
    "type": "function",
    "function": {
                    "name": "tool_save_html",
                    "description": "Save the HTML deck to a file",
      "parameters": {
        "type": "object",
        "properties": {
                            "output_path": {"type": "string"}
        },
        "required": ["output_path"],
        "additionalProperties": False
      }
    }
  }
]

    def process_message(self, message: str) -> str:
        """Process a user message and update the deck state"""
        self.state["messages"].append({"role": "user", "content": message})
        self.state = run_to_completion_node(self.state)
        return self.state.get("deck_html", "")

    # Tool functions for LLM integration
    def tool_generate_deck(self, topic: str, style_hint: str, n_slides: int, **kwargs) -> str:
        """Generate a complete slide deck"""
        print(f"[DEBUG] tool_generate_deck - topic: {topic}, style_hint: {style_hint}, n_slides: {n_slides}")
        self.state["topic"] = topic
        self.state["style_hint"] = style_hint
        self.state["n_slides"] = n_slides
        self.state["config_version"] += 1
        self.state.update(todos=[], cursor=0, artifacts={}, deck_html="")
        print(f"[DEBUG] tool_generate_deck - state updated, about to call run_to_completion_node")
        
        # Generate the deck
        print(f"[DEBUG] tool_generate_deck - calling run_to_completion_node")
        self.state = run_to_completion_node(self.state)
        print(f"[DEBUG] tool_generate_deck - run_to_completion_node completed")
        print(f"[DEBUG] tool_generate_deck - artifacts count: {len(self.state.get('artifacts', {}))}")
        print(f"[DEBUG] tool_generate_deck - todos count: {len(self.state.get('todos', []))}")
        return f"Generated {n_slides} slides on '{topic}' with style '{style_hint}'"

    def tool_modify_slide(self, slide_id: int, operation: str, args: dict, **kwargs) -> str:
        """Modify a specific slide"""
        change = Change(slide_id=slide_id, op=operation, args=args)
        self.state["pending_changes"] = [change]
        self.state = run_to_completion_node(self.state)
        return f"Modified slide {slide_id} with operation {operation}"

    def tool_reorder_slides(self, order: List[int], **kwargs) -> str:
        """Reorder slides in the deck"""
        change = Change(op="REORDER_SLIDES", args={"order": order})
        self.state["pending_changes"] = [change]
        self.state = run_to_completion_node(self.state)
        return f"Reordered slides to: {order}"

    def tool_delete_slide(self, slide_id: int, **kwargs) -> str:
        """Delete a slide from the deck"""
        change = Change(slide_id=slide_id, op="DELETE_SLIDE")
        self.state["pending_changes"] = [change]
        self.state = run_to_completion_node(self.state)
        return f"Deleted slide {slide_id}"

    def tool_insert_slide(self, after_slide_id: int, title: str, bullets: List[str], **kwargs) -> str:
        """Insert a new slide after a specific slide"""
        change = Change(
            slide_id=after_slide_id,
            op="INSERT_SLIDE_AFTER",
            args={"title": title, "bullets": bullets}
        )
        self.state["pending_changes"] = [change]
        self.state = run_to_completion_node(self.state)
        return f"Inserted slide '{title}' after slide {after_slide_id}"

    def tool_get_status(self, **kwargs) -> str:
        """Get current status of all slides"""
        if self.state.get("status"):
            status_lines = []
            for slide in self.state["status"]:
                status_lines.append(f"Slide {slide.id}: {slide.title}")
            return "\n".join(status_lines)
        return "No slides generated yet"

    def tool_get_html(self, **kwargs) -> List[str]:
        """Get the list of individual slide HTML strings"""
        slide_ids = [t.id for t in self.state.get("todos", []) if t.action == "WRITE_SLIDE"]
        slides = [self.state.get("artifacts", {}).get(i, "") for i in slide_ids if self.state.get("artifacts", {}).get(i, "")]
        
        # Return slides as complete HTML documents (no cleaning needed)
        print(f"[DEBUG] tool_get_html - returning {len(slides)} complete HTML slides")
        return slides

    def tool_save_html(self, output_path: str, **kwargs) -> str:
        """Save the HTML deck to a file"""
        html_content = self.state.get("deck_html", "")
        if not html_content:
            return "No HTML content to save"
        
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return f"HTML saved to: {output_path}"

    def to_html(self) -> List[str]:
        """Get the list of individual slide HTML strings (compatibility method)"""
        return self.tool_get_html()






# =========================
# Demo and testing
# =========================
if __name__ == "__main__":
    print("HTML Slide Generator - Databricks LLM approach")
    print("=" * 50)
    
    # Create a new deck
    deck = HtmlDeck()
    
    # Generate a simple deck
    result = deck.tool_generate_deck(
        topic="AI and Machine Learning",
        style_hint="Professional, clean, modern",
        n_slides=3
    )
    print(f"Generation result: {result}")
    
    # Get the HTML
    html = deck.tool_get_html()
    if html:
        print("HTML generated successfully!")
        print(f"HTML length: {len(html)} characters")
    else:
        print("No HTML generated")
    
    # Get status
    status = deck.tool_get_status()
    print(f"Status: {status}")
