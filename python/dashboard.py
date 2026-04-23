import json
import os
import queue
import select
import threading
import time
from typing import List, Dict

import psycopg2
from flask import Flask, Response, jsonify, send_from_directory


DB_CONFIG = {
    "host": os.environ.get("PGHOST", "localhost"),
    "port": int(os.environ.get("PGPORT", "5432")),
    "dbname": os.environ.get("PGDATABASE", "testdb"),
    "user": os.environ.get("PGUSER", "postgres"),
    "password": os.environ.get("PGPASSWORD", "postgres"),
}

DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "8080"))

app = Flask(__name__, static_folder="web", static_url_path="")
clients: set[queue.Queue] = set()
clients_lock = threading.Lock()


def wait_for_postgres(retries: int = 30, delay: float = 2.0) -> None:
    for _ in range(retries):
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            conn.close()
            return
        except psycopg2.OperationalError:
            time.sleep(delay)
    raise RuntimeError("PostgreSQL did not become ready in time.")


def fetch_stats() -> List[Dict[str, int | str]]:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, order_count, updated_at
                FROM stats
                ORDER BY status
                """
            )
            rows = cur.fetchall()
        return [
            {
                "status": row[0],
                "order_count": row[1],
                "updated_at": row[2].isoformat(),
            }
            for row in rows
        ]
    finally:
        conn.close()


def ensure_stats_notify_trigger() -> None:
    """Create LISTEN/NOTIFY plumbing if DB was initialized before trigger existed."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE OR REPLACE FUNCTION notify_stats_changed()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    PERFORM pg_notify('stats_changed', 'changed');
                    RETURN NULL;
                END;
                $$;
                """
            )
            cur.execute(
                """
                DROP TRIGGER IF EXISTS stats_changed_notify ON stats;
                CREATE TRIGGER stats_changed_notify
                AFTER INSERT OR UPDATE OR DELETE ON stats
                FOR EACH STATEMENT
                EXECUTE FUNCTION notify_stats_changed();
                """
            )
        conn.commit()
    finally:
        conn.close()


def broadcast_stats() -> None:
    payload = json.dumps({"stats": fetch_stats()})
    dead_queues: list[queue.Queue] = []
    with clients_lock:
        for q in clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead_queues.append(q)
        for q in dead_queues:
            clients.discard(q)


def db_listener() -> None:
    wait_for_postgres()
    ensure_stats_notify_trigger()

    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

    cur = conn.cursor()
    cur.execute("LISTEN stats_changed;")

    # Push initial state once at startup.
    broadcast_stats()

    while True:
        # Block until PostgreSQL signals that there is data to read on this
        # connection; this is more reliable than tight polling loops.
        ready, _, _ = select.select([conn], [], [], 15)
        if not ready:
            continue

        conn.poll()
        while conn.notifies:
            conn.notifies.pop(0)
            broadcast_stats()


@app.get("/")
def index() -> Response:
    resp = send_from_directory("web", "index.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/stats")
def api_stats() -> Response:
    resp = jsonify({"stats": fetch_stats()})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/events")
def events() -> Response:
    def event_stream():
        q: queue.Queue = queue.Queue(maxsize=10)
        with clients_lock:
            clients.add(q)

        # Send an immediate snapshot to the new subscriber.
        q.put(json.dumps({"stats": fetch_stats()}))

        try:
            while True:
                try:
                    data = q.get(timeout=10)
                    yield f"event: stats\ndata: {data}\n\n"
                except queue.Empty:
                    # Keep the stream alive across intermediaries/load balancers.
                    yield ": keepalive\n\n"
        finally:
            with clients_lock:
                clients.discard(q)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    threading.Thread(target=db_listener, daemon=True).start()
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)
