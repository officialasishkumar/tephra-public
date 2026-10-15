"""Process entry point: the ``tephra`` console script and the ASGI ``app`` for uvicorn."""

import uvicorn
from fastapi import FastAPI

from tephra.api.server import configure_logging, create_app
from tephra.config import get_settings

__all__ = ["app", "run"]


def _build() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, project=settings.gcp_project)
    return create_app(settings)


app = _build()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.port,
        proxy_headers=True,
        # Cloud Run's front end is the only peer and sets X-Forwarded-Proto, so desk cookies
        # are marked Secure. uvicorn then reports the leftmost X-Forwarded-For entry, which
        # the caller writes; the login throttle counts the rightmost (auth.client_key).
        forwarded_allow_ips="*",
        log_config=None,
        log_level=settings.log_level.lower(),
        access_log=False,
        # SSE streams never end by themselves; do not let them hold a shutdown open.
        timeout_graceful_shutdown=8,
    )


if __name__ == "__main__":
    run()
