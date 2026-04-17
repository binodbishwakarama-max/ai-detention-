# AI Evaluation Engine

Production-grade backend for evaluating AI model outputs at enterprise scale.

## Architecture

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Client   │────▶│  FastAPI  │────▶│ Postgres │
│  (REST)   │     │   API    │     │   16     │
└──────────┘     └──┬──┬────┘     └──────────┘
                    │  │
              ┌─────┘  └─────┐
              ▼              ▼
        ┌──────────┐  ┌──────────┐
        │  Redis 7  │  │  Celery  │
        │  (cache)  │  │ Workers  │
        └──────────┘  └──┬───────┘
                         │
                    ┌────▼─────┐
                    │  MinIO   │
                    │  (S3)    │
                    └──────────┘
```

## Quick Start

```bash
# Clone and start all services
git clone <repo-url> eval-engine
cd eval-engine
cp .env.example .env
docker compose up -d

# API is available at http://localhost:8000
# Frontend is available at http://localhost:5173
# Swagger docs at http://localhost:8000/docs
# MinIO console at http://localhost:9001
```

## Contributing

We welcome contributions! Please see our [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and coding standards.

## Next Steps

This project is evolving. Our current focus is:
- **Enhanced Analysis**: Integrating more LLM providers for parallel evaluation.
- **E2E Testing**: Expanding Playwright coverage for complex user workflows.
- **Performance**: Optimizing the Celery worker pipeline for high-concurrency inference.

For a detailed view of our future plans, see [ROADMAP.md](ROADMAP.md).

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register user & organization |
| POST | `/api/v1/auth/login` | Authenticate (returns JWT) |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET | `/api/v1/auth/me` | Get current user profile |
| POST | `/api/v1/auth/api-keys` | Create API key |
| DELETE | `/api/v1/auth/api-keys/{id}` | Revoke API key |
| POST | `/api/v1/evaluations/configs` | Create evaluation config |
| GET | `/api/v1/evaluations/configs` | List configs (paginated) |
| GET | `/api/v1/evaluations/configs/{id}` | Get config by ID |
| PATCH | `/api/v1/evaluations/configs/{id}` | Update config |
| DELETE | `/api/v1/evaluations/configs/{id}` | Soft-delete config |
| POST | `/api/v1/evaluations/runs` | Trigger evaluation run |
| GET | `/api/v1/evaluations/runs` | List runs (filterable) |
| GET | `/api/v1/evaluations/runs/{id}` | Get run status |
| POST | `/api/v1/evaluations/runs/{id}/cancel` | Cancel run |
| POST | `/api/v1/datasets` | Initiate dataset upload |
| POST | `/api/v1/datasets/{id}/confirm` | Confirm upload |
| GET | `/api/v1/datasets` | List datasets |
| GET | `/api/v1/datasets/{id}` | Get dataset |
| DELETE | `/api/v1/datasets/{id}` | Delete dataset |
| GET | `/api/v1/metrics` | List available metrics |
| POST | `/api/v1/metrics` | Create custom metric |
| GET | `/api/v1/results/run/{id}` | Get run results |
| GET | `/api/v1/results/run/{id}/summary` | Get results summary |
| POST | `/api/v1/results/run/{id}/export` | Export to S3 |
| GET | `/api/v1/health` | Liveness probe |
| GET | `/api/v1/health/ready` | Readiness probe |
| POST | `/api/v1/submissions` | Create a startup submission |
| GET | `/api/v1/submissions` | List submissions (paginated) |
| GET | `/api/v1/submissions/{id}` | Get submission detail |
| PATCH | `/api/v1/submissions/{id}` | Update a submission |
| DELETE | `/api/v1/submissions/{id}` | Soft-delete a submission |
| POST | `/api/v1/submissions/{id}/evaluate` | Trigger evaluation pipeline |

## Project Structure

```
src/
├── api/                 # FastAPI routes
│   ├── deps.py         # Dependency injection (auth, pagination)
│   └── v1/             # API version 1
│       ├── auth.py     # Authentication endpoints
│       ├── datasets.py # Dataset management
│       ├── evaluations.py # Evaluation CRUD
│       ├── health.py   # Health checks
│       ├── metrics.py  # Metric management
│       └── results.py  # Result queries
├── middleware/          # Request processing
│   ├── audit.py        # Audit logging
│   ├── correlation.py  # Request ID propagation
│   ├── error_handler.py # Structured exceptions
│   └── rate_limiter.py # Redis sliding window
├── models/             # SQLAlchemy ORM
│   ├── base.py         # UUID7 PK, soft-delete mixin
│   ├── organization.py # Multi-tenant root
│   ├── user.py         # Authenticated entity
│   ├── api_key.py      # Programmatic credentials
│   ├── dataset.py      # S3-backed datasets
│   ├── evaluation.py   # Config, Run, Result
│   ├── metric.py       # Evaluation metrics
│   └── audit_log.py    # Immutable audit trail
├── schemas/            # Pydantic v2 request/response
├── services/           # Business logic
│   ├── auth_service.py
│   ├── evaluation_service.py
│   ├── dataset_service.py
│   ├── metric_service.py
│   ├── result_service.py
│   ├── cache_service.py
│   ├── storage_service.py
│   ├── webhook_service.py
│   └── audit_service.py
├── workers/            # Celery async tasks
│   ├── celery_app.py   # Celery configuration
│   ├── evaluation_worker.py
│   ├── export_worker.py
│   └── cleanup_worker.py
├── utils/              # Shared utilities
├── config.py           # Pydantic settings
├── database.py         # Async SQLAlchemy
├── redis_client.py     # Redis connection
├── s3_client.py        # S3/MinIO client
├── security.py         # JWT, bcrypt, API keys
└── main.py             # FastAPI app factory
```

## Design Decisions

- **UUID7 primary keys**: Time-ordered for B-tree index locality
- **Soft deletes**: GDPR right-to-erasure via scheduled hard-delete workers
- **Append-only audit logs**: SOC2 CC6.1 compliant
- **Presigned S3 uploads**: Zero bandwidth through API
- **Sliding window rate limiting**: Smoother than fixed window
- **acks_late Celery tasks**: At-least-once delivery guarantee
- **HMAC-SHA256 webhooks**: Tamper-proof delivery notifications

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v --asyncio-mode=auto
```

## Kubernetes Deployment

```bash
kubectl apply -f k8s/deployment.yaml
```
