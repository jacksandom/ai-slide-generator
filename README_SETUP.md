# AI Slide Generator - Quick Setup Guide

## 🚀 One-Command Setup & Start

For first-time setup or to start the application:

```bash
./start.sh
```

This script will:
- ✅ Check system requirements (Python 3, Node.js, npm)
- ✅ Create Python virtual environment (if needed)
- ✅ Install all Python dependencies
- ✅ Install all Node.js dependencies  
- ✅ Start both backend and frontend servers

## 📋 System Requirements

Before running the script, ensure you have:

- **Python 3.7+** - [Download](https://www.python.org/downloads/)
- **Node.js 14+** - [Download](https://nodejs.org/)
- **npm** (comes with Node.js)

## 🎯 Access Points

After running `./start.sh`:

- **Frontend (React):** http://localhost:3000
- **Backend (FastAPI):** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

## 🛠 Manual Commands (Alternative)

If you prefer manual control:

### Backend only:
```bash
source .venv/bin/activate
npm run backend
```

### Frontend only:
```bash
npm run frontend
```

### Both servers:
```bash
source .venv/bin/activate
npm run dev
```

## 🔧 Troubleshooting

### Script Permission Error
```bash
chmod +x start.sh
./start.sh
```

### Port Already in Use
- Kill processes on ports 3000 or 8000
- Or modify ports in package.json scripts

### Python Virtual Environment Issues
```bash
rm -rf .venv
python3 -m venv .venv
./start.sh
```

### Node.js Dependencies Issues
```bash
rm -rf node_modules frontend/slide-generator-frontend/node_modules
./start.sh
```

## 📁 Project Structure

```
ai-slide-generator/
├── start.sh                    # 🚀 One-command startup script
├── backend/                    # FastAPI backend
│   ├── main.py                # API endpoints
│   └── requirements.txt       # Python dependencies
├── frontend/                   # React frontend
│   └── slide-generator-frontend/
│       ├── src/               # React components
│       └── package.json       # Frontend dependencies
├── src/slide_generator/        # Core logic (shared)
└── package.json               # Root scripts & dependencies
```

## 🎨 Features

- **Real-time Chat:** Messages appear as conversation progresses
- **Live Slide Updates:** Slides refresh automatically
- **AI-Powered:** Uses Databricks LLM and tools
- **Modern UI:** React with TypeScript
- **Fast Backend:** FastAPI with async processing

## 🔄 Development Workflow

1. **First time:** `./start.sh`
2. **Daily development:** `./start.sh` or `npm run dev`
3. **Backend changes:** Auto-reloads via uvicorn
4. **Frontend changes:** Auto-reloads via React dev server

Happy coding! 🎉
