"""FastAPI backend for the slide generator application."""

import html
import json
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional
import re
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn
import time

# Import slide generator modules
import sys
sys.path.append(str(Path(__file__).parent.parent / "src"))

from slide_generator.tools import html_slides_agent
# Make UC tools optional to allow backend to start without unitycatalog/databricks-connect
try:
    from slide_generator.tools import uc_tools  # type: ignore
    TOOL_DICT = uc_tools.UC_tools
except Exception:
    print("Warning: UC tools not available; starting without UC_tools.")
    TOOL_DICT = {}
# Legacy chatbot.py removed - now using LangGraph-based agent
from slide_generator.config import config
from databricks.sdk import WorkspaceClient

# Databricks client - lazy loaded to avoid configuration issues
_ws = None

def get_databricks_client():
    """Get or create Databricks client (lazy initialization)."""
    global _ws
    if _ws is None:
        _ws = WorkspaceClient(profile=config.databricks_profile, product='slide-generator')
    return _ws

def get_logo_base64():
    """Load the EY-Parthenon logo and encode it as base64 for embedding in HTML."""
    logo_path = Path(__file__).parent.parent / "src" / "slide_generator" / "assets" / "EY-Parthenon_Logo_2021.svg"
    try:
        with open(logo_path, 'rb') as logo_file:
            logo_data = logo_file.read()
            return base64.b64encode(logo_data).decode('utf-8')
    except FileNotFoundError:
        print(f"Warning: Logo file not found at {logo_path}")
        return ""

# Session management - replaces global state
class SessionManager:
    """Manages per-session slide agents and conversation state."""
    
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}
        # Default theme for slide agents
        self.default_theme = html_slides_agent.SlideTheme(
            bottom_right_logo_url=None,
            footer_text=None
        )
    
    def get_or_create_session(self, session_id: str) -> Dict:
        """Get or create session data including agent and conversation."""
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                'slide_agent': html_slides_agent.SlideDeckAgent(theme=self.default_theme),
                'conversation': {
                    'openai_conversation': [{"role": "system", "content": config.system_prompt}],
                    'api_conversation': []
                },
                'created_at': time.time()
            }
        return self.sessions[session_id]
    
    def get_slide_agent(self, session_id: str) -> html_slides_agent.SlideDeckAgent:
        """Get the slide agent for a session."""
        session = self.get_or_create_session(session_id)
        return session['slide_agent']
    
    def reset_session_agent(self, session_id: str) -> None:
        """Reset the slide agent for a session."""
        session = self.get_or_create_session(session_id)
        session['slide_agent'] = html_slides_agent.SlideDeckAgent(theme=self.default_theme)
    
    def clear_session_agent(self, session_id: str) -> None:
        """Clear the slide agent state but keep the agent instance."""
        session = self.get_or_create_session(session_id)
        agent = session['slide_agent']
        if agent is not None:
            agent.initial_state.update({
                "todos": [],
                "artifacts": {},
                "status": [],
                "messages": [],
                "config": html_slides_agent.SlideConfig(),
                "config_version": 0,
                "last_intent": None,
                "pending_changes": [],
                "errors": [],
                "metrics": {},
                "run_id": ""
            })

# Global session manager instance
session_manager = SessionManager()

