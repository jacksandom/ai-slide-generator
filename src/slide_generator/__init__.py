"""
Slide Generator - AI-powered slide deck creation tool.

This package provides tools for creating professional slide decks using natural language
and AI assistance, with support for HTML and PowerPoint output formats.
"""

__version__ = "0.1.0"
__author__ = "Your Name"

# Main exports
from .tools.html_slides_agent import SlideDeckAgent, SlideTheme

__all__ = [
    "SlideDeckAgent", 
    "SlideTheme",
    "__version__",
]

