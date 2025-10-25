"""FastAPI backend for the slide generator application."""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import time
import json
import asyncio

# Import slide generator modules
import sys
sys.path.append(str(Path(__file__).parent.parent / "src"))

from slide_generator.tools import html_slides_agent
from slide_generator.tools.html_slides_agent_fanout import FanOutSlideDeckAgent, FanOutProgressTracker
from slide_generator.config import config, get_output_path

# Initialize slide agent with neutral branding
ey_theme = html_slides_agent.SlideTheme(
    bottom_right_logo_url=None,
    footer_text=None
)

# Use fan-out agent for better performance and parallel Genie calls
slide_agent = FanOutSlideDeckAgent(theme=ey_theme)

# Global variable to store the latest slides
latest_slides = []

# Initialize V3 PowerPoint converter
try:
    from slide_generator.tools.html_to_pptx_v3 import HtmlToPptxConverterV3
    from databricks.sdk import WorkspaceClient
    
    # Initialize with Databricks client
    db_client = WorkspaceClient(profile="logfood", product='slide-generator')
    pptx_converter_v3 = HtmlToPptxConverterV3(
        workspace_client=db_client,
        model_endpoint="databricks-claude-sonnet-4-5"
    )
    print("✅ V3 PowerPoint converter initialized")
except Exception as e:
    print(f"⚠️  V3 converter initialization failed: {e}")
    print("   PowerPoint export will not be available")
    pptx_converter_v3 = None

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

# Global conversation state (in production, use proper session management)
conversations: Dict[str, List] = {}

def get_or_create_conversation(session_id: str) -> List:
    """Get or create conversation for session"""
    if session_id not in conversations:
        conversations[session_id] = []
    return conversations[session_id]

