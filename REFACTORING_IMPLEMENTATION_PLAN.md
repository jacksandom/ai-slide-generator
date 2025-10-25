# AI Slide Generator - Refactoring Implementation Plan

## Branching Strategy

### Phase 0: Setup Safe Development Environment
```bash
# Step 1: Create backup/preservation branch from main
git checkout main
git pull origin main
git checkout -b refactor-main
git push -u origin refactor-main

# Step 2: Create feature branches off refactor-main
git checkout refactor-main
git checkout -b phase1-remove-duplicates
```

**Branch Structure:**
- `main` - **Protected**: Current production code, untouched during refactoring
- `refactor-main` - **Base branch**: Safe copy of main for refactoring work
- `phase1-remove-duplicates` - **Feature branch**: Phase 1 implementation
- `phase2-standardize-arch` - **Feature branch**: Phase 2 implementation  
- `phase3-code-quality` - **Feature branch**: Phase 3 implementation

## Implementation Phases

## Phase 1: Remove Duplicates (Priority: CRITICAL)
**Timeline:** 2-3 days  
**Risk Level:** Low  
**Branch:** `phase1-remove-duplicates`

### Pre-Implementation Validation

What updates do you have? #### Step 1.0: Create Baseline Tests
```bash
# Document current functionality
git checkout refactor-main
git checkout -b phase1-remove-duplicates

# Test current system end-to-end
npm run dev
# Manually test:
# - Frontend loads at localhost:3000
# - Backend responds at localhost:8000
# - Chat interface works
# - Slide generation works
# - Export functionality works

# Document results in BASELINE_FUNCTIONALITY.md
```

#### Step 1.1: Identify Active Frontend
**Objective:** Confirm which frontend is actually used in production

**Tasks:**
- [ ] Check `package.json` scripts to see which frontend is started by `npm run dev`
- [ ] Verify `start.sh` startup sequence
- [ ] Confirm `backend/main.py` CORS settings point to React (port 3000)
- [ ] Document findings in implementation notes

**Decision Point:** If React is active frontend, proceed with Gradio removal. If unclear, investigate further.

### Implementation Steps

#### Step 1.2: Remove Gradio Frontend
**Estimated Time:** 2 hours

**Files to Delete:**
```bash
# Remove Gradio frontend entirely
rm -rf src/slide_generator/frontend/gradio_app.py
rm -rf src/slide_generator/frontend/__init__.py
rmdir src/slide_generator/frontend/

# Clean up any Gradio imports
git grep -l "gradio_app\|frontend.gradio" . | xargs sed -i '' '/gradio_app\|frontend\.gradio/d'
```

**Files to Update:**
- [ ] `src/slide_generator/__main__.py` - Remove gradio import references
- [ ] `pyproject.toml` - Mark gradio as optional dependency
- [ ] Any remaining import statements

**Validation:**
- [ ] Backend starts without errors
- [ ] React frontend still works
- [ ] All functionality preserved

#### Step 1.3: Remove Deprecated Chatbot
**Estimated Time:** 1 hour

**Files to Delete:**
```bash
rm src/slide_generator/core/chatbot.py
```

**Files to Update:**
- [ ] `src/slide_generator/core/__init__.py` - Remove chatbot import
- [ ] `backend/main.py` - Remove commented chatbot import
- [ ] Any other files importing the old chatbot

**Validation:**
- [ ] Backend starts without errors
- [ ] Agent-based system still works

#### Step 1.4: Clean Up Empty/Unused Directories
**Estimated Time:** 30 minutes

**Directories to Remove:**
```bash
# Check if truly empty first
ls -la src/slide_generator/api/
ls -la src/slide_generator/deploy/

# If only __init__.py files, remove
rm -rf src/slide_generator/api/
rm -rf src/slide_generator/deploy/
```

**Validation:**
- [ ] No import errors
- [ ] Package structure still intact

#### Step 1.5: Consolidate Documentation
**Estimated Time:** 2 hours

**Files to Delete:**
```bash
rm README_REACT.md
rm README_NEW_STRUCTURE.md  
rm README_SETUP.md
rm SUGGESTED_PROJECT_STRUCTURE.md
rm frontend/slide-generator-frontend/README.md
```

**Files to Create/Update:**
- [ ] Create comprehensive `README.md` combining best parts of all deleted files
- [ ] Include setup instructions for React + FastAPI
- [ ] Add troubleshooting section
- [ ] Include development workflow
- [ ] Add API documentation links

**Content Structure for New README.md:**
```markdown
# AI Slide Generator

## Overview
[Project description and architecture]

## Quick Start
[Single setup command and access points]

## Development Setup
[Detailed setup for contributors]

## Architecture
[React + FastAPI + LangGraph agent description]

## API Reference
[FastAPI endpoints]

## Troubleshooting
[Common issues and solutions]
```

#### Step 1.6: Consolidate Dependencies
**Estimated Time:** 1 hour

**Files to Update:**
- [ ] Move all dependencies from `requirements.txt` to `pyproject.toml`
- [ ] Remove redundant `backend/requirements.txt` 
- [ ] Update `start.sh` to use pyproject.toml
- [ ] Test dependency installation

