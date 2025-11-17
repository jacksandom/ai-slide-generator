# Databricks App Deployment Plan

## Overview

This plan outlines the modernized approach to deploying the AI Slide Generator as a Databricks App, incorporating current best practices from Microsoft Azure Databricks documentation and reference implementations.

**Key Goals:**
1. Automated deployment from local to remote workspace
2. Environment-based configuration with app.yaml
3. Foundation for user authorization and multi-session support
4. Production-ready logging and monitoring
5. Simplified build and deployment workflow

## Architecture Changes

### Current State (Local Development)
- **Backend**: FastAPI with uvicorn (port 8000)
- **Frontend**: React + Vite dev server (port 3000)
- **CORS**: Enabled for cross-origin requests
- **Session**: Single global session
- **Auth**: None

### Target State (Databricks App)
- **Backend**: FastAPI serving both API and static frontend (port 8080)
- **Frontend**: Built static assets served by FastAPI
- **CORS**: Disabled (same-origin)
- **Session**: Single session with user context extraction (multi-session in Phase 4)
- **Auth**: Databricks-provided headers (X-Forwarded-User, etc.)
- **Logging**: Structured JSON to stdout/stderr
- **Deployment**: Automated via Databricks SDK

---

## Component 1: Automated Deployment Infrastructure

### 1.1 Deployment Script (`databricks-app/deploy.py`)

**Purpose**: Automate the build, package, and deployment process to Databricks workspace.

**Key Features:**
- Build frontend to static assets
- Package backend and frontend into deployment directory
- Upload to Databricks workspace
- Create or update Databricks App
- Set appropriate permissions
- Verify deployment health

**Reference**: Based on `initialsetup.py` pattern from sql-migration-assistant

**Functions Required:**
1. `setup_deployment_directory()`: Create clean deployment structure
2. `build_frontend()`: Build React app to production bundle
3. `package_backend()`: Copy Python source and dependencies
4. `upload_to_workspace()`: Upload files to Databricks workspace file system
5. `setup_app()`: Create or update Databricks App
6. `setup_permissions()`: Configure user/group access
7. `verify_deployment()`: Health check on deployed app

**Configuration:**
- Read from `.env` for Databricks credentials
- Read from `config/config.yaml` for app settings
- Support for dev/staging/prod environments

### 1.2 Deployment Configuration (`databricks-app/config.py`)

**Purpose**: Centralized configuration for deployment process.

**Settings:**
```python
class DeploymentConfig:
    # Workspace settings
    workspace_host: str
    workspace_path: str  # e.g., /Users/{email}/apps/ai-slide-generator
    
    # App settings
    app_name: str
    display_name: str
    compute_size: str  # SMALL, MEDIUM, LARGE
    
    # Permissions
    default_permissions: List[Permission]
    
    # Build settings
    frontend_dist_path: Path
    backend_src_path: Path
    deployment_root: Path
```

### 1.3 Workspace Client Wrapper (`databricks-app/client.py`)

**Purpose**: Simplified wrapper around Databricks SDK for deployment operations.

**Methods:**
- `upload_directory(local_path, workspace_path)`
- `create_or_update_app(app_config)`
- `set_permissions(app_name, permissions)`
- `get_app_status(app_name)`
- `get_app_logs(app_name)`
- `delete_app(app_name)` (for cleanup/rollback)

---

## Component 2: App Configuration (`app.yaml`)

### 2.1 App Manifest

**Location**: `app.yaml` (root directory)

**Purpose**: Defines how Databricks Apps should run the application.

