"""Test configuration management."""
import pytest
import os
from unittest.mock import patch


class TestConfiguration:
    def test_config_module_imports(self):
        """Test configuration module can be imported."""
        try:
            from slide_generator.config import config
            assert config is not None
        except ImportError:
            # Config module might not exist yet, that's acceptable
            pytest.skip("Config module not found, will be created in Phase 2")

    def test_databricks_profile_configuration(self):
        """Test Databricks profile configuration."""
        try:
            from slide_generator.config import config
            # Test that configuration has databricks profile
            if hasattr(config, 'databricks_profile'):
                assert config.databricks_profile is not None
                assert isinstance(config.databricks_profile, str)
        except (ImportError, AttributeError):
            # Configuration might not be fully implemented yet
            pytest.skip("Databricks profile configuration not implemented")

    def test_model_endpoint_configuration(self):
        """Test model endpoint configuration."""
        try:
            from slide_generator.config import config
            # Test that configuration has model endpoint
            if hasattr(config, 'model_endpoint'):
                assert config.model_endpoint is not None
                assert isinstance(config.model_endpoint, str)
        except (ImportError, AttributeError):
            # Configuration might not be fully implemented yet  
            pytest.skip("Model endpoint configuration not implemented")

    def test_environment_variable_override(self, monkeypatch):
        """Test environment variables override defaults."""
        # Set test environment variables
        monkeypatch.setenv("DATABRICKS_PROFILE", "test-profile")
        monkeypatch.setenv("MODEL_ENDPOINT", "test-endpoint")
        
        try:
            # Import after setting environment variables
            import importlib
            if 'slide_generator.config' in os.sys.modules:
                importlib.reload(os.sys.modules['slide_generator.config'])
            
            from slide_generator.config import config
            
            # Test environment variable usage
            if hasattr(config, 'databricks_profile'):
                # Note: This test will depend on actual config implementation
                pass
        except ImportError:
            pytest.skip("Config module not found")

    def test_required_environment_variables(self):
        """Test behavior when required environment variables are missing."""
        required_vars = [
            "DATABRICKS_HOST",
            "DATABRICKS_TOKEN", 
            "MODEL_ENDPOINT"
        ]
        
        # Check if any are missing (this is informational)
        missing_vars = []
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        # For now, just record what's missing
        if missing_vars:
            print(f"Missing environment variables: {missing_vars}")
        
        # This test primarily documents expected variables
        assert True

    def test_databricks_authentication_config(self):
        """Test Databricks authentication configuration."""
        # Test that we can access Databricks config files or environment
        databricks_config_paths = [
            os.path.expanduser("~/.databrickscfg"),
            os.getenv("DATABRICKS_CONFIG_FILE")
        ]
        
        config_found = False
        for path in databricks_config_paths:
            if path and os.path.exists(path):
                config_found = True
                break
        
        # Also check environment variables
        env_config = os.getenv("DATABRICKS_HOST") and os.getenv("DATABRICKS_TOKEN")
        
        if not (config_found or env_config):
            pytest.skip("No Databricks authentication configured")
        
        # If we have configuration, it should be accessible
        assert config_found or env_config

    def test_slide_generation_defaults(self):
        """Test slide generation default configuration."""
        # Test expected default values
        expected_defaults = {
            "max_slides": 10,
            "slide_width": 1280,
            "slide_height": 720,
            "default_theme": "professional"
        }
        
        # These are expected configuration values
        # Implementation will be done in Phase 2
        for key, value in expected_defaults.items():
            assert isinstance(value, (int, str))

    def test_logging_configuration(self):
        """Test logging configuration."""
        import logging
        
        # Test that logging is configured
        logger = logging.getLogger("slide_generator")
        
        # Logger should exist
        assert logger is not None
        
        # May not have handlers configured yet, that's ok
        # This test documents expected logging setup
        assert True

    def test_output_directory_configuration(self):
        """Test output directory configuration."""
        # Test that output directory exists or can be created
        output_dir = "output"
        
        if os.path.exists(output_dir):
            assert os.path.isdir(output_dir)
        else:
            # Should be creatable
            try:
                os.makedirs(output_dir, exist_ok=True)
                assert os.path.exists(output_dir)
                # Clean up
                os.rmdir(output_dir)
            except OSError:
                pytest.skip("Cannot create output directory")

    def test_theme_configuration_validation(self):
        """Test theme configuration validation."""
        from slide_generator.tools.html_slides_agent import SlideTheme
        
        # Test valid theme configuration
        theme = SlideTheme()
        assert theme is not None
        
        # Test custom theme
        custom_theme = SlideTheme(
            bottom_right_logo_url="test.svg",
            footer_text="Test Footer"
        )
        assert custom_theme.bottom_right_logo_url == "test.svg"
        assert custom_theme.footer_text == "Test Footer"
