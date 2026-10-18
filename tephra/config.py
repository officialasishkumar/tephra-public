"""Runtime settings (environment variables) and fixed product and safety constants.

Only composition roots (``tephra.api.server``, ``tephra.pipeline.create_runtime``,
``scripts/*``) call :func:`get_settings`. Library functions take a ``Settings`` argument
so tests can pass ``Settings(_env_file=None, ...)`` explicitly. A hosted airline's work binds
its own settings for the current context (:func:`bind_settings`); elsewhere
:func:`get_settings` is the process's settings, as before.
"""

import math
import os
import re
import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Final, Literal, Self, get_args

from pydantic import (
    AliasChoices,
    Field,
    PositiveInt,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from tephra.models import (
    AdsbQueryPoint,
    BBox,
    FeedId,
    Region,
    RunMode,
    TephraModel,
    UtcDatetime,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
"""Repository root when running from a checkout (the Docker image keeps that layout)."""

# --- product constants ------------------------------------------------------------------

AIRLINE_CODE = "RFA"
AIRLINE_NAME = "Ring of Fire Air"
DISCLAIMER = "Decision support only - fictional airline - not for operational use"
OWN_DISCLAIMER = "Decision support only - not for operational use"
"""An airline's own TEPHRA: its airline is real, and the rest of the disclaimer holds."""
NO_MODEL_LABEL = "NO MODEL"
SHADOW_LINE: Final = "SHADOW - NOT FOR USE"
"""Written by code into every header of a draft a hosted airline makes in SHADOW (advisory,
outbound text, message, document), outside any body a dispatcher can edit."""
SHADOW_WORDS: Final = "Shadow · not for use"
"""The same label as pages show it (the web's base.js keeps an equal constant)."""
REPLAY_BANNER_TEMPLATE = "REPLAY: recorded real feeds from {date}"
"""``{date}`` is ``recorded_from`` formatted as ``%d %b %Y`` (e.g. '07 Oct 2026')."""
SYNTHETIC_BANNER_TEMPLATE = "REPLAY: synthetic demo data, scenario dated {date}"
"""The banner of a synthetic case (``ReplayCase.synthetic``): its feeds were invented for the
demo, so it never says "recorded"."""

# --- safety constants (deliberately not configurable) -----------------------------------

MAX_PLUME_EXTENT_KM = 500.0
MAX_SECTOR_WIDTH_DEG = 180.0
MAX_HORIZON_H = 18.0
"""VAAs forecast to +18 h; nothing in TEPHRA looks further ahead."""
FEED_CLOCK_SLACK = timedelta(minutes=5)
"""A product stamped up to this long after "now" already counts as issued (feed clocks and
replay steps). Record selection and the official floor must use the same value, or a VAAC's
polygons drop out of the cone for a tick."""
MIN_SECRET_CHARS = 32
"""Session secret and task token: shorter values make the desk cookie HMAC guessable."""
ADVISORY_BODY_MAX_CHARS = 400
MAX_BODY_BYTES = 16 * 1024
"""Desk bodies are a PIN, a reason or a 400-character advisory; nothing needs more."""
MAX_NOTICE_BODY_BYTES = 32 * 1024
"""A pasted notice is up to 6,000 characters, and Japanese text takes three bytes each."""
MAX_ONBOARD_BODY_BYTES = 128 * 1024
"""An airline's onboarding answers: 1,000 aircraft rows are about 90 KB of JSON."""
MAX_PUSH_BODY_BYTES = 512 * 1024
"""A push of up to 1,000 positions (about 220 KB): the push itself, the Desk's upload and the
workspace's dry run take the same, so a file the dry run accepts is never refused as too large."""

MOVED_TO_POLICY: dict[str, str] = {
    "TEPHRA_VERTICAL_MARGIN_FT": "vertical_margin_ft",
    "TEPHRA_ALTERNATE_SEARCH_NM": "alternate_search_nm",
}
"""Former settings now in ``data/policy/policy_a.json``. Settings ignores unknown keys, so
without a check a deployment that still sets one would silently run on the policy value."""

# --- free-tier model limits -------------------------------------------------------------


class ModelLimit(TephraModel):
    """Google's free-tier limits for one model id, as the AI Studio rate-limit page shows them
    (the numbers are not published elsewhere; research/06, research/10)."""

    rpm: PositiveInt = Field(description="Requests a minute")
    rpd: int = Field(ge=0, description="Requests per Google quota day (midnight Pacific)")
    tpm: PositiveInt | None = Field(
        default=None, description="Input tokens a minute, where Google sets one (Gemma 4)"
    )


DEFAULT_MODEL_LIMITS: dict[str, ModelLimit] = {
    "gemini-3.8-flash": ModelLimit(rpm=5, rpd=20),
    "gemini-3.5-flash-lite": ModelLimit(rpm=15, rpd=500),
    "gemini-3.1-flash-lite": ModelLimit(rpm=15, rpd=500),
    # Speech has its own pool of about 10 a day; its per-minute limit is not reported, so it
    # is paced as the smallest one seen.
    "gemini-3.8-flash-lite-tts": ModelLimit(rpm=3, rpd=10),
    "gemma-4-31b-it": ModelLimit(rpm=30, rpd=14_400, tpm=16_000),
    "gemma-4-26b-a4b-it": ModelLimit(rpm=30, rpd=14_400, tpm=16_000),
}
"""Free-tier rows as reported on 13 Oct 2026 (the TEPHRA free-models brief, sections 1-3)."""


# --- region presets ---------------------------------------------------------------------

REGIONS: dict[str, Region] = {
    "java_bali": Region(
        key="java_bali",
        name="Java / Bali",
        center_lat=-7.6,
        center_lon=111.0,
        zoom=6.2,
        bbox=BBox(west=104.5, south=-9.8, east=117.5, north=-5.0),
        adsb_points=[
            AdsbQueryPoint(lat=-6.9, lon=107.6, radius_nm=220),
            AdsbQueryPoint(lat=-8.2, lon=113.6, radius_nm=250),
        ],
    ),
    "halmahera": Region(
        key="halmahera",
        name="Halmahera",
        center_lat=1.2,
        center_lon=127.7,
        zoom=7.0,
        bbox=BBox(west=124.5, south=-1.5, east=130.5, north=3.5),
        adsb_points=[AdsbQueryPoint(lat=1.2, lon=127.8, radius_nm=220)],
    ),
    "kyushu": Region(
        key="kyushu",
        name="Kyushu",
        center_lat=31.9,
        center_lon=130.6,
        zoom=7.0,
        bbox=BBox(west=128.0, south=30.0, east=133.0, north=34.5),
        adsb_points=[AdsbQueryPoint(lat=31.8, lon=130.6, radius_nm=200)],
    ),
}

RegionKey = Literal["java_bali", "halmahera", "kyushu"]

_PREFIX = re.compile(r"[A-Z]{3}")
_HEX = re.compile(r"[0-9a-f]{6}")
_AIRPORT = re.compile(r"[A-Z]{4}")

Feature = Literal[
    "connect",
    "crew",
    "notices",
    "satellite",
    "btd",
    "voice",
    "example",
    "present",
    "onboard",
    "hosted",
]
OPT_IN_FEATURES: Final = frozenset({"hosted"})
"""Features only a comma list names: "all" and the default never include them."""
ALL_FEATURES: frozenset[str] = frozenset(get_args(Feature)) - OPT_IN_FEATURES
HOSTED_FEATURES: Final = frozenset({"connect", "crew", "notices"})
"""What a hosted airline's runtime runs (no voice, BTD, sample feed or replays)."""
HERO_FEATURES: frozenset[str] = frozenset()
"""The demo shows the hero path and its three acts only."""


class Airline(TephraModel):
    """Who the drafts and documents speak for: the fictional demo airline, or the airline that
    runs its own TEPHRA (``Settings.airline``)."""

    code: str = Field(description="ICAO designator; RFA for the demo")
    name: str
    iata: str | None = None
    fictional: bool
    shadow: bool = Field(
        default=False,
        exclude_if=lambda value: value is False,
        description="A hosted airline in SHADOW: every draft it makes is stamped",
    )

    @property
    def stamp(self) -> str | None:
        """The line code writes into each draft's header while in SHADOW."""
        return SHADOW_LINE if self.shadow else None

    @property
    def label(self) -> str:
        """'Ring of Fire Air (fictional)' or the airline's own name."""
        return f"{self.name} (fictional)" if self.fictional else self.name

    @property
    def disclaimer(self) -> str:
        return DISCLAIMER if self.fictional else OWN_DISCLAIMER

    @property
    def operator(self) -> str:
        """The operator line of a document: 'Ring of Fire Air (fictional)' or 'Name (ICAO
        RFB, IATA RB)'."""
        if self.fictional:
            return self.label
        codes = f"ICAO {self.code}" + (f", IATA {self.iata}" if self.iata else "")
        return f"{self.name} ({codes})"


DEMO_AIRLINE: Final = Airline(code=AIRLINE_CODE, name=AIRLINE_NAME, fictional=True)


class Settings(BaseSettings):
    """All environment variables TEPHRA reads. Prefix ``TEPHRA_`` unless aliased."""

    model_config = SettingsConfigDict(
        env_prefix="TEPHRA_",
        env_file=".env",
        env_file_encoding="utf-8",
        # "TEPHRA_SESSION_SECRET=" copied from .env.example means unset, not an empty key.
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        protected_namespaces=(),
    )

    # Model access. Gemini is reached only with an AI Studio key, never Vertex AI or ADC.
    llm: Literal["gemini", "ollama", "stub"] = Field(
        default="stub",
        description=(
            "'stub' is deterministic and offline, labelled NO MODEL; 'ollama' runs every model "
            "step on a model served by Ollama on this computer (TEPHRA_MODEL and "
            "TEPHRA_MODEL_LITE are then Ollama tags such as gemma4:e4b)"
        ),
    )
    ollama_url: str = Field(
        default="http://127.0.0.1:11434", description="Ollama's address (TEPHRA_LLM=ollama)"
    )
    ollama_num_ctx: int = Field(
        default=32768,
        ge=4096,
        description="The local model's context window in tokens (an agent's whole conversation)",
    )
    ollama_parallel: int = Field(
        default=1,
        ge=1,
        le=16,
        description=(
            "Requests sent to Ollama at once; start Ollama with OLLAMA_NUM_PARALLEL at least "
            "this (more only helps on a machine with the memory bandwidth for it)"
        ),
    )
    ollama_think: Literal["none", "main", "all"] = Field(
        default="main",
        description=(
            "Which local calls think before they answer: 'main' is the Plume reader only (a "
            "small model fills its numbers badly without it), 'all' adds every agent turn and "
            "draft (better answers, several times slower)"
        ),
    )
    model: str = Field(default="gemini-3.8-flash", description="Plume Reader (multimodal)")
    model_lite: str = Field(
        default="gemini-3.5-flash-lite",
        description=(
            "Exposure Planner and Dispatch Drafter (ADK), Ask, Notice and Satellite Readers, "
            "recovery, messages, handover, SRA narrative, backtest report, transcription"
        ),
    )
    model_tts: str = Field(
        default="gemini-3.8-flash-lite-tts",
        description="Ask TEPHRA's spoken answers (text-to-speech)",
    )
    model_limits: dict[str, ModelLimit] = Field(
        default_factory=lambda: dict(DEFAULT_MODEL_LIMITS),
        description=(
            "Google's free-tier limits per model id (JSON, e.g. "
            '{"gemini-3.5-flash-lite": {"rpm": 15, "rpd": 500}}); rows given here are added to '
            "or replace the defaults. Budgets and pacing are counted per model id"
        ),
    )
    ai_budget_margin: float = Field(
        default=0.1,
        ge=0,
        lt=1,
        description=(
            "Fraction of each free limit TEPHRA leaves unused: the app budget is rpd x (1 - "
            "margin) calls per Google quota day (midnight to midnight Pacific), and requests a "
            "minute are paced at rpm x (1 - margin)"
        ),
    )
    model_daily_budget: int | None = Field(
        default=None,
        ge=0,
        description=(
            "When set, the calls per Google quota day (midnight to midnight Pacific) TEPHRA "
            "allows TEPHRA_MODEL instead of its free limit less the margin"
        ),
    )
    model_lite_daily_budget: int | None = Field(
        default=None,
        ge=0,
        description=(
            "When set, the calls per Google quota day (midnight to midnight Pacific) TEPHRA "
            "allows TEPHRA_MODEL_LITE instead of its free limit less the margin"
        ),
    )
    ai_urgent_share: float = Field(
        default=0.3,
        gt=0,
        lt=1,
        description=(
            "Share of each model's daily budget held for urgent work (a flight inside or about "
            "to enter the area, a plume read it waits on); urgent work is never paced and may "
            "also take routine's share, never the interactive one"
        ),
    )
    ai_interactive_share: float = Field(
        default=0.2,
        gt=0,
        lt=1,
        description=(
            "Share held for work a person waits on: Ask, voice, notices, messages, handover, "
            "documents and Desk-started recovery"
        ),
    )
    ai_routine_burst: float = Field(
        default=0.05,
        ge=0,
        lt=1,
        description=(
            "Routine work (the rest of the budget) is admitted in proportion to the part of the "
            "quota day gone by, plus this share of the budget at once (at least one call)"
        ),
    )
    ai_reserve_release: float = Field(
        default=0.75,
        gt=0,
        le=1,
        description=(
            "Part of the quota day after which the unused urgent and interactive shares flow "
            "to routine work (the interactive one to urgent work too), all of them by midnight "
            "Pacific"
        ),
    )
    gemini_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("GEMINI_API_KEY")
    )
    llm_timeout_s: float = Field(default=60.0, gt=0)
    plan_parallel: int = Field(
        default=1,
        ge=1,
        le=16,
        description="Flights one Coordinator run plans at once (each is committed on its own)",
    )
    duty_run_timeout_s: float = Field(
        default=900.0,
        gt=0,
        description="A Duty Officer run, with every delegation it makes (each plans flights)",
    )
    ai_answer_keep_h: float = Field(
        default=72.0,
        gt=0,
        description=(
            "Wall-clock hours a model's answer stays in ai_answers for the same material "
            "question (a LIVE answer no longer than its skill's own limit)"
        ),
    )
    ai_answer_plan_min: int = Field(
        default=60,
        gt=0,
        description="Minutes a plan (and its draft) answers the same material question",
    )
    ai_answer_duty_min: int = Field(
        default=30,
        gt=0,
        description="Minutes a Duty Officer run's decisions answer the same work list",
    )
    ai_answer_ask_min: int = Field(
        default=10,
        gt=0,
        description="Minutes an Ask TEPHRA answer answers the same question in the same picture",
    )

    # Storage.
    store: Literal["sqlite", "firestore"] = "sqlite"
    sqlite_path: Path = PROJECT_ROOT / ".state" / "tephra.sqlite3"
    data_dir: Path = PROJECT_ROOT / "data"
    cache_dir: Path = PROJECT_ROOT / ".state" / "cache"
    gcp_project: str | None = None
    gcs_bucket: str | None = None
    firestore_database: str = "(default)"

    # Desk and task authentication.
    desk_pin: SecretStr | None = Field(default=None, description="Unset disables desk login")
    session_secret: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_urlsafe(32)),
        description="Signs desk cookies; random per process when unset",
    )
    desk_session_ttl_h: float = Field(default=12.0, gt=0)
    task_token: SecretStr | None = Field(
        default=None, description="X-Tephra-Task-Token for POST /tasks/tick; unset rejects all"
    )

    # Run mode and scheduling.
    mode: RunMode = RunMode.LIVE
    replay_case: str | None = Field(default=None, description="Case id; newest when unset")
    replay_speed: float = Field(default=1.0, gt=0)
    replay_start: datetime | None = Field(
        default=None,
        description=(
            "UTC time to start the replay clock at (clamped into the case window); with "
            "replay_end, the start of the looping window"
        ),
    )
    replay_end: UtcDatetime | None = Field(
        default=None,
        description=(
            "UTC end of a looping replay window; needs TEPHRA_REPLAY_START and TEPHRA_REPLAY_CASE"
        ),
    )
    auto_replay: bool = False
    auto_replay_after_ticks: int = Field(default=3, ge=1)
    local_scheduler: bool = Field(
        default=False, description="Run ticks in-process (local dev); Cloud Scheduler otherwise"
    )
    tick_interval_s: int = Field(default=60, ge=10)
    region: RegionKey = "java_bali"
    features: Annotated[frozenset[str], NoDecode] = Field(
        default=ALL_FEATURES,
        description=(
            "Optional features shown in the nav, menus, legend, index and board; 'all', 'hero' "
            "or a comma list. Hidden features keep their routes and tests (except onboard, "
            "whose routes answer 404); their scheduled model work stops. 'hosted' (TEPHRA "
            "for verified airlines) is opt-in: only a comma list turns it on, never 'all'"
        ),
    )
    ai_answer_replay_keep_h: float = Field(
        default=2160.0,
        gt=0,
        description=(
            "Wall-clock hours a REPLAY answer stays in ai_answers (a replay asks the same "
            "question every loop)"
        ),
    )
    replay_quantum_s: int = Field(
        default=0,
        ge=0,
        le=300,
        description=(
            "REPLAY only: the replay clock seen by ticks and the worker is floored to this many "
            "seconds (0 = exact); the Wall clock keeps seconds"
        ),
    )
    cloud_region: str | None = Field(
        default=None, description="Region shown under Runs on (deploy sets TEPHRA_CLOUD_REGION)"
    )
    secrets_source: Literal["secret-manager", "environment"] = Field(
        default="environment",
        description="Set by deploy/cloudrun.sh beside --set-secrets; never inferred",
    )
    visitor_access: Literal["off", "replay"] = Field(
        default="off",
        description="'replay': anyone may enter the Desk as a visitor while a replay plays",
    )
    visitor_session_ttl_h: float = Field(default=2.0, gt=0)
    visitor_decision_cap: int = Field(default=40, ge=1)
    visitor_ask_cap: int = Field(default=3, ge=0)
    tick_deadline_s: int = Field(
        default=100,
        ge=20,
        description=(
            "Seconds a tick may take before it publishes what it has; under Cloud Scheduler's "
            "120 s attempt deadline"
        ),
    )
    recovery_auto: bool = Field(
        default=True,
        description=(
            "Run the recovery agent once when the set of closed RFA airports changes; the Desk's "
            "'run' button works either way. Each run is one lite-tier agent session."
        ),
    )
    science: bool = Field(default=False, description="Raw Himawari HSD BTD; needs [science]")
    nict_frames: bool = Field(
        default=False,
        description=(
            "Also crop NICT true-colour tiles for the Wall. Off by default: NICT's terms allow "
            "non-commercial use only and research/05 did not clear them; the Wall's GIBS layers "
            "give open true-colour context instead."
        ),
    )
    vona_live: bool = Field(
        default=False,
        description=(
            "Poll MAGMA's VONA pages live. Off by default: magma.esdm.go.id's robots.txt "
            "disallows all crawling (research/05). Turn on only with PVMBG's permission; "
            "REPLAY serves recorded VONAs either way."
        ),
    )

    # Reconciliation tolerances and activity rules.
    height_tolerance_ft: int = Field(default=2000, ge=0)
    direction_tolerance_deg: float = Field(default=45.0, ge=0, le=180)
    lag_threshold_min: int = Field(default=20, ge=0)
    silence_threshold_min: int = Field(default=30, ge=0)
    active_radius_km: float = Field(default=300.0, gt=0)
    vona_window_h: float = Field(default=24.0, gt=0)

    # Exposure. Margins, buffers and minima are operator policy (data/policy/policy_a.json).
    exposure_lookahead_min: int = Field(
        default=60, gt=0, description="'If current track and level are held' projection"
    )
    default_horizon_h: float = Field(default=6.0, gt=0, le=MAX_HORIZON_H)
    adsb_radius_nm: int = Field(default=250, gt=0, le=250)
    crew_fix_history_min: int = Field(
        default=30,
        gt=0,
        le=360,
        description="How long airline ADS-B positions are kept in memory, so a crew report "
        "entered after the observation can still be placed at the flight's fix",
    )

    # Feed cadences (seconds).
    cadence_sigmet_s: int = 60
    cadence_vona_s: int = 300
    cadence_jma_volcano_s: int = 300
    cadence_vaac_s: int = 300
    cadence_frames_s: int = 600
    cadence_hsd_s: int = 600
    cadence_winds_s: int = 3600
    cadence_taf_s: int = 1800
    cadence_adsb_s: int = 30
    stale_factor: float = Field(default=3.0, gt=1, description="Stale after factor x cadence")

    # HTTP politeness.
    http_timeout_s: float = Field(default=20.0, gt=0)
    http_retries: int = Field(default=2, ge=0, le=5)
    adsb_min_interval_s: float = Field(default=1.1, ge=1.0)

    # Science (split-window BTD).
    btd_band_pair: Literal["B13-B15", "B14-B15"] = "B13-B15"
    btd_threshold_k: float = -0.5
    btd_half_width_km: float = Field(default=250.0, gt=0)

    # Server.
    port: int = Field(default=8080, validation_alias=AliasChoices("PORT", "TEPHRA_PORT"))
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    max_upload_bytes: int = Field(
        default=1_310_720,
        ge=MAX_BODY_BYTES,
        description=(
            "Largest request body of POST /api/desk/ask/voice (one recording up to 1 MiB plus "
            "multipart overhead); every other route is held to MAX_BODY_BYTES or "
            "MAX_NOTICE_BODY_BYTES"
        ),
    )
    build_sha: str | None = Field(
        default=None, description="Commit the image was built from (set by the Dockerfile)"
    )
    max_event_streams: int = Field(
        default=200,
        ge=1,
        description=(
            "Open GET /api/events streams; each holds a Cloud Run request slot, so keep "
            "this below the service's --concurrency. With hosted on, each airline's own "
            "places (TEPHRA_HOSTED_STREAMS_PER_TENANT) are held apart from the demo's within it"
        ),
    )
    airline_session_ttl_h: float = Field(
        default=12.0, gt=0, le=72, description="Hours an airline workspace sign-in lasts"
    )
    fleet_prefixes: Annotated[frozenset[str], NoDecode] = Field(
        default=frozenset(),
        description=(
            "Own-fleet filter: callsign prefixes (ICAO 3 letters, comma list); with "
            "fleet_hexes empty too, every airline-style aircraft is checked (the default)"
        ),
    )
    fleet_hexes: Annotated[frozenset[str], NoDecode] = Field(
        default=frozenset(),
        description="Own-fleet filter: ICAO 24-bit addresses (6 hex digits, comma list)",
    )
    network_airports: Annotated[frozenset[str], NoDecode] = Field(
        default=frozenset(),
        description=(
            "The airline's own airports (ICAO 4 letters, comma list) checked for closure by "
            "code every tick; empty: only recovery's RFA network airports (the default)"
        ),
    )
    policy_file: str = Field(
        default="policy/policy_a.json",
        pattern=r"^policy/[a-z0-9_-]{1,40}\.json$",
        description="The operator policy file, relative to TEPHRA_DATA_DIR",
    )
    airline_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=120,
        pattern=r"^[^\x00-\x1f\x7f]+$",
        description=(
            "An airline's own TEPHRA: the airline's name, said in drafts and documents in "
            "place of the fictional Ring of Fire Air (needs the own fleet)"
        ),
    )
    airline_icao: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{3}$",
        description="An airline's own TEPHRA: its ICAO designator; its own callsigns too",
    )
    airline_iata: str | None = Field(
        default=None, pattern=r"^[A-Z0-9]{2}$", description="An airline's own TEPHRA: IATA code"
    )
    airline_schedule: str | None = Field(
        default=None,
        pattern=r"^airline/[a-z0-9_-]{1,40}\.json$",
        description=(
            "An airline's own TEPHRA: its flights.json, relative to "
            "TEPHRA_DATA_DIR; names a fleet aircraft by its scheduled flight"
        ),
    )
    airline_fleet: str | None = Field(
        default=None,
        pattern=r"^airline/[a-z0-9_-]{1,40}\.json$",
        description=(
            "An airline's own TEPHRA: its fleet.json (registrations and addresses), relative "
            "to TEPHRA_DATA_DIR; ties an aircraft to its schedule and registration"
        ),
    )

    # Hosted airlines (feature "hosted"; off unless TEPHRA_FEATURES names it).
    key_secret: SecretStr | None = Field(
        default=None,
        description=(
            "Seals each hosted airline's model key (AES-256-GCM, key derived with HKDF); unset: "
            "derived from TEPHRA_SESSION_SECRET. Rotating it makes every sealed key unreadable"
        ),
    )
    hosted_max_tenants: int = Field(
        default=3, ge=0, le=3, description="Airlines in SHADOW or LIVE at once on this site"
    )
    hosted_tick_budget_s: int = Field(
        default=40,
        ge=35,
        le=45,
        description="Seconds an airline's tick may take in a hosted pass (publishes 15 s early)",
    )
    hosted_reads_cap: int = Field(
        default=40_000,
        ge=0,
        description="Site backstop: document reads a Pacific day before every airline pauses",
    )
    hosted_writes_cap: int = Field(
        default=16_000,
        ge=0,
        description="Site backstop: document writes a Pacific day before every airline pauses",
    )
    hosted_deletes_cap: int = Field(
        default=16_000,
        ge=0,
        description="Site backstop: document deletes a Pacific day before every airline pauses",
    )
    hosted_tenant_share: float = Field(
        default=0.6,
        gt=0,
        le=1,
        description=(
            "Part of each site cap shared by the airlines: each gets cap x share / "
            "TEPHRA_HOSTED_MAX_TENANTS a day and pauses alone past it"
        ),
    )
    hosted_blob_puts_cap: int = Field(
        default=4_000,
        ge=0,
        description="Satellite frame uploads by airlines a calendar month (storage operations)",
    )
    hosted_rss_limit_mb: int = Field(
        default=700,
        ge=200,
        description="No airline starts while the process uses more memory than this (MB)",
    )
    hosted_push_gap_s: float = Field(
        default=10.0, ge=1, description="Seconds between two pushes on one airline key"
    )
    hosted_streams_per_tenant: int = Field(
        default=10, ge=1, le=50, description="Open event streams per airline"
    )
    hosted_tenant: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{3}$",
        description="Set only in a hosted airline's runtime settings, never from the environment",
    )
    hosted_stage: Literal["setup", "shadow", "live"] | None = Field(
        default=None,
        description="Set only in a hosted airline's runtime settings, never from the environment",
    )

    @model_validator(mode="before")
    @classmethod
    def _not_moved_to_policy(cls, data: Any) -> Any:
        # A .env file's unknown keys arrive lower-cased with the prefix kept
        # ("tephra_vertical_margin_ft"); keyword arguments arrive as field names. Settings
        # reads the environment without regard to case, so the check does too.
        keys = {str(key).lower() for key in data} if isinstance(data, dict) else set()
        environ = {name.upper(): value for name, value in os.environ.items()}
        moved = [
            env
            for env, key in MOVED_TO_POLICY.items()
            if {key, env.lower()} & keys or environ.get(env, "").strip()
        ]
        if moved:
            raise ValueError(
                f"{', '.join(moved)} moved to data/policy/policy_a.json; remove the setting"
                " and change the policy file (with a new version) instead"
            )
        return data

    @field_validator("model_limits", mode="after")
    @classmethod
    def _with_default_limits(cls, value: dict[str, ModelLimit]) -> dict[str, ModelLimit]:
        return {**DEFAULT_MODEL_LIMITS, **value}

    @field_validator("features", mode="before")
    @classmethod
    def _parse_features(cls, value: Any) -> frozenset[str]:
        if isinstance(value, frozenset):
            names = value
        elif isinstance(value, str):
            text = value.strip()
            if text == "all":
                return ALL_FEATURES
            if text in ("", "hero"):
                return HERO_FEATURES
            names = frozenset(part.strip() for part in text.split(",") if part.strip())
        else:
            names = frozenset(value)
        unknown = sorted(names - ALL_FEATURES - OPT_IN_FEATURES)
        if unknown:
            raise ValueError(f"unknown feature(s): {', '.join(unknown)}")
        return names

    @field_validator("fleet_prefixes", mode="before")
    @classmethod
    def _parse_prefixes(cls, value: Any) -> frozenset[str]:
        return _code_list(value, _PREFIX, upper=True, what="fleet prefix")

    @field_validator("fleet_hexes", mode="before")
    @classmethod
    def _parse_hexes(cls, value: Any) -> frozenset[str]:
        return _code_list(value, _HEX, upper=False, what="fleet hex")

    @field_validator("network_airports", mode="before")
    @classmethod
    def _parse_airports(cls, value: Any) -> frozenset[str]:
        return _code_list(value, _AIRPORT, upper=True, what="network airport")

    @field_validator("airline_name", mode="before")
    @classmethod
    def _tidy_name(cls, value: Any) -> Any:
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator(
        "airline_icao", "airline_iata", "airline_schedule", "airline_fleet", mode="before"
    )
    @classmethod
    def _tidy_code(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, str):
            return value
        value = value.strip()
        return (
            value.upper() if info.field_name in ("airline_icao", "airline_iata") else value
        ) or None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        # A hosted airline without a readable key runs with every model step unavailable;
        # nowhere else may gemini run keyless.
        if self.llm == "gemini" and self.gemini_api_key is None and self.hosted_tenant is None:
            raise ValueError("TEPHRA_LLM=gemini needs GEMINI_API_KEY (Google AI Studio key)")
        if self.llm == "ollama" and not all(":" in m for m in (self.model, self.model_lite)):
            raise ValueError(
                "TEPHRA_LLM=ollama needs TEPHRA_MODEL and TEPHRA_MODEL_LITE set to Ollama tags "
                "(name:tag, e.g. gemma4:e4b)"
            )
        if self.ai_urgent_share + self.ai_interactive_share >= 1:
            raise ValueError(
                "TEPHRA_AI_URGENT_SHARE + TEPHRA_AI_INTERACTIVE_SHARE must leave a share for "
                "routine work (their sum must be below 1)"
            )
        for name in ("session_secret", "task_token", "key_secret"):
            secret = getattr(self, name)
            if secret is not None and len(secret.get_secret_value().strip()) < MIN_SECRET_CHARS:
                raise ValueError(
                    f"TEPHRA_{name.upper()} must be at least {MIN_SECRET_CHARS} characters; "
                    "generate one with secrets.token_urlsafe(32)"
                )
        self._check_replay_window()
        self._check_own_airline()
        self._check_hosted()
        if self.store == "firestore" and not (self.gcp_project and self.gcs_bucket):
            raise ValueError(
                "TEPHRA_STORE=firestore needs TEPHRA_GCP_PROJECT and TEPHRA_GCS_BUCKET"
            )
        return self

    def _check_replay_window(self) -> None:
        """A window is refused, never clamped: it loops inside one named case, and
        ``replay.start_replay_clock`` checks that it lies within that case's recording."""
        if self.replay_end is None:
            return
        if self.replay_start is None or not self.replay_case:
            raise ValueError(
                "TEPHRA_REPLAY_END needs TEPHRA_REPLAY_START and TEPHRA_REPLAY_CASE: the replay "
                "loops over that window of that case"
            )
        if self.replay_start.tzinfo is None:
            raise ValueError("TEPHRA_REPLAY_START must carry a UTC offset (e.g. ...Z)")
        if self.replay_end <= self.replay_start:
            raise ValueError("TEPHRA_REPLAY_END must be after TEPHRA_REPLAY_START")

    def _check_own_airline(self) -> None:
        """The airline settings belong to an airline's own TEPHRA; without an own fleet they
        would label the fictional demo airline's drafts with a real airline's name."""
        own = [
            f"TEPHRA_{name.upper()}"
            for name in (
                "airline_name",
                "airline_icao",
                "airline_iata",
                "airline_schedule",
                "airline_fleet",
            )
            if getattr(self, name) is not None
        ]
        if own and not (self.fleet_prefixes or self.fleet_hexes):
            raise ValueError(
                f"{', '.join(own)}: only for an airline's own TEPHRA; set TEPHRA_FLEET_PREFIXES"
                " or TEPHRA_FLEET_HEXES too"
            )

    def _check_hosted(self) -> None:
        if (self.hosted_tenant is None) != (self.hosted_stage is None):
            raise ValueError("hosted_tenant and hosted_stage are set together, or neither")
        if "hosted" not in self.features:
            return
        if "onboard" not in self.features:
            raise ValueError(
                "TEPHRA_FEATURES: hosted needs onboard (airlines sign up and are verified there)"
            )
        if "session_secret" not in self.model_fields_set and self.key_secret is None:
            raise ValueError(
                "TEPHRA_FEATURES=hosted needs TEPHRA_SESSION_SECRET or TEPHRA_KEY_SECRET set: a "
                "random per-process secret would make every sealed model key unreadable after "
                "a restart"
            )
        held_apart = self.hosted_max_tenants * self.hosted_streams_per_tenant
        if self.max_event_streams <= held_apart:
            raise ValueError(
                "TEPHRA_MAX_EVENT_STREAMS must be more than TEPHRA_HOSTED_MAX_TENANTS x "
                f"TEPHRA_HOSTED_STREAMS_PER_TENANT ({held_apart}): those places are held apart "
                "for the airlines and the demo needs at least one"
            )

    @property
    def airline(self) -> Airline:
        """The demo's fictional airline while no own fleet is set; else the airline whose
        fleet it is. An own fleet without TEPHRA_AIRLINE_NAME and TEPHRA_AIRLINE_ICAO raises:
        its drafts would otherwise speak for the fictional airline (create_runtime and
        create_app read this at startup)."""
        if not (self.fleet_prefixes or self.fleet_hexes):
            return DEMO_AIRLINE
        if self.airline_name is None or self.airline_icao is None:
            raise ValueError(
                "an airline's own TEPHRA (TEPHRA_FLEET_PREFIXES or TEPHRA_FLEET_HEXES) needs "
                "TEPHRA_AIRLINE_NAME and TEPHRA_AIRLINE_ICAO: its drafts name the airline"
            )
        return Airline(
            code=self.airline_icao,
            name=self.airline_name,
            iata=self.airline_iata,
            fictional=False,
            shadow=self.hosted_stage == "shadow",
        )

    def unlimited_models(self) -> list[str]:
        """Configured models with no free-tier limits row: TEPHRA never calls them (their
        budget is 0, so every step on them says AI UNAVAILABLE) until a row is added."""
        configured = {self.model, self.model_lite, self.model_tts}
        return sorted(configured - self.model_limits.keys())

    def daily_budget(self, model_id: str) -> int:
        """Calls a Google quota day TEPHRA allows ``model_id``: the override set for
        TEPHRA_MODEL or TEPHRA_MODEL_LITE, else its free limit less the margin, else 0 (a
        model with no limits row is never called)."""
        overrides = [
            budget
            for model, budget in (
                (self.model, self.model_daily_budget),
                (self.model_lite, self.model_lite_daily_budget),
            )
            if model == model_id and budget is not None
        ]
        if overrides:
            return min(overrides)
        limit = self.model_limits.get(model_id)
        return 0 if limit is None else self._under_margin(limit.rpd)

    def paced_rpm(self, model_id: str) -> int:
        """Requests a minute sent to ``model_id``: its free limit less the margin, at least 1."""
        limit = self.model_limits.get(model_id)
        return 1 if limit is None else max(1, self._under_margin(limit.rpm))

    def paced_tpm(self, model_id: str) -> int | None:
        """Input tokens a minute sent to ``model_id``, for a model Google limits by tokens."""
        limit = self.model_limits.get(model_id)
        if limit is None or limit.tpm is None:
            return None
        return max(1, self._under_margin(limit.tpm))

    def _under_margin(self, value: int) -> int:
        # round() first: 15 x 0.9 is 13.5 but 20 x 0.9 must not come out as 17.999...
        return math.floor(round(value * (1 - self.ai_budget_margin), 6))

    @property
    def region_preset(self) -> Region:
        return REGIONS[self.region]

    @property
    def regions(self) -> list[Region]:
        return list(REGIONS.values())

    def cadence_s(self, feed: FeedId) -> int:
        cadences = {
            FeedId.SIGMET: self.cadence_sigmet_s,
            FeedId.VONA: self.cadence_vona_s,
            FeedId.JMA_VOLCANO: self.cadence_jma_volcano_s,
            FeedId.VAAC_TOKYO: self.cadence_vaac_s,
            FeedId.VAAC_DARWIN: self.cadence_vaac_s,
            FeedId.TAF: self.cadence_taf_s,
            FeedId.METAR: self.cadence_taf_s,
            FeedId.ADSB: self.cadence_adsb_s,
            FeedId.WINDS: self.cadence_winds_s,
            FeedId.FRAMES: self.cadence_frames_s,
            FeedId.HSD: self.cadence_hsd_s,
        }
        return cadences[feed]

    def stale_after_s(self, feed: FeedId) -> int:
        return int(self.cadence_s(feed) * self.stale_factor)