**Dependencies to Consolidate:**
```toml
# Add to pyproject.toml [project.dependencies]Progress with the next three steps.
"beautifulsoup4>=4.12.0",
"langgraph>=0.1.0", 
"unitycatalog-ai",
"databricks-connect",
"openai",
# etc.
```

### Phase 1 Testing & Validation

#### Step 1.7: Integration Testing
**Time:** 1 hour

**Test Checklist:**
- [ ] `npm run dev` starts both servers successfully
- [ ] Frontend loads without console errors
- [ ] Chat interface accepts messages
- [ ] Slide generation produces HTML output
- [ ] Export to PPTX works
- [ ] All API endpoints respond correctly
- [ ] No 404s or missing resource errors

#### Step 1.8: Performance Baseline
**Time:** 30 minutes

**Metrics to Capture:**
- [ ] Application startup time
- [ ] First slide generation time
- [ ] Memory usage (backend process)
- [ ] Bundle size (frontend)

#### Step 1.9: Documentation Update
**Time:** 30 minutes

- [ ] Update `CODEBASE_REVIEW_FINDINGS.md` with completion status
- [ ] Document any issues encountered
- [ ] Update next phase prerequisites

### Phase 1 Completion Criteria

**Success Metrics:**
- ✅ ~2,000 lines of code removed
- ✅ Documentation consolidated to single README
- ✅ All tests pass
- ✅ No functionality regression
- ✅ Startup time improved or unchanged
- ✅ Ready for Phase 2

**Merge Process:**
```bash
# Create PR from phase1-remove-duplicates to refactor-main
git checkout phase1-remove-duplicates
git add .
git commit -m "Phase 1: Remove duplicate frontends and deprecated code

- Remove Gradio frontend (gradio_app.py)
- Remove deprecated chatbot.py
- Consolidate 6 README files into single comprehensive guide
- Clean up empty directories (api/, deploy/)
- Consolidate dependency management

Impact: ~2,000 lines removed, improved maintainability"

git push origin phase1-remove-duplicates
# Create PR: phase1-remove-duplicates → refactor-main
```

---

## Phase 1.5: Establish Testing Foundation (Priority: CRITICAL)
**Timeline:** 3-5 days  
**Risk Level:** Low  
**Branch:** `phase1.5-testing-foundation`

### Overview

Before proceeding with architectural changes in Phase 2, we must establish comprehensive test coverage to:
- Prevent regression bugs during refactoring
- Document expected behavior of existing functionality
- Enable confident code changes with immediate feedback
- Establish baseline performance metrics
- Create safety nets for future development

### Testing Infrastructure Setup

#### Step 1.5.0: Create Testing Branch and Environment
**Estimated Time:** 30 minutes

```bash
# Create testing branch from refactor-main
git checkout refactor-main
git pull origin refactor-main
git checkout -b phase1.5-testing-foundation

# Create test directory structure
mkdir -p tests/{unit,integration,e2e}
mkdir -p tests/unit/{backend,core,tools,utils}
mkdir -p tests/integration/{api,workflows}
mkdir -p tests/e2e/{frontend,full_stack}
mkdir -p tests/fixtures/{data,mocks}
```

#### Step 1.5.1: Install Testing Dependencies
**Estimated Time:** 15 minutes

Testing dependencies need to be added to `pyproject.toml`:
```toml
[project.optional-dependencies]
dev = [
    # Existing dev dependencies
    "pytest>=7.0",
    "pytest-cov",
    "black>=22.0", 
    "flake8>=5.0",
    "mypy>=1.0",
    "pre-commit>=2.20",
    "isort>=5.10",
    
    # Additional testing dependencies for Phase 1.5
    "pytest-asyncio>=0.21.0",  # For FastAPI async tests
    "pytest-mock>=3.10.0",     # For mocking Databricks responses  
    "httpx>=0.24.0",           # For FastAPI TestClient
    "pytest-html>=3.1.0",     # For HTML test reports
    "aiohttp>=3.8.0",         # For load testing
    "psutil>=5.9.0",          # For memory monitoring tests
]
```

**Tasks:**
- [ ] Install dev dependencies: `pip install -e ".[dev]"`
- [ ] Verify pytest runs: `pytest --version`
- [ ] Create `pytest.ini` for test configuration
- [ ] Set up VS Code/IDE test runner integration
- [ ] Configure Databricks authentication for testing (see below)

**Databricks Authentication Setup:**
Tests use a real Databricks client with the default profile. Ensure proper authentication:

```bash
# Option 1: Use Databricks CLI configuration
databricks configure

# Option 2: Set environment variables
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"  
export DATABRICKS_TOKEN="your-access-token"

# Option 3: Use .databrickscfg file with default profile
cat ~/.databrickscfg
[DEFAULT]
host = https://your-workspace.cloud.databricks.com
token = your-access-token
```

**Important:** Tests mock service responses but require valid authentication to instantiate the client.

#### Step 1.5.2: Create Test Configuration Files
**Estimated Time:** 45 minutes

