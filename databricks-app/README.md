# Databricks App Deployment

Automated deployment infrastructure for deploying the AI Slide Generator as a Databricks App.

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Databricks workspace with Apps enabled
- Databricks CLI configured or `DATABRICKS_HOST` and `DATABRICKS_TOKEN` in `.env`

### Deploy to Databricks

```bash
# 1. Build the application
bash databricks-app/build.sh

# 2. Deploy to development
python databricks-app/deploy.py --env development

# 3. Deploy to production
python databricks-app/deploy.py --env production
```

### Clean Deployment

Remove existing app and redeploy:
```bash
python databricks-app/deploy.py --env development --clean
```

## What Gets Deployed

The deployment package includes:
- **Backend**: Python FastAPI application
- **Frontend**: React static assets (built)
- **Configuration**: `app.yaml` with environment settings
- **Dependencies**: `requirements.txt` and lock file

## Deployment Structure

```
deploy/                          # Build output (generated)
├── src/                         # Backend Python code
├── frontend/dist/               # Built React app
├── config/                      # Application configuration
├── app.yaml                     # Databricks Apps manifest
├── requirements.txt             # Python dependencies
└── DEPLOYMENT_INFO.txt          # Build metadata
```

## Configuration Files

### `app.yaml`
Main configuration for Databricks Apps:
- Startup command
- Environment variables
- Compute resources
- Permissions

Variants:
- `app.dev.yaml` - Development environment
- `app.prod.yaml` - Production environment

### Environment Variables

**Production** (set in `app.yaml`):
```yaml
env:
  - name: ENVIRONMENT
    value: production
  - name: LOG_LEVEL
    value: INFO
  - name: LOG_FORMAT
    value: json
```

**Development** (set in `.env`):
```bash
ENVIRONMENT=development
LOG_LEVEL=DEBUG
DEV_USER_ID=dev@local.test
DEV_USER_EMAIL=dev@local.test
DEV_USERNAME=Dev User
```

## Scripts

### `build.sh`
Builds the application for deployment:
1. Cleans previous build
2. Builds frontend to static assets
3. Packages backend code
4. Creates deployment directory

### `deploy.py`
Deploys application to Databricks:
1. Runs build script
2. Uploads files to workspace
3. Creates or updates app
4. Sets permissions
5. Verifies deployment

Options:
- `--env {development|production}` - Target environment
- `--clean` - Clean workspace before deployment
- `--dry-run` - Build only, don't deploy

### `verify.py`
Verifies deployment health:
- Checks app status
- Tests health endpoint
- Validates logging
- Reports metrics

### `rollback.py`
Rolls back to previous version:
- Lists available versions
- Restores previous deployment
- Verifies rollback success

## Local Testing

Test production build locally before deploying:

```bash
# Build frontend
cd frontend
npm run build
cd ..

# Set production environment
export ENVIRONMENT=production
export SERVE_FRONTEND=true
export LOG_FORMAT=json
export LOG_LEVEL=INFO

# Simulate Databricks headers (for local testing)
export DEV_USER_ID=test@databricks.com
export DEV_USER_EMAIL=test@databricks.com
export DEV_USERNAME=Test User

# Run backend (serves frontend)
uvicorn src.api.main:app --host 0.0.0.0 --port 8080
```

**Access**: http://localhost:8080

**Test with simulated headers**:
```bash
curl -H "X-Forwarded-User: test@databricks.com" \
     -H "X-Forwarded-Email: test@databricks.com" \
     http://localhost:8080/api/health | jq
```

## User Authorization

### Databricks Apps Headers

In production, Databricks Apps automatically provides:
- `X-Forwarded-User`: User ID (email)
- `X-Forwarded-Email`: User email address
- `X-Forwarded-Preferred-Username`: Display name
- `X-Real-Ip`: Client IP address
- `X-Request-Id`: Unique request ID

These are extracted by `UserContextMiddleware` and attached to request state.

### Development Fallback

When `ENVIRONMENT=development`, the middleware uses environment variables:
- `DEV_USER_ID`
- `DEV_USER_EMAIL`
- `DEV_USERNAME`

This allows local testing without Databricks headers.

## Logging

### Structured JSON Logging

All logs are output in JSON format for easy parsing:

```json
{
  "timestamp": "2024-11-17T10:00:00Z",
  "level": "INFO",
  "logger": "src.api.routes.chat",
  "message": "Chat request received",
  "user_id": "user@databricks.com",
  "request_id": "abc-123",
  "duration_ms": 1500
}
```

### Log Outputs
- **stdout**: INFO and DEBUG messages
- **stderr**: WARNING, ERROR, CRITICAL messages

### Viewing Logs

**Databricks Apps UI**:
1. Navigate to Apps → AI Slide Generator
2. Click "Logs" tab
3. Filter by level, user, time range

