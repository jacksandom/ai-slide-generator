# Databricks App Implementation Checklist

Track implementation progress for deploying AI Slide Generator as a Databricks App.

## Phase 1: Foundation (Week 1)

**Goal**: Basic deployment infrastructure and environment configuration

### Configuration Files
- [ ] Create `app.yaml` with production settings
  - [ ] Define startup command (`uvicorn src.api.main:app --host 0.0.0.0 --port 8080`)
  - [ ] Set environment variables (ENVIRONMENT, LOG_LEVEL, LOG_FORMAT)
  - [ ] Configure compute resources (size: SMALL)
  - [ ] Define default permissions
  - [ ] Add health check endpoint configuration
- [ ] Create `app.dev.yaml` for development environment
- [ ] Create `app.prod.yaml` for production environment
- [ ] Update `requirements.txt` with production dependencies
  - [ ] Add `python-json-logger>=2.0.0`
  - [ ] Verify all existing dependencies are present
  - [ ] Generate `requirements.lock` file

### Backend - User Context
- [ ] Create `src/api/middleware/` directory
- [ ] Implement `src/api/middleware/auth.py`
  - [ ] `UserContextMiddleware` class
  - [ ] Extract X-Forwarded-* headers
  - [ ] Development fallback using env vars
  - [ ] Attach user context to request.state
- [ ] Create `src/api/models/auth.py`
  - [ ] `UserContext` Pydantic model
  - [ ] `session_key` property (for Phase 4)
- [ ] Create `src/api/services/session_manager.py`
  - [ ] `SessionManager` class (single session for Phase 3)
  - [ ] `get_session()` method with user context logging
  - [ ] Stubs for Phase 4 multi-session support
- [ ] Add user context dependency injection
  - [ ] `get_user_context()` dependency function
  - [ ] Update routes to accept `UserContext` parameter

### Backend - Logging
- [ ] Create `src/utils/logging_config.py`
  - [ ] `JSONFormatter` class
  - [ ] `setup_logging()` function
  - [ ] Configure stdout/stderr handlers
  - [ ] Support for text format (development)
- [ ] Create `src/api/middleware/logging.py`
  - [ ] `RequestLoggingMiddleware` class
  - [ ] Log request start with user context
  - [ ] Log request completion with duration
  - [ ] Log errors with full context
- [ ] Update `src/api/main.py`
  - [ ] Call `setup_logging()` at startup
  - [ ] Add `UserContextMiddleware`
  - [ ] Add `RequestLoggingMiddleware`
  - [ ] Middleware order: Logging → UserContext

### Backend - Settings
- [ ] Update `src/config/settings.py`
  - [ ] Add `environment` field (development/production)
  - [ ] Add `log_level` field
  - [ ] Add `log_format` field (json/text)
  - [ ] Add `serve_frontend` field
  - [ ] Add `frontend_dist_path` field
  - [ ] Add `is_production` property
  - [ ] Add `is_development` property
  - [ ] Add placeholder session settings (commented for Phase 4)

### Testing
- [ ] Test local production mode
  - [ ] Build frontend: `cd frontend && npm run build`
  - [ ] Set environment variables (ENVIRONMENT=production, etc.)
  - [ ] Run backend: `uvicorn src.api.main:app --port 8080`
  - [ ] Verify frontend loads from http://localhost:8080
  - [ ] Verify API responds at /api/health
- [ ] Test header extraction
  - [ ] Use curl with X-Forwarded-* headers
  - [ ] Verify user_id appears in logs
  - [ ] Verify request_id tracking works
- [ ] Test JSON logging
  - [ ] Verify log format is valid JSON
  - [ ] Verify stdout gets INFO logs
  - [ ] Verify stderr gets ERROR logs
  - [ ] Verify all required fields present

### Documentation
- [ ] Review and understand DEPLOYMENT_PLAN.md
- [ ] Update README.md if needed
- [ ] Document environment variables in .env.example
- [ ] Create PHASE_3_IMPLEMENTATION.md with progress notes