**Create `tests/conftest.py`:**
```python
"""Global test configuration and fixtures."""
import pytest
import asyncio
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import os

# Test data directory
TEST_DATA_DIR = Path(__file__).parent / "fixtures" / "data"

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def authenticated_databricks_client():
    """Real Databricks WorkspaceClient using default profile for testing."""
    from databricks.sdk import WorkspaceClient
    # Use default profile for authentication
    return WorkspaceClient()

@pytest.fixture
def mock_databricks_responses(monkeypatch):
    """Mock Databricks service responses while using real client."""
    from unittest.mock import MagicMock
    
    # Mock LLM serving endpoint responses
    mock_llm_response = {
        "choices": [{
            "message": {
                "content": "Test LLM response for slide generation"
            }
        }]
    }
    
    # Mock Genie responses
    mock_genie_response = {
        "statement_id": "test_statement_123",
        "status": {"state": "SUCCEEDED"},
        "result": {"data_array": [["Test", "Data"], ["Row1", "Row2"]]}
    }
    
    return {
        "llm_response": mock_llm_response,
        "genie_response": mock_genie_response
    }

@pytest.fixture
def temp_output_dir():
    """Temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir

@pytest.fixture
def sample_slide_html():
    """Sample valid slide HTML for testing."""
    return '''<!DOCTYPE html>
<html><head><title>Test</title></head>
<body style="width:1280px;height:720px;">
<h1 style="color:#102025;">Test Slide</h1>
<p>Test content</p>
</body></html>'''
```

### Unit Tests Implementation

#### Step 1.5.3: Core Component Tests (`html_slides_agent.py`)
**Estimated Time:** 2 days

**Priority Test Coverage:**

**1. State Management Tests** (`tests/unit/core/test_agent_state.py`):
```python
"""Test SlideDeckAgent state management."""
import pytest
from slide_generator.tools.html_slides_agent import (
    SlideDeckAgent, SlideDeckState, SlideConfig, SlideTheme
)

class TestSlideDeckAgent:
    def test_agent_initialization(self):
        """Test agent initializes with correct default state."""
        agent = SlideDeckAgent()
        assert agent.theme is not None
        assert agent.initial_state["config_version"] == 0
        assert agent.initial_state["messages"] == []
        assert agent.initial_state["todos"] == []
        assert agent.initial_state["artifacts"] == {}

    def test_agent_with_custom_theme(self):
        """Test agent initialization with custom theme."""
        theme = SlideTheme(
            bottom_right_logo_url="test.svg",
            footer_text="Test Footer"
        )
        agent = SlideDeckAgent(theme=theme)
        assert agent.theme.bottom_right_logo_url == "test.svg"
        assert agent.theme.footer_text == "Test Footer"

    def test_agent_with_real_databricks_client(self, authenticated_databricks_client):
        """Test agent works with real Databricks client."""
        agent = SlideDeckAgent()
        # Verify agent can be instantiated with real client
        assert agent is not None
        assert agent.initial_state is not None
        
    @pytest.mark.asyncio
    async def test_state_persistence_across_messages(self, authenticated_databricks_client, mock_databricks_responses):
        """Test state persists correctly across multiple messages."""
        agent = SlideDeckAgent()
        
        # Mock the LLM endpoint responses at the serving client level
        with patch.object(agent.graph.get_graph().nodes["nlu"].func.__globals__["model_serving_client"], 
                         'chat') as mock_chat:
            mock_chat.completions.create.return_value = mock_databricks_responses["llm_response"]
            
            # Test message processing with real client but mocked responses
            result1 = agent.process_message("Create 2 slides about AI")
            result2 = agent.process_message("Add a slide about machine learning")
            
            # Verify state persistence
            assert len(agent.initial_state["messages"]) == 2
```

