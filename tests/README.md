# AI Slide Generator - Testing Guide

## Overview

This directory contains comprehensive test suites for the AI Slide Generator, implementing a robust testing foundation that enables confident refactoring and development. The testing strategy uses **real Databricks authentication** with **mocked service responses** to ensure authentic integration testing while maintaining predictable test outcomes.

## Test Structure

```
tests/
├── unit/                 # Unit tests for individual components
│   ├── core/            # Tests for slide agent core logic
│   ├── tools/           # Tests for slide generation tools
│   ├── utils/           # Tests for utility functions
│   └── backend/         # Tests for backend components
├── integration/         # Integration tests for API and workflows
│   ├── api/             # FastAPI endpoint tests
│   └── workflows/       # Multi-component workflow tests
├── e2e/                 # End-to-end tests for complete user journeys
│   ├── frontend/        # React component integration tests
│   └── full_stack/      # Complete application workflow tests
├── performance/         # Load and performance tests
├── fixtures/            # Test data and mock objects
│   ├── data/            # Sample data for testing
│   └── mocks/           # Mock Databricks responses
└── conftest.py          # Global test configuration
```

## Running Tests

### Prerequisites

1. **Install development dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

2. **Configure Databricks authentication** (required for integration tests):
   ```bash
   # Option 1: Use Databricks CLI
   databricks configure
   
   # Option 2: Set environment variables
   export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
   export DATABRICKS_TOKEN="your-access-token"
   
   # Option 3: Use .databrickscfg file with default profile
   cat ~/.databrickscfg
   [DEFAULT]
   host = https://your-workspace.cloud.databricks.com
   token = your-access-token
   ```

### Basic Test Execution

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/unit/              # Unit tests only
pytest tests/integration/       # Integration tests only
pytest tests/e2e/              # End-to-end tests only
pytest tests/performance/       # Performance tests only

# Run tests with specific markers
pytest -m "unit"               # Only unit tests
pytest -m "integration"        # Only integration tests
pytest -m "e2e"               # Only end-to-end tests
pytest -m "performance"       # Only performance tests
pytest -m "databricks"        # Tests requiring Databricks auth
pytest -m "not slow"          # Skip slow tests
```

### Test Coverage

```bash
# Run tests with coverage reporting
pytest --cov=slide_generator --cov-report=html --cov-report=term-missing

# View HTML coverage report
open htmlcov/index.html

# Generate coverage report for CI
pytest --cov=slide_generator --cov-report=xml
```

### Frontend Tests

```bash
# Navigate to frontend directory
cd frontend/slide-generator-frontend

# Run React component tests
npm test

# Run tests with coverage
npm test -- --coverage --watchAll=false

# Run tests in CI mode
CI=true npm test
```

## Testing Strategy

### Databricks Integration Approach

Our testing strategy balances **authentic integration** with **test reliability**:

#### ✅ **What We Use Real Databricks For:**
- **Authentication**: Tests use actual `WorkspaceClient()` with default profile
- **Client Initialization**: Validates SDK integration and connection setup
- **Service Discovery**: Ensures endpoints and services are properly configured
- **Error Handling**: Tests authentic error conditions and recovery

#### ✅ **What We Mock:**
- **LLM Responses**: Mock serving endpoint responses for deterministic output
- **Genie SQL Results**: Mock SQL execution results for consistent data
- **Vector Search**: Mock search responses (feature being deprecated)
- **External API Calls**: Mock any calls outside Databricks ecosystem

#### 🎯 **Benefits of This Approach:**
- **Production-Like Testing**: Real authentication validates actual deployment scenarios
- **Predictable Results**: Mocked responses ensure consistent test outcomes
- **Fast Execution**: No actual LLM calls means tests run quickly
- **Cost Effective**: No compute or token usage during testing
- **Comprehensive Coverage**: Tests both happy path and error scenarios

### Test Categories

#### 1. Unit Tests (`tests/unit/`)
**Purpose**: Test individual functions and classes in isolation
**Coverage**: >90% line coverage for core components
**Execution Time**: <30 seconds total
**Dependencies**: Minimal external dependencies

```bash
# Example unit test execution
pytest tests/unit/core/test_agent_state.py -v
```

#### 2. Integration Tests (`tests/integration/`)
**Purpose**: Test component interactions and API endpoints
**Coverage**: All public APIs and critical workflows
**Execution Time**: 2-5 minutes
**Dependencies**: Real Databricks client, mocked responses

```bash
# Example integration test
pytest tests/integration/api/test_endpoints.py::TestChatEndpoints::test_chat_endpoint_valid_message -v
```

#### 3. End-to-End Tests (`tests/e2e/`)
**Purpose**: Test complete user workflows from UI to backend
**Coverage**: Critical user journeys and error recovery
**Execution Time**: 5-15 minutes
**Dependencies**: Full application stack

```bash
# Example E2E test
pytest tests/e2e/test_full_workflows.py::TestCompleteWorkflows::test_complete_slide_generation_workflow -v
```

#### 4. Performance Tests (`tests/performance/`)
**Purpose**: Validate performance characteristics and resource usage
**Coverage**: Load testing, memory usage, response times
**Execution Time**: 2-30 minutes (depending on test)
**Dependencies**: System monitoring tools

```bash
# Example performance test
pytest tests/performance/test_load.py::TestPerformanceLoad::test_concurrent_requests_load -v
```

## Test Markers

Tests are categorized using pytest markers for flexible execution:

```python
@pytest.mark.unit          # Unit tests
@pytest.mark.integration   # Integration tests  
@pytest.mark.e2e          # End-to-end tests
@pytest.mark.performance  # Performance tests
@pytest.mark.databricks   # Requires Databricks authentication
@pytest.mark.slow         # Long-running tests (>30 seconds)
```

### Running Specific Test Types

```bash
# Fast test suite (for development)
pytest -m "not slow and not performance"

