# React Frontend Implementation

This is a React.js version of the Gradio slide generator app, serviced by a FastAPI backend. It replicates the original Gradio functionality and design as closely as possible.

## Architecture

- **Frontend**: React + TypeScript with styled-components
- **Backend**: FastAPI with the same core slide generation functionality
- **Communication**: REST API calls between frontend and backend

## Features

### Replicated from Gradio App:
- ✅ Chat interface for natural language slide creation
- ✅ Real-time slide preview with HTML rendering
- ✅ EY-Parthenon branding and theming
- ✅ Tool integration (Databricks LLM, Genie, RAG, Visualization)
- ✅ Slide management (refresh, reset, export)
- ✅ Conversation history tracking
- ✅ Responsive design matching Gradio layout
- ✅ Error handling and loading states

### Enhancements:
- Modern React components with TypeScript
- Styled-components for consistent theming
- Better mobile responsiveness
- Improved accessibility features
- Concurrent development server setup

## Project Structure

```
ai-slide-generator/
├── backend/                    # FastAPI backend
│   ├── main.py                # Main FastAPI application
│   └── requirements.txt       # Python dependencies
├── frontend/                  # React frontend
│   └── slide-generator-frontend/
│       ├── src/
│       │   ├── components/    # React components
│       │   │   ├── ChatInterface.tsx
│       │   │   └── SlideViewer.tsx
│       │   ├── App.tsx        # Main App component
│       │   └── App.css        # Global styles
│       └── package.json       # Frontend dependencies
├── src/                       # Original slide generator modules
│   └── slide_generator/       # Core functionality (shared)
└── package.json              # Root package for dev scripts
```

## Setup and Installation

### Prerequisites
- Python 3.9+
- Node.js 16+
- npm or yarn
- Databricks workspace access

### Installation

1. **Install all dependencies:**
   ```bash
   npm run install-all
   ```

2. **Set up environment variables:**
   ```bash
   export DATABRICKS_HOST="your-databricks-host"
   export DATABRICKS_TOKEN="your-databricks-token"
   export LLM_ENDPOINT="databricks-claude-sonnet-4"
   ```

3. **Start both frontend and backend:**
   ```bash
   npm run dev
   ```

   This will start:
   - FastAPI backend on `http://localhost:8000`
   - React frontend on `http://localhost:3000`

### Manual Setup

If you prefer to run servers separately:

1. **Backend:**
   ```bash
   cd backend
   pip install -r requirements.txt
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

2. **Frontend:**
   ```bash
   cd frontend/slide-generator-frontend
   npm install
   npm start
   ```

## API Endpoints

The FastAPI backend provides the following endpoints:

- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /chat` - Handle chat messages
- `GET /slides/html` - Get current slides HTML
- `POST /slides/refresh` - Refresh slides
- `POST /slides/reset` - Reset slides to empty deck
- `POST /slides/export` - Export slides to file
- `GET /conversation/{session_id}` - Get conversation history (debugging)

## Usage

1. Open `http://localhost:3000` in your browser
2. Start chatting with the AI assistant in the left panel
3. Watch your slides generate in real-time in the right panel
4. Use the buttons to refresh, reset, or export your slides

### Example Prompts
- "Create a 3-slide deck about AI benefits"
- "Generate a succinct report on EY Parthenon"
- "Add a title slide with my name"
- "Create an agenda slide with 5 topics"

## Differences from Gradio Version

### Similarities:
- Identical core functionality
- Same LLM integration and tool usage
- Matching visual design and layout
- Same conversation flow and slide generation

### Improvements:
- Better TypeScript support and type safety
- Modern React hooks and state management
- Enhanced responsive design
- Improved error handling and user feedback
- Better accessibility features
- Concurrent development setup

## Development

### Available Scripts

- `npm run dev` - Start both frontend and backend
- `npm run frontend` - Start only React frontend
- `npm run backend` - Start only FastAPI backend
- `npm run build` - Build React app for production
- `npm run install-all` - Install all dependencies

### Adding New Features

1. **Backend changes**: Modify `backend/main.py` and core modules
2. **Frontend changes**: Add/modify React components in `frontend/slide-generator-frontend/src/`
3. **Styling**: Use styled-components for consistent theming

## Troubleshooting

### Common Issues

1. **CORS errors**: Ensure FastAPI CORS middleware allows `http://localhost:3000`
2. **Module import errors**: Check Python path in `backend/main.py`
3. **Databricks connection**: Verify environment variables are set correctly
4. **Port conflicts**: Change ports in package.json scripts if needed

### Debugging

- Backend logs: Check terminal running uvicorn
- Frontend logs: Check browser console
- API testing: Use `http://localhost:8000/docs` for Swagger UI
- Conversation debugging: Use `/conversation/default` endpoint

## Deployment

### Production Build

```bash
# Build frontend
npm run build

# Serve with your preferred web server
# Backend can be deployed with Docker/WSGI
```

### Docker Deployment

Create a `Dockerfile` for containerized deployment:

```dockerfile
# Multi-stage build for React + FastAPI
FROM node:16 AS frontend
WORKDIR /app/frontend
COPY frontend/slide-generator-frontend/ .
RUN npm install && npm run build

FROM python:3.9
WORKDIR /app
COPY backend/ ./backend/
COPY src/ ./src/
COPY --from=frontend /app/frontend/build ./static/
RUN pip install -r backend/requirements.txt
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Contributing

1. Create feature branch from `react-frontend`
2. Make changes to either frontend or backend
3. Test thoroughly with `npm run dev`
4. Submit pull request with detailed description

## License

Same as parent project - MIT License
