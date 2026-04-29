# wal2json Prototype

A minimal CDC (Change Data Capture) prototype using **PostgreSQL 17**, the **wal2json** logical decoding plugin, and **Python**.

<img width="2732" height="2048" alt="localhost_8080_(iPad Pro) (1)" src="https://github.com/user-attachments/assets/bc69172f-447f-488a-8afb-1cf81224cd51" />

## Architecture


```
┌──────────────────────────────────────────────────────────────┐
│  Docker Compose                                              │
│                                                              │
│  ┌─────────────┐    WAL (logical)    ┌──────────────────┐   │
│  │  PostgreSQL │ ─────────────────▶  │  consumer.py     │   │
│  │  + wal2json │                     │  (repl slot)     │   │
│  └──────┬──────┘                     └──────────────────┘   │
│         │ SQL (INSERT/UPDATE/DELETE)                         │
│  ┌──────┴──────┐                     ┌──────────────────┐   │
│  │ producer.py │                     │ dashboard.py     │   │
│  └─────────────┘                     │ + web/index.html │   │
│                                      │ (SSE live UI)    │   │
│                                      └──────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

| Service    | Description |
|------------|-------------|
| `postgres` | PostgreSQL 17 with `wal2json` installed; `wal_level=logical` |
| `consumer` | Python script that opens a replication slot and prints WAL events |
| `dashboard` | Flask app that serves the frontend UI and streams live stats via Server-Sent Events |
| `producer` | Python script that generates a stream of DML changes (manual profile) |

## Quick start

### 1. Start PostgreSQL + consumer + dashboard

```bash
docker compose up --build
```

The consumer will wait for Postgres to be healthy, create the `wal2json_slot` replication slot, then begin streaming.

The dashboard will also start and expose a live UI at:

```text
http://localhost:8080
```

It fetches initial stats from `/api/stats` and then subscribes to `/events` for real-time updates.

### 2. Start the producer (separate terminal)

```bash
docker compose run --rm producer
```

The producer inserts orders, updates statuses, deletes cancelled orders, and adjusts product stock every 2 seconds. You will see colour-coded events appear in the consumer output:

```
--- BEGIN  xid=742  ts=2026-04-23T10:00:01.123Z ---
[INSERT] public.orders
  data     : {"id": 1, "customer": "Alice", "product": "Widget A", ...}
--- COMMIT ---

--- BEGIN  xid=743  ts=2026-04-23T10:00:03.456Z ---
[UPDATE] public.orders
  data     : {"id": 1, "customer": "Alice", "product": "Widget A", "status": "shipped", ...}
  identity : {"id": 1}
--- COMMIT ---
```

At the same time, the frontend dashboard updates the status counters live with flip-style animations as rows change.

### 3. Tear down

```bash
docker compose down -v   # -v also removes the pg_data volume
```

## Configuration

All services read their settings from environment variables. Override them in `docker-compose.yml` or via `--env`:

| Variable          | Default         | Description                          |
|-------------------|-----------------|--------------------------------------|
| `PGHOST`          | `postgres`      | Postgres hostname                    |
| `PGPORT`          | `5432`          | Postgres port                        |
| `PGDATABASE`      | `testdb`        | Database name                        |
| `PGUSER`          | `postgres`      | Database user                        |
| `PGPASSWORD`      | `postgres`      | Database password                    |
| `SLOT_NAME`       | `wal2json_slot` | Logical replication slot name        |
| `CHANGE_INTERVAL` | `2`             | Seconds between producer operations  |
| `DASHBOARD_PORT`  | `8080`          | Frontend/dashboard HTTP port         |

## SQL-only version

If you only want PostgreSQL + wal2json (without the Python producer/consumer/dashboard), use the SQL-only setup:

- [postgres-sql-only/README.md](postgres-sql-only/README.md)

## Running the Python scripts locally (no Docker)

```bash
cd python
pip install -r requirements.txt

# terminal 1 – assumes Postgres is reachable on localhost:5432
PGHOST=localhost python consumer.py

# terminal 2
PGHOST=localhost python producer.py

# terminal 3 (frontend + API)
PGHOST=localhost DASHBOARD_PORT=8080 python dashboard.py
```

Then open `http://localhost:8080` in your browser.

## Project layout

```
.
├── docker-compose.yml
├── postgres/
│   ├── Dockerfile          # postgres:17 + postgresql-17-wal2json
│   └── init.sql            # creates orders and products tables
└── python/
    ├── Dockerfile
    ├── requirements.txt    # psycopg2-binary
    ├── consumer.py         # logical replication consumer
    ├── dashboard.py        # Flask dashboard + SSE endpoint
    ├── producer.py         # DML workload generator
    └── web/
        └── index.html      # live frontend UI
```

## References

- [wal2json](https://github.com/eulerto/wal2json) – output plugin for logical decoding
- [psycopg2 replication support](https://www.psycopg.org/docs/extras.html#replication-support-objects)
- [PostgreSQL logical replication](https://www.postgresql.org/docs/current/logical-replication.html)
