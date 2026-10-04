"""OIDC check for the routes Google calls: Pub/Sub push and Cloud Tasks.

The service is public (Telegram must reach the webhook), so Cloud Run IAM does
not guard ``/push`` and ``/tasks/reminder``: they verify the Google-signed
token themselves. It must be issued by Google for this service (audience =
``WORKER_URL``, set on the push subscriptions and the reminder tasks) on behalf
of the runtime service account (``WORKER_SA``). Anything else gets a 403.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request

from assistant.config import get_worker_settings

log = logging.getLogger(__name__)


def require_google_oidc(request: Request) -> None:
    """FastAPI dependency; fails closed when the service URL or SA is unset."""
    settings = get_worker_settings()
    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ")
    if not (settings.worker_url and settings.worker_sa) or not token or token == header:
        log.warning("oidc_rejected reason=missing")
        raise HTTPException(status_code=403)
    import google.auth.transport.requests
    from google.oauth2 import id_token

    # ponytail: Google's certs are fetched on every call (one small GET per
    # push); cache them with a cachecontrol session if push volume grows.
    try:
        claims = id_token.verify_oauth2_token(
            token,
            google.auth.transport.requests.Request(),
            audience=settings.worker_url,
        )
    except ValueError:  # bad signature, expired, wrong issuer or audience
        log.warning("oidc_rejected reason=invalid")
        raise HTTPException(status_code=403) from None
    if claims.get("email") != settings.worker_sa or not claims.get("email_verified"):
        log.warning("oidc_rejected reason=caller")
        raise HTTPException(status_code=403)
