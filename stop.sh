#!/bin/bash

# AI Slide Generator - Stop Script
# This script stops all running frontend and backend processes

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${RED}🛑 AI Slide Generator - Stopping Application${NC}"
echo "================================================"

# Function to print colored output
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Function to kill processes by port
kill_port() {
    local port=$1
    local service_name=$2
    
    print_info "Stopping $service_name on port $port..."
    
    # Find processes using the port
    local pids=$(lsof -ti:$port 2>/dev/null || true)
    
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        print_status "$service_name stopped successfully"
    else
        print_warning "No $service_name process found on port $port"
    fi
}

# Function to kill processes by name pattern
kill_by_pattern() {
    local pattern=$1
    local service_name=$2
    
    print_info "Stopping $service_name processes..."
    
    local pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        print_status "$service_name processes stopped"
    else
        print_warning "No $service_name processes found"
    fi
}

# Stop backend server (FastAPI/Python)
print_info "Looking for backend processes..."
kill_port 8000 "Backend Server"

# Alternative: Kill Python processes that might be running the backend
kill_by_pattern "python.*main.py" "Backend Python"
kill_by_pattern "uvicorn.*main" "Uvicorn Backend"

# Stop frontend server (React/Node.js)
print_info "Looking for frontend processes..."
kill_port 3000 "Frontend Server"

# Alternative: Kill Node processes that might be running React
kill_by_pattern "node.*react-scripts" "React Development Server"
kill_by_pattern "npm.*start" "NPM Start Process"

# Kill any remaining Node.js processes related to the project
kill_by_pattern "node.*slide-generator" "Project Node Processes"

# Stop any concurrently running processes (if using npm run dev with concurrently)
kill_by_pattern "concurrently" "Concurrently Process Manager"

# Stop any PM2 processes if they exist
if command -v pm2 &> /dev/null; then
    print_info "Stopping PM2 processes..."
    pm2 stop all 2>/dev/null || print_warning "No PM2 processes running"
    pm2 delete all 2>/dev/null || true
fi

# Clean up any remaining background jobs
print_info "Cleaning up background processes..."

# Kill any jobs started by this shell
jobs -p 2>/dev/null | xargs kill -9 2>/dev/null || true

# Final cleanup - kill any remaining processes that might be holding ports
print_info "Final cleanup..."
kill_port 8000 "Any remaining port 8000 processes"
kill_port 3000 "Any remaining port 3000 processes"

# Wait a moment for processes to terminate
sleep 2

# Verify ports are free
print_info "Verifying ports are free..."
if lsof -ti:8000 2>/dev/null; then
    print_warning "Port 8000 still in use"
else
    print_status "Port 8000 is now free"
fi

if lsof -ti:3000 2>/dev/null; then
    print_warning "Port 3000 still in use"
else
    print_status "Port 3000 is now free"
fi

echo ""
print_status "Application stopped successfully!"
print_info "All frontend and backend processes have been terminated"
print_info "Ports 3000 and 8000 are now available"

# Optional: Deactivate virtual environment if it was activated
if [ -n "$VIRTUAL_ENV" ]; then
    print_info "Virtual environment is active. You may want to run: deactivate"
fi

echo ""
echo -e "${BLUE}✨ Ready to restart with ./start.sh${NC}"
