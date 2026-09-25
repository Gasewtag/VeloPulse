# VeloPulse Engineering Roadmap & Sprint Execution Plan

This document establishes the sprint-by-sprint engineering plan for **VeloPulse**. Each phase maps directly to an isolated Git feature branch, technical deliverables, and an unambiguous Definition of Done (DoD).

---

## 🗺️ Sprint Overview Matrix

```
Sprint 00 [docs/initial-project-specification]  ──► Core specs, architecture & git config
      │
Sprint 01 [feat/01-skeleton-docker]             ──► Python 3.12, FastAPI skeleton, Docker Compose, Ruff/Mypy
      │
Sprint 02 [feat/02-db-models-migrations]        ──► SQLAlchemy 2.0 async models, Alembic, PostgreSQL 16
      │
Sprint 03 [feat/03-strava-webhook-auth]         ──► Strava OAuth2 handshake, webhook subscription endpoint
      │
Sprint 04 [feat/04-taskiq-background-workers]   ──► Taskiq + Redis broker, activity ingestion task & deduplication
      │
Sprint 05 [feat/05-weather-enrichment]          ──► Open-Meteo client, geo-temporal caching & weather multiplier
      │
Sprint 06 [feat/06-wear-calculation-engine]     ──► Torque/elevation factor, wear points engine, threshold events
      │
Sprint 07 [feat/07-telegram-bot-notifications]  ──► aiogram 3.x bot, interactive wear alerts & inline keyboards
      │
Sprint 08 [feat/08-maintenance-scheduler-history]──► Maintenance logs, lifespan resets, component swap workflows
      │
Sprint 09 [feat/09-observability-ci-cd]         ──► Prometheus metrics, health checks, GitHub Actions CI matrix
```

---

## Sprint 00: Project Foundation & Technical Specifications
* **Branch:** `docs/initial-project-specification`
* **Objective:** Establish architectural clarity, component wear calculation models, database relational designs, and repository guidelines before code execution.
* **Key Deliverables:**
  - `README.md`: Problem statement, architecture flowchart, domain overview, stack breakdown, local quickstart.
  - `ARCHITECTURE.md`: Deep dive into webhook vs. polling, mathematical wear formulas, decoupled notifications, complete DDL and indexing strategy.
  - `ROADMAP.md`: Sprint-by-sprint breakdown with branches and DoD.
  - `.gitignore`: Standardized rules for Python 3.12, virtual environments, Docker, IDEs, and OS artifacts.
* **Definition of Done (DoD):**
  - [x] All 4 foundational documentation and configuration files committed.
  - [x] Mermaid diagrams render without syntax errors.
  - [x] DDL specifications and formulas mathematically verified.

---

## Sprint 01: Project Skeleton, Environment & Containerization
* **Branch:** `feat/01-skeleton-docker`
* **Objective:** Set up modern Python 3.12 application packaging, Docker Compose multi-service topology, code quality tooling, and base FastAPI bootstrap.
* **Key Deliverables:**
  - Modern `pyproject.toml` with `hatchling` or `setuptools` build backend, defining project metadata and dependency groups (`dev`, `test`, `prod`).
  - Strict code quality configuration: `ruff` (linter & formatter), `mypy` with `--strict` flags, and `pre-commit` hooks.
  - Multi-stage `Dockerfile` optimizing image size and layer caching.
  - `docker-compose.yml` orchestrating FastAPI API gateway, PostgreSQL 16, and Redis 7 with persistent named volumes and health checks.
  - Base FastAPI application initialization with `/health` probe endpoint.
* **Definition of Done (DoD):**
  - `docker compose up --build` launches API, DB, and Redis with all containers reporting healthy status.
  - `curl -f http://localhost:8000/health` returns `{"status": "healthy", "version": "0.1.0"}`.
  - `ruff check .`, `ruff format --check .`, and `mypy src/` pass with zero errors or warnings.

---

