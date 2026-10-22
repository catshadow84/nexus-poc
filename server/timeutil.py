from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime.

    The database stores naive UTC datetimes, so we keep them naive.
    This replaces the deprecated datetime.utcnow().
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)