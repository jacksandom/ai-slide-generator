"""Core business logic for slide generation."""

# Note: Legacy chatbot.py removed - replaced by LangGraph agent (html_slides_agent.py)

try:
    from .chatbot_langchain import ChatbotLangChain
    __all__ = ["ChatbotLangChain"]
except ImportError:
    # LangChain dependencies not available
    __all__ = []