**Content:**
```yaml
# Databricks App Configuration
# See: https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/

name: ai-slide-generator
display_name: "AI Slide Generator"
description: "Generate and edit HTML slide decks using AI with Databricks Genie integration"

# Startup command - runs from app root directory
# Databricks Apps expects the app to listen on 0.0.0.0:8080
command: 
  - "uvicorn"
  - "src.api.main:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "8080"
  - "--log-level"
  - "info"

# Environment variables available at runtime
env:
  # Application environment
  - name: ENVIRONMENT
    value: production
  
  # Logging configuration
  - name: LOG_LEVEL
    value: INFO
  - name: LOG_FORMAT
    value: json
  
  # MLflow configuration
  - name: MLFLOW_TRACKING_URI
    value: databricks
  
  # Databricks Apps system environment variables are automatically available:
  # - DATABRICKS_HOST
  # - DATABRICKS_TOKEN
  # See: https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/system-env

# Compute resources
# Options: SMALL, MEDIUM, LARGE
# See: https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/resources
compute:
  size: SMALL
  # For future scaling:
  # min_replicas: 1
  # max_replicas: 3

# Default permissions (can be overridden during deployment)
permissions:
  - level: CAN_USE
    group_name: users
  # Add specific users/groups as needed:
  # - level: CAN_MANAGE
  #   user_name: admin@company.com

# Health check endpoint (optional but recommended)
health_check:
  endpoint: /api/health
  interval_seconds: 60
  timeout_seconds: 10
```

### 2.2 Environment-Specific Variants

**Development**: `app.dev.yaml`
```yaml
name: ai-slide-generator-dev
env:
  - name: ENVIRONMENT
    value: development
  - name: LOG_LEVEL
    value: DEBUG
compute:
  size: SMALL
```

**Production**: `app.prod.yaml`
```yaml
name: ai-slide-generator
env:
  - name: ENVIRONMENT
    value: production
  - name: LOG_LEVEL
    value: INFO
compute:
  size: MEDIUM
```

---

## Component 3: Python Dependencies (`requirements.txt`)

### 3.1 Update Requirements File

**Current**: Already has most dependencies

**Required Updates:**
```txt
# Core dependencies (already present)
databricks-sdk>=0.20.0
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6
pydantic>=2.4.0
pydantic-settings>=2.0.0
httpx>=0.25.0
jinja2>=3.1.0
python-dotenv>=1.0.0
pyyaml>=6.0.0
mlflow>=3.0.0
pandas>=2.0.0
databricks-langchain>=0.1.0
langchain>=0.3.0
langchain-core>=0.3.0
langchain-community>=0.3.0

# HTML parsing (already present)
beautifulsoup4>=4.12.0
lxml>=4.9.0

# Production server optimization
gunicorn>=21.0.0  # Optional: for production WSGI

# Structured logging
python-json-logger>=2.0.0

# Static file serving (FastAPI already includes this via Starlette)
# No additional packages needed
```

### 3.2 Lock File

**Action**: Generate lock file for reproducible builds
```bash
pip freeze > requirements.lock
```

**Use in deployment**: Install from lock file for consistency
```bash
pip install -r requirements.lock
```

---

## Component 4: User Authorization Foundation

### 4.1 Middleware for User Context (`src/api/middleware/auth.py`)

**Purpose**: Extract user information from Databricks-provided headers and attach to request state.

**Key Headers** (provided by Databricks Apps):
- `X-Forwarded-User`: User ID (email)
- `X-Forwarded-Email`: User email
- `X-Forwarded-Preferred-Username`: Display name
- `X-Real-Ip`: Client IP address
- `X-Request-Id`: Unique request identifier

**Reference**: https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/system-env

**Implementation:**
```python
class UserContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract user info from headers (production)
        user_id = request.headers.get("x-forwarded-user")
        email = request.headers.get("x-forwarded-email")
        username = request.headers.get("x-forwarded-preferred-username")
        
        # Fallback for local development
        if not user_id and os.getenv("ENVIRONMENT") == "development":
            user_id = os.getenv("DEV_USER_ID", "dev@local.test")
            email = os.getenv("DEV_USER_EMAIL", "dev@local.test")
            username = os.getenv("DEV_USERNAME", "Dev User")
        
        # Attach to request state
        request.state.user = UserContext(
            user_id=user_id,
            email=email,
            username=username,
        )
        
        response = await call_next(request)
        return response
```

### 4.2 User Context Model (`src/api/models/auth.py`)

```python
class UserContext(BaseModel):
    """User context extracted from headers."""
    user_id: str
    email: str
    username: str
    
    @property
    def session_key(self) -> str:
        """Generate session key for user (Phase 4)."""
        return f"session:{self.user_id}"
```

