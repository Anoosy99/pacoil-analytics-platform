# PACOIL Analytics Platform

Working internship **demonstration with fictional data only**. No company data, industrial connections or control commands are included.

## Open it from GitHub

1. Select **Code → Codespaces → Create codespace on main**.
2. Wait for dependencies to install and port **8000** to open. If it does not open automatically, open the **Ports** tab and choose **Open in Browser** for port 8000.
3. Choose Owner, Technical manager or Supply-chain manager. Demo password: **`pacoil-demo`**.

Keep the forwarded port private. Codespaces is a development environment that stops when inactive, not permanent hosting; account usage limits apply. If the automatic startup fails, run the local startup command below in its terminal.

## Run locally (Python 3.12 recommended)

From this repository folder:

```bash
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or on macOS/Linux:

```bash
source .venv/bin/activate
```

Then:

```bash
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000. API documentation: http://localhost:8000/docs.

Local/Codespaces startup uses SQLite (`demo.db`) so no database installation is necessary. For the PostgreSQL version:

```bash
docker compose up --build
```

Open the same address. PostgreSQL data persists in the named `pgdata` volume. These database credentials are demo-only; the database port is not exposed to the host.

## Five-minute demonstration

1. Sign in as **Owner**: five industrial sources and one fictional inventory source are visible.
2. Watch readings refresh every five seconds; the browser polls every three seconds.
3. Pause **F601**. Wait more than 15 seconds: a delayed badge and attention entry appear, while its last reading remains visible.
4. Resume it. Fresh readings clear the delayed status. Missing historical readings are not invented.
5. Export CSV, then sign out and sign in as **Technical manager**. Inventory is absent from both API responses and exports.
6. Sign in as **Supply-chain manager**: only the fictional stock source is available.

All values, sources' metric assignments, freshness thresholds and simulated patterns are illustrative, not verified plant specifications. Charts scale to the visible range. “Recent mean” covers the latest 60 stored observations, not a guaranteed five-minute window.

## What works

- FastAPI backend, responsive dashboard, SQLAlchemy storage.
- Automatic deterministic simulation, startup history, persistent readings and import counts.
- Timestamp/source deduplication and basic numeric validation.
- Source freshness detection, pause/resume demonstration and collection-error display.
- Server-side role filtering for reads/exports; owner-only simulation controls.
- Expiring demo sessions, logout, CSV export (latest 10,000 authorised records).
- PostgreSQL Compose configuration, Codespaces setup and test workflow.

## Architecture and boundaries

The demo connector generates records that pass through `ingest()` before database storage. Replace the generator with an approved source connector and mapping after inspecting actual company exports. No production source adapter is implemented yet.

For simplicity, collection runs in the FastAPI lifespan. **Run exactly one application process/worker.** Simulation pause state and login sessions are in memory and reset on restart. For deployment beyond this demo, move collection to a separately supervised worker with persistent checkpoints, retry/backfill handling and import monitoring. Implement migrations, company SSO or individual accounts, approved permissions, secret management, HTTPS, backups, retention and deployment monitoring before admitting real data. The shared password and self-selected roles are intentionally demo-only.

The database grows while the demo runs; retention is not yet implemented. Initial history is seeded only on an empty database. PostgreSQL is supported by configuration; local automated tests use SQLite.

## Tests

```bash
python -m pytest -q
```

Tests cover unauthorised access, role isolation in dashboards/exports, owner-only controls, stale-data detection, recovery, deduplication, invalid values and logout.

GitHub stores and tests the source code. GitHub Pages cannot run this Python backend. No production site is deployed by this repository.