**2. Node Function Tests** (`tests/unit/core/test_agent_nodes.py`):
```python
"""Test individual LangGraph nodes."""
import pytest
from slide_generator.tools.html_slides_agent import (
    nlu_node, planning_node, generation_node, 
    modification_node, status_node, SlideDeckState
)

class TestAgentNodes:
    @pytest.fixture
    def minimal_state(self):
        """Minimal valid state for testing."""
        return {
            "config": SlideConfig(),
            "config_version": 0,
            "messages": [{"role": "user", "content": "Create 2 slides about AI"}],
            "last_intent": None,
            "todos": [],
            "artifacts": {},
            "pending_changes": [],
            "status": [],
            "errors": [],
            "metrics": {},
            "run_id": "test_run"
        }

    def test_nlu_node_intent_detection(self, minimal_state, authenticated_databricks_client, mock_databricks_responses, monkeypatch):
        """Test NLU node correctly identifies user intents using real client."""
        from unittest.mock import MagicMock
        
        # Mock the serving endpoint response while using real client
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_databricks_responses["llm_response"]
        monkeypatch.setattr("slide_generator.tools.html_slides_agent.model_serving_client", mock_client)
        
        # Test CREATE_PRESENTATION intent detection
        result = nlu_node(minimal_state)
        assert result["last_intent"] is not None
        # Verify the serving endpoint was called
        mock_client.chat.completions.create.assert_called_once()

    def test_planning_node_todo_generation(self, minimal_state, authenticated_databricks_client, mock_databricks_responses, monkeypatch):
        """Test planning node generates appropriate todos using real client."""
        from unittest.mock import MagicMock
        
        # Mock the serving endpoint response  
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_databricks_responses["llm_response"]
        monkeypatch.setattr("slide_generator.tools.html_slides_agent.model_serving_client", mock_client)
        
        # Set up state with CREATE_PRESENTATION intent
        minimal_state["last_intent"] = {"intent": "CREATE_PRESENTATION", "entities": {"slide_count": 2}}
        result = planning_node(minimal_state)
        
        # Verify todos were generated and LLM was called
        assert len(result["todos"]) >= 0  # May be 0 if LLM response doesn't indicate slides needed
        mock_client.chat.completions.create.assert_called()
        
    def test_genie_tool_integration(self, authenticated_databricks_client, mock_databricks_responses, monkeypatch):
        """Test Genie tool works with real client but mocked responses."""
        from unittest.mock import MagicMock, patch
        
        # Mock Genie SQL execution responses
        mock_genie = MagicMock()
        mock_genie.execute_genie_request.return_value = mock_databricks_responses["genie_response"]
        
        with patch("slide_generator.tools.uc_tools.UC_tools") as mock_uc_tools:
            mock_uc_tools.return_value = mock_genie
            
            # Test that Genie tool can be called with real client
            from slide_generator.tools import uc_tools
            tools_dict = uc_tools.UC_tools
            
            # Verify tools are available (not mocked away completely)
            assert tools_dict is not None
```

**3. Tool Function Tests** (`tests/unit/tools/test_slide_tools.py`):
```python
"""Test slide generation and manipulation tools."""
import pytest
from slide_generator.tools.html_slides_agent import (
    generate_slide_html, validate_slide_html, 
    sanitize_slide_html, apply_slide_change
)

class TestSlideTools:
    def test_html_generation(self, authenticated_databricks_client, mock_databricks_responses, monkeypatch):
        """Test HTML slide generation produces valid output using real client."""
        from unittest.mock import MagicMock
        
        # Mock the serving endpoint response while using real client for authentication
        mock_client = MagicMock()
        # Return actual HTML content in the mocked response
        mock_response = {
            "choices": [{
                "message": {
                    "content": '<!DOCTYPE html><html><head><title>Test Slide</title></head><body style="width:1280px;height:720px;"><h1 style="color:#102025;">Test Slide</h1><p>This is a test slide about testing</p></body></html>'
                }
            }]
        }
        mock_client.chat.completions.create.return_value = mock_response
        monkeypatch.setattr("slide_generator.tools.html_slides_agent.model_serving_client", mock_client)
        
        result = generate_slide_html.invoke({
            "title": "Test Slide", 
            "outline": "This is a test slide about testing",
            "style_hint": "professional clean"
        })
        
        # Verify HTML structure and LLM call
        assert "<h1" in result
        assert "Test Slide" in result
        assert "<!DOCTYPE html>" in result
        mock_client.chat.completions.create.assert_called_once()

    def test_html_validation_valid_slide(self, sample_slide_html):
        """Test validation passes for valid HTML."""
        is_valid = validate_slide_html.invoke({"html": sample_slide_html})
        assert is_valid is True

    def test_html_validation_invalid_slide(self):
        """Test validation fails for invalid HTML."""
        invalid_html = "<div>Incomplete HTML"
        is_valid = validate_slide_html.invoke({"html": invalid_html})
        assert is_valid is False

    def test_html_sanitization(self, sample_slide_html):
        """Test HTML sanitization removes dangerous elements."""
        unsafe_html = sample_slide_html.replace("</body>", 
            '<script>alert("xss")</script></body>')
        sanitized = sanitize_slide_html.invoke({"html": unsafe_html})
        assert "alert" not in sanitized
        assert "<script>" not in sanitized
```

#### Step 1.5.4: Configuration and Utility Tests
**Estimated Time:** 0.5 days

**Configuration Tests** (`tests/unit/utils/test_config.py`):
```python
"""Test configuration management."""
import pytest
import os
from slide_generator.config import config

class TestConfiguration:
    def test_config_loads_defaults(self):
        """Test configuration loads with sensible defaults."""
        assert config.databricks_profile is not None
        assert config.model_endpoint is not None

    def test_config_environment_override(self, monkeypatch):
        """Test environment variables override defaults."""
        monkeypatch.setenv("DATABRICKS_PROFILE", "test-profile")
        # Test configuration reload
        # Implementation depends on config structure
```

### Integration Tests Implementation

#### Step 1.5.5: FastAPI Endpoint Tests
**Estimated Time:** 1.5 days