## Sprint 02: Async Persistence Layer, Database Models & Alembic Migrations
* **Branch:** `feat/02-db-models-migrations`
* **Objective:** Implement the complete relational schema using SQLAlchemy 2.0 Async, configure Alembic migrations, and validate database interactions using `asyncpg`.
* **Key Deliverables:**
  - Async database engine and session factory (`async_sessionmaker`) with connection pool tuning (`pool_size=20`, `max_overflow=10`).
  - Declarative SQLAlchemy models: `User`, `Bike`, `Component`, `Activity`, `ActivityComponentWear`, and `MaintenanceLog`.
  - Alembic configuration supporting asynchronous migrations (`env.py` async runner).
  - Initial database migration generating all tables, enums, check constraints, foreign keys, and indexes.
  - Integration tests using `testcontainers-postgres` or local test database verifying model relationships, cascade deletes, and constraints.
* **Definition of Done (DoD):**
  - `alembic upgrade head` applies cleanly from scratch on an empty PostgreSQL instance.
  - `alembic downgrade base` cleanly reverts all schema elements without orphan dependencies.
  - Automated tests verify CRUD operations for all entities with >90% code coverage on model definitions.

---

## Sprint 03: Strava OAuth 2.0 Flow & Webhook Ingestion Gateway
* **Branch:** `feat/03-strava-webhook-auth`
* **Objective:** Build athlete onboarding via Strava OAuth 2.0 and establish high-speed webhook ingestion meeting Strava's sub-2-second verification SLA.
* **Key Deliverables:**
  - Strava OAuth 2.0 endpoints:
    * `/api/v1/auth/strava/authorize`: Generates authorization URL with `activity:read_all,profile:read_all` scopes.
    * `/api/v1/auth/strava/callback`: Exchanges authorization code for access/refresh tokens, upserts `User` record, and imports active bikes/gear.
  - Strava Webhook endpoints:
    * `GET /api/v1/webhooks/strava`: Handles `hub.challenge` verification handshake returning JSON response in `<50ms`.
    * `POST /api/v1/webhooks/strava`: Ingests `activity.create` events, validates signature, pushes payload to Redis queue, and immediately returns `HTTP 204 No Content`.
  - Webhook subscription management CLI command (`python -m velopulse.cli.strava register-webhook`).
* **Definition of Done (DoD):**
  - [x] Webhook verification challenge passes Strava's automated subscription validation tests.
  - [x] Incoming webhook POST requests respond with `204 No Content` within an SLA of `<50ms` under simulated load.
  - [x] OAuth flow securely saves and refreshes athlete tokens with encrypted refresh token storage (`Fernet` symmetric encryption).
  - [x] Fully decoupled dual-mode architecture: Production Strava v3 REST/OAuth API + Offline Sandbox (`STRAVA_MOCK_MODE=true`) ensuring development and testing are unblocked by Strava's June 2026 Developer API subscriber policy.
  - [x] Strava webhook lifecycle & event simulation CLI implemented (`velopulse.cli.strava`).
  - [x] Automated test suite with 39 passing tests and 88% overall test coverage.

> [!NOTE]
> **Strava API Policy & Offline Testing Note (June 2026):**
> Creating Strava Developer API applications currently requires an active paid Strava subscription. VeloPulse implements a resilient Mock/Sandbox mode (`STRAVA_MOCK_MODE=true` in `.env`) enabling full local development and end-to-end testing without external network dependencies or API credentials. For live production environments, set `STRAVA_MOCK_MODE=false` and insert standard Strava credentials. Public tunneling for real-world webhook validation is supported via optional `ngrok` profile (`docker compose --profile tunnel up ngrok`).

---

