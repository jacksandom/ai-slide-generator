"""Core business logic for slide generation."""

# Note: Chatbot is deprecated in favor of the new LangGraph agent
# from .chatbot import Chatbot

try:
    from .chatbot_langchain import ChatbotLangChain
    __all__ = ["ChatbotLangChain"]
except ImportError:
    # LangChain dependencies not available
    __all__ = []