---

## Phase 2: Deployment Automation (Week 2)

**Goal**: Automated build and deploy to Databricks workspace

### Build Scripts
- [ ] Create `databricks-app/build.sh`
  - [ ] Clean previous build
  - [ ] Build frontend (npm ci && npm run build)
  - [ ] Copy backend source to deploy/
  - [ ] Copy config files to deploy/
  - [ ] Copy requirements files to deploy/
  - [ ] Copy app.yaml to deploy/
  - [ ] Copy frontend/dist to deploy/
  - [ ] Create DEPLOYMENT_INFO.txt with metadata
  - [ ] Make executable (chmod +x)
- [ ] Test build script locally
  - [ ] Run: `bash databricks-app/build.sh`
  - [ ] Verify deploy/ directory structure
  - [ ] Verify all files present
  - [ ] Verify frontend assets in deploy/frontend/dist/

### Deployment Infrastructure
- [ ] Create `databricks-app/config.py`
  - [ ] `DeploymentConfig` class
  - [ ] Load from environment and YAML
  - [ ] Workspace settings (host, path)
  - [ ] App settings (name, compute)
  - [ ] Permission settings
- [ ] Create `databricks-app/client.py`
  - [ ] Initialize `WorkspaceClient`
  - [ ] `upload_directory()` method
  - [ ] `create_or_update_app()` method
  - [ ] `set_permissions()` method
  - [ ] `get_app_status()` method
  - [ ] `get_app_logs()` method
  - [ ] `delete_app()` method
- [ ] Create `databricks-app/deploy.py`
  - [ ] `AppDeployer` class
  - [ ] `build()` method
  - [ ] `setup_deployment_directory()` method
  - [ ] `upload_to_workspace()` method
  - [ ] `setup_app()` method
  - [ ] `setup_permissions()` method
  - [ ] `verify_deployment()` method
  - [ ] CLI argument parsing (--env, --clean, --dry-run)
  - [ ] Main entry point

### Deployment Testing
- [ ] Test workspace upload
  - [ ] Run with --dry-run flag
  - [ ] Verify workspace path creation
  - [ ] Verify file upload logic
- [ ] Test app creation
  - [ ] Deploy to development environment
  - [ ] Verify app created in workspace
  - [ ] Verify app status is RUNNING
  - [ ] Get app URL from response
- [ ] Test permissions
  - [ ] Verify default permissions applied
  - [ ] Test with different user accounts
  - [ ] Verify access control works

### Utilities
- [ ] Create `databricks-app/verify.py`
  - [ ] Check app status
  - [ ] Test health endpoint
  - [ ] Validate logging
  - [ ] Report metrics
- [ ] Create `databricks-app/rollback.py`
  - [ ] List available versions
  - [ ] Restore previous version
  - [ ] Verify rollback success

---

## Phase 3: Frontend Integration (Week 3)

**Goal**: Serve frontend from FastAPI in production

### Frontend Build Configuration
- [ ] Update `frontend/vite.config.ts`
  - [ ] Set build.outDir to 'dist'
  - [ ] Set build.assetsDir to 'assets'
  - [ ] Disable sourcemaps for production
  - [ ] Configure manual chunks (react-vendor, editor, dnd)
  - [ ] Keep dev server proxy configuration
- [ ] Create `frontend/.env.production`
  - [ ] Set VITE_API_URL to empty string (same origin)
- [ ] Create `frontend/.env.development`
  - [ ] Set VITE_API_URL to http://localhost:8000
- [ ] Update `frontend/src/services/api.ts`
  - [ ] Use `import.meta.env.VITE_API_URL || ''` for base URL
  - [ ] Verify all API calls work with empty base URL

### Backend Static Serving
- [ ] Update `src/api/main.py`
  - [ ] Import StaticFiles, FileResponse, Path
  - [ ] Get settings.serve_frontend flag
  - [ ] Get settings.frontend_dist_path
  - [ ] Mount /assets directory (if production)
  - [ ] Add catch-all route for SPA (if production)
  - [ ] Skip API paths in catch-all
  - [ ] Serve index.html for all other routes
