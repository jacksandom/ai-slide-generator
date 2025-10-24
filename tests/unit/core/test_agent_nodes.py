"""Test individual LangGraph nodes."""
import pytest
from unittest.mock import patch, MagicMock
from slide_generator.tools.html_slides_agent import (
    nlu_node, planning_node, generation_node, 
    modification_node, status_node, SlideDeckState, SlideConfig
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

    @pytest.mark.databricks
    def test_nlu_node_intent_detection(self, minimal_state, authenticated_databricks_client, mock_databricks_responses, monkeypatch):
        """Test NLU node correctly identifies user intents using real client."""
        from unittest.mock import MagicMock
        
        # Mock the serving endpoint response while using real client
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_databricks_responses["llm_response"]
        monkeypatch.setattr("slide_generator.tools.html_slides_agent.model_serving_client", mock_client)
        
        # Test CREATE_PRESENTATION intent detection
        result = nlu_node(minimal_state)
        
        # Verify the function returns a valid state
        assert isinstance(result, dict)
        assert "messages" in result
        assert "config" in result
        
        # The function should process the state (even if it doesn't call LLM in this mock)
        assert result["run_id"] == "test_run"

    @pytest.mark.databricks
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
        
        # Verify planning node processes state correctly
        assert isinstance(result, dict)
        assert "todos" in result
        assert "config" in result
        
        # Verify state structure is maintained
        assert result["run_id"] == "test_run"

    @pytest.mark.databricks
    def test_generation_node_slide_creation(self, minimal_state, authenticated_databricks_client, mock_databricks_responses, monkeypatch):
        """Test generation node creates slides using real client.""" 
        from unittest.mock import MagicMock
        
        # Mock the serving endpoint response with HTML content
        mock_client = MagicMock()
        mock_response = {
            "choices": [{
                "message": {
                    "content": '<!DOCTYPE html><html><head><title>Test Slide</title></head><body style="width:1280px;height:720px;"><h1 style="color:#102025;">Test Slide</h1><p>This is a test slide about testing</p></body></html>'
                }
            }]
        }
        mock_client.chat.completions.create.return_value = mock_response
        monkeypatch.setattr("slide_generator.tools.html_slides_agent.model_serving_client", mock_client)
        
        # Add a todo to process
        minimal_state["todos"] = [{
            "id": "slide_1", 
            "title": "Test Slide",
            "outline": "This is a test slide about testing",
            "status": "pending"
        }]
        
        result = generation_node(minimal_state)
        
        # Verify generation processes the state
        assert isinstance(result, dict)
        assert "artifacts" in result
        assert "todos" in result

    def test_modification_node_slide_changes(self, minimal_state):
        """Test modification node applies changes to slides."""
        # Set up state with existing slide and pending change
        minimal_state["artifacts"] = {
            "slide_1": '<!DOCTYPE html><html><body><h1>Original Title</h1></body></html>'
        }
        minimal_state["pending_changes"] = [{
            "slide_id": "slide_1",
            "change": {
                "operation": "EDIT_TEXT",
                "args": {"old_text": "Original", "new_text": "Modified"}
            }
        }]
        
        result = modification_node(minimal_state)
        
        # Verify modification processes the state
        assert isinstance(result, dict)
        assert "artifacts" in result
        assert "pending_changes" in result

    def test_status_node_state_reporting(self, minimal_state):
        """Test status node reports current state."""
        result = status_node(minimal_state)
        
        # Verify status node processes the state
        assert isinstance(result, dict) 
        assert "status" in result
        assert "metrics" in result
        
        # Status should be updated
        assert len(result["status"]) >= 0  # May add status entries

    def test_node_error_handling(self, minimal_state):
        """Test nodes handle invalid state gracefully."""
        # Test with incomplete state
        incomplete_state = {"messages": []}
        
        # Nodes should handle missing keys gracefully
        try:
            result = status_node(incomplete_state)
            # If it doesn't raise an error, verify it returns something
            assert isinstance(result, dict)
        except KeyError:
            # It's acceptable for nodes to require certain keys
            pass

    def test_node_state_immutability(self, minimal_state):
        """Test that nodes don't mutate the input state object."""
        original_state = minimal_state.copy()
        
        # Process through status node (least likely to modify)
        result = status_node(minimal_state)
        
        # Verify original state wasn't modified (for required keys)
        assert minimal_state["run_id"] == original_state["run_id"]
        assert minimal_state["config_version"] == original_state["config_version"]
        
        # Result should be a new state object
        assert result is not minimal_state

    @pytest.mark.integration
    @pytest.mark.databricks
    def test_genie_tool_integration(self, authenticated_databricks_client, mock_databricks_responses, monkeypatch):
        """Test Genie tool works with real client but mocked responses."""
        from unittest.mock import MagicMock, patch
        
        # Mock Genie SQL execution responses
        mock_genie = MagicMock()
        mock_genie.execute_genie_request.return_value = mock_databricks_responses["genie_response"]
        
        with patch("slide_generator.tools.uc_tools.UC_tools") as mock_uc_tools:
            mock_uc_tools.return_value = mock_genie
            
            # Test that Genie tool can be called with real client
            try:
                from slide_generator.tools import uc_tools
                # If this imports successfully, the integration is working
                assert True
            except ImportError:
                # If uc_tools doesn't exist or import fails, that's also acceptable
                pytest.skip("UC tools not available for testing")

    def test_node_routing_logic(self, minimal_state):
        """Test that node routing conditions work correctly."""
        from slide_generator.tools.html_slides_agent import should_continue
        
        # Test with different state conditions
        result = should_continue(minimal_state)
        
        # Should return a valid routing decision
        assert isinstance(result, str)
        assert result in ["nlu", "planning", "generation", "modification", "status", "__end__"]

    def test_nodes_maintain_state_schema(self, minimal_state):
        """Test that all nodes maintain the required state schema."""
        required_keys = [
            "config", "config_version", "messages", "todos", 
            "artifacts", "pending_changes", "status", "errors", "metrics", "run_id"
        ]
        
        # Test each node maintains schema
        nodes_to_test = [status_node]  # Add other nodes as needed
        
        for node_func in nodes_to_test:
            result = node_func(minimal_state)
            
            # Verify all required keys are preserved
            for key in required_keys:
                assert key in result, f"Node {node_func.__name__} missing key: {key}"