### 4.3 Session Manager Foundation (`src/api/services/session_manager.py`)

**Phase 3**: Single session with user context logging
**Phase 4**: Multi-session support with per-user isolation

```python
class SessionManager:
    """Manage user sessions (foundation for Phase 4)."""
    
    def __init__(self):
        # Phase 3: Single global session
        self._global_session = None
        
        # Phase 4: Will become:
        # self._sessions: Dict[str, Session] = {}
        # self._session_lock = asyncio.Lock()
    
    async def get_session(self, user_context: UserContext) -> Session:
        """Get session for user."""
        # Phase 3: Return global session (log user context)
        logger.info(f"Session accessed by user: {user_context.user_id}")
        return self._global_session
        
        # Phase 4: Will become per-user session lookup
    
    async def create_session(self, user_context: UserContext) -> Session:
        """Create new session for user (Phase 4)."""
        pass
    
    async def cleanup_sessions(self):
        """Clean up expired sessions (Phase 4)."""
        pass
```

### 4.4 Dependency Injection

**Update routes to use user context:**
```python
from fastapi import Depends, Request

def get_user_context(request: Request) -> UserContext:
    """Extract user context from request state."""
    return request.state.user

@router.post("/api/chat")
async def chat(
    request: ChatRequest,
    user_context: UserContext = Depends(get_user_context),
):
    """Chat endpoint with user context."""
    logger.info(f"Chat request from {user_context.user_id}")
    # Use user_context for logging, future session lookup
    ...
```

---

## Component 5: Environment Configuration

### 5.1 Settings Update (`src/config/settings.py`)

**Add environment-aware settings:**

```python
class Settings(BaseSettings):
    # Environment
    environment: Literal["development", "production"] = "development"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    
    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    
    # Frontend (production only)
    serve_frontend: bool = False
    frontend_dist_path: Path = Path("frontend/dist")
    
    # Databricks
    databricks_host: str
    databricks_token: str
    
    # MLflow
    mlflow_tracking_uri: str = "databricks"
    
    # Session (Phase 4)
    # session_timeout_minutes: int = 60
    # max_sessions_per_user: int = 5
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @property
    def is_production(self) -> bool:
        return self.environment == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment == "development"
```

### 5.2 Frontend Serving (`src/api/main.py` updates)

**Add static file serving for production:**

```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

settings = get_settings()

# Serve static files in production
if settings.is_production and settings.serve_frontend:
    frontend_path = settings.frontend_dist_path
    
    if frontend_path.exists():
        # Serve static assets (JS, CSS, images)
        app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")
        
        # Serve index.html for all non-API routes (SPA routing)
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # API routes handled by routers
            if full_path.startswith("api/"):
                return {"error": "Not found"}, 404
            
            # Serve index.html for all other routes
            return FileResponse(str(frontend_path / "index.html"))
```

---

## Component 6: Structured Logging

### 6.1 JSON Logger (`src/utils/logging_config.py`)

**Purpose**: Structured logging for Databricks Apps log aggregation.

**Reference**: https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/best-practices

```python
import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        
        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)

def setup_logging(log_level: str = "INFO", log_format: str = "json"):
    """Configure logging for the application."""
    
    # Create handlers
    stdout_handler = logging.StreamHandler(sys.stdout)
    stderr_handler = logging.StreamHandler(sys.stderr)
    
    # INFO and DEBUG to stdout, WARNING+ to stderr
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)
    stderr_handler.setLevel(logging.WARNING)
    
    # Apply formatter
    if log_format == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    stdout_handler.setFormatter(formatter)
    stderr_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)
```

### 6.2 Request Logging Middleware (`src/api/middleware/logging.py`)

```python
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all HTTP requests with timing."""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Extract user context if available
        user_id = getattr(request.state, "user", {}).get("user_id", "unknown")
        request_id = request.headers.get("x-request-id", "unknown")
        
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "user_id": user_id,
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            }
        )
        
        try:
            response = await call_next(request)
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                f"Request completed: {request.method} {request.url.path} {response.status_code}",
                extra={
                    "user_id": user_id,
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            )
            
            return response
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Request failed: {request.method} {request.url.path}",
                extra={
                    "user_id": user_id,
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                },
                exc_info=True
            )
            raise
```