- [ ] Update CORS middleware
  - [ ] Only enable CORS in development
  - [ ] Disable CORS in production (same origin)
  - [ ] Environment check: `if settings.is_development`

### Testing
- [ ] Test local production build
  - [ ] Build frontend
  - [ ] Set ENVIRONMENT=production, SERVE_FRONTEND=true
  - [ ] Run backend on port 8080
  - [ ] Access http://localhost:8080 (not :3000)
  - [ ] Verify frontend loads
  - [ ] Verify API calls work (no CORS errors)
  - [ ] Test all features (chat, slides, editing)
- [ ] Test deployment to Databricks
  - [ ] Run full deployment: `python databricks-app/deploy.py --env development`
  - [ ] Access Databricks Apps URL
  - [ ] Verify frontend loads
  - [ ] Verify API works
  - [ ] Test user features
  - [ ] Check logs in Databricks

### Browser Testing
- [ ] Chrome/Edge
  - [ ] Frontend loads
  - [ ] No console errors
  - [ ] API calls succeed
  - [ ] Features work
- [ ] Firefox
  - [ ] Frontend loads
  - [ ] No console errors
  - [ ] API calls succeed
  - [ ] Features work
- [ ] Safari (if available)
  - [ ] Frontend loads
  - [ ] No console errors
  - [ ] API calls succeed
  - [ ] Features work

---

## Phase 4: Validation & Documentation (Week 4)

**Goal**: Production-ready deployment with comprehensive documentation

### End-to-End Testing
- [ ] User authentication flow
  - [ ] Verify X-Forwarded-* headers extracted
  - [ ] Verify user ID in logs
  - [ ] Test with multiple users
  - [ ] Verify user isolation (Phase 3: logging only)
- [ ] Core features
  - [ ] Send chat message → generate slides
  - [ ] Chat history displays correctly
  - [ ] Slides render properly
  - [ ] Drag-and-drop reordering works
  - [ ] HTML editor works
  - [ ] Slide duplication works
  - [ ] Slide deletion works
  - [ ] Charts render correctly
- [ ] Performance testing
  - [ ] Initial load time < 3 seconds
  - [ ] Slide generation completes
  - [ ] No timeout errors
  - [ ] Smooth UI interactions
  - [ ] Check memory usage
  - [ ] Check CPU usage

### Logging Validation
- [ ] Log format verification
  - [ ] All logs valid JSON
  - [ ] Required fields present (timestamp, level, message)
  - [ ] User context in logs (user_id, request_id)
  - [ ] Duration tracking works
  - [ ] Errors include stack traces
- [ ] Log aggregation
  - [ ] View logs in Databricks Apps UI
  - [ ] Filter by level (INFO, ERROR)
  - [ ] Filter by user_id
  - [ ] Filter by time range
  - [ ] Search log messages
- [ ] Create log queries
  - [ ] Error rate query
  - [ ] Latency query (avg, p95, p99)
  - [ ] User activity query
  - [ ] Endpoint usage query

### Monitoring Setup
- [ ] Health check
  - [ ] Configure health check in app.yaml
  - [ ] Test /api/health endpoint
  - [ ] Verify response format
  - [ ] Test from external monitor
- [ ] Metrics dashboard
  - [ ] Request volume over time
  - [ ] Error rate over time
  - [ ] Latency distribution
  - [ ] Active users
  - [ ] Top endpoints
- [ ] Alerts
  - [ ] Error rate > 5% in 5 minutes
  - [ ] P95 latency > 5 seconds
  - [ ] Health check failures
  - [ ] App crashes
  - [ ] High memory usage

### Documentation
- [ ] Update main README.md
  - [ ] Add Databricks deployment section
  - [ ] Link to databricks-app/README.md
  - [ ] Update architecture diagram if needed
  - [ ] Update "Current Phase" status
