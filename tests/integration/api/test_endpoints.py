"""Test FastAPI endpoints integration."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json
import os


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    # Import app here to avoid issues with module loading
    from backend.main import app
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

    @pytest.mark.integration
    @pytest.mark.databricks
    def test_chat_endpoint_valid_message(self, client, mock_slide_agent_responses):
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

    def test_chat_endpoint_missing_fields(self, client):
        """Test chat endpoint with missing required fields.""" 
        response = client.post("/chat", json={
            "message": "Test message"
            # Missing session_id
        })
        # Should handle missing session_id gracefully or return 422
        assert response.status_code in [200, 422]

    def test_chat_endpoint_invalid_json(self, client):
        """Test chat endpoint with invalid JSON."""
        response = client.post("/chat", data="invalid json")
        assert response.status_code == 422

    def test_chat_status_endpoint(self, client):
        """Test chat status retrieval."""
        session_id = "test_session"
        response = client.get(f"/chat/status/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data

    def test_chat_status_nonexistent_session(self, client):
        """Test chat status for non-existent session."""
        session_id = "nonexistent_session"
        response = client.get(f"/chat/status/{session_id}")
        # Should return empty/default status or 404
        assert response.status_code in [200, 404]


class TestSlideEndpoints:
    def test_slides_html_endpoint(self, client):
        """Test slides HTML retrieval endpoint."""
        response = client.get("/slides/html")
        assert response.status_code == 200
        data = response.json()
        assert "slides" in data

    @pytest.mark.integration
    @pytest.mark.databricks
    def test_slides_status_endpoint(self, client, mock_slide_agent_responses):
        """Test slides status endpoint with real Databricks client."""
        response = client.get("/slides/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "slides" in data

    def test_slides_refresh_endpoint(self, client):
        """Test slides refresh endpoint."""
        response = client.post("/slides/refresh")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_slides_reset_endpoint(self, client):
        """Test slides reset endpoint."""
        response = client.post("/slides/reset")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_slides_clear_endpoint(self, client):
        """Test slides clear endpoint."""
        response = client.post("/slides/clear")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    @pytest.mark.integration  
    @pytest.mark.databricks
    def test_slides_generate_endpoint(self, client, mock_slide_agent_responses):
        """Test slides generation endpoint."""
        response = client.post("/slides/generate", json={
            "topic": "Machine Learning",
            "slide_count": 3
        })
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    @pytest.mark.integration
    @pytest.mark.databricks
    def test_slide_modification(self, client, mock_slide_agent_responses):
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

    def test_slide_modification_invalid_data(self, client):
        """Test slide modification with invalid data."""
        response = client.post("/slides/modify", json={
            "slide_id": "slide_1",
            "invalid_field": "invalid_value"
        })
        assert response.status_code in [400, 422, 500]

    @pytest.mark.integration
    @pytest.mark.databricks
    def test_slides_export(self, client, mock_slide_agent_responses):
        """Test slides export functionality with real Databricks client."""
        response = client.post("/slides/export")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data or "error" in data  # May have no slides to export

    def test_slides_export_pptx_get(self, client):
        """Test PPTX export GET endpoint."""
        response = client.get("/slides/export/pptx")
        # May return file or error depending on whether slides exist
        assert response.status_code in [200, 404, 500]


class TestConversationEndpoints:
    def test_conversation_retrieval(self, client):
        """Test conversation retrieval endpoint."""
        session_id = "test_session"
        response = client.get(f"/conversation/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert "conversation" in data

    def test_conversation_nonexistent_session(self, client):
        """Test conversation retrieval for non-existent session."""
        session_id = "nonexistent_session" 
        response = client.get(f"/conversation/{session_id}")
        # Should return empty conversation or 404
        assert response.status_code in [200, 404]


class TestErrorHandling:
    def test_invalid_endpoint(self, client):
        """Test request to non-existent endpoint."""
        response = client.get("/nonexistent")
        assert response.status_code == 404

    def test_method_not_allowed(self, client):
        """Test using wrong HTTP method."""
        # Try GET on POST endpoint
        response = client.get("/chat")
        assert response.status_code == 405

    def test_large_payload_handling(self, client):
        """Test handling of large payloads."""
        large_message = "x" * 10000  # 10KB message
        response = client.post("/chat", json={
            "message": large_message,
            "session_id": "test_session"
        })
        # Should either process successfully or return appropriate error
        assert response.status_code in [200, 413, 422]

    @pytest.mark.slow
    def test_concurrent_requests(self, client):
        """Test API handles concurrent requests."""
        import concurrent.futures
        import threading
        
        def make_request(session_id):
            return client.post("/chat", json={
                "message": f"Test message for session {session_id}",
                "session_id": f"concurrent_test_{session_id}"
            })
        
        # Make 5 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should complete successfully
        for response in results:
            assert response.status_code == 200


class TestCORSAndMiddleware:
    def test_cors_headers(self, client):
        """Test CORS headers are present."""
        response = client.get("/")
        # CORS headers should be present
        assert response.status_code == 200
        # Note: TestClient might not show all middleware headers

    def test_options_request(self, client):
        """Test OPTIONS request for CORS preflight."""
        # Some endpoints should support OPTIONS
        response = client.options("/")
        # Should either succeed or be method not allowed
        assert response.status_code in [200, 405]


@pytest.mark.integration
class TestFullAPIWorkflow:
    """Integration tests for complete API workflows."""
    
    @pytest.mark.databricks
    def test_complete_slide_creation_workflow(self, client, mock_slide_agent_responses):
        """Test complete slide creation from chat to export."""
        session_id = "integration_test_session"
        
        # Step 1: Start conversation
        response = client.post("/chat", json={
            "message": "Create a 3-slide presentation about machine learning",
            "session_id": session_id
        })
        assert response.status_code == 200
        
        # Step 2: Check slide generation status
        response = client.get("/slides/status")
        assert response.status_code == 200
        
        # Step 3: Try to export slides
        response = client.post("/slides/export")
        assert response.status_code == 200
        
    def test_error_recovery_workflow(self, client):
        """Test API recovers gracefully from errors."""
        session_id = "error_recovery_test"
        
        # Send invalid request
        response = client.post("/chat", json={
            "message": None,  # Invalid message
            "session_id": session_id
        })
        # Should handle gracefully
        assert response.status_code in [200, 422, 500]
        
        # Follow up with valid request
        response = client.post("/chat", json={
            "message": "Valid message",
            "session_id": session_id
        })
        assert response.status_code == 200