---

## Component 7: Frontend Build Configuration

### 7.1 Vite Production Build (`frontend/vite.config.ts`)

**Update for production:**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  
  // Build configuration
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,  // Disable for production
    
    // Optimize bundle
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom'],
          'editor': ['@monaco-editor/react', 'monaco-editor'],
          'dnd': ['@dnd-kit/core', '@dnd-kit/sortable', '@dnd-kit/utilities'],
        },
      },
    },
  },
  
  // Development server
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

### 7.2 Environment Variables

**`frontend/.env.production`:**
```
# Production: API on same origin
VITE_API_URL=
```

**`frontend/.env.development`:**
```
# Development: API on different port
VITE_API_URL=http://localhost:8000
```

### 7.3 API Client Update (`frontend/src/services/api.ts`)

```typescript
// Use same origin in production, different origin in development
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const api = {
  // ... existing methods
}
```

---

## Component 8: Deployment Workflow

### 8.1 Build Script (`databricks-app/build.sh`)

```bash
#!/bin/bash
set -e

echo "Building AI Slide Generator for Databricks Apps..."

# Configuration
DEPLOY_DIR="deploy"
APP_NAME="ai-slide-generator"

# Clean previous build
echo "Cleaning previous build..."
rm -rf $DEPLOY_DIR
mkdir -p $DEPLOY_DIR

# Build frontend
echo "Building frontend..."
cd frontend
npm ci --production
npm run build
cd ..

# Copy files to deploy directory
echo "Packaging application..."

# Backend
cp -r src/ $DEPLOY_DIR/src/
cp -r config/ $DEPLOY_DIR/config/

# Requirements
cp requirements.txt $DEPLOY_DIR/
cp requirements.lock $DEPLOY_DIR/ 2>/dev/null || true

# Configuration
cp app.yaml $DEPLOY_DIR/

# Frontend (built assets)
mkdir -p $DEPLOY_DIR/frontend/dist
cp -r frontend/dist/ $DEPLOY_DIR/frontend/

# Create deployment metadata
cat > $DEPLOY_DIR/DEPLOYMENT_INFO.txt << EOF
Deployment Package: AI Slide Generator
Build Date: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Git Commit: $(git rev-parse HEAD 2>/dev/null || echo "N/A")
Git Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "N/A")
EOF

echo "✓ Build complete: $DEPLOY_DIR/"
```

### 8.2 Deployment Script (`databricks-app/deploy.py`)

**Full implementation** (simplified here):

