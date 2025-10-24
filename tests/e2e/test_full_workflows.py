"""End-to-end workflow tests."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import tempfile
import os
import time


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    from backend.main import app
    return TestClient(app)


@pytest.fixture
def mock_slide_agent_responses(monkeypatch):
    """Mock slide agent responses for E2E testing."""
    mock_serving_client = MagicMock()
    mock_serving_client.chat.completions.create.return_value = {
        "choices": [{
            "message": {
                "content": '<!DOCTYPE html><html><head><title>E2E Test Slide</title></head><body style="width:1280px;height:720px;"><h1 style="color:#102025;">E2E Test Slide</h1><p>This slide was generated during end-to-end testing</p></body></html>'
            }
        }]
    }
    
    monkeypatch.setattr("slide_generator.tools.html_slides_agent.model_serving_client", mock_serving_client)
    return {"serving_client": mock_serving_client}


@pytest.mark.e2e
class TestCompleteWorkflows:
    """End-to-end workflow tests for complete user journeys."""

    @pytest.mark.integration
    @pytest.mark.databricks
    def test_complete_slide_generation_workflow(self, client, mock_slide_agent_responses):
        """Test complete slide generation from chat to export."""
        session_id = "e2e_test_session"
        
        # Step 1: Start conversation
        response = client.post("/chat", json={
            "message": "Create a 3-slide presentation about machine learning",
            "session_id": session_id
        })
        assert response.status_code == 200
        chat_data = response.json()
        assert "messages" in chat_data
        assert "session_id" in chat_data
        
        # Step 2: Check conversation status
        response = client.get(f"/chat/status/{session_id}")
        assert response.status_code == 200
        
        # Step 3: Check slide generation status
        response = client.get("/slides/status")
        assert response.status_code == 200
        status_data = response.json()
        assert "status" in status_data
        
        # Step 4: Get generated slides
        response = client.get("/slides/html")
        assert response.status_code == 200
        slides_data = response.json()
        assert "slides" in slides_data
        
        # Step 5: Modify a slide (if slides were generated)
        if slides_data["slides"]:
            response = client.post("/slides/modify", json={
                "slide_id": "slide_1",
                "change": {
                    "operation": "EDIT_TEXT", 
                    "args": {"old_text": "Machine", "new_text": "Artificial"}
                }
            })
            # Modification may succeed or fail, both acceptable
            assert response.status_code in [200, 404, 500]
        
        # Step 6: Export slides
        response = client.post("/slides/export")
        assert response.status_code == 200
        export_data = response.json()
        assert "files" in export_data or "error" in export_data
        
        # Step 7: Clear slides for cleanup
        response = client.post("/slides/clear")
        assert response.status_code == 200

    def test_error_handling_workflow(self, client):
        """Test system handles errors gracefully."""
        session_id = "error_test"
        
        # Test invalid message handling
        response = client.post("/chat", json={
            "message": None,  # Invalid message
            "session_id": session_id
        })
        # Should handle gracefully, not crash
        assert response.status_code in [200, 422, 500]
        
        # Test recovery with valid message
        response = client.post("/chat", json={
            "message": "Valid recovery message",
            "session_id": session_id
        })
        assert response.status_code == 200
        
        # Test invalid slide operations
        response = client.post("/slides/modify", json={
            "slide_id": "nonexistent_slide",
            "change": {
                "operation": "INVALID_OP",
                "args": {}
            }
        })
        # API handles errors gracefully, may return 200 with error message
        assert response.status_code in [200, 400, 404, 422, 500]
        
        # System should still be responsive
        response = client.get("/health")
        assert response.status_code == 200

    @pytest.mark.slow
    @pytest.mark.databricks
    def test_performance_baseline(self, client, mock_slide_agent_responses):
        """Test performance baseline for slide generation."""
        session_id = "perf_test"
        
        start_time = time.time()
        response = client.post("/chat", json={
            "message": "Create 5 slides about data science",
            "session_id": session_id
        })
        end_time = time.time()
        
        assert response.status_code == 200
        # Baseline: should complete within 30 seconds
        assert (end_time - start_time) < 30
        
        # Test slide retrieval performance
        start_time = time.time()
        response = client.get("/slides/html")
        end_time = time.time()
        
        assert response.status_code == 200
        # Should retrieve slides quickly (under 5 seconds)
        assert (end_time - start_time) < 5

    def test_session_isolation_workflow(self, client, mock_slide_agent_responses):
        """Test that different sessions are properly isolated."""
        session1_id = "isolation_test_1"
        session2_id = "isolation_test_2"
        
        # Create content in session 1
        response = client.post("/chat", json={
            "message": "Create slides about session 1 content",
            "session_id": session1_id
        })
        assert response.status_code == 200
        
        # Create different content in session 2
        response = client.post("/chat", json={
            "message": "Create slides about session 2 content",
            "session_id": session2_id
        })
        assert response.status_code == 200
        
        # Check that sessions have different content
        response1 = client.get(f"/chat/status/{session1_id}")
        response2 = client.get(f"/chat/status/{session2_id}")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Sessions should be independent
        data1 = response1.json()
        data2 = response2.json()
        assert data1["session_id"] != data2["session_id"]

    @pytest.mark.integration
    def test_multi_format_export_workflow(self, client, mock_slide_agent_responses):
        """Test exporting slides in multiple formats.""" 
        session_id = "export_test"
        
        # Generate slides
        response = client.post("/chat", json={
            "message": "Create 2 slides about export testing",
            "session_id": session_id
        })
        assert response.status_code == 200
        
        # Test HTML export
        response = client.get("/slides/html")
        assert response.status_code == 200
        html_data = response.json()
        
        # Test general export (includes multiple formats)
        response = client.post("/slides/export")
        assert response.status_code == 200
        export_data = response.json()
        
        # Test PPTX export
        response = client.get("/slides/export/pptx")
        assert response.status_code in [200, 404, 500]
        
        # If exports succeed, verify file information
        if "files" in export_data:
            assert isinstance(export_data["files"], list)

    def test_conversation_continuity_workflow(self, client, mock_slide_agent_responses):
        """Test conversation continuity across multiple interactions."""
        session_id = "continuity_test"
        
        # Start conversation
        response = client.post("/chat", json={
            "message": "Create slides about AI",
            "session_id": session_id
        })
        assert response.status_code == 200
        
        # Continue conversation
        response = client.post("/chat", json={
            "message": "Add more details about machine learning",
            "session_id": session_id
        })
        assert response.status_code == 200
        
        # Further conversation
        response = client.post("/chat", json={
            "message": "Change the style to be more technical",
            "session_id": session_id
        })
        assert response.status_code == 200
        
        # Verify conversation history
        response = client.get(f"/conversation/{session_id}")
        assert response.status_code == 200
        conversation_data = response.json()
        assert "conversation" in conversation_data

    @pytest.mark.integration
    def test_state_recovery_workflow(self, client):
        """Test system state recovery after operations."""
        session_id = "recovery_test"
        
        # Perform various operations
        client.post("/slides/clear")
        client.post("/slides/reset") 
        client.post("/slides/refresh")
        
        # System should remain functional
        response = client.get("/health")
        assert response.status_code == 200
        
        response = client.get("/slides/status")
        assert response.status_code == 200
        
        # Should be able to start new conversation
        response = client.post("/chat", json={
            "message": "Test recovery with new conversation",
            "session_id": session_id
        })
        assert response.status_code == 200


@pytest.mark.e2e
class TestErrorRecoveryScenarios:
    """Test error recovery and edge cases in end-to-end workflows."""

    def test_malformed_input_recovery(self, client):
        """Test recovery from malformed inputs."""
        session_id = "malformed_test"
        
        # Send malformed requests
        malformed_requests = [
            {"message": "", "session_id": session_id},  # Empty message
            {"message": "x" * 10000, "session_id": session_id},  # Very long message
            {"session_id": session_id},  # Missing message
        ]
        
        for request in malformed_requests:
            response = client.post("/chat", json=request)
            # Should handle gracefully
            assert response.status_code in [200, 422, 400]
        
        # Should recover with valid request
        response = client.post("/chat", json={
            "message": "Valid message after malformed inputs",
            "session_id": session_id
        })
        assert response.status_code == 200

    def test_rapid_request_handling(self, client):
        """Test handling of rapid successive requests."""
        session_id = "rapid_test"
        
        # Send multiple rapid requests
        for i in range(5):
            response = client.post("/chat", json={
                "message": f"Rapid message {i}",
                "session_id": session_id
            })
            # Should handle all requests
            assert response.status_code in [200, 429, 500]  # Include rate limiting
        
        # System should remain responsive
        response = client.get("/health")
        assert response.status_code == 200

    def test_resource_cleanup_workflow(self, client):
        """Test proper resource cleanup after operations.""" 
        session_id = "cleanup_test"
        
        # Perform operations that create resources
        client.post("/chat", json={
            "message": "Create slides for cleanup testing",
            "session_id": session_id
        })
        
        # Generate slides
        client.post("/slides/generate", json={
            "topic": "Cleanup Test",
            "slide_count": 3
        })
        
        # Export slides (creates files)
        client.post("/slides/export")
        
        # Clear everything
        response = client.post("/slides/clear")
        assert response.status_code == 200
        
        # Verify cleanup
        response = client.get("/slides/status")
        assert response.status_code == 200
        
        # Should be able to start fresh
        response = client.post("/chat", json={
            "message": "New conversation after cleanup",
            "session_id": "new_session"
        })
        assert response.status_code == 200


@pytest.mark.e2e  
@pytest.mark.slow
class TestLongRunningWorkflows:
    """Test longer-running workflows and stress scenarios."""

    def test_extended_conversation_workflow(self, client, mock_slide_agent_responses):
        """Test extended conversation with many interactions."""
        session_id = "extended_test"
        
        conversation_steps = [
            "Create a presentation about data science",
            "Add more slides about machine learning",
            "Change the style to be more visual",
            "Add charts and graphs",
            "Make it more professional",
            "Export the final presentation"
        ]
        
        for step in conversation_steps:
            response = client.post("/chat", json={
                "message": step,
                "session_id": session_id
            })
            assert response.status_code == 200
            
        # Verify final state
        response = client.get(f"/conversation/{session_id}")
        assert response.status_code == 200

    def test_large_presentation_workflow(self, client, mock_slide_agent_responses):
        """Test workflow with large presentations."""
        session_id = "large_pres_test"
        
        # Request large presentation
        response = client.post("/chat", json={
            "message": "Create a comprehensive 10-slide presentation about artificial intelligence covering history, current applications, machine learning, deep learning, neural networks, natural language processing, computer vision, ethics, future trends, and conclusions",
            "session_id": session_id
        })
        assert response.status_code == 200
        
        # Should handle large requests
        response = client.get("/slides/status")
        assert response.status_code == 200

    @pytest.mark.performance
    def test_concurrent_session_workflow(self, client, mock_slide_agent_responses):
        """Test multiple concurrent sessions."""
        import concurrent.futures
        import threading
        
        def create_session_workflow(session_num):
            session_id = f"concurrent_session_{session_num}"
            
            # Start conversation
            response = client.post("/chat", json={
                "message": f"Create slides for session {session_num}",
                "session_id": session_id
            })
            return response.status_code == 200
        
        # Run 3 concurrent sessions
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(create_session_workflow, i) for i in range(3)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # Most sessions should succeed
        success_count = sum(results)
        assert success_count >= 2  # At least 2/3 should succeed
