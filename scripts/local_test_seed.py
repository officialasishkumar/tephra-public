"""Seed a running local TEPHRA with the fixed test logins of docs/LOCAL-TEST-ACCOUNTS.md.

    uv run python scripts/local_test_seed.py --wait              # http://127.0.0.1:8080
    uv run python scripts/local_test_seed.py --url http://127.0.0.1:8081

It starts nothing: it talks to a server started by ``scripts/local_test_server.py`` (whose task
token it uses), through the HTTP API only, and is safe to re-run (what exists is skipped). It
makes the TEPHRA staff account, the fictional airline Ring of Fire Charter (RFB) with its
onboarding answers submitted, and has staff verify it. With hosting on it then has the airline
set up by its ops manager, the policy confirmed, a fake model key saved (the server runs the
stub model), a dispatcher and a viewer joined by invite, one push key made, one sample push
sent and shadow runs started.

Values the server makes at random (recovery codes, the push key, invite links) are printed and
kept in ``.local-test/seeded-<port>.txt`` (gitignored). Every value is local-only.
"""

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final, NamedTuple
from urllib.parse import urlsplit

import httpx
from local_test_server import ENV, seeded_file


class Person(NamedTuple):
    name: str
    email: str


PASSWORD: Final = "local test password 2026"
STAFF: Final = Person("M. Tan", "m.tan@tephra.example")
OPS_MANAGER: Final = Person("Ana Ops", "ops@rfb.example")
DISPATCHER: Final = Person("Dee Disp", "dee@rfb.example")
VIEWER: Final = Person("Vic View", "vic@rfb.example")
ICAO: Final = "RFB"
AIRLINE: Final = "Ring of Fire Charter"
MODEL: Final = "gemini-3.8-flash"
MODEL_LITE: Final = "gemini-3.5-flash-lite"
FAKE_MODEL_KEY: Final = "local-test-fake-model-key-0000000000000000"
PUSH_KEY_NAME: Final = "RFB OpsTrack (local test)"
TASK_TOKEN: Final = ENV["TEPHRA_TASK_TOKEN"]
CSRF: Final = {"X-Tephra-Desk": "1"}

ANSWERS: Final[dict[str, Any]] = {
    "format": "tephra.onboard/2",
    "airline": {
        "name": AIRLINE,
        "icao": ICAO,
        "iata": "RB",
        "callsign_prefix": ICAO,
        "state_of_operator": "Indonesia",
        "aoc_number": "AOC-RFB-0001",
        "main_base": "WIII",
        "ops_email": OPS_MANAGER.email,
        "contact_name": OPS_MANAGER.name,
    },
    "policy": {
        "preset": "A",
        "changes": [
            {
                "name": "exposure.vertical_margin_ft",
                "value": 3000,
                "reason": "Our SRA section 4.2 asks for a wider vertical margin (test value).",
            }
        ],
        "risk_owner": "Director of Flight Operations",
        "sra_ref": "RFB-SRA-VA rev 1",
    },
    "fleet": {
        "aircraft": [
            {
                "registration": "PK-RFX",
                "type_icao": "A320",
                "seats": 180,
                "home_base": "WIII",
                "hex": "8a0b17",
            },
            {
                "registration": "PK-RFY",
                "type_icao": "A320",
                "seats": 180,
                "home_base": "WIII",
                "hex": "8a0b18",
            },
            {
                "registration": "PK-RFZ",
                "type_icao": "AT76",
                "seats": 70,
                "home_base": "WADD",
                "hex": None,
            },
        ],
        "extra_prefixes": [],
    },
    "network": {
        "airports": [
            {"icao": "WIII", "alternates": ["WIHH"]},
            {"icao": "WADD", "alternates": ["WARR"]},
            {"icao": "WARR", "alternates": []},
        ]
    },
    "schedule": {"provided": False, "flights": 0, "tails": 0, "crews": 0, "crew_bases": []},
    "feeds": {
        "positions": True,
        "flight_plans": False,
        "pilot_reports": True,
        "source_system": "RFB OpsTrack (test)",
    },
    "people": {
        "dispatchers": [
            {"name": DISPATCHER.name, "role": "approves"},
            {"name": VIEWER.name, "role": "views"},
        ]
    },
    "assistant": {"provider": "none", "model": None, "model_lite": None},
}


