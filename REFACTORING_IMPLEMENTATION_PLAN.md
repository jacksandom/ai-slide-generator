# AI Slide Generator - Refactoring Implementation Plan

## Branching Strategy

### Phase 0: Setup Safe Development Environment
```bash
# Step 1: Create backup/preservation branch from main
git checkout main
git pull origin main
git checkout -b refactor-main
git push -u origin refactor-main

# Step 2: Create feature branches off refactor-main
git checkout refactor-main
git checkout -b phase1-remove-duplicates
```

**Branch Structure:**
- `main` - **Protected**: Current production code, untouched during refactoring
- `refactor-main` - **Base branch**: Safe copy of main for refactoring work
- `phase1-remove-duplicates` - **Feature branch**: Phase 1 implementation
- `phase2-standardize-arch` - **Feature branch**: Phase 2 implementation  
- `phase3-code-quality` - **Feature branch**: Phase 3 implementation

## Implementation Phases

## Phase 1: Remove Duplicates (Priority: CRITICAL)
**Timeline:** 2-3 days  
**Risk Level:** Low  
**Branch:** `phase1-remove-duplicates`

### Pre-Implementation Validation

#### Step 1.0: Create Baseline Tests
```bash
# Document current functionality
git checkout refactor-main
git checkout -b phase1-remove-duplicates

# Test current system end-to-end
npm run dev
# Manually test:
# - Frontend loads at localhost:3000
# - Backend responds at localhost:8000
# - Chat interface works
# - Slide generation works
# - Export functionality works

# Document results in BASELINE_FUNCTIONALITY.md
```

#### Step 1.1: Identify Active Frontend
**Objective:** Confirm which frontend is actually used in production

**Tasks:**
- [ ] Check `package.json` scripts to see which frontend is started by `npm run dev`
- [ ] Verify `start.sh` startup sequence
- [ ] Confirm `backend/main.py` CORS settings point to React (port 3000)
- [ ] Document findings in implementation notes

**Decision Point:** If React is active frontend, proceed with Gradio removal. If unclear, investigate further.

### Implementation Steps

#### Step 1.2: Remove Gradio Frontend
**Estimated Time:** 2 hours

**Files to Delete:**
```bash
# Remove Gradio frontend entirely
rm -rf src/slide_generator/frontend/gradio_app.py
rm -rf src/slide_generator/frontend/__init__.py
rmdir src/slide_generator/frontend/

# Clean up any Gradio imports
git grep -l "gradio_app\|frontend.gradio" . | xargs sed -i '' '/gradio_app\|frontend\.gradio/d'
```

**Files to Update:**
- [ ] `src/slide_generator/__main__.py` - Remove gradio import references
- [ ] `pyproject.toml` - Mark gradio as optional dependency
- [ ] Any remaining import statements

**Validation:**
- [ ] Backend starts without errors
- [ ] React frontend still works
- [ ] All functionality preserved

#### Step 1.3: Remove Deprecated Chatbot
**Estimated Time:** 1 hour

**Files to Delete:**
```bash
rm src/slide_generator/core/chatbot.py
```

**Files to Update:**
- [ ] `src/slide_generator/core/__init__.py` - Remove chatbot import
- [ ] `backend/main.py` - Remove commented chatbot import
- [ ] Any other files importing the old chatbot

**Validation:**
- [ ] Backend starts without errors
- [ ] Agent-based system still works

#### Step 1.4: Clean Up Empty/Unused Directories
**Estimated Time:** 30 minutes

**Directories to Remove:**
```bash
# Check if truly empty first
ls -la src/slide_generator/api/
ls -la src/slide_generator/deploy/

# If only __init__.py files, remove
rm -rf src/slide_generator/api/
rm -rf src/slide_generator/deploy/
```

**Validation:**
- [ ] No import errors
- [ ] Package structure still intact

#### Step 1.5: Consolidate Documentation
**Estimated Time:** 2 hours

**Files to Delete:**
```bash
rm README_REACT.md
rm README_NEW_STRUCTURE.md  
rm README_SETUP.md
rm SUGGESTED_PROJECT_STRUCTURE.md
rm frontend/slide-generator-frontend/README.md
```

**Files to Create/Update:**
- [ ] Create comprehensive `README.md` combining best parts of all deleted files
- [ ] Include setup instructions for React + FastAPI
- [ ] Add troubleshooting section
- [ ] Include development workflow
- [ ] Add API documentation links