# CI test suite (includes slower tests)
pytest -m "not performance"

# Full test suite (includes performance tests)
pytest

# Only tests that require Databricks
pytest -m "databricks"

# Only tests that don't require Databricks
pytest -m "not databricks"
```

## Test Configuration

### Global Configuration (`conftest.py`)

Key fixtures available to all tests:

- `authenticated_databricks_client`: Real WorkspaceClient with default profile
- `mock_databricks_responses`: Standardized mock responses for consistency
- `temp_output_dir`: Temporary directory for test outputs
- `sample_slide_html`: Valid slide HTML for validation testing
- `mock_slide_agent_state`: Predefined agent state for testing

### Environment Variables

Tests respect these environment variables:

```bash
# Databricks Configuration
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=your-access-token
DATABRICKS_PROFILE=default  # Optional, defaults to 'default'

# Test Configuration
PYTEST_TIMEOUT=300          # Test timeout in seconds
TEST_LOG_LEVEL=INFO         # Logging level for tests
SKIP_SLOW_TESTS=true       # Skip tests marked as 'slow'
```

## Writing New Tests

### Unit Test Template

```python
"""Test module for [component name]."""
import pytest
from slide_generator.tools.html_slides_agent import ComponentToTest


class TestComponentToTest:
    def test_basic_functionality(self):
        """Test basic functionality of component."""
        component = ComponentToTest()
        result = component.method_to_test()
        assert result is not None

    @pytest.mark.databricks
    def test_with_databricks_integration(self, authenticated_databricks_client, mock_databricks_responses):
        """Test component with Databricks integration."""
        component = ComponentToTest(client=authenticated_databricks_client)
        # Test uses real client but mocked responses
        result = component.method_requiring_databricks()
        assert result is not None