## Sprint 04: Taskiq Distributed Worker & Event Processing Pipeline
* **Branch:** `feat/04-taskiq-background-workers`
* **Objective:** Establish the asynchronous background processing infrastructure using Taskiq, Redis broker, and idempotent task execution.
* **Key Deliverables:**
  - Taskiq broker and worker initialization module (`velopulse.tasks.broker:broker`).
  - Activity Ingestion Task (`ingest_activity_task`):
    * Consumes raw webhook payloads from Redis.
    * Enforces distributed lock to prevent duplicate concurrent ingestion of the same activity.
    * Fetches detailed activity summary and GPS coordinate stream from Strava REST API v3 using user access token.
    * Automatically refreshes expired Strava tokens via OAuth refresh handler.
    * Persists `Activity` record and associates with matching `Bike` based on `gear_id`.
  - Taskiq worker container definition in `docker-compose.yml`.
  - Dead-Letter Queue (DLQ) configuration for unrecoverable task failures with backoff retry policy.
* **Definition of Done (DoD):**
  - Emitting a simulated webhook event triggers Taskiq worker execution and creates the corresponding `Activity` in PostgreSQL.
  - Duplicate webhook events for the same `strava_activity_id` are identified and safely ignored without double ingestion.
  - Worker gracefully handles and retries transient Strava 429/500 API responses.

---

## Sprint 05: Geo-Temporal Weather Telemetry Integration (Open-Meteo)
* **Branch:** `feat/05-weather-enrichment`
* **Objective:** Connect the ride processing pipeline to Open-Meteo's historical archive to accurately detect rain, wet road surfaces, and temperature.
* **Key Deliverables:**
  - Async Open-Meteo API client (`OpenMeteoClient`) with rate limiting and connection reuse via `httpx.AsyncClient`.
  - Geo-temporal weather extraction:
    * Extracts start latitude, longitude, and ride timestamp window.
    * Retrieves hourly precipitation (mm), rain indicator, snowfall, and temperature.
  - Weather Telemetry Enrichment Task (`enrich_weather_task`):
    * Computes ride surface condition classification (`DRY`, `DAMP`, `WET_RAIN`, `MUD_GRIT`).
    * Updates `Activity` record with `is_weather_enriched = true` and detailed JSONB weather metrics.
  - Local caching layer in Redis for repeated geographic lookups within the same hour bucket.
* **Definition of Done (DoD):**
  - [x] Historical rides ingested with GPS coordinates receive verified meteorological data from Open-Meteo.
  - [x] Weather conditions properly classify dry vs. rainy rides with simulated and real GPS datasets.
  - [x] Unit tests with mocked Open-Meteo responses achieve >90% coverage for the weather module.
  - [x] Geo-temporal Redis caching layer implemented with ~1.1km grid precision and 7-day TTL.
  - [x] End-to-end Taskiq pipeline handoff from activity ingestion to weather enrichment.


---

## Sprint 06: Component Wear Calculation Engine & Degradation Models
* **Branch:** `feat/06-wear-calculation-engine`
* **Objective:** Implement the physics-based wear calculation algorithms and trigger domain events when component lifespans cross critical thresholds.
* **Key Deliverables:**
  - Wear Calculation Domain Service:
    * Implements the multi-factor equation: $\Delta WP = D \times E_f \times W_m \times C_m$.
    * Calculates Elevation Factor ($E_f$) from elevation gain and gradient.
    * Applies Environmental Multiplier ($W_m$) derived from Sprint 05 weather classification.
    * Applies component-specific coefficient ($C_m$) for chains, cassettes, brake pads, tires, and suspension.
  - Batch wear attribution:
    * Creates `ActivityComponentWear` rows for all active components attached to the ride's `Bike`.
    * Atomically updates `Component.current_wear_points` and shifts component status (`OPTIMAL`, `ATTENTION_NEEDED`, `REPLACE_RECOMMENDED`).
  - Domain Event Dispatcher:
    * Emits `ComponentThresholdExceededEvent` when a component crosses 80%, 100%, or 120% wear.
* **Definition of Done (DoD):**
  - [x] Mathematical calculation unit test suite validates exact wear points against benchmark reference tables across dry flat, rainy hilly, and muddy gravel test fixtures.
  - [x] Status transitions strictly adhere to the state machine rules defined in `ARCHITECTURE.md`.
  - [x] Database updates execute within a single atomic database transaction per activity.
  - [x] Seamless Taskiq background processing with Redis distributed lock and idempotency.
  - [x] Pipeline handoff connected from weather enrichment to wear calculation.