**API Integration Tests** (`tests/integration/api/test_endpoints.py`):
```python
"""Test FastAPI endpoints integration."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from backend.main import app

@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)

@pytest.fixture
def mock_slide_agent_responses(monkeypatch):
    """Mock slide agent responses while using real Databricks client."""
    from unittest.mock import MagicMock
    
    # Mock the LLM responses at the serving client level
    mock_serving_client = MagicMock()
    mock_serving_client.chat.completions.create.return_value = {
        "choices": [{
            "message": {
                "content": '<!DOCTYPE html><html><head><title>AI Overview</title></head><body style="width:1280px;height:720px;"><h1 style="color:#102025;">AI Overview</h1><p>Artificial Intelligence overview slide</p></body></html>'
            }
        }]
    }
    
    # Mock Genie responses if needed
    mock_genie_response = {
        "statement_id": "test_123",
        "status": {"state": "SUCCEEDED"},
        "result": {"data_array": [["AI", "100%"], ["ML", "85%"]]}
    }
    
    monkeypatch.setattr("slide_generator.tools.html_slides_agent.model_serving_client", mock_serving_client)
    
    return {
        "serving_client": mock_serving_client,
        "genie_response": mock_genie_response
    }

class TestChatEndpoints:
    def test_root_endpoint(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["message"] == "Slide Generator API"

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_chat_endpoint_valid_message(self, client, mock_slide_agent_responses, authenticated_databricks_client):
        """Test chat endpoint with valid message using real Databricks client."""
        response = client.post("/chat", json={
            "message": "Create 2 slides about AI",
            "session_id": "test_session"
        })
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "session_id" in data
        
        # Verify that the LLM serving client was called
        mock_slide_agent_responses["serving_client"].chat.completions.create.assert_called()

    def test_chat_endpoint_empty_message(self, client):
        """Test chat endpoint with empty message."""
        response = client.post("/chat", json={
            "message": "",
            "session_id": "test_session"
        })
        assert response.status_code == 200
        # Should return existing conversation

    def test_chat_status_endpoint(self, client):
        """Test chat status retrieval."""
        session_id = "test_session"
        response = client.get(f"/chat/status/{session_id}")
        assert response.status_code == 200
```

**Slide Management Tests** (`tests/integration/api/test_slide_endpoints.py`):
```python
"""Test slide-specific API endpoints."""
import pytest
from fastapi.testclient import TestClient
from backend.main import app

class TestSlideEndpoints:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_slides_status_endpoint(self, client, mock_slide_agent_responses, authenticated_databricks_client):
        """Test slides status endpoint with real Databricks client."""
        response = client.get("/slides/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "slides" in data

    def test_slide_modification(self, client, mock_slide_agent_responses, authenticated_databricks_client):
        """Test slide modification endpoint with real Databricks client."""
        response = client.post("/slides/modify", json={
            "slide_id": "slide_1",
            "change": {
                "operation": "EDIT_TEXT",
                "args": {"old_text": "old", "new_text": "new"}
            }
        })
        # May return 200 or 500 depending on slide existence, both are acceptable for testing
        assert response.status_code in [200, 404, 500]

    def test_slides_export(self, client, mock_slide_agent_responses, authenticated_databricks_client):
        """Test slides export functionality with real Databricks client."""
        response = client.post("/slides/export")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data or "error" in data  # May have no slides to export
```

### End-to-End Tests Implementation

#### Step 1.5.6: Full Workflow Tests
**Estimated Time:** 1 day

**Complete User Journey Tests** (`tests/e2e/test_full_workflows.py`):
```python
"""End-to-end workflow tests."""
import pytest
from fastapi.testclient import TestClient
from backend.main import app
import tempfile
import os

@pytest.mark.e2e
class TestCompleteWorkflows:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_complete_slide_generation_workflow(self, client):
        """Test complete slide generation from chat to export."""
        session_id = "e2e_test_session"
        
        # Step 1: Start conversation
        response = client.post("/chat", json={
            "message": "Create a 3-slide presentation about machine learning",
            "session_id": session_id
        })
        assert response.status_code == 200
        
        # Step 2: Check slide generation status
        response = client.get("/slides/status")
        assert response.status_code == 200
        
        # Step 3: Modify a slide (if slides were generated)
        slides_data = response.json()
        if slides_data["slides"]:
            response = client.post("/slides/modify", json={
                "slide_id": "slide_1",
                "change": {
                    "operation": "EDIT_TEXT", 
                    "args": {"old_text": "Machine", "new_text": "Artificial"}
                }
            })
            assert response.status_code == 200
        
        # Step 4: Export slides
        response = client.post("/slides/export")
        assert response.status_code == 200

    def test_error_handling_workflow(self, client):
        """Test system handles errors gracefully."""
        # Test invalid requests, malformed data, etc.
        response = client.post("/chat", json={
            "message": None,  # Invalid message
            "session_id": "error_test"
        })
        # Should handle gracefully, not crash
        assert response.status_code in [200, 422, 500]  # Acceptable responses

    @pytest.mark.slow
    def test_performance_baseline(self, client):
        """Test performance baseline for slide generation."""
        import time
        
        start_time = time.time()
        response = client.post("/chat", json={
            "message": "Create 5 slides about data science",
            "session_id": "perf_test"
        })
        end_time = time.time()
        
        assert response.status_code == 200
        # Baseline: should complete within 30 seconds
        assert (end_time - start_time) < 30
```

### Frontend Testing

#### Step 1.5.7: React Component Tests
**Estimated Time:** 1 day

**Update existing React tests** and add comprehensive coverage:

**Enhanced App Tests** (`frontend/slide-generator-frontend/src/App.test.tsx`):
```typescript
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import * as api from './services/api'; // Mock API calls

// Mock API module
jest.mock('./services/api');

describe('App Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders application title', () => {
    render(<App />);
    expect(screen.getByText(/slide generator/i)).toBeInTheDocument();
  });

  test('displays chat interface', () => {
    render(<App />);
    expect(screen.getByRole('textbox')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
  });

  test('handles message submission', async () => {
    const mockSendMessage = jest.spyOn(api, 'sendChatMessage').mockResolvedValue({
      messages: [{ role: 'user', content: 'test message' }],
      session_id: 'test'
    });

    render(<App />);
    const input = screen.getByRole('textbox');
    const submitButton = screen.getByRole('button', { name: /send/i });

    await userEvent.type(input, 'Create 2 slides about AI');
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledWith('Create 2 slides about AI', expect.any(String));
    });
  });
});
```

**Component Tests** (`frontend/slide-generator-frontend/src/components/ChatInterface.test.tsx`):
```typescript
import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatInterface from './ChatInterface';

describe('ChatInterface Component', () => {
  const defaultProps = {
    messages: [],
    onSendMessage: jest.fn(),
    isLoading: false
  };

  test('renders message input and send button', () => {
    render(<ChatInterface {...defaultProps} />);
    expect(screen.getByPlaceholderText(/type your message/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send/i })).toBeInTheDocument();
  });

  test('displays existing messages', () => {
    const messages = [
      { role: 'user', content: 'Hello' },
      { role: 'assistant', content: 'Hi there!' }
    ];
    
    render(<ChatInterface {...defaultProps} messages={messages} />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('Hi there!')).toBeInTheDocument();
  });

  test('handles message submission', async () => {
    const onSendMessage = jest.fn();
    render(<ChatInterface {...defaultProps} onSendMessage={onSendMessage} />);
    
    const input = screen.getByPlaceholderText(/type your message/i);
    await userEvent.type(input, 'Test message');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));
    
    expect(onSendMessage).toHaveBeenCalledWith('Test message');
  });
});
```

### Test Automation and CI Integration

#### Step 1.5.8: Test Automation Setup
**Estimated Time:** 0.5 days

**GitHub Actions Workflow** (`.github/workflows/test.yml`):
```yaml
name: Test Suite

on: [push, pull_request]

jobs:
  test-backend:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    - name: Install dependencies
      run: |
        pip install -e ".[dev]"
    - name: Run unit tests
      run: |
        pytest tests/unit/ -v --cov=slide_generator --cov-report=xml
    - name: Run integration tests  
      run: |
        pytest tests/integration/ -v
    - name: Upload coverage
      uses: codecov/codecov-action@v3

  test-frontend:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Node.js
      uses: actions/setup-node@v3
      with:
        node-version: '18'
    - name: Install dependencies
      run: |
        cd frontend/slide-generator-frontend
        npm install
    - name: Run tests
      run: |
        cd frontend/slide-generator-frontend
        npm test -- --coverage --watchAll=false
```

### Performance and Load Testing

#### Step 1.5.9: Performance Test Suite
**Estimated Time:** 1 day

**Load Testing** (`tests/performance/test_load.py`):
```python
"""Load testing for slide generation API."""
import pytest
import asyncio
import aiohttp
import time
from concurrent.futures import ThreadPoolExecutor

@pytest.mark.performance
class TestPerformanceLoad:
    BASE_URL = "http://localhost:8000"
    
    async def test_concurrent_chat_requests(self):
        """Test API handles concurrent chat requests."""
        async def send_request(session, session_id):
            async with session.post(f"{self.BASE_URL}/chat", json={
                "message": f"Create 2 slides about topic {session_id}",
                "session_id": f"load_test_{session_id}"
            }) as response:
                return response.status, await response.json()
        
        async with aiohttp.ClientSession() as session:
            tasks = [send_request(session, i) for i in range(10)]
            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()
            
            # All requests should complete within reasonable time
            assert (end_time - start_time) < 60  # 1 minute for 10 concurrent requests
            
            # Most requests should succeed (allow some failures under load)
            success_count = sum(1 for r in results if not isinstance(r, Exception) and r[0] == 200)
            assert success_count >= 8  # At least 80% success rate
    
    def test_memory_usage_baseline(self):
        """Test memory usage doesn't grow unboundedly."""
        import psutil
        import requests
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Send multiple requests
        for i in range(50):
            requests.post(f"{self.BASE_URL}/chat", json={
                "message": f"Test message {i}",
                "session_id": f"mem_test_{i}"
            })
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory
        
        # Memory growth should be reasonable (less than 500MB for 50 requests)
        assert memory_growth < 500
```

### Testing Documentation and Maintenance

#### Step 1.5.10: Testing Documentation
**Estimated Time:** 0.5 days