```

### Integration Test Template

```python
"""Integration tests for [feature name]."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.main import app
    return TestClient(app)


class TestFeatureIntegration:
    @pytest.mark.integration
    @pytest.mark.databricks
    def test_api_endpoint(self, client, mock_slide_agent_responses):
        """Test API endpoint integration."""
        response = client.post("/api/endpoint", json={"test": "data"})
        assert response.status_code == 200
```

### Performance Test Template

```python
"""Performance tests for [feature name]."""
import pytest
import time


@pytest.mark.performance
class TestFeaturePerformance:
    def test_response_time_baseline(self, client):
        """Test that feature meets response time requirements."""
        start_time = time.time()
        
        # Execute operation
        result = client.post("/api/operation")
        
        end_time = time.time()
        response_time = end_time - start_time
        
        assert response_time < 5.0  # Should complete within 5 seconds
        assert result.status_code == 200
```

## Test Requirements

### Code Coverage Goals
- **Unit Tests**: >90% line coverage for core components
- **Integration Tests**: All public API endpoints covered
- **E2E Tests**: All critical user workflows covered
- **Overall**: >80% total line coverage

### Performance Baselines
- **Single Request**: <10 seconds response time
- **Concurrent Load**: Handle 5 concurrent requests successfully
- **Memory Usage**: <200MB growth over 20 requests
- **Error Recovery**: System remains responsive after errors

### Quality Gates
- All tests must pass before merge
- No decrease in coverage percentage
- Performance tests must meet baseline requirements
- Linting and type checking must pass

## Continuous Integration

### GitHub Actions Workflow

Tests run automatically on:
- **Push** to `main`, `refactor-main`, or feature branches
- **Pull Request** creation or updates
- **Scheduled** runs for performance monitoring

### CI Test Matrix

1. **Backend Tests**
   - Python 3.11 on Ubuntu
   - Unit + Integration tests
   - Coverage reporting

2. **Frontend Tests**
   - Node.js 18 on Ubuntu
   - React component tests
   - Build verification

3. **E2E Tests**
   - Full stack integration
   - Complete user workflows
   - Cross-browser compatibility

4. **Performance Tests**
   - Load testing
   - Memory monitoring
   - Performance regression detection

### Failure Handling

- **Unit/Integration Test Failures**: Block merge, require fixes
- **Performance Test Failures**: Warning, manual review required
- **Flaky Tests**: Auto-retry up to 3 times
- **Timeout**: Tests must complete within 30 minutes

## Debugging Test Failures

### Common Issues and Solutions

#### 1. Databricks Authentication Failures
```bash
# Check authentication
databricks auth profiles list
databricks auth env

# Verify connection
databricks workspace list
```

#### 2. Mock Response Mismatches
```python
# Debug actual vs expected responses
print(f"Expected: {expected_response}")
print(f"Actual: {actual_response}")
```

#### 3. Flaky Tests
```bash
# Run test multiple times to identify flakiness
pytest tests/path/to/test.py::test_name -v --count=10
```

#### 4. Performance Test Failures
```bash
# Run performance tests with detailed output
pytest tests/performance/ -v -s --tb=short
```

### Test Data Debugging

```bash
# View test artifacts
ls -la tests/fixtures/data/

# Check test outputs
ls -la htmlcov/
open htmlcov/index.html
```

## Maintenance

### Regular Tasks

1. **Weekly**: Review test coverage reports
2. **Monthly**: Update performance baselines
3. **Quarterly**: Review and update test data
4. **Per Release**: Full test suite validation

### Updating Test Dependencies

```bash
# Update testing dependencies
pip install --upgrade pytest pytest-cov pytest-asyncio

# Update frontend testing dependencies
cd frontend/slide-generator-frontend
npm update @testing-library/react @testing-library/user-event
```

### Adding New Test Categories

1. Create new directory in `tests/`
2. Add `__init__.py` file
3. Update `pyproject.toml` markers
4. Add to CI workflow
5. Update this documentation

## Best Practices

### ✅ **DO:**
- Use descriptive test names that explain what is being tested
- Mock external dependencies to ensure test reliability
- Test both happy paths and error conditions
- Include performance assertions in integration tests
- Use real Databricks authentication for authentic testing
- Clean up resources in test teardown
- Group related tests in classes
- Use fixtures for common test setup

### ❌ **DON'T:**
- Make API calls to actual LLM endpoints in tests
- Hardcode credentials in test files
- Write tests that depend on external services being available
- Create tests that modify shared state without cleanup
- Skip writing tests for new functionality
- Use production data in tests
- Write overly complex test logic

### 🎯 **Testing Philosophy:**
- Tests should be **fast, reliable, and comprehensive**
- Real authentication provides confidence, mocked responses provide speed
- Every bug should have a corresponding test to prevent regression
- Performance is a feature and should be tested as such
- Tests are documentation - they show how the system should behave

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing Guide](https://fastapi.tiangolo.com/tutorial/testing/)
- [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
- [Databricks SDK Documentation](https://databricks-sdk-py.readthedocs.io/)
- [Performance Testing Best Practices](https://martinfowler.com/articles/practical-test-pyramid.html)

---

## Quick Reference

```bash
# Essential test commands
pytest                                    # Run all tests
pytest -m "not slow"                     # Skip slow tests
pytest --cov=slide_generator             # Run with coverage
pytest tests/unit/ -v                    # Unit tests only
pytest -k "test_chat"                    # Tests matching pattern
pytest --lf                             # Re-run last failed tests

# Frontend tests
cd frontend/slide-generator-frontend && npm test

# Performance monitoring
pytest tests/performance/ -v -s

# Generate coverage report
pytest --cov=slide_generator --cov-report=html
open htmlcov/index.html
```

For detailed information about specific test categories or troubleshooting, see the corresponding sections above.