```python
#!/usr/bin/env python3
"""
Deploy AI Slide Generator to Databricks Apps.

Usage:
    python databricks-app/deploy.py --env production
    python databricks-app/deploy.py --env development --clean
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.apps import App, AppPermission, PermissionLevel

logger = logging.getLogger(__name__)

class AppDeployer:
    """Deploy AI Slide Generator to Databricks Apps."""
    
    def __init__(self, environment: str = "production"):
        self.environment = environment
        self.workspace_client = WorkspaceClient()
        self.config = self._load_config()
    
    def deploy(self, clean: bool = False):
        """Execute deployment workflow."""
        logger.info(f"Starting deployment for environment: {self.environment}")
        
        # 1. Build application
        self.build()
        
        # 2. Setup deployment directory in workspace
        workspace_path = self.setup_deployment_directory(clean=clean)
        
        # 3. Upload files
        self.upload_to_workspace(workspace_path)
        
        # 4. Create or update app
        app = self.setup_app()
        
        # 5. Setup permissions
        self.setup_permissions(app.name)
        
        # 6. Verify deployment
        self.verify_deployment(app.name)
        
        logger.info(f"✓ Deployment complete: {app.url}")
        return app
    
    def build(self):
        """Run build script."""
        logger.info("Building application...")
        subprocess.run(["bash", "databricks-app/build.sh"], check=True)
    
    def setup_deployment_directory(self, clean: bool = False) -> str:
        """Create deployment directory in workspace."""
        workspace_path = f"/Workspace/Users/{self.config['user_email']}/apps/ai-slide-generator"
        
        if clean:
            logger.info(f"Cleaning workspace path: {workspace_path}")
            # Delete existing directory
            try:
                self.workspace_client.workspace.delete(workspace_path, recursive=True)
            except Exception:
                pass
        
        # Create directory
        self.workspace_client.workspace.mkdirs(workspace_path)
        return workspace_path
    
    def upload_to_workspace(self, workspace_path: str):
        """Upload deployment package to workspace."""
        logger.info(f"Uploading to {workspace_path}...")
        
        deploy_dir = Path("deploy")
        
        for file_path in deploy_dir.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(deploy_dir)
                workspace_file_path = f"{workspace_path}/{relative_path}"
                
                # Create parent directories
                parent = str(Path(workspace_file_path).parent)
                self.workspace_client.workspace.mkdirs(parent)
                
                # Upload file
                with open(file_path, "rb") as f:
                    self.workspace_client.workspace.upload(
                        workspace_file_path,
                        f.read(),
                        overwrite=True
                    )
        
        logger.info(f"✓ Uploaded {len(list(deploy_dir.rglob('*')))} files")
    
    def setup_app(self) -> App:
        """Create or update Databricks App."""
        app_name = f"ai-slide-generator-{self.environment}"
        
        logger.info(f"Setting up app: {app_name}")
        
        try:
            # Try to get existing app
            app = self.workspace_client.apps.get(app_name)
            logger.info(f"Updating existing app: {app_name}")
            # Update app (restart with new code)
            app = self.workspace_client.apps.update(
                name=app_name,
                # Update triggers restart
            )
        except Exception:
            # Create new app
            logger.info(f"Creating new app: {app_name}")
            app = self.workspace_client.apps.create_and_wait(
                app=App(name=app_name)
            )
        
        return app
    
    def setup_permissions(self, app_name: str):
        """Configure app permissions."""
        logger.info(f"Setting up permissions for {app_name}")
        
        permissions = [
            AppPermission(
                permission_level=PermissionLevel.CAN_USE,
                group_name="users"
            ),
            # Add more permissions as needed
        ]
        
        self.workspace_client.apps.set_permissions(
            app_name=app_name,
            permissions=permissions
        )
    
    def verify_deployment(self, app_name: str):
        """Verify app is running."""
        logger.info(f"Verifying deployment: {app_name}")
        
        app = self.workspace_client.apps.get(app_name)
        
        if app.status == "RUNNING":
            logger.info(f"✓ App is running: {app.url}")
        else:
            logger.warning(f"App status: {app.status}")
            # Could fetch logs here for debugging

def main():
    parser = argparse.ArgumentParser(description="Deploy AI Slide Generator")
    parser.add_argument(
        "--env",
        choices=["development", "production"],
        default="production",
        help="Environment to deploy to"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean workspace directory before deployment"
    )
    
    args = parser.parse_args()
    
    deployer = AppDeployer(environment=args.env)
    deployer.deploy(clean=args.clean)

if __name__ == "__main__":
    main()
```

### 8.3 Rollback Script (`databricks-app/rollback.py`)

```python
"""Rollback to previous app version."""

def rollback_app(app_name: str):
    """Rollback app to previous version."""
    # Implementation depends on versioning strategy
    pass
```

---

## Component 9: Testing & Validation

### 9.1 Local Production Testing

**Test production build locally:**

```bash
# Build frontend
cd frontend && npm run build && cd ..

# Set production environment
export ENVIRONMENT=production
export SERVE_FRONTEND=true
export LOG_FORMAT=json

# Run backend (serves frontend)
uvicorn src.api.main:app --host 0.0.0.0 --port 8080
```

**Verify:**
- Frontend loads from http://localhost:8080
- API responds at http://localhost:8080/api/health
- Logs are in JSON format
- No CORS errors

### 9.2 Header Simulation

**Test user context extraction:**