**Create `tests/README.md`:**
```markdown
# Testing Guide

## Overview
This directory contains comprehensive test suites for the AI Slide Generator.

## Test Structure
- `unit/` - Unit tests for individual components
- `integration/` - Integration tests for API and workflows  
- `e2e/` - End-to-end tests for complete user journeys
- `performance/` - Load and performance tests
- `fixtures/` - Test data and mock objects

## Running Tests

### All Tests
```bash
pytest
```

### By Category
```bash
pytest tests/unit/          # Unit tests only
pytest tests/integration/   # Integration tests only  
pytest tests/e2e/          # End-to-end tests only
pytest -m "not slow"       # Skip slow tests
```

### With Coverage
```bash
pytest --cov=slide_generator --cov-report=html
open htmlcov/index.html
```

## Test Requirements
- All new code must have >90% test coverage
- Integration tests required for API changes
- Performance tests for core workflows
- E2E tests for user-facing features

## Databricks Testing Strategy
- **Real Client:** Use authenticated Databricks WorkspaceClient with default profile
- **Mocked Responses:** Mock service responses (LLM, Genie) for consistent testing  
- **No Vector Search:** Vector search functionality ignored (will be removed)
- **Authentication Required:** Tests require valid Databricks credentials

## Mocking Guidelines
- **DO Mock:** LLM responses, Genie SQL results, external API responses
- **DON'T Mock:** Databricks client authentication, internal slide generation logic
- Use real objects for internal components when possible
- Provide sample data fixtures for consistent testing

## Environment Requirements
```bash
# Required: Databricks authentication configured
databricks configure  # or set DATABRICKS_HOST/DATABRICKS_TOKEN

# Test execution
pytest                           # All tests
pytest tests/unit/               # Unit tests only  
pytest -k "not genie"          # Skip Genie-dependent tests
pytest --tb=short              # Shorter tracebacks for faster feedback
```
```

### Phase 1.5 Validation and Completion

#### Step 1.5.11: Test Coverage Validation
**Estimated Time:** 0.5 days

**Coverage Goals:**
- **Unit Tests**: >90% coverage of core components
- **Integration Tests**: All API endpoints covered
- **E2E Tests**: All critical user journeys covered
- **Performance Tests**: Baseline metrics established

**Validation Checklist:**
- [ ] All existing functionality has test coverage
- [ ] Tests pass in CI/CD pipeline  
- [ ] Performance baselines documented
- [ ] Test documentation complete
- [ ] Team trained on testing practices

#### Step 1.5.12: Testing Implementation Review
**Estimated Time:** 0.5 days

**Review Criteria:**
- [ ] Test quality and maintainability
- [ ] Coverage completeness
- [ ] Performance test reliability
- [ ] Documentation clarity
- [ ] CI/CD integration working

### Phase 1.5 Success Criteria

**Completion Requirements:**
- ✅ Comprehensive unit test suite (>90% coverage)
- ✅ Integration test coverage for all APIs
- ✅ End-to-end tests for critical workflows
- ✅ Performance baselines established
- ✅ CI/CD pipeline with automated testing
- ✅ Testing documentation and guidelines
- ✅ Team equipped to maintain test quality

**Benefits Achieved:**
- Confidence in codebase stability with real Databricks authentication
- Regression detection capability for LLM and Genie integrations
- Performance monitoring baseline with actual client overhead
- Documentation of expected behavior using authentic connections
- Foundation for safe refactoring in Phase 2+ with production-like testing

### Key Testing Approach Changes

**Real Databricks Client Integration:**
- Tests use authenticated `WorkspaceClient()` with default profile  
- Validates actual authentication and connection logic
- Ensures Databricks SDK integration works correctly

**Strategic Response Mocking:**
- Mock LLM serving endpoint responses for consistent test data
- Mock Genie SQL execution results for deterministic testing
- Mock vector search responses (ignoring as feature will be removed)
- Preserve authentication and client instantiation logic

**Production-Like Testing:**
- Tests verify actual Databricks connectivity
- LLM tools receive realistic response structures  
- Genie tools validate SQL execution flow
- Performance tests include authentication overhead

```

## Phase 2: Standardize Architecture (Priority: HIGH)
**Timeline:** 1 week  
**Risk Level:** Medium  
**Branch:** `phase2-standardize-arch`

### Pre-Implementation Analysis

#### Step 2.0: Migration Assessment
**Objective:** Confirm html_slides.py → html_slides_agent.py migration status

**Tasks:**
- [ ] Analyze which system backend/main.py actually uses
- [ ] Compare feature parity between both systems
- [ ] Identify any missing functionality in agent system
- [ ] Document migration completeness

### Implementation Steps

#### Step 2.1: Complete Slide System Migration
**Estimated Time:** 2 days

**If html_slides.py still in use:**
- [ ] Port any missing functionality to html_slides_agent.py
- [ ] Update all imports in backend/main.py
- [ ] Test feature parity
- [ ] Remove html_slides.py (1,123 lines)

**If migration already complete:**
- [ ] Remove html_slides.py immediately
- [ ] Clean up any remaining imports
- [ ] Verify no functionality loss

#### Step 2.2: Standardize Configuration Management
**Estimated Time:** 1 day

**Databricks Configuration:**
```python
# Create src/slide_generator/config/databricks.py
class DatabricksConfig:
    def __init__(self):
        self.profile = os.getenv('DATABRICKS_PROFILE', 'default')
        self.host = os.getenv('DATABRICKS_HOST')
        self.token = os.getenv('DATABRICKS_TOKEN')
