"""Shared rate limiter instance.

Lives outside app.py so route modules (src/api/*.py) can import `limiter`
and decorate individual endpoints with @limiter.limit(...) without a
circular import (app.py imports the route routers).
"""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    """Rate-limit key function that honors X-Forwarded-For.

    The app sits behind Caddy (see Caddyfile), so request.client.host (what
    slowapi's default get_remote_address uses) is always Caddy's internal
    address, not the real client — that would rate-limit all traffic as a
    single IP. Caddy's reverse_proxy forwards X-Forwarded-For by default.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# Default: 100/minute per client IP for any route without a more specific
# @limiter.limit(...) override.
limiter = Limiter(key_func=client_ip, default_limits=["100/minute"])
