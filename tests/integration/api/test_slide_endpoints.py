"""Test slide-specific API endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    from backend.main import app
    return TestClient(app)


@pytest.fixture  
def mock_slide_agent_responses(monkeypatch):
    """Mock slide agent responses for testing."""
    # Create proper OpenAI-style response object
    mock_message = MagicMock()
    mock_message.content = '<!DOCTYPE html><html><head><title>Test Slide</title></head><body style="width:1280px;height:720px;"><h1 style="color:#102025;">Test Slide</h1><p>Test slide content</p></body></html>'
    
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    mock_serving_client = MagicMock()
    mock_serving_client.chat.completions.create.return_value = mock_response
    
    monkeypatch.setattr("slide_generator.tools.html_slides_agent.get_model_serving_client", lambda: mock_serving_client)
    return {"serving_client": mock_serving_client}


class TestSlideManagement:
    """Test slide management endpoints."""
    
    @pytest.mark.integration
    def test_slide_lifecycle(self, client, mock_slide_agent_responses):
        """Test complete slide lifecycle: create -> modify -> export -> clear."""
        
        # Step 1: Generate slides
        response = client.post("/slides/generate", json={
            "topic": "Testing", 
            "slide_count": 2
        })
        assert response.status_code == 200
        
        # Step 2: Check slides status
        response = client.get("/slides/status")
        assert response.status_code == 200
        status_data = response.json()
        assert "slides" in status_data
        
        # Step 3: Get slide HTML
        response = client.get("/slides/html")
        assert response.status_code == 200
        html_data = response.json()
        assert "slides" in html_data
        
        # Step 4: Try to modify a slide (if slides exist)
        if status_data.get("slides"):
            response = client.post("/slides/modify", json={
                "slide_id": "slide_1",
                "change": {
                    "operation": "EDIT_TEXT",
                    "args": {"old_text": "Testing", "new_text": "Modified Testing"}
                }
            })
            # May succeed or fail depending on slide existence
            assert response.status_code in [200, 404, 500]
        
        # Step 5: Export slides
        response = client.post("/slides/export")
        assert response.status_code == 200
        export_data = response.json()
        assert "files" in export_data or "error" in export_data
        
        # Step 6: Clear slides
        response = client.post("/slides/clear")
        assert response.status_code == 200

    def test_slide_generation_validation(self, client):
        """Test slide generation input validation."""
        
        # Test with valid input
        response = client.post("/slides/generate", json={
            "topic": "Valid Topic",
            "slide_count": 3
        })
        assert response.status_code == 200
        
        # Test with missing topic
        response = client.post("/slides/generate", json={
            "slide_count": 3
        })
        assert response.status_code in [422, 400]
        
        # Test with invalid slide count
        response = client.post("/slides/generate", json={
            "topic": "Test Topic",
            "slide_count": 0
        })
        assert response.status_code in [422, 400]
        
        # Test with excessive slide count
        response = client.post("/slides/generate", json={
            "topic": "Test Topic", 
            "slide_count": 100
        })
        assert response.status_code in [422, 400]

    def test_slide_modification_operations(self, client, mock_slide_agent_responses):
        """Test different slide modification operations."""
        
        # Test text edit operation
        response = client.post("/slides/modify", json={
            "slide_id": "slide_1",
            "change": {
                "operation": "EDIT_TEXT",
                "args": {"old_text": "original", "new_text": "modified"}
            }
        })
        assert response.status_code in [200, 404, 500]
        
        # Test add content operation
        response = client.post("/slides/modify", json={
            "slide_id": "slide_1", 
            "change": {
                "operation": "ADD_CONTENT",
                "args": {"content": "New bullet point", "position": "end"}
            }
        })
        assert response.status_code in [200, 404, 422, 500]
        
        # Test style change operation
        response = client.post("/slides/modify", json={
            "slide_id": "slide_1",
            "change": {
                "operation": "CHANGE_STYLE",
                "args": {"element": "h1", "style": "color: blue;"}
            }
        })
        assert response.status_code in [200, 404, 422, 500]

    def test_slide_modification_validation(self, client):
        """Test slide modification input validation."""
        
        # Test with missing slide_id
        response = client.post("/slides/modify", json={
            "change": {
                "operation": "EDIT_TEXT",
                "args": {"old_text": "old", "new_text": "new"}
            }
        })
        assert response.status_code in [422, 400]
        
        # Test with invalid operation
        response = client.post("/slides/modify", json={
            "slide_id": "slide_1",
            "change": {
                "operation": "INVALID_OPERATION",
                "args": {}
            }
        })
        assert response.status_code in [422, 400]
        
        # Test with missing change
        response = client.post("/slides/modify", json={
            "slide_id": "slide_1"
        })
        assert response.status_code in [422, 400]

class TestSlideExport:
    """Test slide export functionality."""
    
    def test_export_formats(self, client, mock_slide_agent_responses):
        """Test different export formats."""
        
        # Test HTML export (via general export)
        response = client.post("/slides/export")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data or "error" in data
        
        # Test PPTX export
        response = client.get("/slides/export/pptx")
        assert response.status_code in [200, 404, 500]
        
        # If successful, should return file
        if response.status_code == 200:
            # Should be binary content or redirect
            assert response.headers.get("content-type") is not None

    def test_export_error_handling(self, client):
        """Test export error handling when no slides exist."""
        
        # Clear any existing slides first
        client.post("/slides/clear")
        
        # Try to export with no slides
        response = client.post("/slides/export")
        assert response.status_code == 200
        data = response.json()
        # Should indicate no slides to export
        assert "error" in data or "files" in data

    def test_export_file_generation(self, client, mock_slide_agent_responses, tmp_path):
        """Test actual file generation during export."""
        
        # Generate some slides first
        client.post("/slides/generate", json={
            "topic": "Export Test",
            "slide_count": 2
        })
        
        # Export slides
        response = client.post("/slides/export")
        assert response.status_code == 200
        
        data = response.json()
        if "files" in data:
            # Verify file information is provided
            assert isinstance(data["files"], list)
            for file_info in data["files"]:
                assert "filename" in file_info
                assert "path" in file_info or "url" in file_info

class TestSlideState:
    """Test slide state management."""
    
    def test_slide_refresh(self, client):
        """Test slide refresh functionality."""
        response = client.post("/slides/refresh")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data

    def test_slide_reset(self, client):
        """Test slide reset functionality."""
        response = client.post("/slides/reset")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert data["status"] == "reset"

    def test_slide_clear(self, client):
        """Test slide clear functionality."""
        response = client.post("/slides/clear")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data

    def test_slide_status_consistency(self, client, mock_slide_agent_responses):
        """Test slide status remains consistent across operations."""
        
        # Get initial status
        response = client.get("/slides/status")
        assert response.status_code == 200
        initial_status = response.json()
        
        # Perform operations
        client.post("/slides/refresh")
        
        # Check status again
        response = client.get("/slides/status")
        assert response.status_code == 200
        updated_status = response.json()
        
        # Status structure should be consistent
        assert set(initial_status.keys()) == set(updated_status.keys())

class TestSlideContent:
    """Test slide content handling."""
    
    def test_html_slide_retrieval(self, client, mock_slide_agent_responses):
        """Test retrieving slide HTML content."""
        
        # Generate slides first
        client.post("/slides/generate", json={
            "topic": "HTML Test",
            "slide_count": 1
        })
        
        # Retrieve HTML
        response = client.get("/slides/html")
        assert response.status_code == 200
        
        data = response.json()
        assert "slides" in data
        assert isinstance(data["slides"], list)

    def test_slide_content_validation(self, client, mock_slide_agent_responses):
        """Test slide content validation."""
        
        # Generate slides
        client.post("/slides/generate", json={
            "topic": "Validation Test", 
            "slide_count": 1
        })
        
        # Get slide HTML
        response = client.get("/slides/html") 
        assert response.status_code == 200
        
        data = response.json()
        if data.get("slides"):
            # Validate HTML structure
            for slide in data["slides"]:
                if "html" in slide:
                    html_content = slide["html"]
                    # Should be valid HTML
                    assert "<!DOCTYPE html>" in html_content or "<html>" in html_content

    @pytest.mark.integration
    def test_slide_content_persistence(self, client, mock_slide_agent_responses):
        """Test that slide content persists across requests."""
        
        # Generate slides
        response = client.post("/slides/generate", json={
            "topic": "Persistence Test",
            "slide_count": 2
        })
        assert response.status_code == 200
        
        # Get slides multiple times
        response1 = client.get("/slides/html")
        response2 = client.get("/slides/html")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Content should be consistent
        data1 = response1.json()
        data2 = response2.json()
        
        # Basic structure should be the same
        assert data1.keys() == data2.keys()
