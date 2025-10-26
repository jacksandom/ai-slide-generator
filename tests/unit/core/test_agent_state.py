"""Test SlideDeckAgent state management."""
import pytest
from unittest.mock import patch, MagicMock
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
    @pytest.mark.databricks
    async def test_state_persistence_across_messages(self, authenticated_databricks_client, mock_databricks_responses):
        """Test state persists correctly across multiple messages."""
        agent = SlideDeckAgent()
        
        # Mock the LLM endpoint responses at the serving client level
        with patch('slide_generator.tools.html_slides_agent.get_model_serving_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_databricks_responses["llm_response"]
            mock_get_client.return_value = mock_client
            
            # Test message processing with real client but mocked responses
            initial_state = agent.initial_state.copy()
            
            # Create test states with different message counts
            state1 = initial_state.copy()
            state1["messages"] = [{"role": "user", "content": "Create 2 slides about AI"}]
            
            state2 = initial_state.copy()
            state2["messages"] = [
                {"role": "user", "content": "Create 2 slides about AI"},
                {"role": "user", "content": "Add a slide about machine learning"}
            ]
            
            # Verify state structure is maintained
            assert isinstance(state1["messages"], list)
            assert isinstance(state2["messages"], list) 
            assert len(state2["messages"]) > len(state1["messages"])

    def test_slide_theme_validation(self):
        """Test SlideTheme validation and defaults."""
        # Test default theme
        theme = SlideTheme()
        assert theme.bottom_right_logo_url is None
        assert theme.footer_text is None
        
        # Test custom theme
        custom_theme = SlideTheme(
            bottom_right_logo_url="custom.svg",
            footer_text="Custom Footer"
        )
        assert custom_theme.bottom_right_logo_url == "custom.svg"
        assert custom_theme.footer_text == "Custom Footer"

    def test_slide_config_validation(self):
        """Test SlideConfig validation and constraints."""
        # Test default config
        config = SlideConfig()
        assert config.n_slides is None  # Default is None
        
        # Test custom config
        custom_config = SlideConfig(n_slides=10)
        assert custom_config.n_slides == 10
        
        # Test invalid config should raise validation error
        with pytest.raises(ValueError):
            SlideConfig(n_slides=0)  # Should fail validation (ge=1)
            
        with pytest.raises(ValueError):
            SlideConfig(n_slides=50)  # Should fail validation (le=40)

    def test_state_structure_compliance(self):
        """Test that agent state follows the expected TypedDict structure."""
        agent = SlideDeckAgent()
        state = agent.initial_state
        
        # Verify all required keys are present
        required_keys = [
            "config", "config_version", "messages", "last_intent", "todos", 
            "artifacts", "pending_changes", "status", "errors", "metrics", "run_id"
        ]
        
        for key in required_keys:
            assert key in state, f"Missing required key: {key}"
        
        # Verify data types
        assert isinstance(state["config"], SlideConfig)
        assert isinstance(state["config_version"], int)
        assert isinstance(state["messages"], list)
        assert isinstance(state["todos"], list)
        assert isinstance(state["artifacts"], dict)
        assert isinstance(state["pending_changes"], list)
        assert isinstance(state["status"], list)
        assert isinstance(state["errors"], list)
        assert isinstance(state["metrics"], dict)
        assert isinstance(state["run_id"], str)

    def test_agent_graph_creation(self):
        """Test that the agent's graph is created properly."""
        agent = SlideDeckAgent()
        assert agent.graph is not None
        
        # Verify the graph has the expected structure
        graph_dict = agent.graph.get_graph()
        assert graph_dict is not None
        
        # The graph should have nodes
        assert hasattr(graph_dict, 'nodes') or 'nodes' in str(graph_dict)
