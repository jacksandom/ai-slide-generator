#!/bin/bash

# AI Slide Generator - Start Script
# This script handles dependency installation and starts both frontend and backend servers

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 AI Slide Generator - Starting Application${NC}"
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

# Check if we're in the right directory
if [ ! -f "package.json" ] || [ ! -d "src" ]; then
    print_error "Please run this script from the project root directory"
    exit 1
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not installed"
    exit 1
fi

# Check if Node.js is available
if ! command -v node &> /dev/null; then
    print_error "Node.js is required but not installed"
    print_info "Please install Node.js from https://nodejs.org/"
    exit 1
fi

# Check if npm is available
if ! command -v npm &> /dev/null; then
    print_error "npm is required but not installed"
    exit 1
fi

print_info "Checking Python version: $(python3 --version)"
print_info "Checking Node.js version: $(node --version)"
print_info "Checking npm version: $(npm --version)"

# Setup Python virtual environment
print_info "Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    print_status "Creating virtual environment"
    python3 -m venv .venv
else
    print_status "Virtual environment already exists"
fi

# Activate virtual environment
print_status "Activating virtual environment"
source .venv/bin/activate

# Install Python dependencies
print_info "Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    print_status "Installing main Python requirements"
    pip install -r requirements.txt
fi

if [ -f "backend/requirements.txt" ]; then
    print_status "Installing backend Python requirements"
    pip install -r backend/requirements.txt
fi

# Install Node.js dependencies
print_info "Installing Node.js dependencies..."

# Root package.json dependencies
if [ -f "package.json" ]; then
    print_status "Installing root Node.js dependencies"
    npm install
fi

# Frontend dependencies
if [ -f "frontend/slide-generator-frontend/package.json" ]; then
    print_status "Installing frontend dependencies"
    cd frontend/slide-generator-frontend
    npm install
    cd ../..
else
    print_warning "Frontend package.json not found - skipping frontend dependencies"
fi

print_status "All dependencies installed successfully!"

# Start the application
echo ""
echo -e "${BLUE}🎯 Starting Application Servers${NC}"
echo "=================================="

print_info "Backend will start on: http://localhost:8000"
print_info "Frontend will start on: http://localhost:3000"
print_info "Press Ctrl+C to stop both servers"

echo ""
print_status "Starting both servers..."

# Start the development servers
npm run dev