def _code_list(value: Any, pattern: re.Pattern[str], *, upper: bool, what: str) -> frozenset[str]:
    """A comma or whitespace separated list of codes; a bad entry stops startup, named."""
    parts = value.replace(",", " ").split() if isinstance(value, str) else list(value)
    codes = frozenset(part.strip().upper() if upper else part.strip().lower() for part in parts)
    if bad := sorted(code for code in codes if pattern.fullmatch(code) is None):
        raise ValueError(f"invalid {what}: {', '.join(bad)}")
    return codes


def apply_process_env(settings: Settings, *, export_key: bool = True) -> None:
    """Point ADK and google-genai at the Gemini API key and away from Vertex AI.

    Current SDKs call the switch GOOGLE_GENAI_USE_ENTERPRISE and still honour the older
    GOOGLE_GENAI_USE_VERTEXAI, so both are pinned off. GOOGLE_API_KEY is overwritten only
    when GEMINI_API_KEY is set, so a stray key from the shell never wins. With the hosted
    feature on, the key is never exported: every model client is given its key explicitly,
    and a client that reads the environment finds none instead of TEPHRA's key.
    """
    if settings.hosted_tenant is not None:
        raise ValueError("a hosted airline's settings never reach the process environment")
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
    os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "FALSE"
    if export_key and "hosted" not in settings.features and settings.gemini_api_key is not None:
        os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key.get_secret_value()