def _append_api_message(session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Append a message to the conversation history"""
    conv = get_or_create_conversation(session_id)
    conv.append(ChatMessage(role=role, content=content, metadata=metadata))


def _run_llm_flow(session_id: str, user_prompt: str) -> None:
    """Run the new LLM-based slide generation flow with user prompt"""
    global slide_agent
    
    try:
        # Check if this is a follow-on request or first-time request
        is_follow_on = slide_agent is not None and slide_agent.initial_state.get("todos") and len(slide_agent.initial_state.get("artifacts", {})) > 0
        
        if not is_follow_on:
            # First-time request: create new agent if needed
            if slide_agent is None:
                print(f"[DEBUG] LLM Flow - Creating new agent for first-time request")
                slide_agent = html_slides_agent.SlideDeckAgent(theme=ey_theme)
            else:
                print(f"[DEBUG] LLM Flow - Reusing existing agent for first-time request")
            
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
        status_text = "\n".join([f"Slide {s.position}: {s.title}" for s in status_list])
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

def _run_llm_flow_streaming(session_id: str, user_prompt: str) -> None:
    """Run the LLM flow with streaming progress updates"""
    global slide_agent
    
    try:
        # Check if this is a follow-on request or first-time request
        is_follow_on = slide_agent is not None and slide_agent.initial_state.get("todos") and len(slide_agent.initial_state.get("artifacts", {})) > 0
        
        # Create progress tracker with callback to append API messages
        def progress_callback(update):
            """Callback function to send progress updates to the chat"""
            progress_text = f"🔄 {update.step} ({update.progress_percent}%)"
            if update.details:
                progress_text += f" - {update.details}"
            if update.current_slide_title:
                progress_text += f" - Working on: {update.current_slide_title}"
            
            _append_api_message(
                session_id,
                role="assistant",
                content=progress_text,
                metadata={
                    "title": "Progress Update",
                    "progress": update.model_dump()
                }
            )
        
        progress_tracker = html_slides_agent.ProgressTracker(session_id, progress_callback)
        
        if not is_follow_on:
            # First-time request: create new agent with progress tracking
            if slide_agent is None:
                print(f"[DEBUG] Streaming Flow - Creating new agent for first-time request")
                slide_agent = html_slides_agent.SlideDeckAgent(theme=ey_theme, progress_tracker=progress_tracker)
            else:
                print(f"[DEBUG] Streaming Flow - Reusing existing agent for first-time request")
                slide_agent.progress_tracker = progress_tracker
            
            _append_api_message(
                session_id,
                role="assistant",
                content=(
                    "I'll analyze your request and generate a professional slide deck using AI. "
                    "You'll see progress updates as I work through each step."
                ),
            )
        else:
            # Follow-on request: reuse existing agent with new progress tracker
            print(f"[DEBUG] Streaming Flow - Reusing existing agent for follow-on request")
            slide_agent.progress_tracker = progress_tracker
            
            _append_api_message(
                session_id,
                role="assistant",
                content="I'll process your follow-on request and update the existing slide deck. You'll see progress updates as I work.",
            )

        print(f"[DEBUG] Streaming Flow - Processing user prompt: {user_prompt}")
        
        # Use the agent's streaming method
        import time
        process_start = time.time()
        result = slide_agent.process_message(user_prompt)  # Use regular method for now
        process_time = time.time() - process_start
        print(f"[DEBUG] Streaming Flow - process_message completed in {process_time:.2f}s")
        
        # Step 3: Check if slides were generated
        slides = result.get("slides", [])
        print(f"[DEBUG] Streaming Flow - Generated {len(slides)} slides")
        
        if not slides:
            _append_api_message(
                session_id,
                role="assistant",
                content="❌ No slides were generated. Please try a different request.",
                metadata={"title": "Agent tool result"}
            )
            return
        
        # Step 4: Show final success message
        _append_api_message(
            session_id,
            role="assistant",
            content=f"✅ Generated {len(slides)} slides successfully",
            metadata={"title": "Agent tool result"}
        )
        
        # Step 5: Show final status
        status_list = result.get("status", [])
        status_text = "\n".join([f"Slide {s.position}: {s.title}" for s in status_list])
        print(f"[DEBUG] Streaming Flow - Status: {status_text}")
        
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
        print(f"[ERROR] Streaming Flow - Error processing request: {e}")
        import traceback
        traceback.print_exc()
        _append_api_message(
            session_id,
            role="assistant",
            content=f"❌ Error processing your request: {str(e)}",
            metadata={"title": "Error"}
        )


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
            return ChatResponse(messages=conv, session_id=session_id)
        
        # Process the LLM flow with streaming updates
        _run_llm_flow_streaming(session_id, user_input)
        conv = get_or_create_conversation(session_id)
        return ChatResponse(messages=conv, session_id=session_id)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat: {str(e)}")

@app.get("/chat/history/{session_id}", response_model=ChatResponse)
async def get_chat_history(session_id: str):
    """Get conversation history for a session"""
    try:
        conv = get_or_create_conversation(session_id)
        return ChatResponse(messages=conv, session_id=session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting chat history: {str(e)}")

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Handle chat messages with real-time streaming using Server-Sent Events and Fan-out Agent"""
    try:
        session_id = request.session_id
        user_input = request.message.strip()
        
        if not user_input:
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        # Add user message to conversation history
        _append_api_message(session_id, role="user", content=user_input)
        
        async def event_generator():
            """Generate Server-Sent Events for real-time updates using Fan-out Agent"""
            global slide_agent
            
            try:
                # Check if this is a follow-on request or first-time request
                is_follow_on = slide_agent is not None and slide_agent.initial_state.get("todos") and len(slide_agent.initial_state.get("artifacts", {})) > 0
                
                # Create fan-out progress tracker with async callback to send SSE events
                async def progress_callback(update):
                    """Async callback function to send progress updates via SSE"""
                    progress_data = {
                        "type": "progress",
                        "step": update.step,
                        "progress_percent": update.progress_percent,
                        "details": update.details,
                        "slides_completed": update.slides_completed,
                        "total_slides": update.total_slides,
                        "current_slide_title": update.current_slide_title,
                        "elapsed_time": update.elapsed_time,
                        "error": update.error,
                        "branch_id": update.branch_id
                    }
                    # Note: We'll handle progress updates in the main loop
                
                progress_tracker = FanOutProgressTracker(session_id, progress_callback)
                print(f"[MAIN] Created fan-out progress_tracker: {progress_tracker}")
                
                if not is_follow_on:
                    # First-time request: create new fan-out agent with progress tracking
                    if slide_agent is None:
                        print(f"[STREAM] Creating new fan-out agent for first-time request")
                        slide_agent = FanOutSlideDeckAgent(theme=ey_theme, progress_tracker=progress_tracker)
                    else:
                        print(f"[STREAM] Reusing existing fan-out agent for first-time request")
                        slide_agent.progress_tracker = progress_tracker
                    
                    # Send initial message
                    initial_msg = "I'll analyze your request and generate a professional slide deck using AI with parallel processing and Genie integration. You'll see real-time progress updates as I work through each step."
                    yield f"data: {json.dumps({'type': 'message', 'content': initial_msg})}\n\n"
                else:
                    # Follow-on request: reuse existing agent with new progress tracker
                    print(f"[STREAM] Reusing existing fan-out agent for follow-on request")
                    slide_agent.progress_tracker = progress_tracker
                    
                    # Send initial message
                    follow_on_msg = "I'll process your follow-on request and update the existing slide deck with parallel processing. You'll see real-time progress updates as I work."
                    yield f"data: {json.dumps({'type': 'message', 'content': follow_on_msg})}\n\n"
                
                print(f"[STREAM] Processing user prompt with fan-out agent: {user_input}")
                
                # Use fan-out agent's streaming method for better performance and parallel Genie calls
                final_state = None
                
                async for chunk in slide_agent.process_message_streaming_async(
                    user_input, 
                    run_id=f"run_{int(time.time())}",
                    max_concurrency=3  # Allow up to 3 parallel slides
                ):
                    node = chunk.get("node")
                    progress = chunk.get("progress", 0)
                    state = chunk.get("state", {})
                    result = chunk.get("result")
                    
                    print(f"[STREAM] Fan-out chunk: node={node}, progress={progress}%")
                    
                    # Check for pending updates from progress_tracker
                    if progress_tracker and hasattr(progress_tracker, 'get_pending_updates'):
                        pending_updates = progress_tracker.get_pending_updates()
                        for update in pending_updates:
                            progress_data = {
                                "type": "progress",
                                "step": update.step,
                                "progress_percent": update.progress_percent,
                                "details": update.details,
                                "slides_completed": update.slides_completed,
                                "total_slides": update.total_slides,
                                "current_slide_title": update.current_slide_title,
                                "elapsed_time": update.elapsed_time,
                                "error": update.error,
                                "branch_id": update.branch_id
                            }
                            print(f"[STREAM] Yielding pending update: {update.step}")
                            yield f"data: {json.dumps(progress_data)}\n\n"
                    
                    # Handle different node types
                    if node == "complete":
                        # Final completion
                        final_state = result
                        print(f"[STREAM] Generation completed successfully")
                        
                        if result and result.get("success"):
                            slides_generated = len(result.get("slides", []))
                            completion_msg = f"✅ Successfully generated {slides_generated} slides with parallel processing and Genie integration!"
                            
                            # Send completion message
                            yield f"data: {json.dumps({'type': 'message', 'content': completion_msg})}\n\n"
                            
                            # Emit final slides update so frontend renders without manual refresh
                            try:
                                slides_list = result.get("slides", []) or []
                                if not slides_list and slide_agent is not None:
                                    # Fallback to agent slides
                                    slides_list = slide_agent.get_slides() or []
                                if not slides_list and isinstance(final_state, dict):
                                    # Fallback to artifacts in final state
                                    artifacts = final_state.get("artifacts", {}) or {}
                                    if isinstance(artifacts, dict):
                                        slides_list = list(artifacts.values())
                                # Cache globally so GET /slides/html is immediately consistent
                                latest_slides = slides_list
                                slides_event = {"type": "slides_update", "slides": slides_list}
                                yield f"data: {json.dumps(slides_event)}\n\n"
                            except Exception as _e:
                                print(f"[STREAM] slides_update emission (complete) failed: {_e}")
                            
                            # Update conversation history
                            _append_api_message(
                                session_id,
                                role="assistant",
                                content=completion_msg,
                                metadata={"slides_generated": slides_generated, "parallel_genie_calls": True}
                            )
                        else:
                            error_msg = "❌ Generation failed. Please try again."
                            yield f"data: {json.dumps({'type': 'message', 'content': error_msg})}\n\n"
                            
                    elif node == "error":
                        # Error handling
                        error_msg = result.get("error", "Unknown error occurred")
                        print(f"[STREAM] Generation error: {error_msg}")
                        yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                        
                    else:
                        # Node completion
                        node_data = {
                            "type": "node_complete",
                            "node": node,
                            "progress": progress,
                            "details": f"Completed {node} step"
                        }
                        yield f"data: {json.dumps(node_data)}\n\n"
                        
                        # Emit slides_update on key nodes so frontend updates automatically
                        try:
                            if node in ("join_results", "status"):
                                slides_list = []
                                # Prefer agent-rendered slides
                                if slide_agent is not None:
                                    slides_list = slide_agent.get_slides() or []
                                # Fallback to state artifacts if needed
                                if not slides_list and isinstance(state, dict):
                                    artifacts = state.get("artifacts", {}) or {}
                                    if isinstance(artifacts, dict):
                                        slides_list = list(artifacts.values())
                                # Only emit if we have something meaningful
                                if slides_list:
                                    # Cache globally
                                    latest_slides = slides_list
                                    slides_event = {"type": "slides_update", "slides": slides_list}
                                    yield f"data: {json.dumps(slides_event)}\n\n"
                        except Exception as _e:
                            print(f"[STREAM] slides_update emission failed on node '{node}': {_e}")
                        
                        # Capture state for final update
                        if state:
                            final_state = state
                
                # Update the agent's state with the final result
                if final_state:
                    print(f"[STREAM] Updating agent state with final state")
                    print(f"[STREAM] Final state keys: {list(final_state.keys())}")
                    
                    # Update the agent's initial_state with the final state
                    for key, value in final_state.items():
                        if key in slide_agent.initial_state:
                            slide_agent.initial_state[key] = value
                    
                    print(f"[STREAM] Agent state updated. Status count: {len(slide_agent.initial_state.get('status', []))}")
                    print(f"[STREAM] Agent state updated. Artifacts count: {len(slide_agent.initial_state.get('artifacts', {}))}")
                
                # Send done event
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
            except Exception as e:
                print(f"[STREAM ERROR] {e}")
                import traceback
                traceback.print_exc()
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing streaming chat: {str(e)}")


@app.get("/chat/status/{session_id}")
async def get_chat_status(session_id: str):
    """Get current conversation status and messages"""
    conv = get_or_create_conversation(session_id)
    return {
        "messages": conv,
        "session_id": session_id,
        "message_count": len(conv)
    }

@app.get("/debug/agent")
async def debug_agent():
    """Debug endpoint to check agent state"""
    return {
        "slide_agent_exists": slide_agent is not None,
        "slide_agent_type": type(slide_agent).__name__ if slide_agent else None,
        "initial_state_keys": list(slide_agent.initial_state.keys()) if slide_agent else [],
        "status_count": len(slide_agent.initial_state.get("status", [])) if slide_agent else 0,
        "artifacts_count": len(slide_agent.initial_state.get("artifacts", {})) if slide_agent else 0
    }

@app.get("/slides/html", response_model=SlidesResponse)
async def get_slides_html():
    """Get current slides as list of HTML strings"""
    try:
        print(f"[DEBUG] get_slides_html - slide_agent: {slide_agent}")
        print(f"[DEBUG] get_slides_html - slide_agent is None: {slide_agent is None}")
        
        if slide_agent is None:
            print(f"[DEBUG] get_slides_html - No slide agent, returning empty slides")
            return SlidesResponse(slides=[])
        
        slides_list = slide_agent.get_slides()
        print(f"[DEBUG] get_slides_html - slides count: {len(slides_list)}")
        if slides_list:
            print(f"[DEBUG] get_slides_html - first slide preview: {slides_list[0][:200]}...")
        
        # If get_slides() returns empty, try getting from artifacts directly
        if not slides_list and 'artifacts' in slide_agent.initial_state:
            artifacts = slide_agent.initial_state['artifacts']
            print(f"[DEBUG] get_slides_html - artifacts count: {len(artifacts)}")
            slides_list = list(artifacts.values())
            print(f"[DEBUG] get_slides_html - slides from artifacts: {len(slides_list)}")
        
        # If still empty, try getting from global latest_slides
        if not slides_list:
            global latest_slides
            print(f"[DEBUG] get_slides_html - latest_slides count: {len(latest_slides)}")
            slides_list = latest_slides
        
        return SlidesResponse(slides=slides_list)
    except Exception as e:
        print(f"[DEBUG] get_slides_html - Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting slides: {str(e)}")

@app.post("/slides/reset")
async def reset_slides():
    """Reset slides to empty deck"""
    try:
        # Create new agent with same theme
        global slide_agent
        slide_agent = html_slides_agent.SlideDeckAgent(theme=ey_theme)
        print(f"[DEBUG] reset_slides - Created new agent, resetting state")
        return {"message": "Slides reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting slides: {str(e)}")

@app.post("/slides/clear")
async def clear_slides():
    """Clear current slides but keep the agent instance for follow-on requests"""
    try:
        global slide_agent
        if slide_agent is not None:
            # Clear the state but keep the agent instance
            slide_agent.initial_state.update({
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
            print(f"[DEBUG] clear_slides - Cleared agent state")
        return {"message": "Slides cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing slides: {str(e)}")

@app.get("/slides/status")
async def get_slides_status():
    """Get current slides status"""
    try:
        status = slide_agent.get_status()
        return {
            "status": [{"id": s.id, "title": s.title, "is_generated": s.is_generated, "is_valid": s.is_valid} for s in status],
            "slides": slide_agent.get_slides()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting slides status: {str(e)}")

@app.post("/slides/export")
async def export_slides():
    """Export slides to individual HTML files in a timestamped directory"""
    try:
        # Validate slides exist
        slides = slide_agent.get_slides()
        if not slides:
            raise HTTPException(
                status_code=400,
                detail="No slides to export. Please generate slides first."
            )
        
        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = get_output_path(f"slides_export_{timestamp}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save slides
        saved_files = slide_agent.save_slides(str(output_dir))
        
        # Get slide information for response
        status = slide_agent.get_status()
        slide_info = [
            {
                "file": Path(f).name,
                "title": s.title,
                "position": s.position
            }
            for f, s in zip(saved_files, status) if s.is_generated
        ]
        
        return {
            "success": True,
            "message": f"Successfully exported {len(saved_files)} slides",
            "output_dir": str(output_dir),
            "slides": slide_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting slides: {str(e)}"
        )

@app.get("/slides/export/pptx")
async def export_slides_pptx(use_screenshot: bool = True) -> FileResponse:
    """Export the current deck to PowerPoint format using V3 converter.
    
    Uses the V3 maximum LLM flexibility approach with proven 100% success rate.
    
    Args:
        use_screenshot: Whether to use screenshot mode (default: True)
            - True: Pixel-perfect charts as images (for presentations)
            - False: Editable PowerPoint charts (for analysis)
    
    Requirements:
        - playwright: pip install playwright && playwright install
        - python-pptx: pip install python-pptx
        - databricks-sdk: pip install databricks-sdk
    
    Returns:
        FileResponse: PowerPoint file for download
    """
    try:
        # Validate slides exist
        slides = slide_agent.get_slides()
        if not slides:
            raise HTTPException(
                status_code=400,
                detail="No slides to export. Please generate slides first."
            )
        
        print(f"[V3 PPTX Export] Starting export of {len(slides)} slides")
        print(f"[V3 PPTX Export] Screenshot mode: {use_screenshot}")
        
        # Check if V3 converter is available
        if pptx_converter_v3 is None:
            raise HTTPException(
                status_code=501,
                detail="V3 PowerPoint converter not initialized. Check server logs for details."
            )
        
        # Generate timestamped output path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = get_output_path(f"slides_v3_{timestamp}.pptx")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"[V3 PPTX Export] Output path: {output_path}")
        
        # Save HTML files for screenshot capture and validation
        html_output_dir = output_path.parent / f"html_v3_{timestamp}"
        html_output_dir.mkdir(parents=True, exist_ok=True)
        
        saved_html_files = []
        for i, status in enumerate(slide_agent.get_status(), 1):
            if status.is_generated:
                # Create sanitized filename
                safe_title = status.title.replace(' ', '_').replace('/', '_')[:30]
                html_file = html_output_dir / f"slide_{i}_{safe_title}.html"
                html_file.write_text(status.html, encoding='utf-8')
                saved_html_files.append(str(html_file))
                print(f"[V3 PPTX Export] Saved HTML {i}: {html_file.name}")
        
        print(f"[V3 PPTX Export] Saved {len(saved_html_files)} HTML files")
        
        # Convert using V3
        result_path = await pptx_converter_v3.convert_slide_deck(
            slides=slides,
            output_path=str(output_path),
            use_screenshot=use_screenshot,
            html_source_paths=saved_html_files
        )
        
        print(f"[V3 PPTX Export] ✅ Conversion complete: {result_path}")
        print(f"[V3 PPTX Export] HTML files available at: {html_output_dir}")
        
        # Verify file was created
        if not os.path.exists(output_path):
            raise Exception("PowerPoint file was not created")
        
        file_size = os.path.getsize(output_path) / 1024
        print(f"[V3 PPTX Export] File size: {file_size:.1f}KB")
        
        # Return file for download
        return FileResponse(
            path=str(output_path),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename=output_path.name,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[V3 PPTX Export] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting to PowerPoint: {str(e)}"
        )

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