- [ ] Review databricks-app/DEPLOYMENT_PLAN.md
  - [ ] Verify all sections accurate
  - [ ] Update with lessons learned
  - [ ] Add troubleshooting tips
- [ ] Review databricks-app/README.md
  - [ ] Verify quick start works
  - [ ] Update any outdated information
  - [ ] Add common issues and solutions
- [ ] Create operational runbook
  - [ ] Deployment procedure
  - [ ] Rollback procedure
  - [ ] Common troubleshooting steps
  - [ ] Escalation path
  - [ ] On-call runbook
- [ ] Update technical documentation
  - [ ] docs/technical/backend-overview.md
  - [ ] docs/technical/frontend-overview.md
  - [ ] Add docs/technical/deployment-overview.md

### Training & Knowledge Transfer
- [ ] Create user guide
  - [ ] How to access the app
  - [ ] Basic usage instructions
  - [ ] Feature documentation
  - [ ] Known limitations
  - [ ] Support contacts
- [ ] Create admin guide
  - [ ] Deployment instructions
  - [ ] Monitoring and alerting
  - [ ] Troubleshooting guide
  - [ ] Maintenance procedures
- [ ] Create video walkthrough (optional)
  - [ ] Deployment process
  - [ ] Using the app
  - [ ] Troubleshooting common issues

### Final Validation
- [ ] Security review
  - [ ] No credentials in code
  - [ ] No secrets in logs
  - [ ] User isolation works
  - [ ] Permissions correctly set
  - [ ] HTTPS enforced (Databricks default)
- [ ] Performance review
  - [ ] Load testing completed
  - [ ] Acceptable response times
  - [ ] No memory leaks
  - [ ] Compute size appropriate
- [ ] Deployment review
  - [ ] Build process reproducible
  - [ ] Deployment process automated
  - [ ] Rollback procedure tested
  - [ ] Documentation complete

---

## Post-Deployment

### Week 5: Monitoring & Iteration
- [ ] Monitor for 1 week
  - [ ] Check error rates daily
  - [ ] Review performance metrics
  - [ ] Gather user feedback
  - [ ] Identify issues
- [ ] Create bug/issue list
- [ ] Prioritize fixes
- [ ] Schedule improvements

### Future Enhancements (Phase 4+)
- [ ] Multi-session support (Phase 4)
  - [ ] Per-user session isolation
  - [ ] Session persistence
  - [ ] Session cleanup
  - [ ] Session limits
- [ ] Unity Catalog integration
  - [ ] Store slides in Unity Catalog
  - [ ] Version control for slides
  - [ ] Sharing and collaboration
- [ ] Export functionality
  - [ ] Export to PDF
  - [ ] Export to PowerPoint
  - [ ] Export to HTML archive
- [ ] Advanced features
  - [ ] Undo/redo
  - [ ] Slide templates
  - [ ] Themes and styling
  - [ ] Collaborative editing

---

## Notes

### Issues Encountered
*Document any issues encountered during implementation*

1. 

### Solutions Applied
*Document solutions to issues*

1. 

### Lessons Learned
*Document key takeaways*

1. 

### Technical Debt
*Track technical debt to address later*

1. 

---

## Sign-Off

### Phase 1 Complete
- [ ] All Phase 1 tasks complete
- [ ] Local testing passed
- [ ] Code reviewed
- [ ] Documentation updated
- **Date**: _________
- **Sign-off**: _________

### Phase 2 Complete
- [ ] All Phase 2 tasks complete
- [ ] Deployment tested
- [ ] Code reviewed
- [ ] Documentation updated
- **Date**: _________
- **Sign-off**: _________

### Phase 3 Complete
- [ ] All Phase 3 tasks complete
- [ ] Frontend integration tested
- [ ] Code reviewed
- [ ] Documentation updated
- **Date**: _________
- **Sign-off**: _________

### Phase 4 Complete
- [ ] All Phase 4 tasks complete
- [ ] End-to-end testing passed
- [ ] Monitoring configured
- [ ] Documentation complete
- [ ] Ready for production
- **Date**: _________
- **Sign-off**: _________