**CLI**:
```bash
# Follow logs in real-time
databricks apps logs --app-name ai-slide-generator --follow

# Get last 100 lines
databricks apps logs --app-name ai-slide-generator --tail 100
```

## Monitoring

### Health Check

**Endpoint**: `/api/health`

**Response**:
```json
{
  "status": "healthy",
  "environment": "production",
  "version": "0.7.0"
}
```

### Key Metrics
- **Request duration**: Logged with each request
- **Error rate**: Tracked in logs
- **User activity**: Per-user request counts
- **App status**: RUNNING, STOPPED, ERROR

### Alerts

Set up alerts for:
- Error rate > 5% in 5 minutes
- P95 latency > 5 seconds
- Health check failures
- App crashes

## Troubleshooting

### App Won't Start

**Check logs**:
```bash
databricks apps logs --app-name ai-slide-generator --tail 50
```

**Common issues**:
- Missing dependencies in `requirements.txt`
- Invalid `app.yaml` configuration
- Frontend build errors
- Port already in use (should be 8080)

### Authentication Errors

**Symptoms**: User ID showing as "unknown"

**Solutions**:
1. Verify `X-Forwarded-*` headers in logs
2. Check middleware is enabled in `main.py`
3. Confirm Databricks Apps is providing headers

### Frontend Not Loading

**Symptoms**: 404 errors, blank page

**Solutions**:
1. Verify frontend built: `ls deploy/frontend/dist/`
2. Check `SERVE_FRONTEND=true` in environment
3. Confirm static file mounting in `main.py`
4. Look for 404s in logs

### Performance Issues

**Symptoms**: Slow response times

**Solutions**:
1. Check compute size (upgrade to MEDIUM/LARGE)
2. Review slow queries in logs
3. Enable caching for Genie queries
4. Optimize frontend bundle size

### Deployment Fails

**Symptoms**: Upload errors, permission denied

**Solutions**:
1. Verify Databricks credentials
2. Check workspace permissions
3. Ensure app name is unique
4. Try with `--clean` flag

## Multi-Session Support (Phase 4)

**Current State (Phase 3)**: Single global session, user context logged

**Future (Phase 4)**: Per-user session isolation

**Foundation in place**:
- `UserContext` model with `session_key` property
- `SessionManager` class (currently returns global session)
- User context dependency injection in routes
- User ID logging for auditability

**To enable** (Phase 4):
1. Uncomment session settings in `settings.py`
2. Implement per-user session lookup in `SessionManager`
3. Add session cleanup background task
4. Update routes to use user-specific sessions

## Security

### Best Practices
- ✅ Never commit `.env` files
- ✅ Use Databricks secrets for sensitive data
- ✅ Log all user actions with user IDs
- ✅ Grant minimum required permissions
- ✅ Regular security audits

### Permissions

**App Permissions** (set in `app.yaml`):
```yaml
permissions:
  - level: CAN_USE        # Can use the app
    group_name: users
  - level: CAN_MANAGE     # Can update/delete
    user_name: admin@company.com
```

**Workspace Permissions**:
- Read access to Genie space
- Write access to MLflow experiments
- Execute access to LLM endpoints

## Development Workflow

### 1. Local Development
```bash
# Terminal 1: Backend
source .venv/bin/activate
uvicorn src.api.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev
```

**Access**: http://localhost:3000

### 2. Local Production Test
```bash
# Build and run in production mode
bash databricks-app/build.sh
export ENVIRONMENT=production
export SERVE_FRONTEND=true
uvicorn src.api.main:app --host 0.0.0.0 --port 8080
```

**Access**: http://localhost:8080

### 3. Deploy to Development
```bash
python databricks-app/deploy.py --env development
```

**Access**: Databricks Apps URL (get from logs or UI)

### 4. Deploy to Production
```bash
python databricks-app/deploy.py --env production
```

**Access**: Databricks Apps URL (share with users)

## Resources

### Documentation
- [Deployment Plan](DEPLOYMENT_PLAN.md) - Comprehensive deployment guide
- [Databricks Apps Docs](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/)
- [Backend Overview](../docs/technical/backend-overview.md)
- [Frontend Overview](../docs/technical/frontend-overview.md)

### Reference Implementations
- [SQL Migration Assistant](https://github.com/robertwhiffin/sandbox/tree/main/sql-migration-assistant)

### Support
- Check logs first: `databricks apps logs --app-name ai-slide-generator`
- Review [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) for detailed guidance
- Consult [Troubleshooting](#troubleshooting) section above

## Next Steps

1. **Review Plan**: Read [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)
2. **Phase 1**: Implement foundation (app.yaml, middleware, logging)
3. **Phase 2**: Create deployment automation
4. **Phase 3**: Integrate frontend serving
5. **Phase 4**: Validate and document

**Ready to start?** Begin with Phase 1 tasks in the deployment plan.

