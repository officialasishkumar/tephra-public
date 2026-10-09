"""Process entry point: the ``tephra`` console script and the ASGI ``app`` for uvicorn."""

import uvicorn
from fastapi import FastAPI

from tephra.api.server import configure_logging, create_app
from tephra.config import get_settings

__all__ = ["app", "run"]


def _build() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    return create_app(settings)


app = _build()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.port,
        proxy_headers=True,
        # Cloud Run's front end is the only peer and sets X-Forwarded-For/-Proto; trusting it
        # lets the login throttle see client addresses and marks desk cookies Secure.
        forwarded_allow_ips="*",
        log_config=None,
        log_level=settings.log_level.lower(),
        access_log=False,
        # SSE streams never end by themselves; do not let them hold a shutdown open.
        timeout_graceful_shutdown=5,
    )


if __name__ == "__main__":
    run()