**Content Structure for New README.md:**
```markdown
# AI Slide Generator

## Overview
[Project description and architecture]

## Quick Start
[Single setup command and access points]

## Development Setup
[Detailed setup for contributors]

## Architecture
[React + FastAPI + LangGraph agent description]

## API Reference
[FastAPI endpoints]

## Troubleshooting
[Common issues and solutions]
```

#### Step 1.6: Consolidate Dependencies
**Estimated Time:** 1 hour

**Files to Update:**
- [ ] Move all dependencies from `requirements.txt` to `pyproject.toml`
- [ ] Remove redundant `backend/requirements.txt` 
- [ ] Update `start.sh` to use pyproject.toml
- [ ] Test dependency installation

**Dependencies to Consolidate:**
```toml
# Add to pyproject.toml [project.dependencies]
"beautifulsoup4>=4.12.0",
"langgraph>=0.1.0", 
"unitycatalog-ai",
"databricks-connect",
"openai",
# etc.
```

### Phase 1 Testing & Validation

#### Step 1.7: Integration Testing
**Time:** 1 hour

**Test Checklist:**
- [ ] `npm run dev` starts both servers successfully
- [ ] Frontend loads without console errors
- [ ] Chat interface accepts messages
- [ ] Slide generation produces HTML output
- [ ] Export to PPTX works
- [ ] All API endpoints respond correctly
- [ ] No 404s or missing resource errors

#### Step 1.8: Performance Baseline
**Time:** 30 minutes

**Metrics to Capture:**
- [ ] Application startup time
- [ ] First slide generation time
- [ ] Memory usage (backend process)
- [ ] Bundle size (frontend)

#### Step 1.9: Documentation Update
**Time:** 30 minutes

- [ ] Update `CODEBASE_REVIEW_FINDINGS.md` with completion status
- [ ] Document any issues encountered
- [ ] Update next phase prerequisites

### Phase 1 Completion Criteria

**Success Metrics:**
- ✅ ~2,000 lines of code removed
- ✅ Documentation consolidated to single README
- ✅ All tests pass
- ✅ No functionality regression
- ✅ Startup time improved or unchanged
- ✅ Ready for Phase 2

**Merge Process:**
```bash
# Create PR from phase1-remove-duplicates to refactor-main
git checkout phase1-remove-duplicates
git add .
git commit -m "Phase 1: Remove duplicate frontends and deprecated code

- Remove Gradio frontend (gradio_app.py)
- Remove deprecated chatbot.py
- Consolidate 6 README files into single comprehensive guide
- Clean up empty directories (api/, deploy/)
- Consolidate dependency management

Impact: ~2,000 lines removed, improved maintainability"

git push origin phase1-remove-duplicates
# Create PR: phase1-remove-duplicates → refactor-main
```

---

## Phase 2: Standardize Architecture (Priority: HIGH)
**Timeline:** 1 week  
**Risk Level:** Medium  
**Branch:** `phase2-standardize-arch`

### Pre-Implementation Analysis

#### Step 2.0: Migration Assessment
**Objective:** Confirm html_slides.py → html_slides_agent.py migration status

**Tasks:**
- [ ] Analyze which system backend/main.py actually uses
- [ ] Compare feature parity between both systems
- [ ] Identify any missing functionality in agent system
- [ ] Document migration completeness

### Implementation Steps

#### Step 2.1: Complete Slide System Migration
**Estimated Time:** 2 days

**If html_slides.py still in use:**
- [ ] Port any missing functionality to html_slides_agent.py
- [ ] Update all imports in backend/main.py
- [ ] Test feature parity
- [ ] Remove html_slides.py (1,123 lines)

**If migration already complete:**
- [ ] Remove html_slides.py immediately
- [ ] Clean up any remaining imports
- [ ] Verify no functionality loss

#### Step 2.2: Standardize Configuration Management
**Estimated Time:** 1 day

**Databricks Configuration:**
```python
# Create src/slide_generator/config/databricks.py
class DatabricksConfig:
    def __init__(self):
        self.profile = os.getenv('DATABRICKS_PROFILE', 'default')
        self.host = os.getenv('DATABRICKS_HOST')
        self.token = os.getenv('DATABRICKS_TOKEN')
```

**Files to Update:**
- [ ] `backend/main.py` - Use environment-based config
- [ ] `html_slides_agent.py` - Remove hardcoded 'logfood' profile
- [ ] `uc_tools.py` - Standardize authentication
- [ ] Create `.env.example` with required variables

