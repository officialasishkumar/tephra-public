"""Runtime settings (environment variables) and fixed product and safety constants.

Only composition roots (``tephra.api.server``, ``tephra.pipeline.create_runtime``,
``scripts/*``) call :func:`get_settings`. Library functions take a ``Settings`` argument
so tests can pass ``Settings(_env_file=None, ...)`` explicitly.
"""

import os
import secrets
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tephra.models import AdsbQueryPoint, BBox, FeedId, Region, RunMode, UtcDatetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
"""Repository root when running from a checkout (the Docker image keeps that layout)."""

# --- product constants ------------------------------------------------------------------

AIRLINE_CODE = "RFA"
AIRLINE_NAME = "Ring of Fire Air"
DISCLAIMER = "Decision support only - fictional airline - not for operational use"
NO_MODEL_LABEL = "NO MODEL"
REPLAY_BANNER_TEMPLATE = "REPLAY: recorded real feeds from {date}"
"""``{date}`` is ``recorded_from`` formatted as ``%d %b %Y`` (e.g. '07 Oct 2026')."""

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
    llm: Literal["gemini", "stub"] = Field(
        default="stub", description="'stub' is deterministic and offline, labelled NO MODEL"
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
    model_daily_budget: int = Field(
        default=18, ge=0, description="Max calls/UTC day to TEPHRA_MODEL (free tier ~20 RPD)"
    )
    model_lite_daily_budget: int = Field(
        default=450, ge=0, description="Max calls/UTC day to TEPHRA_MODEL_LITE (~500 RPD)"
    )
    model_rpm: int = Field(
        default=5, gt=0, description="Requests a minute sent to TEPHRA_MODEL (free-tier pacing)"
    )
    model_lite_rpm: int = Field(
        default=14,
        gt=0,
        description="Requests a minute sent to TEPHRA_MODEL_LITE; the free tier allows 15",
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

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.llm == "gemini" and self.gemini_api_key is None:
            raise ValueError("TEPHRA_LLM=gemini needs GEMINI_API_KEY (Google AI Studio key)")
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
