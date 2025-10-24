# AI Slide Generator

**🎨 AI-powered slide deck generation with natural language and secure data integration**

A modern React + FastAPI application that creates professional slide presentations using AI, with deep integration to Databricks Unity Catalog for secure data access and enterprise-grade governance.

## 🚀 Quick Start

**One-command setup and launch:**

```bash
./start.sh
```

This will automatically:
- ✅ Check system requirements (Python 3.7+, Node.js 14+)
- ✅ Create Python virtual environment
- ✅ Install all dependencies (Python + Node.js)
- ✅ Start both backend and frontend servers

**Access the application:**
- **Frontend (React):** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Documentation:** http://localhost:8000/docs

## 📋 System Requirements

- **Python 3.7+** - [Download](https://www.python.org/downloads/)
- **Node.js 14+** - [Download](https://nodejs.org/)
- **npm** (included with Node.js)
- **Databricks workspace** (for AI/LLM functionality)

## 🏗️ Architecture

### Modern Tech Stack
- **Frontend**: React 18 + TypeScript + Styled Components
- **Backend**: FastAPI + Python 3.9+ with async processing  
- **AI Engine**: LangGraph-based agent with Databricks LLM integration
- **Data Layer**: Unity Catalog for secure data access and governance
- **Communication**: REST API with real-time updates

### System Design
```
┌─────────────────────┐    ┌──────────────────────┐    ┌────────────────────┐
│   React Frontend    │    │   FastAPI Backend    │    │  Databricks Unity  │
│   (Port 3000)       │◄──►│   (Port 8000)        │◄──►│    Catalog         │
│                     │    │                      │    │                    │
│ • Chat Interface    │    │ • LangGraph Agent    │    │ • Secure Data      │
│ • Slide Viewer      │    │ • Slide Generation   │    │ • RAG System       │
│ • Export Controls   │    │ • API Endpoints      │    │ • SQL Tools        │
└─────────────────────┘    └──────────────────────┘    └────────────────────┘
```

## ✨ Key Features

### 🤖 AI-Powered Slide Creation
- **Natural language input**: "Create a 5-slide deck about Q3 sales performance"
- **Intelligent content generation** using advanced LLM models
- **Context-aware slide structuring** with professional layouts
- **Automatic data integration** from your data warehouse

### 🔒 Enterprise Security & Governance  
- **Unity Catalog integration**: Secure access to sensitive client data
- **Role-based access controls** for consultants and teams
- **Complete audit trail** of all data access and slide generation
- **Chain of trust** for all generated content and data lineage

### 🎨 Professional Output
- **Modern, clean design**: Tailwind CSS with professional layouts
- **Brand consistency**: Customizable themes and company branding
- **Multiple export formats**: HTML, PPTX, PDF (coming soon)
- **Responsive slides**: Optimized for presentations and sharing

### 🔧 Advanced Tooling
- **RAG System**: Query internal knowledge bases and documents
- **SQL Generation**: Natural language to SQL for data analysis
- **Data Visualization**: Automatic chart generation with Chart.js
- **Web Search**: Real-time information integration when appropriate

## 🎯 Use Cases

### For Consulting Firms
- **Client Presentations**: Generate tailored decks with secure client data
- **Proposal Creation**: Quickly assemble compelling business proposals  
- **Data Storytelling**: Transform raw data into executive-ready insights
- **Knowledge Sharing**: Leverage firm-wide expertise and templates

### For Business Teams
- **Executive Reporting**: Automated dashboards and status updates
- **Strategic Planning**: Data-driven planning and analysis presentations
- **Training Materials**: Educational content with real examples
- **Compliance Reporting**: Auditable, governed presentation workflows

## 🚦 Development Workflow

### Daily Development
```bash
# Start both servers (recommended)
npm run dev

# Or start individually:
npm run backend    # FastAPI server only
npm run frontend   # React dev server only
```

### Project Structure
```
ai-slide-generator/
├── start.sh                    # 🚀 One-command startup
├── backend/                    # FastAPI backend
│   ├── main.py                # Main API application
│   └── requirements.txt       # Python dependencies
├── frontend/                   # React frontend  
│   └── slide-generator-frontend/
│       ├── src/
│       │   ├── components/    # React components
│       │   │   ├── ChatInterface.tsx
│       │   │   └── SlideViewer.tsx
│       │   ├── App.tsx        # Main application
│       │   └── App.css        # Global styles
│       └── package.json       # Frontend dependencies
├── src/slide_generator/        # Core Python modules
│   ├── tools/                 # Slide generation tools
│   │   ├── html_slides_agent.py  # LangGraph agent (main)
│   │   ├── html_to_pptx.py    # PPTX export functionality
│   │   └── uc_tools.py        # Unity Catalog integration
│   ├── config.py              # Configuration management
│   └── utils/                 # Utility functions
└── package.json               # Root scripts and dependencies
```

## 🔧 Configuration

### Environment Variables
Create a `.env` file with:

```bash
# Databricks Configuration
DATABRICKS_HOST=your-workspace-url
DATABRICKS_TOKEN=your-access-token
DATABRICKS_PROFILE=default

# LLM Configuration  
LLM_ENDPOINT=databricks-claude-sonnet-4

# Application Settings
DEBUG=false
LOG_LEVEL=INFO
```

### Databricks Setup
1. **Create workspace** on Databricks platform
2. **Generate access token** in User Settings → Access Tokens
3. **Configure Unity Catalog** for data governance
4. **Deploy LLM endpoint** (or use existing foundation models)

## 📖 API Reference

### Core Endpoints

#### Chat Interface
```http
POST /chat
Content-Type: application/json

{
  "message": "Create a slide about customer satisfaction trends",
  "session_id": "user-session-123"
}
```

#### Slide Management
```http
GET /slides/html           # Get current slides as HTML
POST /slides/refresh       # Refresh slide display  
POST /slides/reset         # Reset to empty deck
GET /slides/export/pptx    # Export as PowerPoint
```

#### System Health
```http
GET /health               # Health check
GET /                     # System info
```

For complete API documentation, visit http://localhost:8000/docs when running.

## 🧪 Testing

### Run Tests
```bash
# Backend tests
cd backend
python -m pytest

# Frontend tests  
cd frontend/slide-generator-frontend
npm test

# Integration tests
npm run test:integration
```

### Manual Testing Checklist
- [ ] Frontend loads at localhost:3000
- [ ] Backend responds at localhost:8000  
- [ ] Chat interface accepts messages
- [ ] Slide generation produces HTML output
- [ ] Export to PPTX works
- [ ] All API endpoints respond correctly

## 🔄 Troubleshooting

### Common Issues

#### Port Already in Use
```bash
# Kill processes on ports 3000 or 8000
lsof -ti:3000 | xargs kill -9
lsof -ti:8000 | xargs kill -9
```

#### Virtual Environment Issues
```bash
rm -rf .venv
python3 -m venv .venv
./start.sh
```

#### Node Dependencies Issues
```bash
rm -rf node_modules frontend/slide-generator-frontend/node_modules
npm install
cd frontend/slide-generator-frontend && npm install
```

#### Permission Denied on start.sh
```bash
chmod +x start.sh
./start.sh
```

### Debug Mode
Enable detailed logging:
```bash
export DEBUG=true
export LOG_LEVEL=DEBUG
./start.sh
```

## 🚀 Deployment

### Production Build
```bash
# Build frontend for production
cd frontend/slide-generator-frontend
npm run build

# Backend production server
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker backend.main:app
```

### Docker Deployment
```bash
# Build images
docker build -t slide-generator-backend ./backend
docker build -t slide-generator-frontend ./frontend

# Run with docker-compose
docker-compose up -d
```

### Environment Configuration
- **Development**: Uses local endpoints and debug mode
- **Staging**: Points to staging Databricks workspace
- **Production**: Full security, monitoring, and scale configuration

## 🤝 Contributing

### Development Setup
1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Make changes and test thoroughly
4. Commit with clear messages: `git commit -m 'Add amazing feature'`
5. Push to branch: `git push origin feature/amazing-feature`
6. Open Pull Request

### Code Standards
- **Python**: Follow PEP 8, use type hints, add docstrings
- **TypeScript**: Use strict mode, follow React best practices
- **Testing**: Add tests for new features, maintain coverage
- **Documentation**: Update README for significant changes

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

### Getting Help
- **Documentation**: Check this README and API docs
- **Issues**: Report bugs via GitHub Issues
- **Discussions**: Use GitHub Discussions for questions
- **Email**: Contact the development team

### Known Limitations
- **Data Sources**: Currently supports Databricks Unity Catalog primarily
- **Export Formats**: PPTX export in beta, PDF export coming soon
- **Concurrent Users**: Designed for team usage, not high-scale deployment
- **AI Models**: Requires Databricks workspace for full AI functionality

---

**Built with ❤️ for modern slide generation workflows**

*Transform your data into compelling presentations with the power of AI and enterprise-grade security.*
