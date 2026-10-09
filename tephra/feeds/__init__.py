"""Feed pollers. Parsers are pure functions of a FetchResult; fetchers take a Source.

This package init imports only the shared base so that a broken parser module can never
stop the rest of TEPHRA from importing.
"""

from tephra.feeds.base import (
    USER_AGENT,
    FetchError,
    FetchResult,
    HttpSource,
    RecordingSource,
    Source,
    build_url,
)

__all__ = [
    "USER_AGENT",
    "FetchError",
    "FetchResult",
    "HttpSource",
    "RecordingSource",
    "Source",
    "build_url",
]
