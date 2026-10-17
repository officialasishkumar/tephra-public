"""Go live on TEPHRA: the four-item checklist, the region, and whether shadow runs may start
(SPEC §5.1).

- **feeds**: positions and flight plans, where the answers declare them, each arrived through a
  live key in the last 10 minutes (pilot reports are optional and never block). Nothing
  declared: done, the airline's flights are found on public ADS-B by callsign. The counts begin
  again when the process starts, and the detail then says since when.
- **assistant**: a model and a lite model from the free-tier table, and a readable key.
- **policy**: the current version confirmed.
- **people**: at least one dispatcher has joined.

The region is derived from the network's airports when exactly one preset holds any of them;
otherwise the airline chooses, and an airline outside every preset is told the others are not
built.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import Final, cast

from tephra.airline.models import AirlineAnswers
from tephra.config import REGIONS, RegionKey, Settings
from tephra.feeds.airports import AirportCatalogue
from tephra.hosted import keys
from tephra.hosted.feeds import FeedStats, Section
from tephra.hosted.models import (
    GoLive,
    GoLiveItem,
    HostedRefused,
    Member,
    RegionChoice,
    RegionOption,
    Slots,
    TenantRecord,
)
from tephra.hosted.settings_for import hosted_models
from tephra.util import timeutil

__all__ = [
    "FEEDS_FRESH",
    "OUTSIDE_NOTE",
    "checklist",
    "derive_region",
    "regions_for",
    "start_region",
]

FEEDS_FRESH: Final = timedelta(minutes=10)
OUTSIDE_NOTE: Final = "Your network is outside these regions: other regions are not built."
_WORDS: Final[dict[str, str]] = {
    "positions": "Positions",
    "flight_plans": "flight plans",
}


def regions_for(answers: AirlineAnswers, airports: AirportCatalogue) -> list[RegionKey]:
    """The presets that hold at least one of the network's airports (TEPHRA's airport list)."""
    found: list[RegionKey] = []
    for key, region in REGIONS.items():
        for entry in answers.network.airports:
            airport = airports.get(entry.icao)
            if airport is not None and region.bbox.contains(airport.lat, airport.lon):
                found.append(cast(RegionKey, key))
                break
    return found


def derive_region(answers: AirlineAnswers, airports: AirportCatalogue) -> RegionKey | None:
    found = regions_for(answers, airports)
    return found[0] if len(found) == 1 else None


def start_region(
    answers: AirlineAnswers, airports: AirportCatalogue, requested: RegionKey | None
) -> RegionKey:
    """The region shadow runs start in: the derived one (read-only), else the one chosen."""
    derived = derive_region(answers, airports)
    if derived is not None:
        if requested not in (None, derived):
            raise HostedRefused(422, "region", "Your region follows your network's airports")
        return derived
    if requested is None:
        raise HostedRefused(422, "region", "Choose a region")
    return requested


def _feeds_item(
    record: TenantRecord,
    answers: AirlineAnswers,
    stats: FeedStats,
    live_keys: Iterable[str],
    now: datetime,
) -> GoLiveItem:
    declared = answers.feeds
    wanted: list[tuple[Section, bool]] = [
        ("positions", declared.positions),
        ("flight_plans", declared.flight_plans),
    ]
    required = [name for name, declared_it in wanted if declared_it]
    href = f"/a/{record.icao}/feeds"
    keys_now = list(live_keys)
    if not required:
        return GoLiveItem(
            key="feeds",
            done=True,
            title="Feeds connected",
            detail="Public ADS-B only: your flights are found by callsign "
            f"{answers.airline.callsign_prefix}",
            href=href,
        )
    fresh = {
        name: (last := stats.last_received(name, now=now, keys=keys_now)) is not None
        and now - last <= FEEDS_FRESH
        for name in required
    }
    names = " and ".join(_WORDS[name] for name in required)
    names = names[0].upper() + names[1:]
    got = stats.last_received("pilot_reports", now=now, keys=keys_now) is not None
    if all(fresh.values()):
        reports = "received" if got else "none yet (optional)"
        detail = f"{names} received in the last 10 minutes."
    else:
        reports = "optional"
        missing = " and ".join(_WORDS[name] for name in required if not fresh[name])
        missing = missing[0].upper() + missing[1:]
        detail = f"{missing}: none received in the last 10 minutes."
    if declared.pilot_reports:
        detail += f" Pilot reports: {reports}."
    if now - stats.since < FEEDS_FRESH:
        detail += f" Counted since {timeutil.ensure_utc(stats.since):%H:%M}Z."
    return GoLiveItem(
        key="feeds", done=all(fresh.values()), title="Feeds connected", detail=detail, href=href
    )


def _assistant_item(record: TenantRecord, settings: Settings) -> GoLiveItem:
    href = f"/a/{record.icao}/settings/assistant"
    table = hosted_models(settings)
    assistant = record.assistant
    sealed = record.model_key
    if assistant is None or not {assistant.model, assistant.model_lite} <= table.keys():
        done, detail = False, "No model chosen"
    elif sealed is None:
        done, detail = False, "No key set"
    elif not keys.readable(record.icao, sealed, settings):
        done, detail = False, "The key cannot be read: enter it again"
    else:
        done, detail = True, f"Google AI Studio with your own key, ending {sealed.last4}"
    return GoLiveItem(
        key="assistant", done=done, title="Model and key set", detail=detail, href=href
    )


def _policy_item(record: TenantRecord) -> GoLiveItem:
    confirmed = record.policy_confirmed
    done = confirmed is not None and confirmed.version == record.policy_version
    if done and confirmed is not None:
        detail = f"Version {record.policy_version} confirmed by {confirmed.by.split('#')[0]}"
    else:
        detail = f"Version {record.policy_version} not confirmed"
    return GoLiveItem(
        key="policy",
        done=done,
        title="Policy confirmed",
        detail=detail,
        href=f"/a/{record.icao}/settings/policy#versions",
    )


def _people_item(record: TenantRecord, members: Sequence[Member], open_invites: int) -> GoLiveItem:
    joined = sum(1 for member in members if member.role == "dispatcher")
    invites = f"{open_invites} invite{'' if open_invites == 1 else 's'} open"
    people = f"{joined} dispatcher{'' if joined == 1 else 's'} joined"
    detail = f"{people}; {invites}" if joined else f"No dispatcher has joined yet; {invites}"
    return GoLiveItem(
        key="people",
        done=joined > 0,
        title="Dispatchers invited",
        detail=detail,
        href=f"/a/{record.icao}/settings/people",
    )


def checklist(
    record: TenantRecord,
    answers: AirlineAnswers,
    *,
    settings: Settings,
    airports: AirportCatalogue,
    stats: FeedStats,
    live_keys: Iterable[str],
    members: Sequence[Member],
    open_invites: int,
    slots_used: int,
    memory_ok: bool,
    now: datetime,
) -> GoLive:
    """``members`` with their effective roles; ``live_keys`` the ids of the airline's
    unrevoked push keys; ``settings`` the site's."""
    items = [
        _feeds_item(record, answers, stats, live_keys, now),
        _assistant_item(record, settings),
        _policy_item(record),
        _people_item(record, members, open_invites),
    ]
    found = regions_for(answers, airports)
    derived = found[0] if len(found) == 1 else None
    region = None
    if derived is not None:
        region = RegionChoice(key=derived, name=REGIONS[derived].name, derived=True)
    elif record.region is not None:
        region = RegionChoice(key=record.region, name=REGIONS[record.region].name, derived=False)
    max_slots = settings.hosted_max_tenants
    if not all(item.done for item in items):
        blocked = "checklist"
    elif region is None:
        blocked = "region"
    elif slots_used >= max_slots:
        blocked = "airline_limit_reached"
    elif not memory_ok:
        blocked = "site_memory"
    else:
        blocked = None
    return GoLive(
        state=record.state,
        items=items,
        region=region,
        regions=[
            RegionOption(key=cast(RegionKey, key), name=region.name)
            for key, region in REGIONS.items()
        ],
        region_note=OUTSIDE_NOTE if not found else None,
        slots=Slots(used=slots_used, max=max_slots),
        can_start=record.state == "setup" and blocked is None,
        blocked=blocked,
    )
