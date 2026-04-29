# SQL-Only wal2json Demo

This folder contains a minimal PostgreSQL-only setup for testing logical decoding with the `wal2json` plugin.

It starts one container:
- PostgreSQL 17
- `wal2json` installed
- logical replication enabled (`wal_level=logical`)
- schema + logical replication slot initialized from `init.sql`

## Files

- `docker-compose.yml`: Runs PostgreSQL with logical replication settings.
- `Dockerfile`: Extends `postgres:17` and installs `postgresql-17-wal2json`.
- `init.sql`: Creates the `orders` table, sets replica identity, and creates a logical replication slot.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose)

## Start

From this directory:

```bash
docker compose up --build
```

Postgres is exposed on:

- Host: `localhost`
- Port: `5432`
- Database: `testdb_sql_only`
- User: `postgres`
- Password: `postgres`

## Verify wal2json and slot setup

Open a psql shell inside the container:

```bash
docker compose exec postgres psql -U postgres -d testdb_sql_only
```

Check the logical slot:

```sql
SELECT slot_name, plugin, slot_type, active
FROM pg_replication_slots
WHERE slot_name = 'wal2json_replication';
```

Expected plugin is `wal2json` and slot type is `logical`.

## Generate sample WAL changes

In psql, run:

```sql
INSERT INTO orders (customer, product, quantity, price, status)
VALUES ('Alice', 'Widget A', 2, 19.99, 'pending');

UPDATE orders
SET status = 'shipped'
WHERE id = 1;
```

Now peek changes from the slot:

```sql
SELECT *
FROM pg_logical_slot_peek_changes(
  'wal2json_replication',
  NULL,
  NULL,
  'pretty-print', 'on',
  'add-tables', 'public.orders'
);
```

To consume (advance) the slot instead of peeking, use:

```sql
SELECT *
FROM pg_logical_slot_get_changes(
  'wal2json_replication',
  NULL,
  NULL,
  'pretty-print', 'on',
  'add-tables', 'public.orders'
);
```

## Stop

```bash
docker compose down
```

If you need to re-run initialization from `init.sql`, remove the volume too:

```bash
docker compose down -v
```

`init.sql` only runs on first initialization of the data directory.