---

## Sprint 07: Decoupled Notification Dispatcher & Telegram Bot Interface
* **Branch:** `feat/07-telegram-bot-notifications`
* **Objective:** Deploy an interactive Telegram bot using `aiogram 3.x` to alert cyclists of component wear and facilitate instant maintenance logging.
* **Key Deliverables:**
  - Asynchronous Telegram Bot service using `aiogram 3.x`:
    * Deep-linking account onboarding: `/start {token}` links Telegram chat ID to VeloPulse user account.
    * Status inspection commands: `/status`, `/bikes`, `/components`.
  - Decoupled Notification Dispatcher:
    * Consumes `ComponentThresholdExceededEvent`.
    * Generates rich formatted Telegram alert cards with wear progression bars:
      `[████████░░] 82% - Chain on Trek Checkpoint needs cleaning & lubrication`.
    * Attaches actionable inline keyboards: `[✅ Clean & Lube]`, `[🔄 Replace Part]`, `[⏸️ Snooze]`.
  - Callback query handlers:
    * Intercepts button clicks, acknowledges Telegram callback, and schedules maintenance updates.
* **Definition of Done (DoD):**
  - Users can link their Telegram accounts seamlessly via `/start` deeplink.
  - Simulated wear threshold event delivers an immediate interactive push notification with inline buttons.
  - Clicking `[✅ Clean & Lube]` successfully updates component state and updates the Telegram message in-place.

---

## Sprint 08: Interactive Maintenance Logging, Wear History & Manual Adjustments
* **Branch:** `feat/08-maintenance-scheduler-history`
* **Objective:** Provide a complete audit trail for maintenance events, component replacement workflows, and retroactive wear recalibration.
* **Key Deliverables:**
  - Maintenance service:
    * Records `MaintenanceLog` entries (date, cost, service type, technician notes).
    * Handles component replacement: archives previous component to `retired` status, resets wear counters, and registers new component baseline.
  - Telegram conversational FSM (Finite State Machine):
    * Step-by-step wizard for logging maintenance: `/service` -> select bike -> select component -> enter notes/cost.
  - Historical reporting endpoint:
    * `GET /api/v1/bikes/{bike_id}/maintenance`: Returns comprehensive maintenance timeline with accumulated odometer and cost tracking.
* **Definition of Done (DoD):**
  - Full component replacement workflow resets wear to 0.00 while preserving historical wear records.
  - FSM wizard in Telegram handles user cancellation, validation errors, and completes log entry creation.
  - API endpoints verified with full test coverage and OpenAPI documentation.

---

## Sprint 09: Production Hardening, Observability, CI/CD Pipeline & Deployment
* **Branch:** `feat/09-observability-ci-cd`
* **Objective:** Harden application security, add distributed metrics/tracing, establish GitHub Actions CI/CD pipeline, and prepare production deployment manifests.
* **Key Deliverables:**
  - Observability & Telemetry:
    * Prometheus `/metrics` endpoint exposing HTTP latency, queue backlog, and calculation durations.
    * Structured JSON logging with correlation IDs linking webhook requests to background worker tasks.
  - GitHub Actions Workflow (`.github/workflows/ci.yml`):
    * Automated test matrix against Python 3.12.
    * Linting (`ruff check`), formatting (`ruff format --check`), static typing (`mypy`).
    * Full integration test execution against live PostgreSQL and Redis services.
  - Production readiness:
    * Production Dockerfile with unprivileged non-root user (`appuser`).
    * Production `docker-compose.prod.yml` with reverse proxy (Caddy / Nginx) and TLS termination.
    * Automated database backup scripts and secret management documentation.
* **Definition of Done (DoD):**
  - CI pipeline passes on GitHub Actions with 100% green status on all checks.
  - Test suite maintains >85% overall code coverage.
  - Production container boots cleanly as non-root user with zero critical security vulnerabilities.
