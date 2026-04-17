# Testing Strategy

This document outlines the testing strategy for the AI Evaluation Engine. Our goal is to ensure the reliability, correctness, and performance of the application through a comprehensive and automated testing process.

## Guiding Principles

- **Test Pyramid:** We will follow the principles of the test pyramid, with a large base of fast unit tests, a smaller layer of integration tests, and a minimal set of end-to-end tests.
- **Automation:** All tests will be automated and integrated into our CI/CD pipeline to provide rapid feedback and prevent regressions.
- **Clarity and Maintainability:** Tests should be well-documented, easy to understand, and maintainable.

## Types of Tests

### 1. Unit Tests

- **Goal:** To verify that individual components (e.g., functions, classes) work correctly in isolation.
- **Scope:**
  - Backend: Business logic within the `src/services` directory. Utility functions in `src/utils`.
  - Frontend: React components, hooks, and utility functions.
- **Tools:**
  - Backend: `pytest`
  - Frontend: `Vitest` and `React Testing Library`
- **Location:**
  - Backend: `tests/unit`
  - Frontend: Alongside the component files (e.g., `*.test.tsx`).

### 2. Integration Tests

- **Goal:** To verify that different components of the application work together as expected.
- **Scope:**
  - Backend: API endpoints, ensuring they interact correctly with the database, cache, and other services.
  - Frontend: Data fetching, routing, and state management.
- **Tools:**
  - Backend: `pytest` with `TestClient` for FastAPI.
  - Frontend: `Vitest` and `React Testing Library` with mocked API responses.
- **Location:**
  - Backend: `tests/integration`
  - Frontend: `__tests__` or `tests` directory within `frontend/src`.

### 3. End-to-End (E2E) Tests

- **Goal:** To simulate real user workflows from the user's perspective, ensuring the entire application works as a cohesive whole.
- **Scope:** Critical user journeys, such as user registration, creating an evaluation, and viewing results.
- **Tools:** `Playwright` or `Cypress`.
- **Location:** A separate top-level `e2e` directory.

## Code Coverage

- **Goal:** We aim for a minimum of 80% code coverage for unit and integration tests.
- **Tool:** `pytest-cov` for the backend, `Vitest Coverage` for the frontend.
- **Reporting:** Coverage reports will be generated and published as part of the CI pipeline.

## How to Run Tests

### Backend

```bash
# Run all tests
pytest

# Run tests with coverage report
pytest --cov=src
```

### Frontend

```bash
# Run all tests
npm test
```

## Continuous Integration (CI)

Our CI pipeline, configured in `.github/workflows`, will automatically run all tests on every push and pull request to the `main` branch. A pull request will not be mergeable unless all tests pass and code coverage requirements are met.