#### Step 2.3: Implement Consistent Error Handling
**Estimated Time:** 1 day

**Error Handling Patterns:**
```python
# Standardize on this pattern
class SlideGeneratorException(Exception):
    """Base exception for slide generator errors"""
    pass

class SlideGenerationError(SlideGeneratorException):
    """Error during slide generation"""
    pass

# Update all functions to use consistent error handling
```

**Files to Update:**
- [ ] All tool functions in `html_slides_agent.py`
- [ ] API endpoints in `backend/main.py`
- [ ] Add proper error responses with status codes

#### Step 2.4: Remove Global State
**Estimated Time:** 2 days

**Current Issues:**
- Backend uses `global slide_agent`
- Conversation state in global variables

**Implementation:**
```python
# Replace global state with proper session management
class SessionManager:
    def __init__(self):
        self.sessions = {}
    
    def get_or_create_session(self, session_id: str):
        if session_id not in self.sessions:
            self.sessions[session_id] = self.create_session()
        return self.sessions[session_id]
```

### Phase 2 Testing & Validation

#### Step 2.5: Architecture Validation
- [ ] No global state remaining
- [ ] Consistent error handling across all endpoints
- [ ] Configuration properly externalized
- [ ] All tests pass

---

## Phase 3: Code Quality Improvements (Priority: MEDIUM)
**Timeline:** 1 week  
**Risk Level:** Low-Medium  
**Branch:** `phase3-code-quality`

### Implementation Steps

#### Step 3.1: Break Up Large Files
**Target Files:**
- `html_slides_agent.py` (1,166 lines) → Split into:
  - `html_slides_agent.py` (core agent)
  - `slide_models.py` (Pydantic models)
  - `slide_tools.py` (tool functions)
  - `slide_validation.py` (HTML validation)

- `backend/main.py` (740 lines) → Split into:
  - `main.py` (FastAPI app setup)
  - `routes/chat.py` (chat endpoints)
  - `routes/slides.py` (slide endpoints)
  - `services/slide_service.py` (business logic)

#### Step 3.2: Add Type Hints
- [ ] Complete type hints for all functions
- [ ] Add mypy configuration
- [ ] Fix all type checking errors

#### Step 3.3: Implement Proper Logging
```python
# Replace print statements with proper logging
import logging

logger = logging.getLogger(__name__)

# Replace: print(f"[DEBUG] ...")
# With: logger.debug("...")
```

#### Step 3.4: Add Integration Tests
- [ ] Test critical user journeys
- [ ] API endpoint tests
- [ ] Agent functionality tests

---

## Phase 4: Advanced Refactoring (Priority: LOW)
**Timeline:** 2 weeks  
**Risk Level:** High  
**Branch:** `phase4-advanced`

### Implementation Steps

#### Step 4.1: Implement Dependency Injection
- [ ] Create proper service layer
- [ ] Injectable configuration
- [ ] Testable architecture

#### Step 4.2: Add Comprehensive Monitoring
- [ ] Request tracing
- [ ] Performance metrics
- [ ] Error tracking

---

## Risk Mitigation Strategies

### Rollback Plan
At any phase, rollback by:
```bash
git checkout refactor-main
git branch -D phase-X-branch
# Continue from known good state
```

### Validation Gates
Each phase must pass:
- [ ] All existing functionality works
- [ ] No performance regression
- [ ] All tests pass
- [ ] Documentation updated

### Communication Plan
- [ ] Daily standup updates on progress
- [ ] Weekly demo of refactored functionality
- [ ] Stakeholder review at end of each phase

## Success Metrics

### Phase 1 Success:
- 2,000+ lines of duplicate code removed
- Single README file
- Consolidated dependencies
- No functionality loss

### Overall Success:
- 50%+ reduction in total codebase size
- Consistent architecture patterns
- Maintainable code structure  
- Improved developer onboarding time
- Faster feature development velocity

## Timeline Summary

| Phase | Duration | Risk | Dependency |
|-------|----------|------|------------|
| Phase 1 | 2-3 days | Low | None |
| Phase 2 | 1 week | Medium | Phase 1 complete |
| Phase 3 | 1 week | Low-Medium | Phase 2 complete |
| Phase 4 | 2 weeks | High | Phase 3 complete |

**Total Timeline:** 4-5 weeks for complete refactoring
**Minimum Viable:** Phase 1-2 (1.5-2 weeks) for major improvements
