"""Runtime settings (environment variables) and fixed product and safety constants.

Only composition roots (``tephra.api.server``, ``tephra.pipeline.create_runtime``,
``scripts/*``) call :func:`get_settings`. Library functions take a ``Settings`` argument
so tests can pass ``Settings(_env_file=None, ...)`` explicitly.
"""

import math
import os
import secrets
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import (
    AliasChoices,
    Field,
    PositiveInt,
    SecretStr,
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
NO_MODEL_LABEL = "NO MODEL"
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

Feature = Literal["connect", "crew", "notices", "satellite", "btd", "voice", "example", "present"]
ALL_FEATURES: frozenset[str] = frozenset(get_args(Feature))
HERO_FEATURES: frozenset[str] = frozenset()
"""The demo shows the hero path and its three acts only."""


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
            "to enter the area, a plume read it waits on); urgent work is never paced"
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
            "to routine work, all of them by midnight Pacific"
        ),
    )
    gemini_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("GEMINI_API_KEY")
    )
    llm_timeout_s: float = Field(default=60.0, gt=0)
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
            "or a comma list. Hidden features keep their routes and tests; their scheduled "
            "model work stops."
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
            "this below the service's --concurrency"
        ),
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
        unknown = sorted(names - ALL_FEATURES)
        if unknown:
            raise ValueError(f"unknown feature(s): {', '.join(unknown)}")
        return names

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.llm == "gemini" and self.gemini_api_key is None:
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
        for name in ("session_secret", "task_token"):
            secret = getattr(self, name)
            if secret is not None and len(secret.get_secret_value().strip()) < MIN_SECRET_CHARS:
                raise ValueError(
                    f"TEPHRA_{name.upper()} must be at least {MIN_SECRET_CHARS} characters; "
                    "generate one with secrets.token_urlsafe(32)"
                )
        self._check_replay_window()
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


def apply_process_env(settings: Settings) -> None:
    """Point ADK and google-genai at the Gemini API key and away from Vertex AI.

    Current SDKs call the switch GOOGLE_GENAI_USE_ENTERPRISE and still honour the older
    GOOGLE_GENAI_USE_VERTEXAI, so both are pinned off. GOOGLE_API_KEY is overwritten only
    when GEMINI_API_KEY is set, so a stray key from the shell never wins.
    """
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
    os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "FALSE"
    if settings.gemini_api_key is not None:
        os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, read once from the environment (and ``.env`` if present)."""
    settings = Settings()
    apply_process_env(settings)
    return settings
