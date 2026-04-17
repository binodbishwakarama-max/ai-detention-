# Contributing to AI Evaluation Engine

First off, thank you for considering contributing to the AI Evaluation Engine! It’s people like you that make it a great tool for everyone.

## Development Setup

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker and Docker Compose

### Fast Track (Docker)
The easiest way to get started is using Docker Compose:
```bash
docker-compose up -d
```
This spins up the API, Frontend, Workers, and all infrastructure (Postgres, Redis, MinIO).

### Manual Setup (for Backend Developers)
1. **Clone and Setup Virtualenv:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   pip install -e ".[dev]"
   ```
2. **Environment Variables:**
   Copy `.env.example` to `.env` and adjust as needed.
3. **Run Migrations:**
   ```bash
   alembic upgrade head
   ```
4. **Start API:**
   ```bash
   uvicorn src.main:app --reload
   ```

### Manual Setup (for Frontend Developers)
1. **Navigate to Frontend:**
   ```bash
   cd frontend
   npm install
   ```
2. **Start Dev Server:**
   ```bash
   npm run dev
   ```

## Coding Standards

### Backend
- **Type Hints**: All function signatures must include type hints.
- **Async/Await**: We use `asyncpg` and `httpx`. Ensure all I/O is non-blocking.
- **Logging**: Use `structlog` for structured logging.
- **Validation**: Use Pydantic models in `src/schemas/`.

### Frontend
- **Typescript**: No `any`. Use interfaces defined in `src/types/`.
- **Styling**: Use the existing Vanilla CSS design system (see `index.css`).
- **State Management**: Use `@tanstack/react-query` for server state.

## Pull Request Process

1. Create a new branch for your feature or bugfix.
2. Ensure tests pass:
   ```bash
   pytest
   cd frontend && npm run lint
   ```
3. Update documentation if you've added or changed features.
4. Submit a Pull Request against the `main` branch.

## Testing Strategy
- **Unit Tests**: Place in `tests/unit/`. Focus on business logic.
- **Integration Tests**: Place in `tests/integration/`. Focus on API endpoints.
- **E2E Tests**: Use Playwright (located in `frontend/e2e/`).
