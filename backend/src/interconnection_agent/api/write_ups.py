"""How many write-ups the public site lets people start: per visitor and per day.

Starting a write-up is what calls the model; questions come out of each write-up's own
token limit, and the month's spend is limited across everything (``spending``). A day ends
at midnight, California time. A visitor is known only by a keyed hash of the internet
address the website's host passes on, and the record of who started what is kept for two
days.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime

from fastapi import Request

from interconnection_agent.settings import SiteLimits
from interconnection_agent.spending import TIME_ZONE, Conn, check_spend

# Taken inside the transaction that counts and records a start, so two people starting at
# once can't both take the last place.
LOCK = 4_172_309

TURNED_OFF = "Write-ups are turned off on this site for now. Everything else on the page works."
SITE_USED_UP = (
    "The site has written as many write-ups as it can today. More can be started after "
    "midnight, California time. Everything else on the page still works."
)


class WriteUpsOff(RuntimeError):
    """The site's settings turn write-ups off."""


class WriteUpsUsedUp(RuntimeError):
    """The visitor, or the site, has started as many write-ups today as it may."""


def visitor_of(request: Request) -> str:
    """The visitor's internet address: the first one the website's host passes on, or the
    connection's own when the API is reached directly (as in local development)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"


def take_write_up(conn: Conn, address: str, limits: SiteLimits, now: datetime) -> None:
    """Count one more write-up for ``address`` today, or raise why it can't start."""
    if limits.write_ups_per_day == 0 or limits.write_ups_per_visitor_per_day == 0:
        raise WriteUpsOff(TURNED_OFF)
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        check_spend(conn, limits.spend_per_month_usd, now)
        conn.execute(
            "DELETE FROM write_up_starts WHERE at < %s::timestamptz - interval '2 days'", (now,)
        )
        visitor = _hashed(conn, address)
        row = conn.execute(
            "SELECT count(*), count(*) FILTER (WHERE visitor = %(visitor)s) "
            "FROM write_up_starts "
            "WHERE at >= date_trunc('day', %(now)s AT TIME ZONE %(tz)s) AT TIME ZONE %(tz)s "
            "AND at <= %(now)s",
            {"visitor": visitor, "now": now, "tz": TIME_ZONE},
        ).fetchone()
        assert row is not None
        site_today, visitor_today = int(row[0]), int(row[1])  # type: ignore[call-overload]
        if visitor_today >= limits.write_ups_per_visitor_per_day:
            raise WriteUpsUsedUp(_visitor_used_up(limits.write_ups_per_visitor_per_day))
        if site_today >= limits.write_ups_per_day:
            raise WriteUpsUsedUp(SITE_USED_UP)
        conn.execute("INSERT INTO write_up_starts (at, visitor) VALUES (%s, %s)", (now, visitor))


def _visitor_used_up(most: int) -> str:
    started = "1 write-up" if most == 1 else f"{most} write-ups"
    return (
        f"You've started {started} today, the most one visitor can start in a day. You can "
        "start another after midnight, California time. Everything else on the page still "
        "works."
    )


def _hashed(conn: Conn, address: str) -> str:
    conn.execute(
        "INSERT INTO visitor_key (key) VALUES (%s) ON CONFLICT DO NOTHING",
        (secrets.token_bytes(32),),
    )
    row = conn.execute("SELECT key FROM visitor_key").fetchone()
    assert row is not None and isinstance(row[0], bytes)
    return hmac.new(row[0], address.encode(), hashlib.sha256).hexdigest()
