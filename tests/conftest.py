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

@pytest.fixture
def sample_invalid_html():
    """Sample invalid HTML for testing validation."""
    return "<div>Incomplete HTML without proper structure"

@pytest.fixture  
def sample_presentation_request():
    """Sample presentation request for testing."""
    return {
        "message": "Create 3 slides about machine learning",
        "session_id": "test_session_123"
    }

@pytest.fixture
def sample_slide_modification():
    """Sample slide modification request for testing."""
    return {
        "slide_id": "slide_1",
        "change": {
            "operation": "EDIT_TEXT",
            "args": {"old_text": "old", "new_text": "new"}
        }
    }

@pytest.fixture
def mock_slide_agent_state():
    """Mock slide agent state for testing."""
    return {
        "config_version": 0,
        "messages": [],
        "todos": [],
        "artifacts": {},
        "pending_changes": [],
        "status": [],
        "errors": [],
        "metrics": {},
        "run_id": "test_run"
    }
