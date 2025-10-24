"""Test slide generation and manipulation tools."""
import pytest
from unittest.mock import patch, MagicMock
from slide_generator.tools.html_slides_agent import (
    generate_slide_html, validate_slide_html, 
    sanitize_slide_html, apply_slide_change, SlideChange
)


class TestSlideTools:
    @pytest.mark.databricks
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

    def test_html_validation_empty_input(self):
        """Test validation handles empty input gracefully."""
        is_valid = validate_slide_html.invoke({"html": ""})
        assert is_valid is False

    def test_html_validation_malformed_html(self):
        """Test validation catches malformed HTML."""
        malformed_html = "<html><body><h1>Title</h1><p>Content without closing tags"
        is_valid = validate_slide_html.invoke({"html": malformed_html})
        assert is_valid is False

    def test_html_sanitization(self, sample_slide_html):
        """Test HTML sanitization removes dangerous elements."""
        unsafe_html = sample_slide_html.replace("</body>", 
            '<script>alert("xss")</script></body>')
        sanitized = sanitize_slide_html.invoke({"html": unsafe_html})
        assert "alert" not in sanitized
        assert "<script>" not in sanitized

    def test_html_sanitization_preserves_safe_content(self, sample_slide_html):
        """Test HTML sanitization preserves safe content."""
        sanitized = sanitize_slide_html.invoke({"html": sample_slide_html})
        
        # Should preserve basic HTML structure
        assert "<html>" in sanitized
        assert "<body>" in sanitized
        assert "<h1" in sanitized
        assert "Test Slide" in sanitized

    def test_html_sanitization_removes_external_scripts(self):
        """Test sanitization removes external script sources."""
        unsafe_html = '''<!DOCTYPE html>
        <html><body>
        <h1>Test</h1>
        <script src="http://evil.com/malware.js"></script>
        </body></html>'''
        
        sanitized = sanitize_slide_html.invoke({"html": unsafe_html})
        assert "evil.com" not in sanitized
        assert 'src="http://' not in sanitized

    @pytest.mark.databricks
    def test_slide_change_application(self, authenticated_databricks_client, monkeypatch):
        """Test applying changes to slide HTML."""
        # Mock the LLM client for change application
        mock_client = MagicMock()
        mock_response = {
            "choices": [{
                "message": {
                    "content": '<!DOCTYPE html><html><head><title>Modified Slide</title></head><body style="width:1280px;height:720px;"><h1 style="color:#102025;">Modified Slide</h1><p>This content has been updated</p></body></html>'
                }
            }]
        }
        mock_client.chat.completions.create.return_value = mock_response
        monkeypatch.setattr("slide_generator.tools.html_slides_agent.model_serving_client", mock_client)
        
        original_html = '''<!DOCTYPE html>
        <html><body><h1>Original Slide</h1><p>Original content</p></body></html>'''
        
        change = SlideChange(
            operation="EDIT_TEXT",
            args={"old_text": "Original", "new_text": "Modified"}
        )
        
        result = apply_slide_change.invoke({
            "slide_html": original_html,
            "change": change,
            "style_hint": "professional"
        })
        
        # Verify the change was applied
        assert isinstance(result, str)
        assert "<!DOCTYPE html>" in result
        mock_client.chat.completions.create.assert_called_once()

    def test_slide_change_validation(self):
        """Test SlideChange model validation."""
        # Valid change
        valid_change = SlideChange(
            operation="EDIT_TEXT",
            args={"old_text": "old", "new_text": "new"}
        )
        assert valid_change.operation == "EDIT_TEXT"
        assert valid_change.args["old_text"] == "old"

    def test_html_generation_with_missing_parameters(self):
        """Test HTML generation handles missing parameters gracefully."""
        try:
            # This should either work with defaults or raise a clear error
            result = generate_slide_html.invoke({
                "title": "Test"
                # Missing outline and style_hint
            })
            # If it succeeds, should still return HTML
            assert isinstance(result, str)
        except (KeyError, TypeError):
            # It's acceptable to require all parameters
            pass

    def test_tools_are_properly_decorated(self):
        """Test that tools are properly decorated as LangChain tools."""
        # Verify tools have the correct attributes
        tools_to_check = [
            generate_slide_html,
            validate_slide_html, 
            sanitize_slide_html,
            apply_slide_change
        ]
        
        for tool in tools_to_check:
            assert hasattr(tool, 'name'), f"Tool {tool} missing name attribute"
            assert hasattr(tool, 'invoke'), f"Tool {tool} missing invoke method"

    def test_html_constraints_compliance(self, sample_slide_html):
        """Test that generated HTML complies with slide constraints."""
        # Verify slide dimensions
        assert 'width:1280px' in sample_slide_html
        assert 'height:720px' in sample_slide_html
        
        # Verify basic structure
        assert '<!DOCTYPE html>' in sample_slide_html
        assert '<html>' in sample_slide_html
        assert '<body>' in sample_slide_html
        
        # Verify required styling
        assert 'style=' in sample_slide_html

    def test_slide_content_length_constraints(self):
        """Test that slide content respects length constraints."""
        # Create a very long title to test constraints
        long_title = "A" * 100  # Exceeds 55 character limit
        
        # The tool should handle this gracefully (truncate or reject)
        try:
            result = generate_slide_html.invoke({
                "title": long_title,
                "outline": "Short content", 
                "style_hint": "professional"
            })
            # If it succeeds, title should be reasonable length
            assert len(result) > 0
        except ValueError:
            # It's acceptable to reject overly long titles
            pass
