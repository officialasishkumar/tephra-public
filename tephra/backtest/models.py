"""The backtest scorecard (``docs/backtest/scorecard.json``, store collection ``backtest``).

Every number in it is computed by code from polygons; no model writes or changes one.
"""

from typing import Literal

from pydantic import Field

from tephra.models import TephraModel, UtcDatetime

Arm = Literal["D", "G"]


class TickScore(TephraModel):
    """One replay tick of one volcano, scored against the official footprints issued later.

    The ratio fields are ``None`` when their denominator is zero (no later footprint, no zone,
    no official area), never 0.
    """

    t: UtcDatetime
    volcano_id: str
    cone_mode: str
    zone_area_km2: float
    official_area_km2: float
    truth_area_km2: float
    footprints: int = Field(description="Later official footprints this tick is scored against")
    coverage: float | None = Field(default=None, description="|Z and A| / |A| (POD, area form)")
    coverage_official: float | None = Field(default=None, description="|O and A| / |A|")
    coverage_gain: float | None = None
    overwarn: float | None = Field(default=None, description="|Z minus A| / |Z| (1 - precision)")
    excess_vs_official: float | None = Field(default=None, description="|Z| / |O|")
    bias: float | None = Field(default=None, description="|Z| / |A|")
    csi: float | None = Field(default=None, description="|Z and A| / |Z or A| (FMS)")
    csi_official: float | None = None
    hausdorff_km: float | None = None
    centroid_km: float | None = None
    vertical_hit: bool | None = Field(
        default=None, description="Zone top at or above every scored footprint's top"
    )
    airports_in_truth: list[str] = Field(default_factory=list)
    airports_covered: list[str] = Field(default_factory=list)
    floor_ok: bool = Field(description="The cone contains every official layer it was built on")
    input_leaks: int = Field(description="Inputs stamped after this tick's clock (must be 0)")


class FootprintLead(TephraModel):
    """How early the zone, and the official area alone, covered one later official polygon."""

    footprint_id: str
    volcano_id: str
    issued_at: UtcDatetime
    valid_at: UtcDatetime
    lead_zone_min: int | None = Field(description="None: not covered at the last tick before issue")
    lead_official_min: int | None = None
    incremental_min: int | None = Field(
        default=None, description="lead_zone - lead_official (official-only counts 0 if missed)"
    )


class LeadSummary(TephraModel):
    tau: float
    n_footprints: int
    n_missed: int = Field(description="Zone coverage below tau at the last tick before issue")
    n_covered_before_official: int = Field(
        description="Zone covered it and the official area alone did not, or later"
    )
    median_min: float | None = Field(description="Median incremental lead over covered footprints")
    p90_min: float | None = None
    footprints: list[FootprintLead] = Field(default_factory=list)


class Summary(TephraModel):
    """Headline numbers over the ticks that had a later official footprint to score against."""

    ticks_scored: int
    coverage_mean: float | None = None
    coverage_official_mean: float | None = None
    coverage_gain_mean: float | None = None
    overwarn_mean: float | None = None
    excess_vs_official_mean: float | None = None
    csi_mean: float | None = None
    csi_official_mean: float | None = None
    hausdorff_km_median: float | None = None
    centroid_km_median: float | None = None
    vertical_hit_rate: float | None = None


class ModelUse(TephraModel):
    backend: str
    model_id: str
    calls: int = Field(description="New Gemini calls this run spent (cache reads are free)")


class CaseScore(TephraModel):
    case_id: str
    label: str
    arm: Arm
    region: str
    vaacs: list[str]
    t_first: UtcDatetime
    t_last: UtcDatetime
    step_min: int
    volcano_ids: list[str]
    sources_used: list[str]
    latest_input_ts: UtcDatetime | None
    ticks: list[TickScore]
    summary: Summary
    lead: list[LeadSummary]
    floor_violations: int
    input_leaks: int
    models: ModelUse
    notes: list[str] = Field(default_factory=list)


class BacktestScorecard(TephraModel):
    generated_at: UtcDatetime
    step_min: int
    cases: list[CaseScore]
    overall: dict[str, Summary] = Field(description="Per arm, over every case's scored ticks")
    overall_lead: dict[str, list[LeadSummary]] = Field(default_factory=dict)
    floor_violations: int
    input_leaks: int
    caveats: list[str]