_HOSTED_ONLY_ENV: Final = ("TEPHRA_HOSTED_TENANT", "TEPHRA_HOSTED_STAGE")
_bound_settings: ContextVar[Callable[[], Settings] | None] = ContextVar(
    "tephra_settings", default=None
)


@lru_cache(maxsize=1)
def _process_settings() -> Settings:
    """The process's settings, read once from the environment (and ``.env`` if present)."""
    environ = {name.upper() for name, value in os.environ.items() if value.strip()}
    if found := [name for name in _HOSTED_ONLY_ENV if name in environ]:
        raise ValueError(f"{', '.join(found)}: set only for a hosted airline's runtime")
    settings = Settings()
    if settings.hosted_tenant is not None:
        raise ValueError(
            f"{', '.join(_HOSTED_ONLY_ENV)}: set only for a hosted airline's runtime (.env)"
        )
    apply_process_env(settings, export_key="hosted" not in settings.features)
    return settings


def get_settings() -> Settings:
    """The settings bound in this context (a hosted airline's runtime), else the process's."""
    provider = _bound_settings.get()
    return _process_settings() if provider is None else provider()


@contextmanager
def bind_settings(provider: Callable[[], Settings]) -> Iterator[None]:
    """Make ``get_settings()`` answer ``provider()`` in this context and the tasks and threads
    it starts. A provider, not a value: a runtime's later settings reach work already running."""
    token = _bound_settings.set(provider)
    try:
        yield
    finally:
        _bound_settings.reset(token)