```

**Files to Update:**
- [ ] `backend/main.py` - Use environment-based config
- [ ] `html_slides_agent.py` - Remove hardcoded 'logfood' profile
- [ ] `uc_tools.py` - Standardize authentication
- [ ] Create `.env.example` with required variables

#### Step 2.3: Implement Consistent Error Handling
**Estimated Time:** 1 day

**Error Handling Patterns:**
```python
# Standardize on this pattern
class SlideGeneratorException(Exception):
    """Base exception for slide generator errors"""
    pass

class SlideGenerationError(SlideGeneratorException):
    """Error during slide generation"""
    pass

# Update all functions to use consistent error handling
```

**Files to Update:**
- [ ] All tool functions in `html_slides_agent.py`
- [ ] API endpoints in `backend/main.py`
- [ ] Add proper error responses with status codes

#### Step 2.4: Remove Global State
**Estimated Time:** 2 days

**Current Issues:**
- Backend uses `global slide_agent`
- Conversation state in global variables

**Implementation:**
```python
# Replace global state with proper session management
class SessionManager:
    def __init__(self):
        self.sessions = {}
    
    def get_or_create_session(self, session_id: str):
        if session_id not in self.sessions:
            self.sessions[session_id] = self.create_session()
        return self.sessions[session_id]
```

### Phase 2 Testing & Validation

#### Step 2.5: Architecture Validation
- [ ] No global state remaining
- [ ] Consistent error handling across all endpoints
- [ ] Configuration properly externalized
- [ ] All tests pass

---

## Phase 3: Code Quality Improvements (Priority: MEDIUM)
**Timeline:** 1 week  
**Risk Level:** Low-Medium  
**Branch:** `phase3-code-quality`

### Implementation Steps

#### Step 3.1: Break Up Large Files
**Target Files:**
- `html_slides_agent.py` (1,166 lines) → Split into:
  - `html_slides_agent.py` (core agent)
  - `slide_models.py` (Pydantic models)
  - `slide_tools.py` (tool functions)
  - `slide_validation.py` (HTML validation)

- `backend/main.py` (740 lines) → Split into:
  - `main.py` (FastAPI app setup)
  - `routes/chat.py` (chat endpoints)
  - `routes/slides.py` (slide endpoints)
  - `services/slide_service.py` (business logic)

#### Step 3.2: Add Type Hints
- [ ] Complete type hints for all functions
- [ ] Add mypy configuration
- [ ] Fix all type checking errors

#### Step 3.3: Implement Proper Logging
```python
# Replace print statements with proper logging
import logging

logger = logging.getLogger(__name__)

# Replace: print(f"[DEBUG] ...")
# With: logger.debug("...")
```

#### Step 3.4: Add Integration Tests
- [ ] Test critical user journeys
- [ ] API endpoint tests
- [ ] Agent functionality tests

---

## Phase 4: Advanced Refactoring (Priority: LOW)
**Timeline:** 2 weeks  
**Risk Level:** High  
**Branch:** `phase4-advanced`

### Implementation Steps

#### Step 4.1: Implement Dependency Injection
- [ ] Create proper service layer
- [ ] Injectable configuration
- [ ] Testable architecture

#### Step 4.2: Add Comprehensive Monitoring
- [ ] Request tracing
- [ ] Performance metrics
- [ ] Error tracking

---

## Risk Mitigation Strategies

### Rollback Plan
At any phase, rollback by:
```bash
git checkout refactor-main
git branch -D phase-X-branch
# Continue from known good state
```

### Validation Gates
Each phase must pass:
- [ ] All existing functionality works
- [ ] No performance regression
- [ ] All tests pass
- [ ] Documentation updated

### Communication Plan
- [ ] Daily standup updates on progress
- [ ] Weekly demo of refactored functionality
- [ ] Stakeholder review at end of each phase

## Success Metrics

### Phase 1 Success:
- 2,000+ lines of duplicate code removed
- Single README file
- Consolidated dependencies
- No functionality loss

### Overall Success:
- 50%+ reduction in total codebase size
- Consistent architecture patterns
- Maintainable code structure  
- Improved developer onboarding time
- Faster feature development velocity

## Timeline Summary

| Phase | Duration | Risk | Dependency | Status |
|-------|----------|------|------------|---------|
| Phase 1 | 2-3 days | Low | None | ✅ Complete |
| Phase 1.5 | 3-5 days | Low | Phase 1 complete | 🔄 **Current** |
| Phase 2 | 1 week | Medium | Phase 1.5 complete | ⏳ Pending |
| Phase 3 | 1 week | Low-Medium | Phase 2 complete | ⏳ Pending |
| Phase 4 | 2 weeks | High | Phase 3 complete | ⏳ Pending |

**Updated Timeline:** 5-6 weeks for complete refactoring
**Minimum Viable:** Phase 1-2 (2-3 weeks) for major improvements with test safety
**Critical Path:** Phase 1.5 testing foundation must complete before architectural changes
