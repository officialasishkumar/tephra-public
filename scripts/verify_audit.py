"""Verify the audit chain: walk every entry from genesis and report the head.

Over the SQLite file (the default store, ``TEPHRA_SQLITE_PATH``) or, with ``--url``, through
the running service's ``GET /api/audit/verify`` route. Prints one JSON object (``intact``,
``entries``, ``head_seq``, ``head_sha256``, ``problems``) and exits 1 when the chain is not
intact, 2 when it cannot be read.

    uv run python scripts/verify_audit.py
    uv run python scripts/verify_audit.py --sqlite .state/tephra.sqlite3
    uv run python scripts/verify_audit.py --url https://tephra.example.run.app
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

from tephra.config import Settings
from tephra.desk.audit import ChainedAuditEntry, list_entries, verify_chain
from tephra.store.sqlite_store import SqliteStore

VERIFY_PATH = "/api/audit/verify"


async def verify_sqlite(path: Path, blob_dir: Path) -> dict[str, Any]:
    store = SqliteStore(path, blob_dir)
    try:
        problems = await verify_chain(store)
        head = await list_entries(store, limit=1)
    finally:
        await store.aclose()
    newest = ChainedAuditEntry.model_validate(head[0].model_dump()) if head else None
    return {
        "source": str(path),
        "intact": not problems,
        "entries": newest.seq if newest else 0,
        "head_seq": newest.seq if newest else None,
        "head_sha256": newest.sha256 if newest else None,
        "problems": problems,
    }


def verify_url(base: str) -> dict[str, Any]:
    url = base.rstrip("/") + VERIFY_PATH
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    body = response.json()
    return {"source": url, **body}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    settings = Settings(_env_file=None)
    parser.add_argument("--sqlite", type=Path, default=settings.sqlite_path)
    parser.add_argument("--blobs", type=Path, default=settings.cache_dir / "blobs")
    parser.add_argument("--url", help="the service's base URL: verify through its route")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.url:
            result = verify_url(args.url)
        else:
            if not args.sqlite.is_file():
                print(f"no store at {args.sqlite}", file=sys.stderr)
                return 2
            result = asyncio.run(verify_sqlite(args.sqlite, args.blobs))
    except (OSError, httpx.HTTPError, ValueError) as exc:
        print(f"audit chain could not be read: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1, default=str))
    return 0 if result.get("intact") else 1


if __name__ == "__main__":
    raise SystemExit(main())