```bash
curl -H "X-Forwarded-User: test@databricks.com" \
     -H "X-Forwarded-Email: test@databricks.com" \
     -H "X-Forwarded-Preferred-Username: Test User" \
     http://localhost:8080/api/health
```

**Verify logs contain user_id:**
```json
{
  "timestamp": "2024-11-17T10:00:00Z",
  "level": "INFO",
  "user_id": "test@databricks.com",
  "message": "Request started: GET /api/health"
}
```

### 9.3 Integration Tests

**Test deployment script:**
```bash
# Dry run (build only, no upload)
python databricks-app/deploy.py --env development --dry-run

# Deploy to development
python databricks-app/deploy.py --env development

# Verify deployment
python databricks-app/verify.py --env development
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal**: Basic deployment infrastructure

**Tasks:**
1. Create `app.yaml` configuration
2. Update `requirements.txt` with all dependencies
3. Create user context middleware
4. Update settings for environment awareness
5. Add structured JSON logging
6. Test local production build

**Deliverables:**
- ✅ app.yaml
- ✅ Updated requirements.txt
- ✅ UserContextMiddleware
- ✅ JSON logging
- ✅ Local production mode works

### Phase 2: Deployment Automation (Week 2)
**Goal**: Automated build and deploy

**Tasks:**
1. Create `build.sh` script
2. Create `deploy.py` script
3. Add workspace upload logic
4. Add app creation/update logic
5. Add permissions management
6. Test end-to-end deployment

**Deliverables:**
- ✅ Automated build process
- ✅ Automated deployment
- ✅ App created in workspace
- ✅ Permissions configured

### Phase 3: Frontend Integration (Week 3)
**Goal**: Serve frontend from FastAPI

**Tasks:**
1. Update Vite config for production build
2. Add static file serving in FastAPI
3. Update frontend API client
4. Test same-origin requests
5. Verify no CORS issues
6. Deploy to Databricks Apps

**Deliverables:**
- ✅ Frontend builds to static assets
- ✅ Backend serves frontend
- ✅ Single-origin deployment
- ✅ Working app in Databricks

### Phase 4: Validation & Documentation (Week 4)
**Goal**: Production-ready deployment

**Tasks:**
1. End-to-end testing
2. Performance validation
3. Logging verification
4. Documentation
5. Runbook creation
6. Training materials

**Deliverables:**
- ✅ Comprehensive tests
- ✅ Deployment documentation
- ✅ Operational runbook
- ✅ User guide

---

## File Structure

```
ai-slide-generator/
├── databricks-app/              # NEW: Deployment infrastructure
│   ├── DEPLOYMENT_PLAN.md       # This file
│   ├── deploy.py                # Main deployment script
│   ├── build.sh                 # Build script
│   ├── config.py                # Deployment configuration
│   ├── client.py                # Workspace client wrapper
│   ├── verify.py                # Deployment verification
│   ├── rollback.py              # Rollback utility
│   └── README.md                # Deployment guide
├── app.yaml                     # NEW: Databricks Apps manifest
├── app.dev.yaml                 # NEW: Dev environment config
├── app.prod.yaml                # NEW: Prod environment config
├── requirements.lock            # NEW: Locked dependencies
├── src/
│   ├── api/
│   │   ├── middleware/          # NEW: Middleware
│   │   │   ├── auth.py          # User context extraction
│   │   │   └── logging.py       # Request logging
│   │   ├── models/
│   │   │   ├── auth.py          # NEW: User context model
│   │   │   └── ...
│   │   ├── services/
│   │   │   ├── session_manager.py  # NEW: Session manager
│   │   │   └── ...
│   │   └── main.py              # UPDATED: Static file serving
│   ├── config/
│   │   └── settings.py          # UPDATED: Environment settings
│   ├── utils/
│   │   └── logging_config.py    # NEW: JSON logging
│   └── ...
├── frontend/
│   ├── .env.production          # NEW: Production env vars
│   ├── .env.development         # NEW: Development env vars
│   ├── vite.config.ts           # UPDATED: Production build
│   └── ...
├── deploy/                      # NEW: Build output (gitignored)
│   ├── src/
│   ├── frontend/dist/
│   ├── config/
│   ├── app.yaml
│   ├── requirements.txt
│   └── DEPLOYMENT_INFO.txt
└── ...
```

---

## Security Considerations

### Authentication
- **Production**: Databricks-provided headers (automatic)
- **Development**: Environment variable fallback
- **Validation**: Ensure headers are present and valid

### Authorization
- **Phase 3**: Foundation only (user context logging)
- **Phase 4**: Per-user session isolation
- **Future**: Role-based access control (RBAC)

### Secrets Management
- **Never commit**: `.env` files with credentials
- **Use**: Databricks secrets for sensitive data
- **Reference**: https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/system-env

### Data Isolation
- **Phase 3**: Single session (limited isolation)
- **Phase 4**: Per-user sessions (full isolation)
- **Logging**: User IDs in all logs for auditability

---

## Monitoring & Observability

### Logging
- **Format**: JSON for structured logs
- **Output**: stdout (INFO) and stderr (ERROR)
- **Fields**: timestamp, level, user_id, request_id, duration_ms
- **Access**: Databricks Apps log viewer

### Metrics
- **Request duration**: Logged per request
- **Error rate**: Count of 5xx responses
- **User activity**: Requests per user
- **App health**: Health check endpoint

### Alerts
- **Error rate threshold**: > 5% in 5 minutes
- **Latency threshold**: p95 > 5 seconds
- **App downtime**: Health check fails
- **Resource usage**: Memory/CPU limits

### Dashboards
- **App overview**: Status, version, uptime
- **Request metrics**: Volume, latency, errors
- **User activity**: Active users, requests
- **System health**: CPU, memory, disk

---

## Best Practices

### Development
1. **Test locally first**: Always test production build locally
2. **Use environment flags**: Never hardcode environment-specific values
3. **Structured logging**: Use JSON format with context
4. **Version everything**: Tag releases, lock dependencies

### Deployment
1. **Automated deployment**: Use scripts, not manual steps
2. **Idempotent operations**: Deployment can run multiple times safely
3. **Health checks**: Verify app is running after deployment
4. **Rollback plan**: Have working rollback procedure

### Operations
1. **Monitor logs**: Set up alerts for errors
2. **Track metrics**: Monitor performance trends
3. **Document incidents**: Keep runbook updated
4. **Regular updates**: Keep dependencies current

### Security
1. **Least privilege**: Grant minimum required permissions
2. **Audit logging**: Log all user actions
3. **Regular reviews**: Audit permissions quarterly
4. **Secret rotation**: Rotate tokens regularly

---

## References

### Microsoft Azure Databricks Documentation
- [Databricks Apps Overview](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/)
- [System Environment Variables](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/system-env)
- [App Runtime](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/app-runtime)
- [Resources](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/resources)
- [Genie Integration](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/genie)
- [Best Practices](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/best-practices)
- [Deployment Guide](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/deploy)

### Reference Implementations
- [SQL Migration Assistant (initialsetup.py)](https://github.com/robertwhiffin/sandbox/blob/main/sql-migration-assistant/src/sql_migration_assistant/infra/initialsetup.py)
- [SQL Migration Assistant (infra/__init__.py)](https://github.com/robertwhiffin/sandbox/blob/main/sql-migration-assistant/src/sql_migration_assistant/infra/__init__.py)

### Internal Documentation
- [Current Deployment Plan (PHASE_3_DATABRICKS_DEPLOYMENT.md)](../PHASE_3_DATABRICKS_DEPLOYMENT.md) - Previous approach
- [Backend Overview](../docs/technical/backend-overview.md)
- [Frontend Overview](../docs/technical/frontend-overview.md)

---

## Next Steps

After this plan is approved:

1. **Review and refine**: Discuss plan with team
2. **Set timeline**: Allocate 4 weeks for implementation
3. **Start Phase 1**: Create foundation files
4. **Iterate**: Test each phase before proceeding
5. **Document**: Keep documentation current

**Ready to implement?** Start with Phase 1, Week 1 tasks.