class Seeded:
    """The random values, printed and kept in the local file as ``label: value`` lines."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.values: dict[str, str] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                label, sep, value = line.partition(": ")
                if sep and not line.startswith("#"):
                    self.values[label] = value

    def keep(self, label: str, value: str) -> None:
        print(f"  {label}: {value}")
        self.values[label] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# local test values made by the server (scripts/local_test_seed.py)"]
        lines += [f"{k}: {v}" for k, v in self.values.items()]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def step(text: str) -> None:
    print(f"- {text}", flush=True)


def fail(response: httpx.Response, doing: str) -> None:
    sys.exit(f"local_test_seed: {doing}: HTTP {response.status_code} {response.text[:300]}")


def ok(response: httpx.Response, doing: str) -> Any:
    if response.status_code >= 400:
        fail(response, doing)
    return response.json() if response.content else None


def client(base: str, address: str) -> httpx.Client:
    """One browser: its own cookies, and its own forwarded address, so the per-address sign-up
    throttle (three a day) is not spent on the seed's accounts."""
    return httpx.Client(
        base_url=base, headers={**CSRF, "X-Forwarded-For": address}, timeout=30, trust_env=False
    )


def wait_for(base: str, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            if httpx.get(f"{base}/api/airline/session", timeout=3, trust_env=False).is_success:
                return
        except httpx.TransportError:
            pass
        if time.monotonic() > deadline:
            sys.exit(f"local_test_seed: no server answered at {base} in {seconds:g} s")
        time.sleep(1)


# --- TEPHRA staff -----------------------------------------------------------------------


def staff_signed_in(base: str) -> httpx.Client:
    c = client(base, "10.77.0.1")
    r = c.post(
        "/tasks/operator-invite",
        json={"name": STAFF.name, "email": STAFF.email},
        headers={"X-Tephra-Task-Token": TASK_TOKEN},
    )
    if r.status_code == 409:
        ok(
            c.post("/api/admin/sign-in", json={"email": STAFF.email, "password": PASSWORD}),
            f"sign in as TEPHRA staff {STAFF.email}",
        )
        step(f"TEPHRA staff {STAFF.email}: exists, signed in")
        return c
    token = ok(r, "mint the first staff link (task token)")["link"].partition("#")[2]
    ok(
        c.post(
            "/api/admin/invite/accept",
            json={"token": token, "email": STAFF.email, "password": PASSWORD},
        ),
        "accept the first staff link",
    )
    step(f"TEPHRA staff {STAFF.email}: created")
    return c


# --- the airline ------------------------------------------------------------------------


def airline_signed_in(base: str, seeded: Seeded) -> httpx.Client:
    c = client(base, "10.77.0.2")
    r = c.post(
        "/api/airline/accounts",
        json={"email": OPS_MANAGER.email, "password": PASSWORD, "acknowledge": True, "website": ""},
    )
    if r.status_code == 409:
        ok(
            c.post("/api/airline/sign-in", json={"email": OPS_MANAGER.email, "password": PASSWORD}),
            f"sign in as {OPS_MANAGER.email}",
        )
        step(f"airline account {OPS_MANAGER.email}: exists, signed in")
        return c
    step(f"airline account {OPS_MANAGER.email}: created")
    seeded.keep(f"recovery code {OPS_MANAGER.email}", ok(r, "create the account")["recovery_code"])
    return c


def submitted_and_verified(holder: httpx.Client, staff: httpx.Client) -> None:
    me = ok(holder.get("/api/airline/me"), "read the airline")
    if me["status"] == "draft":
        me = ok(
            holder.post("/api/airline/submit", json={"version": me["version"], "answers": ANSWERS}),
            "submit the onboarding answers",
        )
        step(f"{AIRLINE} ({ICAO}): answers submitted")
    if me["status"] == "pending":
        ok(
            staff.post(
                f"/api/admin/airlines/{me['id']}/verify",
                json={"version": me["version"], "note": "Local test airline"},
            ),
            "verify the airline as staff",
        )
        step(f"{AIRLINE}: verified by TEPHRA staff")
    elif me["status"] == "verified":
        step(f"{AIRLINE}: verified already")
    else:
        sys.exit(f"local_test_seed: {AIRLINE} is {me['status']}; start with --fresh")


# --- hosting ----------------------------------------------------------------------------


def hosting_on(holder: httpx.Client) -> bool:
    r = holder.get("/api/hosted/me")
    if r.status_code == 404:
        return False
    ok(r, "read the hosted airlines")
    return True


def set_up(holder: httpx.Client, staff: httpx.Client) -> None:
    me = ok(holder.get("/api/hosted/me"), "read the hosted airlines")
    if me["waiting"] == "hosting_not_approved":
        airline_id = ok(holder.get("/api/airline/me"), "read the airline")["id"]
        row = ok(staff.get(f"/api/admin/airlines/{airline_id}"), "read the airline as staff")
        ok(
            staff.post(
                f"/api/admin/airlines/{airline_id}/approve-hosting",
                json={"version": row["version"]},
            ),
            "approve hosting",
        )
        step(f"{ICAO}: hosting approved")
        me = ok(holder.get("/api/hosted/me"), "read the hosted airlines")
    if me["can_set_up"] is not None:
        ok(
            holder.post("/api/hosted/setup", json={"display_name": OPS_MANAGER.name}),
            "set the airline up",
        )
        step(f"{ICAO}: set up by its ops manager {OPS_MANAGER.name}")
    elif any(m["icao"] == ICAO for m in me["memberships"]):
        step(f"{ICAO}: set up already")
    else:
        sys.exit(f"local_test_seed: {ICAO} cannot be set up: {me}")


def tenant(path: str) -> str:
    return f"/a/{ICAO}/api/tenant{path}"


def policy_confirmed(holder: httpx.Client) -> None:
    tab = ok(holder.get(tenant("/policy")), "read the policy")
    version = tab["current"]["version"]
    if (tab["confirmed"] or {}).get("version") == version:
        step(f"policy v{version}: confirmed already")
        return
    ok(holder.post(tenant("/policy/confirm"), json={"version": version}), "confirm the policy")
    step(f"policy v{version}: confirmed")


def assistant_set(holder: httpx.Client) -> None:
    tab = ok(holder.get(tenant("/assistant")), "read the assistant settings")
    offered = {m["name"] for m in tab["models"]}
    if not {MODEL, MODEL_LITE} <= offered:
        sys.exit(f"local_test_seed: {MODEL} / {MODEL_LITE} not offered: {sorted(offered)}")
    if (tab["model"], tab["model_lite"]) != (MODEL, MODEL_LITE):
        body = {
            "model": MODEL,
            "model_lite": MODEL_LITE,
            "reserve_share": tab["reserve_share"],
            "daily_limits": {},
        }
        ok(holder.put(tenant("/assistant"), json=body), "choose the models")
        step(f"models: {MODEL} / {MODEL_LITE}")
    if tab["key"]["set"]:
        step("model key: set already")
        return
    ok(holder.put(tenant("/assistant/key"), json={"key": FAKE_MODEL_KEY}), "save the model key")
    step("model key: the fake test key saved (the server runs the stub model)")


def member_joined(
    base: str, holder: httpx.Client, person: Person, role: str, address: str, seeded: Seeded
) -> None:
    people = ok(holder.get(tenant("/people")), "read People")
    if any(m["email"] == person.email for m in people["members"]):
        step(f"{role} {person.email}: joined already")
        return
    for old in people["invites"]:
        if old["email"] == person.email:
            ok(holder.post(tenant(f"/people/invites/{old['id']}/revoke")), "revoke an old invite")
    made = ok(
        holder.post(tenant("/people/invites"), json={"email": person.email, "role": role}),
        f"invite the {role}",
    )
    seeded.keep(f"invite link {person.email} (used)", made["link"])
    joined = ok(
        client(base, address).post(
            "/api/hosted/invites/join",
            json={
                "token": made["link"].partition("#")[2],
                "email": person.email,
                "password": PASSWORD,
                "display_name": person.name,
                "acknowledge": True,
            },
        ),
        f"join as the {role}",
    )
    step(f"{role} {person.email}: joined")
    seeded.keep(f"recovery code {person.email}", joined["recovery_code"])


def push_key(holder: httpx.Client, seeded: Seeded) -> str | None:
    """The push key's value when this run knows it (made now, or kept from an earlier run)."""
    label = f"push key {PUSH_KEY_NAME}"
    keys = ok(holder.get(tenant("/keys")), "read the push keys")["keys"]
    live = [k for k in keys if k["name"] == PUSH_KEY_NAME and k["revoked_at"] is None]
    if live:
        step(f"push key {PUSH_KEY_NAME}: exists")
        return seeded.values.get(label)
    made = ok(holder.post(tenant("/keys"), json={"name": PUSH_KEY_NAME}), "make the push key")
    step(f"push key {PUSH_KEY_NAME}: made")
    seeded.keep(label, made["key"])
    return str(made["key"])


def sample_push(base: str, holder: httpx.Client, key: str | None, seeded: Seeded) -> None:
    """Two positions of the fleet stamped on the airline's clock, so Feeds is ticked."""
    if key is None:
        keys = ok(holder.get(tenant("/keys")), "read the push keys")["keys"]
        found = next(k for k in keys if k["name"] == PUSH_KEY_NAME and k["revoked_at"] is None)
        key = ok(holder.post(tenant(f"/keys/{found['id']}/rotate")), "rotate the push key")["key"]
        step("push key: rotated (its value was not kept here)")
        seeded.keep(f"push key {PUSH_KEY_NAME}", str(key))
    now = datetime.fromisoformat(ok(holder.get(tenant("/header")), "read the header")["wall_now"])

    def at(seconds: int) -> str:
        return (now - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

    positions = [
        {
            "hex": "8a0b17",
            "callsign": "RFB401",
            "type_icao": "A320",
            "lat": -6.95,
            "lon": 107.6,
            "alt_baro_ft": 33000,
            "gs_kt": 450,
            "track_deg": 100,
            "observed_at": at(15),
        },
        {
            "hex": "8a0b18",
            "callsign": "RFB417",
            "type_icao": "A320",
            "lat": -6.4,
            "lon": 106.2,
            "alt_baro_ft": 29000,
            "gs_kt": 430,
            "track_deg": 95,
            "observed_at": at(20),
        },
    ]
    r = httpx.post(
        f"{base}/a/{ICAO}/api/push/positions",
        json={"format": "tephra.airline/1", "positions": positions},
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
        trust_env=False,
    )
    ok(r, "push the sample positions")
    step("sample push: 2 positions")


def shadow_started(base: str, holder: httpx.Client, key: str | None, seeded: Seeded) -> None:
    golive = ok(holder.get(tenant("/golive")), "read Go live")
    if golive["state"] != "setup":
        step(f"{ICAO}: {golive['state']} already")
        return
    feeds = next(item for item in golive["items"] if item["key"] == "feeds")
    if not feeds["done"]:
        sample_push(base, holder, key, seeded)
        golive = ok(holder.get(tenant("/golive")), "read Go live")
    if not golive["can_start"] or golive["region"] is None:
        sys.exit(f"local_test_seed: shadow runs cannot start: {golive['blocked']} {golive}")
    ok(holder.post(tenant("/start"), json={"region": golive["region"]["key"]}), "start shadow runs")
    step(f"{ICAO}: shadow runs started ({golive['region']['name']})")


def seed(base: str, seeded: Seeded) -> None:
    staff = staff_signed_in(base)
    holder = airline_signed_in(base, seeded)
    submitted_and_verified(holder, staff)
    if not hosting_on(holder):
        step("hosting is off on this server: done")
        return
    set_up(holder, staff)
    policy_confirmed(holder)
    assistant_set(holder)
    member_joined(base, holder, DISPATCHER, "dispatcher", "10.77.0.3", seeded)
    member_joined(base, holder, VIEWER, "viewer", "10.77.0.4", seeded)
    key = push_key(holder, seeded)
    shadow_started(base, holder, key, seeded)
    step("done")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", default="http://127.0.0.1:8080", help="the running server")
    parser.add_argument("--wait", action="store_true", help="wait up to 90 s for the server")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    if args.wait:
        wait_for(base, 90)
    port = urlsplit(base).port or 80
    seed(base, Seeded(seeded_file(port)))


if __name__ == "__main__":
    main()
