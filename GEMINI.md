# VeloPulse - Agent Instructions & Workspace Guidelines

These instructions guide the agent's behavior, container operations, environment management, and quality assurance workflows for VeloPulse.

---

## 1. Environment Variables & `.env` Auditing

- **Proactive Validation**: Before starting Docker services, running tasks, or running external integrations, always check `.env` to verify required variables are present and not empty.
- **Immediate User Notification**: If an operation or service profile requires a variable that is missing, empty, or set to placeholder values, **halt and immediately notify the user** with instructions on what variable to add and where to obtain it.
  - **Ngrok Tunnel (`--profile tunnel`)**: Requires `NGROK_AUTHTOKEN`. Notify the user if attempting to start `ngrok` without a valid token from [ngrok dashboard](https://dashboard.ngrok.com/).
  - **Strava Integration**: If `STRAVA_MOCK_MODE=false`, require `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, and `STRAVA_VERIFY_TOKEN`.
  - **Telegram Bot**: Requires valid `TELEGRAM_BOT_TOKEN` from [@BotFather](https://t.me/BotFather) when testing live Telegram dispatches.
- **Security & Secret Preservation**:
  - Never commit `.env` to git.
  - Never print sensitive credentials or full tokens in conversation outputs or logs.
  - Always update [.env.example](file:///E:/all/projects/VeloPulse/.env.example) when introducing new environment variables.

---

## 2. Docker & Container Lifecycle Rules

- **Automatic Rebuild on Dependency/Config Changes**:
  - Whenever [pyproject.toml](file:///E:/all/projects/VeloPulse/pyproject.toml), [Dockerfile](file:///E:/all/projects/VeloPulse/Dockerfile), or [docker-compose.yml](file:///E:/all/projects/VeloPulse/docker-compose.yml) are modified, immediately rebuild and recreate the containers:
    ```bash
    docker compose up -d --build
    ```
- **Service Reloads**:
  - `velopulse_api` runs with `--reload` mounted to `./src`, but background worker `velopulse_worker` (Taskiq) may need a restart if task definitions or imported models change:
    ```bash
    docker compose restart worker
    ```
- **Health Verification**:
  - Check container status after any deployment or restart:
    ```bash
    docker compose ps
    ```
  - Inspect logs for errors if containers fail to stay healthy:
    ```bash
    docker compose logs --tail 50 <service>
    ```

---

## 3. Testing & Verification Standards

- **In-Container Execution**: Always execute tests inside the running `api` container where all dependencies, PostgreSQL, and Redis connections are live:
  ```bash
  docker compose exec -T api pytest -v
  ```
- **Linting and Typing**:
  - Maintain clean code with Ruff and Mypy:
    ```bash
    docker compose exec -T api ruff check .
    docker compose exec -T api mypy src
    ```
- **Non-Negotiable Green Bar**:
  - Never commit changes or report a task completed until all unit and integration tests pass.
  - When fixing bugs or implementing new features, always add or update corresponding test cases in `tests/`.

---

## 4. Database & Migration Rules

- **Alembic Migrations**:
  - When modifying SQLAlchemy models in `src/velopulse/models/`, generate migrations:
    ```bash
    docker compose exec -T api alembic revision --autogenerate -m "<description>"
    ```
  - Apply migrations:
    ```bash
    docker compose exec -T api alembic upgrade head
    ```

---

## 5. Communication & Git Workflow

- Keep responses concise, dry, and technical.
- Always provide clickable file links using `[filename](file:///path/to/file)` format.
- Ensure commits are focused and follow conventional commit conventions (`feat: ...`, `fix: ...`, `test: ...`).