# Initialize FastAPI app
app = FastAPI(title="Slide Generator API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state removed - now using SessionManager for proper session isolation

# --- Demo static mode -------------------------------------------------------
# When enabled, any user prompt will render a predefined set of static slides
# without calling the LLM or tools. Useful for controlled demos.
# NOTE: This is currently enabled and uses the new LLM flow (_run_llm_flow)
DEMO_STATIC_MODE: bool = True

def _append_api_message(session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    session = session_manager.get_or_create_session(session_id)
    session["conversation"]["api_conversation"].append(ChatMessage(role=role, content=content, metadata=metadata))





def _run_llm_flow(session_id: str, user_prompt: str) -> None:
    """Run the new LLM-based slide generation flow with user prompt"""
    try:
        # Get session-specific slide agent
        slide_agent = session_manager.get_slide_agent(session_id)
        
        # Check if this is a follow-on request or first-time request
        is_follow_on = slide_agent is not None and slide_agent.initial_state.get("todos") and len(slide_agent.initial_state.get("artifacts", {})) > 0
        
        if not is_follow_on:
            # First-time request: agent already created by session manager
            print(f"[DEBUG] LLM Flow - Using session agent for first-time request")
            
            _append_api_message(
                session_id,
                role="assistant",
                content=(
                    "I'll analyze your request and generate a professional slide deck using AI. "
                    "Let me process your message and extract the key information."
                ),
            )
        else:
            # Follow-on request: reuse existing agent
            print(f"[DEBUG] LLM Flow - Reusing existing agent for follow-on request")
            print(f"[DEBUG] LLM Flow - Current artifacts: {len(slide_agent.initial_state.get('artifacts', {}))}")
            print(f"[DEBUG] LLM Flow - Current todos: {len(slide_agent.initial_state.get('todos', []))}")
            
            _append_api_message(
                session_id,
                role="assistant",
                content="I'll process your follow-on request and update the existing slide deck.",
            )

        # Step 2: Process the message using the agent's built-in logic
        _append_api_message(
            session_id,
            role="assistant",
            content="Processing your request with AI...",
            metadata={"title": "Agent is using a tool"}
        )
        
        print(f"[DEBUG] LLM Flow - Processing user prompt: {user_prompt}")
        
        # Use the agent's process_message method
        import time
        process_start = time.time()
        result = slide_agent.process_message(user_prompt)
        process_time = time.time() - process_start
        print(f"[DEBUG] LLM Flow - process_message completed in {process_time:.2f}s")
        # print(f"[DEBUG] LLM Flow - process_message result: {result}")
        
        # Step 3: Check if slides were generated
        slides = result.get("slides", [])
        print(f"[DEBUG] LLM Flow - Generated {len(slides)} slides")
        
        if not slides:
            _append_api_message(
                session_id,
                role="assistant",
                content="❌ No slides were generated. Please try a different request.",
                metadata={"title": "Agent tool result"}
            )
            return
        
        # Step 4: Show progress efficiently (no artificial delays)
        _append_api_message(
            session_id,
            role="assistant",
            content=f"✅ Generated {len(slides)} slides successfully",
            metadata={"title": "Agent tool result"}
        )
        
        # Step 5: Show final status
        status_list = result.get("status", [])
        status_text = "\n".join([f"Slide {s.id}: {s.title}" for s in status_list])
        print(f"[DEBUG] LLM Flow - Status: {status_text}")
        
        if is_follow_on:
            _append_api_message(
                session_id,
                role="assistant",
                content=f"Slide deck updated successfully!\n\n{status_text}"
            )
        else:
            _append_api_message(
                session_id,
                role="assistant",
                content=f"Slide deck created successfully!\n\n{status_text}"
            )
        
        # Signal completion to stop frontend polling
        _append_api_message(session_id, role="assistant", content="Generation complete.", metadata={"title": "Done"})
        
    except Exception as e:
        print(f"[ERROR] LLM Flow - Error processing request: {e}")
        import traceback
        traceback.print_exc()
        _append_api_message(
            session_id,
            role="assistant",
            content=f"❌ Error processing your request: {str(e)}",
            metadata={"title": "Error"}
        )

def _run_prism_flow(session_id: str) -> None:
    try:
        # Reset the session agent for demo mode
        session_manager.reset_session_agent(session_id)
        slide_agent = session_manager.get_slide_agent(session_id)

        PRISM_SLIDES: List[str] = [
            """<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"/><meta content=\"width=device-width, initial-scale=1.0\" name=\"viewport\"/><title>Project Prism - The Opportunity</title><link href=\"https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css\" rel=\"stylesheet\"/><link href=\"https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.4.0/css/all.min.css\" rel=\"stylesheet\"/><link href=\"https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&amp;display=swap\" rel=\"stylesheet\"/><style>body{font-family:'Roboto',sans-serif;background-color:white;color:#1A365D;margin:0;padding:0}.slide-container{width:1280px;min-height:720px;overflow:hidden;position:relative}.header{padding:0 60px 8px}.header h1{margin:0}.content{padding:0 60px}.opportunity-icon{color:#FF5722;font-size:48px;margin-bottom:20px}.cost-icon{color:#FF5722;font-size:48px;margin-bottom:20px}.separator{width:2px;background-color:#E2E8F0;height:400px}.accent-text{color:#FF5722;font-weight:500}</style></head><body><div class=\"slide-container\"><div class=\"header\"><h1 class=\"text-3xl font-bold\">The Opportunity: AI Slide Generation for Consulting</h1></div><div class=\"content\"><div class=\"flex justify-between items-start\"><div class=\"w-1/2 pr-10\"><div class=\"opportunity-icon\"><i class=\"fas fa-lightbulb\"></i></div><h2 class=\"text-xl font-semibold mb-4\">Transforming Slide Creation for Consulting</h2><p class=\"mb-4\">Imagine if consulting firms could <span class=\"accent-text\">instantly create tailored, secure slides</span> from proprietary know-how &amp; sensitive client data—<span class=\"accent-text\">automagically</span>.</p><ul class=\"list-disc pl-5 space-y-2\"><li>Leverage existing firm knowledge bases and client data</li><li>Maintain security and compliance across all materials</li><li>Generate high-quality slides that align with firm branding</li></ul><p class=\"mt-4\">Unlocking immediate value for industry leaders:</p><div class=\"flex space-x-4 mt-2\"><span class=\"font-semibold\">EY</span><span class=\"font-semibold\">KPMG</span><span class=\"font-semibold\">BCG</span><span class=\"font-semibold\">+ more</span></div></div><div class=\"separator mx-8\"></div><div class=\"w-1/2 pl-10\"><div class=\"cost-icon\"><i class=\"fas fa-chart-line\"></i></div><h2 class=\"text-xl font-semibold mb-4\">The Cost of Manual Slide Creation</h2><div class=\"mb-4\"><span class=\"text-4xl font-bold accent-text\">4 hours</span><span class=\"text-xl ml-2\">spent daily on slide creation</span></div><div class=\"bg-gray-50 p-4 rounded-lg mb-4\"><p class=\"font-semibold mb-2\">Impact per consultant:</p><table class=\"w-full\"><tr><td>Daily hours on slides:</td><td class=\"text-right\">4 hours</td></tr><tr><td>Average billing rate:</td><td class=\"text-right\">$300/hour</td></tr><tr class=\"border-t border-gray-300\"><td class=\"font-semibold\">Daily cost:</td><td class=\"text-right font-semibold\">$1,200</td></tr><tr><td class=\"font-semibold\">Annual cost (250 days):</td><td class=\"text-right font-semibold\">$300,000</td></tr></table></div><p class=\"mt-4\"><span class=\"accent-text font-semibold\">Project Prism</span> converts wasted hours into billable client value—increasing impact and profitability.</p></div></div></div></div></body></html>""",
            """<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"/><meta content=\"width=device-width, initial-scale=1.0\" name=\"viewport\"/><title>Project Prism Architecture</title><link href=\"https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css\" rel=\"stylesheet\"/><link href=\"https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.4.0/css/all.min.css\" rel=\"stylesheet\"/><link href=\"https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&amp;display=swap\" rel=\"stylesheet\"/><style>body{font-family:'Roboto',sans-serif;background-color:white;color:#1A365D;margin:0;padding:0}.slide-container{width:1280px;min-height:720px;overflow:hidden;position:relative}.header{padding:0 60px 8px}.header h1{margin:0}.content{padding:0 60px}#prism-s2 .content{transform:scale(0.59);transform-origin:top center}.arch-box{border:2px solid #FF5722;border-radius:8px;background-color:#FFF5F2;padding:15px;position:relative}.arch-box-inner{border:1px solid #FF5722;border-radius:4px;background-color:white;padding:10px;margin:5px 0;display:flex;align-items:center;justify-content:center}.arrow{color:#FF5722;position:absolute;font-size:20px}.arrow-right:before{content:\"\\f061\";font-family:\"Font Awesome 5 Free\";font-weight:900}.arrow-down:before{content:\"\\f063\";font-family:\"Font Awesome 5 Free\";font-weight:900}.arrow-up:before{content:\"\\f062\";font-family:\"Font Awesome 5 Free\";font-weight:900}.icon-box{color:#FF5722;font-size:24px;margin-bottom:10px}</style></head><body><div class=\"slide-container\" id=\"prism-s2\"><div class=\"header\"><h1 class=\"text-3xl font-bold\">Project Prism Architecture</h1></div><div class=\"content\"><div class=\"flex flex-col items-center\"><div class=\"arch-box w-64 mb-8\"><div class=\"icon-box text-center\"><i class=\"fas fa-users\"></i></div><div class=\"text-center font-semibold mb-2\">Users</div><div class=\"text-sm text-center\">Natural language prompts for slide generation</div></div><div class=\"h-10 flex justify-center items-center\"><i class=\"fas fa-arrow-down text-orange-500\"></i></div><div class=\"arch-box w-3/4 mb-8\"><div class=\"icon-box text-center\"><i class=\"fas fa-desktop\"></i></div><div class=\"text-center font-semibold mb-2\">Project Prism App Interface</div><div class=\"flex justify-around\"><div class=\"arch-box-inner text-center w-1/4\"><div class=\"text-sm font-medium\">Interactive Editor</div></div><div class=\"arch-box-inner text-center w-1/4\"><div class=\"text-sm font-medium\">Review Pane</div></div><div class=\"arch-box-inner text-center w-1/4\"><div class=\"text-sm font-medium\">Export</div></div></div></div><div class=\"h-10 flex justify-center items-center\"><i class=\"fas fa-arrow-down text-orange-500\"></i></div><div class=\"arch-box w-3/4 mb-8\"><div class=\"icon-box text-center\"><i class=\"fas fa-brain\"></i></div><div class=\"text-center font-semibold\">LLM Content Creator</div><div class=\"text-sm text-center\">Intelligent content generation and orchestration</div></div><div class=\"h-10 flex justify-center items-center\"><i class=\"fas fa-arrow-down text-orange-500\"></i></div><div class=\"flex w-full justify-between mb-8\"><div class=\"arch-box w-5/12\"><div class=\"icon-box text-center\"><i class=\"fas fa-tools\"></i></div><div class=\"text-center font-semibold mb-2\">Agents / Tools</div><div class=\"grid grid-cols-2 gap-2\"><div class=\"arch-box-inner text-center\"><div class=\"text-sm font-medium\">RAG</div></div><div class=\"arch-box-inner text-center\"><div class=\"text-sm font-medium\">SQL</div></div><div class=\"arch-box-inner text-center\"><div class=\"text-sm font-medium\">Data Viz</div></div><div class=\"arch-box-inner text-center\"><div class=\"text-sm font-medium\">Iconographer</div></div><div class=\"arch-box-inner text-center col-span-2\"><div class=\"text-sm font-medium\">Web Search</div></div></div></div><div class=\"arch-box w-5/12\"><div class=\"icon-box text-center\"><i class=\"fas fa-file-powerpoint\"></i></div><div class=\"text-center font-semibold mb-2\">Slide Creation Framework</div><div class=\"flex flex-col space-y-2\"><div class=\"arch-box-inner text-center\"><div class=\"text-sm font-medium\">CSS Theme</div></div><div class=\"arch-box-inner text-center\"><div class=\"text-sm font-medium\">HTML Deck Manager</div></div><div class=\"arch-box-inner text-center\"><div class=\"text-sm font-medium\">Export Manager</div></div><div class=\"flex items-center\"><div class=\"flex-grow h-0.5 bg-gray-300\"></div><div class=\"px-2 text-gray-500 text-xs\">connects to</div><div class=\"flex-grow h-0.5 bg-gray-300\"></div></div><div class=\"arch-box-inner text-center\"><div class=\"text-sm font-medium\">Lakebase State Machine</div></div></div></div></div></div></body></html>""",
            """<!DOCTYPE html>

<html lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Key Benefits for Consulting Firms</title>
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet"/>
<link href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.4.0/css/all.min.css" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&amp;display=swap" rel="stylesheet"/>
<style>
        body {
            font-family: 'Roboto', sans-serif;
            background-color: white;
            color: #1A365D;
            margin: 0;
            padding: 0;
        }
        .slide-container {
            width: 1280px;
            min-height: 720px;
            overflow: hidden;
            position: relative;
        }
        .header {
            padding: 0 60px 8px;
        }
        .header h1 { margin: 0; }
        .content {
            padding: 0 60px;
        }
        .icon-circle {
            width: 64px;
            height: 64px;
            border-radius: 32px;
            background-color: #FFF5F2;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 15px;
        }
        .benefit-icon {
            color: #FF5722;
            font-size: 28px;
        }
        .benefit-box {
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 25px;
            background-color: #F8FAFC;
            height: 100%;
        }
        
    </style>
</head>
<body>
<div class="slide-container">
<div class="header">
<h1 class="text-3xl font-bold">Key Benefits for Analysts &amp; Consulting Firms</h1>
 </div>
<div class="content">
<div class="grid grid-cols-3 gap-8">
<!-- Benefit 1 -->
<div class="benefit-box flex flex-col items-center text-center">
<div class="icon-circle">
<i class="benefit-icon fas fa-clock"></i>
</div>
<h3 class="text-xl font-semibold mb-2">Cut Deck Creation Time</h3>
<p class="text-gray-700">Reduce slide creation time by 75% through AI-powered automation</p>
</div>
<!-- Benefit 2 -->
<div class="benefit-box flex flex-col items-center text-center">
<div class="icon-circle">
<i class="benefit-icon fas fa-shield-alt"></i>
</div>
<h3 class="text-xl font-semibold mb-2">Enterprise-Grade Security</h3>
<p class="text-gray-700">Secure access to client data via Databricks Unity Catalog</p>
</div>
<!-- Benefit 3 -->
<div class="benefit-box flex flex-col items-center text-center">
<div class="icon-circle">
<i class="benefit-icon fas fa-brain"></i>
</div>
<h3 class="text-xl font-semibold mb-2">AI Model Flexibility</h3>
<p class="text-gray-700">Choose AI models based on specific use cases and requirements</p>
</div>
<!-- Benefit 4 -->
<div class="benefit-box flex flex-col items-center text-center">
<div class="icon-circle">
<i class="benefit-icon fas fa-database"></i>
</div>
<h3 class="text-xl font-semibold mb-2">Automated Data Warehousing</h3>
<p class="text-gray-700">Convert natural language to SQL for seamless data analysis</p>
</div>
<!-- Benefit 5 -->
<div class="benefit-box flex flex-col items-center text-center">
<div class="icon-circle">
<i class="benefit-icon fas fa-check-circle"></i>
</div>
<h3 class="text-xl font-semibold mb-2">Consistent Quality</h3>
<p class="text-gray-700">Align perfectly with firm-native templates and branding</p>
</div>
<!-- Benefit 6 -->
<div class="benefit-box flex flex-col items-center text-center">
<div class="icon-circle">
<i class="benefit-icon fas fa-handshake"></i>
</div>
<h3 class="text-xl font-semibold mb-2">Client Trust</h3>
<p class="text-gray-700">Deliver high-quality materials that strengthen relationships</p>
</div>
</div>
</div>
        
</div>
</body>
</html>""",
            """<html><body style='font-family:Arial'><div style='width:1280px;height:720px;display:flex;align-items:center;justify-content:center'><h1>Slide 4 (placeholder)</h1></div></body></html>""",
            """<!DOCTYPE html>

<html lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>What Sets Project Prism Apart</title>
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet"/>
<link href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.4.0/css/all.min.css" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&amp;display=swap" rel="stylesheet"/>
<style>
        body { font-family: 'Roboto', sans-serif; background-color: white; color: #1A365D; margin: 0; padding: 0; }
        .slide-container { width: 1280px; min-height: 720px; overflow: hidden; position: relative; }
        .header { padding: 0 60px 8px; }
        .header h1{ margin: 0; }
        .content { padding: 0 60px; }
        .icon-shield { width: 80px; height: 80px; border-radius: 40px; background-color: #FFF5F2; display: flex; align-items: center; justify-content: center; margin-bottom: 20px; }
        .advantage-icon { color: #FF5722; font-size: 32px; }
        .advantage-card { border: 1px solid #E2E8F0; border-radius: 8px; padding: 20px; background-color: #F8FAFC; height: 100%; transition: transform 0.2s; }
        .advantage-card:hover { transform: translateY(-5px); }
        .accent-text { color: #FF5722; font-weight: 500; }
    </style>
</head>
<body>
<div class=\"slide-container\">
<div class=\"header\">
<h1 class=\"text-3xl font-bold\">What Sets Project Prism Apart</h1>
</div>
<div class=\"content\">
<div class=\"flex items-center mb-10\">
<div class=\"icon-shield mr-6\">
<i class=\"advantage-icon fas fa-shield-alt\"></i>
</div>
<div>
<h2 class=\"text-2xl font-semibold mb-2\">Deep Integration with <span class=\"accent-text\">Databricks Unity Catalog</span></h2>
<p class=\"text-lg\">The foundation of our enterprise security and governance capabilities</p>
</div>
</div>
<div class=\"grid grid-cols-2 gap-8\">
<div class=\"advantage-card\">
<div class=\"flex items-center mb-4\"><div class=\"text-orange-500 mr-3 text-2xl\"><i class=\"fas fa-lock\"></i></div><h3 class=\"text-xl font-semibold\">Enterprise-Grade Security</h3></div>
<ul class=\"space-y-2 ml-8\">
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>End-to-end encryption of sensitive client data</span></li>
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>Role-based access controls for consultants</span></li>
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>Fully auditable data access and slide generation</span></li>
</ul>
</div>
<div class=\"advantage-card\">
<div class=\"flex items-center mb-4\"><div class=\"text-orange-500 mr-3 text-2xl\"><i class=\"fas fa-balance-scale\"></i></div><h3 class=\"text-xl font-semibold\">Complete Governance Framework</h3></div>
<ul class=\"space-y-2 ml-8\">
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>Chain of trust for all generated content</span></li>
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>Compliance with industry regulations</span></li>
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>Automated documentation of data lineage</span></li>
</ul>
</div>
<div class=\"advantage-card\">
<div class=\"flex items-center mb-4\"><div class=\"text-orange-500 mr-3 text-2xl\"><i class=\"fas fa-brain\"></i></div><h3 class=\"text-xl font-semibold\">Flexible AI Orchestration</h3></div>
<ul class=\"space-y-2 ml-8\">
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>Choice of proprietary or open source models</span></li>
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>Custom model training on firm knowledge bases</span></li>
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>Advanced reasoning for complex slides</span></li>
</ul>
</div>
<div class=\"advantage-card\">
<div class=\"flex items-center mb-4\"><div class=\"text-orange-500 mr-3 text-2xl\"><i class=\"fas fa-network-wired\"></i></div><h3 class=\"text-xl font-semibold\">Built for Enterprise Integration</h3></div>
<ul class=\"space-y-2 ml-8\">
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>Seamless connectivity with existing systems</span></li>
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>Designed for regulated environments</span></li>
<li class=\"flex items-start\"><i class=\"fas fa-check text-green-500 mr-2 mt-1\"></i><span>Scales with organizational needs</span></li>
</ul>
</div>
</div>
</div>
</div>
</body>
</html>""",
        ]

        TITLES = ["The Opportunity", "Architecture", "Key Benefits", "Placeholder", "What Sets Prism Apart"]

        # Share high-level plan
        plan_lines = [f"{idx+1}) {title}" for idx, title in enumerate(TITLES)]
        _append_api_message(
            session_id,
            role="assistant",
            content=(
                "Plan: I'll generate a concise 5-slide deck in this order:\n\n"
                + "\n".join(plan_lines)
            ),
            metadata={"title": "Plan"}
        )

        for i in range(5):
            title = TITLES[i]
            # Announce what we're doing
            _append_api_message(session_id, role="assistant", content=f"Planning slide {i+1}: {title}…")
            # Realistic single tool usage message for refresh hook
            _append_api_message(session_id, role="assistant", content="Using HTML Deck Manager to render slide…", metadata={"title": "🔧 Using a tool"})
            time.sleep(0.9)
            # Add slide to agent's artifacts directly
            slide_id = i + 1
            slide_agent.initial_state["artifacts"][slide_id] = PRISM_SLIDES[i]
            # Also add to todos if not already present
            if not any(todo.id == slide_id for todo in slide_agent.initial_state["todos"]):
                from slide_generator.tools.html_slides_agent import SlideTodo
                slide_agent.initial_state["todos"].append(
                    SlideTodo(id=slide_id, action="WRITE_SLIDE", title=title, details="", depends_on=[])
                )
            # Provide hint for next slide BEFORE the tool result so tool result is last
            if i < 4:
                _append_api_message(session_id, role="assistant", content=f"Next: Slide {i+2} – {TITLES[i+1]}")
                time.sleep(0.1)
            # Trigger frontend refresh (ChatInterface listens for 'tool result')
            _append_api_message(session_id, role="assistant", content=f"✅ Slide {i+1} ready: {title}", metadata={"title": "🔧 Tool result"})

        outline = "\n".join([f"{i+1}) {TITLES[i]}" for i in range(5)])
        _append_api_message(session_id, role="assistant", content=f"All set. Here's your deck outline:\n\n{outline}")
        # Signal completion explicitly so the frontend can stop polling
        _append_api_message(session_id, role="assistant", content="Generation complete.", metadata={"title": "Done"})
    except Exception as e:
        _append_api_message(session_id, role="assistant", content=f"Demo flow error: {e}")
# Pydantic models for API requests/responses
class ChatMessage(BaseModel):
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    messages: List[ChatMessage]
    session_id: str

class SlidesResponse(BaseModel):
    slides: List[str]

def openai_to_api_message(openai_msg: Dict) -> List[ChatMessage]:
    """Convert OpenAI format message to API ChatMessage format"""
    if openai_msg["role"] == "system":
        return []  # Don't display system messages
    
    elif openai_msg["role"] == "user":
        return [ChatMessage(role="user", content=openai_msg["content"])]
    
    elif openai_msg["role"] == "assistant":
        messages = []
        if "tool_calls" in openai_msg and openai_msg["content"]:
            # Assistant with tool calls
            messages.append(ChatMessage(role="assistant", content=openai_msg["content"]))
            tool_content = f"Calling tool {openai_msg['tool_calls'][0]['function']['name']} with arguments {openai_msg['tool_calls'][0]['function']['arguments']}"
            messages.append(ChatMessage(
                role="assistant",
                content=tool_content,
                metadata={"title": "🔧 Using a tool"}
            ))
        else:
            # Regular assistant message
            messages.append(ChatMessage(role="assistant", content=openai_msg["content"]))
        return messages
    
    elif openai_msg["role"] == "tool":
        # Tool result - display as assistant message with special formatting
        return [ChatMessage(
            role="assistant", 
            content=f"✅ {openai_msg['content']}",
            metadata={"title": "🔧 Tool result"}
        )]
    
    return []

def get_or_create_conversation(session_id: str) -> Dict:
    """Get or create conversation for session using session manager"""
    session = session_manager.get_or_create_session(session_id)
    return session["conversation"]

def update_conversations_with_openai_message(session_id: str, openai_msg: Dict):
    """Add OpenAI message to both conversation lists"""
    conv = get_or_create_conversation(session_id)
    conv["openai_conversation"].append(openai_msg)
    api_messages = openai_to_api_message(openai_msg)
    conv["api_conversation"].extend(api_messages)

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Slide Generator API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat messages and return conversation history"""
    try:
        session_id = request.session_id
        user_input = request.message.strip()
        
        if not user_input:
            conv = get_or_create_conversation(session_id)
            return ChatResponse(messages=conv["api_conversation"], session_id=session_id)
        
        # Demo static mode: bypass LLM and tools, render predefined slides
        if DEMO_STATIC_MODE:
            # Minimal transcript: add user only, then process synchronously
            update_conversations_with_openai_message(session_id, {"role": "user", "content": user_input})
            # Process the LLM flow synchronously to block until completion
            _run_llm_flow(session_id, user_input)
            conv = get_or_create_conversation(session_id)
            return ChatResponse(messages=conv["api_conversation"], session_id=session_id)

        # Normal mode: Add user message and process synchronously
        user_msg_openai = {"role": "user", "content": user_input}
        update_conversations_with_openai_message(session_id, user_msg_openai)
        # Process the conversation synchronously to block until completion
        _run_llm_flow(session_id, user_input)
        conv = get_or_create_conversation(session_id)
        return ChatResponse(messages=conv["api_conversation"], session_id=session_id)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat: {str(e)}")


@app.get("/chat/status/{session_id}")
async def get_chat_status(session_id: str):
    """Get current conversation status and messages"""
    conv = get_or_create_conversation(session_id)
    return {
        "messages": conv["api_conversation"],
        "session_id": session_id,
        "message_count": len(conv["api_conversation"])
    }

@app.get("/slides/html", response_model=SlidesResponse)
async def get_slides_html(session_id: str = "default"):
    """Get current slides as list of HTML strings"""
    try:
        slide_agent = session_manager.get_slide_agent(session_id)
        print(f"[DEBUG] get_slides_html - slide_agent: {slide_agent}")
        
        slides_list = slide_agent.get_slides()
        print(f"[DEBUG] get_slides_html - slides count: {len(slides_list)}")
        if slides_list:
            print(f"[DEBUG] get_slides_html - first slide preview: {slides_list[0][:200]}...")
        
        return SlidesResponse(slides=slides_list)
    except Exception as e:
        print(f"[DEBUG] get_slides_html - Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting slides: {str(e)}")

@app.post("/slides/refresh")
async def refresh_slides(session_id: str = "default"):
    """Refresh slides display"""
    try:
        slide_agent = session_manager.get_slide_agent(session_id)
        slides_list = slide_agent.get_slides()
        return {"slides": slides_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error refreshing slides: {str(e)}")

@app.post("/slides/reset")
async def reset_slides(session_id: str = "default"):
    """Reset slides to empty deck"""
    try:
        session_manager.reset_session_agent(session_id)
        print(f"[DEBUG] reset_slides - Reset session agent for session {session_id}")
        return {"message": "Slides reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting slides: {str(e)}")

@app.post("/slides/clear")
async def clear_slides(session_id: str = "default"):
    """Clear current slides but keep the agent instance for follow-on requests"""
    try:
        session_manager.clear_session_agent(session_id)
        print(f"[DEBUG] clear_slides - Cleared session agent state for session {session_id}")
        return {"message": "Slides cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing slides: {str(e)}")

@app.post("/slides/generate")
async def generate_slides(request: Dict[str, Any]):
    """Generate slides using the new LLM-based approach"""
    try:
        topic = request.get("topic", "AI and Machine Learning")
        style_hint = request.get("style_hint", "Professional, clean, modern")
        n_slides = request.get("n_slides", 3)
        session_id = request.get("session_id", "default")
        
        # Get session-specific slide agent
        slide_agent = session_manager.get_slide_agent(session_id)
        
        # Use the new LLM-based generation
        result = slide_agent.process_message(
            f"Create a {n_slides}-slide presentation about '{topic}' with a '{style_hint}' style"
        )
        
        return {
            "message": "Slides generated successfully",
            "result": result,
            "slides": slide_agent.get_slides()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating slides: {str(e)}")

@app.post("/slides/modify")
async def modify_slide(request: Dict[str, Any]):
    """Modify a specific slide using the new LLM-based approach"""
    try:
        slide_id = request.get("slide_id", 1)
        changes = request.get("changes", [])
        session_id = request.get("session_id", "default")
        
        # Get session-specific slide agent
        slide_agent = session_manager.get_slide_agent(session_id)
        
        # Convert changes to a natural language request
        change_description = f"Modify slide {slide_id}: " + "; ".join(changes)
        result = slide_agent.process_message(change_description)
        
        return {
            "message": "Slide modified successfully",
            "result": result,
            "slides": slide_agent.get_slides()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error modifying slide: {str(e)}")

@app.get("/slides/status")
async def get_slides_status(session_id: str = "default"):
    """Get current slides status"""
    try:
        slide_agent = session_manager.get_slide_agent(session_id)
        status = slide_agent.get_status()
        return {
            "status": [{"id": s.id, "title": s.title, "is_generated": s.is_generated, "is_valid": s.is_valid} for s in status],
            "slides": slide_agent.get_slides()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting slides status: {str(e)}")

@app.post("/slides/export")
async def export_slides(session_id: str = "default"):
    """Export slides to file"""
    try:
        slide_agent = session_manager.get_slide_agent(session_id)
        output_path = config.get_output_path("exported_slides.html")
        saved_files = slide_agent.save_slides(str(output_path.parent))
        return {"message": f"Slides exported successfully to {len(saved_files)} files", "path": str(output_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting slides: {str(e)}")

@app.get("/slides/export/pptx")
async def export_slides_pptx(session_id: str = "default") -> FileResponse:
    """Export the current deck to a PPTX file and stream it back.

    Uses the HtmlToPptxConverter from tools/html_to_pptx.py (pulled from export-visuals branch).
    """
    try:
        from slide_generator.tools.html_to_pptx import HtmlToPptxConverter
        from slide_generator.config import get_output_path

        # Compose output path (timestamped)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = get_output_path(f"slides_{ts}.pptx")

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create adapter that implements the SlideDeckProtocol for the converter
        class SlideDeckAgentAdapter:
            def __init__(self, agent):
                self.agent = agent
            
            def get_slides(self):
                """Get slides as list of HTML strings."""
                return self.agent.get_slides()
            
            def to_html(self):
                """Compatibility method - same as get_slides."""
                return self.get_slides()
                
            @property
            def theme(self):
                """Get the slide theme."""
                return self.agent.theme
        
        # Get session-specific slide agent
        slide_agent = session_manager.get_slide_agent(session_id)
        adapter = SlideDeckAgentAdapter(slide_agent)
        converter = HtmlToPptxConverter(adapter)
        await converter.convert_to_pptx(str(output_path), include_charts=True)

        # Stream file
        return FileResponse(
            path=str(output_path),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=output_path.name,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting PPTX: {str(e)}")

@app.get("/conversation/{session_id}")
async def get_conversation(session_id: str):
    """Get conversation history for debugging"""
    conv = get_or_create_conversation(session_id)
    return {
        "openai_conversation": conv["openai_conversation"],
        "api_conversation": conv["api_conversation"]
    }

if __name__ == "__main__":
    print("🚀 Starting Slide Generator FastAPI Backend")
    print(f"📊 Using LLM endpoint: {config.llm_endpoint}")
    print(f"📁 Output directory: {config.output_dir}")
    
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )

