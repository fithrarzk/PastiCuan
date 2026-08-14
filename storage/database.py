"""Optional PostgreSQL/Supabase connection helpers."""

from __future__ import annotations

import os


def connect_from_env(*, writer: bool = False):
    """Open a short-lived pooled connection.

    Railway should set only SUPABASE_DATABASE_URL. Scheduled jobs may set the
    writer URL separately so write authority never reaches Telegram handlers.
    """
    name = "SUPABASE_WRITER_DATABASE_URL" if writer else "SUPABASE_DATABASE_URL"
    url = os.getenv(name)
    if not url:
        raise RuntimeError(f"{name} is not configured.")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install psycopg[binary] to use Supabase persistence.") from exc
    timeout = max(2, min(15, int(os.getenv("SUPABASE_CONNECT_TIMEOUT", "3"))))
    return psycopg.connect(url, connect_timeout=timeout, application_name="pasticuan")
