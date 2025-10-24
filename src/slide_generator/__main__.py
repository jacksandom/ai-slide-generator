"""
Entry point for the slide generator package.

DEPRECATED: The Gradio frontend has been removed in favor of the React frontend.
To start the application, use:
    npm run dev
"""

import sys


def main():
    """Deprecated main entry point - redirect users to new startup method."""
    print("🚨 DEPRECATED: The Gradio frontend has been removed.")
    print("📋 The slide generator now uses a React frontend + FastAPI backend.")
    print("")
    print("🚀 To start the application, run:")
    print("   npm run dev")
    print("")
    print("This will start both the backend (port 8000) and frontend (port 3000)")
    print("Then navigate to: http://localhost:3000")
    
    return 1


if __name__ == "__main__":
    sys.exit(main())

