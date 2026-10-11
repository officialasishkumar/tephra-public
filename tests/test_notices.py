"""JMA eruption reports, the Notice Reader's verification, and the notice routes.

JMA documents are the real files in tests/fixtures/jma (PDL 1.0); Indonesian, Filipino and
Japanese notices are the hand-written synthetic_* files. The model is a scripted stand-in:
no network and no Gemini call.
"""

import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from tephra.agents.llm import LlmCall, LlmPart, StubBackend, prompt_hash
from tephra.agents.notice_reader import (
    PROMPT_PATH,
    ColourRead,
    FlagRead,
    HeightRead,
    NoticeExtraction,
    NoticeReading,
    ObserverRead,
    TextRead,
    normalise_notice,
    notice_id,
    parse_notice_time,
    read_notice,
)
from tephra.api import ApiError
from tephra.api.auth import require_desk
from tephra.api.routes_notices import router
from tephra.api.server import _json, get_runtime
from tephra.config import PROJECT_ROOT
from tephra.desk import audit
from tephra.feeds.base import FetchError, FetchResult, build_url
from tephra.feeds.jma_volcano import (
    CREDIT,
    JMA_EQVOL_URL,
    fetch_jma_volcano,
    parse_jma_entries,
    parse_jma_report,
)
from tephra.feeds.volcanoes import load_volcanoes
from tephra.models import (
    AuditAction,
    AviationColor,
    FeedId,
    LlmBackendName,
    RunMode,
    SessionInfo,
    SseEvent,
    Vona,
)
from tephra.store.base import Collection
from tephra.store.sqlite_store import SqliteStore
from tephra.util.events import EventBus
from tephra.util.hashing import sha256_bytes
from tephra.util.timeutil import FixedClock, use_clock

FIXTURES = Path(__file__).parent / "fixtures"
JMA = FIXTURES / "jma"
NOTICES = FIXTURES / "notices"
DATA_URL = "https://www.data.jma.go.jp/developer/xml/data/"
VFVO52 = "20261008050115_0_VFVO52_400000.xml"
AT = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
CATALOGUE = load_volcanoes(PROJECT_ROOT / "data")


@pytest.fixture(autouse=True)
def clock() -> Any:
    with use_clock(FixedClock(AT)):
        yield


# --- JMA XML ----------------------------------------------------------------------------


def jma_result(content: bytes, url: str) -> FetchResult:
    return FetchResult(
        feed=FeedId.VONA,
        url=url,
        status_code=200,
        content=content,
        content_type="application/xml",
        fetched_at=AT,
        sha256=sha256_bytes(content),
    )


def fixture_result(name: str) -> FetchResult:
    url = JMA_EQVOL_URL if name == "eqvol.xml" else DATA_URL + name
    return jma_result((JMA / name).read_bytes(), url)


def eruption_doc(
    code: str, *, name: str = "桜島", kind: str = "噴火", plume: str = "", event_id: str = "9_506"
) -> bytes:
    """A small VFVO52/56-shaped document built from the element names of the real VFVO52."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Report xmlns="http://xml.kishou.go.jp/jmaxml1/"><Control><Title>t</Title></Control>
<Head xmlns="http://xml.kishou.go.jp/jmaxml1/informationBasis1/">
<ReportDateTime>2026-10-09T10:05:00+09:00</ReportDateTime><EventID>{event_id}</EventID>
<Headline><Text>{code} test</Text></Headline></Head>
<Body xmlns="http://xml.kishou.go.jp/jmaxml1/body/volcanology1/"
 xmlns:jmx_eb="http://xml.kishou.go.jp/jmaxml1/elementBasis1/">
<VolcanoInfo><Item><EventTime>
<EventDateTimeUTC>2026-10-09T01:00:00Z</EventDateTimeUTC></EventTime>
<Kind><Name>{kind}</Name></Kind>
<Areas><Area><Name>{name}</Name><Code>506</Code></Area></Areas></Item></VolcanoInfo>
<VolcanoObservation>{plume}</VolcanoObservation></Body></Report>""".encode()


def plume_xml(direction: str = "南東", height: str = "8200", unit: str = "FT") -> str:
    return (
        "<ColorPlume>"
        f'<jmx_eb:PlumeHeightAboveSeaLevel unit="{unit}">{height}</jmx_eb:PlumeHeightAboveSeaLevel>'
        f'<jmx_eb:PlumeDirection unit="漢字">{direction}</jmx_eb:PlumeDirection>'
        "</ColorPlume>"
    )


def test_real_eruption_report_becomes_a_vona() -> None:
    vona = parse_jma_report(fixture_result(VFVO52), CATALOGUE)
    assert vona is not None
    assert vona.volcano_name == "Sakurajima"
    assert vona.provenance.source_id == "JMA-VFVO52-20261008140100_506"
    assert vona.provenance.feed is FeedId.VONA
    assert vona.provenance.url == DATA_URL + VFVO52
    assert vona.issued_at == datetime(2026, 10, 8, 5, 1, tzinfo=UTC)
    assert vona.eruption_at == datetime(2026, 10, 8, 4, 53, tzinfo=UTC)
    assert vona.ash_observed is True
    assert vona.cloud_top_ft == 6800
    assert vona.cloud_top_m == round(6800 / 3.28084)
    assert vona.color_code is AviationColor.UNKNOWN
    assert vona.movement_text == "直上"
    assert vona.movement_toward_deg is None
    assert "噴煙量：中量" in (vona.remarks or "")  # noqa: RUF001
    assert "海抜6800FT" in vona.raw_text
    assert vona.raw_text.endswith(CREDIT)


@pytest.mark.parametrize(
    "name",
    [
        "20261008020006_0_VFVO50_010000.xml",
        "20261009070326_0_VFVO51_400000.xml",
        "20261011140052_0_VFVO53_010000.xml",
        "20261008050149_0_VFVO60_010000.xml",
    ],
)
def test_reports_without_an_ash_observation_are_not_vonas(name: str) -> None:
    assert parse_jma_report(fixture_result(name), CATALOGUE) is None


def test_kanji_direction_is_the_flow_toward_degrees() -> None:
    url = DATA_URL + "20261009100500_0_VFVO52_400000.xml"
    vona = parse_jma_report(jma_result(eruption_doc("52", plume=plume_xml("南東")), url), CATALOGUE)
    assert vona is not None
    assert (vona.movement_toward_deg, vona.movement_text) == (135.0, "南東")
    assert vona.cloud_top_ft == 8200


def test_an_eruption_with_no_plume_still_counts_when_it_is_the_kind() -> None:
    url = DATA_URL + "20261009100500_0_VFVO56_010000.xml"
    flash = parse_jma_report(jma_result(eruption_doc("56"), url), CATALOGUE)
    assert flash is not None
    assert flash.provenance.source_id == "JMA-VFVO56-9_506"
    assert (flash.ash_observed, flash.cloud_top_ft, flash.movement_toward_deg) == (True, None, None)
    other = eruption_doc("52", kind="火山性微動")
    assert parse_jma_report(jma_result(other, DATA_URL + "x_0_VFVO52_1.xml"), CATALOGUE) is None


def test_plume_height_in_metres_is_converted_and_unknown_volcanoes_are_skipped() -> None:
    url = DATA_URL + "20261009100500_0_VFVO52_400000.xml"
    in_metres = eruption_doc("52", plume=plume_xml(height="2000", unit="m"))
    vona = parse_jma_report(jma_result(in_metres, url), CATALOGUE)
    assert vona is not None
    assert vona.cloud_top_ft == round(2000 * 3.28084)
    unlisted = eruption_doc("52", name="御嶽山", plume=plume_xml())
    assert parse_jma_report(jma_result(unlisted, url), CATALOGUE) is None


def test_a_document_that_is_not_xml_is_an_error_not_a_guess() -> None:
    with pytest.raises(ValueError, match="not XML"):
        parse_jma_report(jma_result(b"<html>Service Unavailable", DATA_URL + VFVO52), CATALOGUE)


def test_real_feed_lists_only_ash_fall_forecasts_so_nothing_is_fetched() -> None:
    entries = parse_jma_entries(fixture_result("eqvol.xml"))
    assert len(entries) == 28  # 29 entries; the 29th is an earthquake report (VXSE53)
    assert {entry.code for entry in entries} == {"VFVO53"}


class FakeSource:
    def __init__(self, responses: Mapping[str, bytes]) -> None:
        self.responses = dict(responses)
        self.requested: list[str] = []

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        full_url = build_url(url, params)
        self.requested.append(full_url)
        if full_url not in self.responses:
            raise FetchError(full_url, feed, "HTTP 404")
        return jma_result(self.responses[full_url], full_url)

    async def aclose(self) -> None:
        return None


def atom(entries: Sequence[tuple[str, str]]) -> bytes:
    """An Atom feed of ``(document name, updated)`` entries."""
    items = "".join(
        f"<entry><title>t</title><id>{DATA_URL}{name}</id><updated>{updated}</updated>"
        f'<link type="application/xml" href="{DATA_URL}{name}"/></entry>'
        for name, updated in entries
    )
    return f'<feed xmlns="http://www.w3.org/2005/Atom"><title>f</title>{items}</feed>'.encode()


async def test_fetch_reads_only_new_eruption_entries_for_catalogue_volcanoes() -> None:
    new, old = "20261011100000_0_VFVO52_400000.xml", "20261001000000_0_VFVO52_400000.xml"
    forecast = "20261011110000_0_VFVO53_010000.xml"
    feed = atom(
        [
            (new, "2026-10-11T10:00:00Z"),
            (old, "2026-10-01T00:00:00Z"),
            (forecast, "2026-10-11T11:00:00Z"),
        ]
    )
    doc = eruption_doc("52", plume=plume_xml(), event_id="20261011_506")
    source = FakeSource({JMA_EQVOL_URL: feed, DATA_URL + new: doc, DATA_URL + old: doc})
    since = AT - timedelta(hours=6)
    vonas = await fetch_jma_volcano(source, CATALOGUE, since=since)
    assert [v.provenance.source_id for v in vonas] == ["JMA-VFVO52-20261011_506"]
    assert source.requested == [JMA_EQVOL_URL, DATA_URL + new]

    again = FakeSource({JMA_EQVOL_URL: feed, DATA_URL + new: doc})
    assert (
        await fetch_jma_volcano(
            again, CATALOGUE, since=since, known_urls=frozenset({DATA_URL + new})
        )
        == []
    )
    assert again.requested == [JMA_EQVOL_URL]


async def test_fetch_skips_a_report_stamped_after_now_and_one_that_fails() -> None:
    future, broken = "20261011140000_0_VFVO52_400000.xml", "20261011110000_0_VFVO52_400000.xml"
    feed = atom([(future, "2026-10-11T14:00:00Z"), (broken, "2026-10-11T11:00:00Z")])
    source = FakeSource({JMA_EQVOL_URL: feed})
    assert await fetch_jma_volcano(source, CATALOGUE, since=AT - timedelta(days=1)) == []
    assert source.requested == [JMA_EQVOL_URL, DATA_URL + broken]


async def test_an_unreadable_feed_raises() -> None:
    source = FakeSource({JMA_EQVOL_URL: b"<html>nope"})
    with pytest.raises(ValueError, match="not XML"):
        await fetch_jma_volcano(source, CATALOGUE, since=AT - timedelta(days=1))


# --- notice time ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("date_text", "time_text", "expected"),
    [
        ("11 Oktober 2026", "19:59 WIT", datetime(2026, 10, 11, 10, 59, tzinfo=UTC)),
        ("11 Oktober 2026", "07.05 WIB", datetime(2026, 10, 11, 0, 5, tzinfo=UTC)),
        ("11 Oktober 2026", "22:30 WITA", datetime(2026, 10, 11, 14, 30, tzinfo=UTC)),
        ("October 11, 2026", "1959 UTC", datetime(2026, 10, 11, 19, 59, tzinfo=UTC)),
        ("11 Oktubre 2026", "8:00 AM PHT", datetime(2026, 10, 11, 0, 0, tzinfo=UTC)),
        ("11 Oktubre 2026", "12:05 AM PHT", datetime(2026, 10, 10, 16, 5, tzinfo=UTC)),
        ("11 Oktubre 2026", "1:30 PM PHT", datetime(2026, 10, 11, 5, 30, tzinfo=UTC)),
        ("2026年10月11日", "19時59分頃（日本時間）", datetime(2026, 10, 11, 10, 59, tzinfo=UTC)),  # noqa: RUF001
        ("２０２６年１０月１１日", "１９時５９分 JST", datetime(2026, 10, 11, 10, 59, tzinfo=UTC)),
        ("2026-10-11", "10:59Z", datetime(2026, 10, 11, 10, 59, tzinfo=UTC)),
    ],
)
def test_notice_times_are_converted_by_code(
    date_text: str, time_text: str, expected: datetime
) -> None:
    assert parse_notice_time(date_text, time_text) == expected


@pytest.mark.parametrize(
    ("date_text", "time_text"),
    [
        ("11 Oktubre 2026", "8:00 AM"),  # no zone word: a zone is never assumed
        ("11 Oktober", "19:59 WIT"),  # no year
        ("31 Februari 2026", "19:59 WIT"),  # no such day
        ("11 Oktober 2026", "25:61 WIT"),
        ("11 Oktober 2026", "pagi hari WIT"),
        ("kemarin", "19:59 WIT"),
    ],
)
def test_notice_times_that_cannot_be_read_are_none(date_text: str, time_text: str) -> None:
    assert parse_notice_time(date_text, time_text) is None


# --- the Notice Reader ------------------------------------------------------------------


def text_of(name: str) -> str:
    return normalise_notice((NOTICES / name).read_text(encoding="utf-8"))


def say(value: str | None, evidence: str | None = None) -> TextRead:
    return TextRead(value=value, evidence=value if evidence is None else evidence)


def blank(**changes: Any) -> NoticeExtraction:
    base: dict[str, Any] = {
        "language": "id",
        "volcano": TextRead(),
        "date_text": TextRead(),
        "time_text": TextRead(),
        "colour_code": ColourRead(),
        "alert_level": TextRead(),
        "ash_observed": FlagRead(),
        "plume_height": HeightRead(),
        "direction": TextRead(),
        "observer_type": ObserverRead(),
    }
    return NoticeExtraction(**{**base, **changes})


def indonesian(**changes: Any) -> NoticeExtraction:
    column = "Tinggi kolom abu teramati ± 1200 m di atas puncak (± 2557 m di atas permukaan laut)"
    fields: dict[str, Any] = {
        "volcano": say("Ibu", "G. Ibu"),
        "date_text": say("11 Oktober 2026"),
        "time_text": say("19:59 WIT"),
        "alert_level": say("Level II (Waspada)"),
        "ash_observed": FlagRead(value=True, evidence=column),
        "plume_height": HeightRead(value=1200, unit="m", datum="above_summit", evidence=column),
        "direction": say("ke arah barat dan barat laut"),
        "observer_type": ObserverRead(value="ground_observer", evidence="dari pos pengamatan"),
    }
    return blank(**{**fields, **changes})


class ScriptedLlm:
    """Answers with the scripted extractions in order, as a non-stub backend would."""

    def __init__(self, answers: Sequence[NoticeExtraction | None], name: LlmBackendName = "gemini"):
        self.name: LlmBackendName = name
        self._answers = list(answers)
        self.calls = 0
        self.parts: list[Sequence[LlmPart]] = []

    def model_id(self, tier: str) -> str:
        return "gemini-test-lite"

    def reserve(self, tier: str) -> bool:
        return True

    def exhaust(self, tier: str) -> None:
        raise AssertionError("the Notice Reader never closes a tier itself")

    async def structured[T: BaseModel](
        self,
        *,
        tier: str,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        assert tier == "lite"
        answer = self._answers[self.calls]
        self.calls += 1
        self.parts.append(parts)
        call = LlmCall(
            backend=self.name,
            model_id="gemini-test-lite",
            prompt_hash=prompt_hash(system, parts),
            raw_text="{}" if answer is None else answer.model_dump_json(),
            error=None if answer is not None else "api_error 503 UNAVAILABLE",
        )
        return (None if answer is None else schema.model_validate(answer.model_dump())), call


async def test_indonesian_notice_is_verified_and_becomes_a_vona() -> None:
    llm = ScriptedLlm([indonesian()])
    source = text_of("synthetic_id_ash_seen.txt")
    reading = await read_notice(source, llm, CATALOGUE)
    assert (reading.status, reading.verified, reading.reason) == ("verified", True, None)
    assert reading.id == notice_id(source)
    assert reading.id.startswith("NOTICE-")
    assert reading.language == "id"
    assert reading.label is None
    assert llm.calls == 1

    vona = reading.vona
    assert vona is not None
    assert vona.provenance.source_id == reading.id
    assert vona.provenance.feed is FeedId.VONA
    assert vona.volcano_name == "Ibu"
    assert vona.issued_at == datetime(2026, 10, 11, 10, 59, tzinfo=UTC)
    assert vona.color_code is AviationColor.UNKNOWN
    assert vona.ash_observed is True
    assert vona.cloud_top_m == 1200 + 1357
    assert vona.cloud_top_ft == round((1200 + 1357) * 3.28084)
    assert vona.movement_text == "ke arah barat dan barat laut"
    assert vona.source_text == "Ground observer"
    assert vona.raw_text == source

    derived = {field.name: field.derived for field in reading.fields}
    assert derived["notice_time"] == "2026-10-11T10:59:00.000Z UTC"
    assert derived["plume_height"] == f"{vona.cloud_top_ft} ft above sea level (2557 m)"
    assert derived["volcano"] == "Ibu (268030)"
    assert all(field.evidence in source for field in reading.fields if " | " not in field.evidence)


async def test_the_sea_level_height_gives_the_same_top_and_thousands_dots_are_read() -> None:
    sea = HeightRead(
        value=2557,
        unit="m",
        datum="above_sea_level",
        evidence="± 1200 m di atas puncak (± 2557 m di atas permukaan laut)",
    )
    reading = await read_notice(
        text_of("synthetic_id_ash_seen.txt"), ScriptedLlm([indonesian(plume_height=sea)]), CATALOGUE
    )
    assert reading.vona is not None
    assert reading.vona.cloud_top_m == 2557

    dotted = "Tinggi kolom abu teramati 2.557 m di atas permukaan laut"
    source = text_of("synthetic_id_ash_seen.txt").replace(
        "± 1200 m di atas puncak (± 2557 m di atas permukaan laut)",
        "2.557 m di atas permukaan laut",
    )
    dotted_read = HeightRead(value=2557, unit="m", datum="above_sea_level", evidence=dotted)
    llm = ScriptedLlm(
        [indonesian(plume_height=dotted_read, ash_observed=FlagRead(value=True, evidence=dotted))]
    )
    assert (await read_notice(source, llm, CATALOGUE)).status == "verified"


async def test_not_observed_is_recorded_as_not_observed_and_sets_no_height() -> None:
    quiet = "Visual letusan tidak teramati karena tertutup kabut"
    answer = blank(
        volcano=say("Ibu", "G. Ibu"),
        date_text=say("11 Oktober 2026"),
        time_text=say("03:15 WIT"),
        ash_observed=FlagRead(value=False, evidence=quiet),
    )
    reading = await read_notice(
        text_of("synthetic_id_not_observed.txt"), ScriptedLlm([answer]), CATALOGUE
    )
    assert reading.verified
    vona = reading.vona
    assert vona is not None
    assert (vona.ash_observed, vona.cloud_top_ft, vona.cloud_top_m) == (False, None, None)
    assert vona.issued_at == datetime(2026, 10, 10, 18, 15, tzinfo=UTC)


async def test_filipino_card_with_pm_time_and_a_height_with_no_datum() -> None:
    source = text_of("synthetic_fil_kanlaon_card.txt")
    answer = blank(
        language="fil",
        volcano=say("Kanlaon", "Bulkang Kanlaon"),
        date_text=say("11 Oktubre 2026"),
        time_text=say("8:00 AM PHT"),
        alert_level=say("ANTAS NG ALERTO 2"),
        ash_observed=FlagRead(value=True, evidence="1 pagsingaw ng abo (45 minuto ang haba)"),
        plume_height=HeightRead(
            value=2500, unit="m", datum="unclear", evidence="Plume: 2500 metrong taas"
        ),
        direction=say("napadpad sa timog-kanluran"),
    )
    reading = await read_notice(source, ScriptedLlm([answer]), CATALOGUE)
    assert reading.verified
    assert reading.language == "fil"
    vona = reading.vona
    assert vona is not None
    assert vona.issued_at == datetime(2026, 10, 11, 0, 0, tzinfo=UTC)
    assert vona.ash_observed is True
    assert vona.cloud_top_ft is None
    height = next(field for field in reading.fields if field.name == "plume_height")
    assert height.derived is not None
    assert height.derived.startswith("not used")


async def test_japanese_notice_with_full_width_digits_and_height_above_the_crater() -> None:
    raw = (NOTICES / "synthetic_ja_sakurajima.txt").read_text(encoding="utf-8")
    source = normalise_notice(raw)
    assert "2026年10月11日19時59分頃(日本時間)" in source
    assert "1200m" in source
    column = "噴煙は火口上1200mまで上がり"
    answer = blank(
        language="ja",
        volcano=say("桜島"),
        date_text=say("2026年10月11日"),
        time_text=say("19時59分頃(日本時間)"),
        alert_level=say("噴火警戒レベル3"),
        ash_observed=FlagRead(value=True, evidence=column),
        plume_height=HeightRead(value=1200, unit="m", datum="above_summit", evidence=column),
        direction=say("南東へ流れています"),
    )
    reading = await read_notice(raw, ScriptedLlm([answer]), CATALOGUE)
    assert reading.verified, reading.reason
    vona = reading.vona
    assert vona is not None
    assert vona.volcano_name == "Sakurajima"
    assert vona.issued_at == datetime(2026, 10, 11, 10, 59, tzinfo=UTC)
    assert vona.cloud_top_m == 1200 + 1117


def rejected(reading: NoticeReading, fragment: str) -> None:
    assert reading.status == "unverified"
    assert not reading.verified
    assert reading.vona is None
    assert any(fragment in problem for problem in [*reading.problems, reading.reason or ""])


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        (
            {"ash_observed": FlagRead(value=True, evidence="Kolom abu setinggi gunung terlihat")},
            "ash_observed: evidence",
        ),
        (
            {
                "plume_height": HeightRead(
                    value=1300,
                    unit="m",
                    datum="above_summit",
                    evidence="± 1200 m di atas puncak (± 2557 m di atas permukaan laut)",
                )
            },
            "plume_height",
        ),
        (
            {
                "plume_height": HeightRead(
                    value=1200,
                    unit="m",
                    datum="above_sea_level",
                    evidence="± 1200 m di atas puncak (± 2557 m di atas permukaan laut)",
                )
            },
            "plume_height",
        ),
        (
            {
                "plume_height": HeightRead(
                    value=1200,
                    unit="ft",
                    datum="above_summit",
                    evidence="± 1200 m di atas puncak (± 2557 m di atas permukaan laut)",
                )
            },
            "plume_height",
        ),
        ({"colour_code": ColourRead(value="RED", evidence="Level II (Waspada)")}, "colour_code"),
        ({"alert_level": say("Alert Level 3", "Level II (Waspada)")}, "alert_level"),
        ({"date_text": say("2026-10-11", "11 Oktober 2026")}, "date_text: value"),
        ({"time_text": say("20:59 WIT", "19:59 WIT")}, "time_text: value"),
        ({"volcano": say("Minggu")}, "volcano"),
        ({"volcano": say("Dukono", "G. Ibu")}, "volcano"),
        ({"direction": say("ke arah timur", "ke arah barat")}, "direction"),
    ],
)
async def test_claims_the_notice_does_not_support_make_it_unverified(
    changes: dict[str, Any], fragment: str
) -> None:
    llm = ScriptedLlm([indonesian(**changes), indonesian(**changes)])
    reading = await read_notice(text_of("synthetic_id_ash_seen.txt"), llm, CATALOGUE)
    rejected(reading, fragment)
    assert llm.calls == 2  # one repair, then it stands as not verified
    assert reading.reason is not None
    assert reading.reason.startswith("NOT VERIFIED")


async def test_one_repair_can_save_a_notice() -> None:
    bad = indonesian(ash_observed=FlagRead(value=True, evidence="Kolom abu raksasa"))
    llm = ScriptedLlm([bad, indonesian()])
    reading = await read_notice(text_of("synthetic_id_ash_seen.txt"), llm, CATALOGUE)
    assert reading.verified
    assert llm.calls == 2
    repair = llm.parts[1][-1].text or ""
    assert repair.startswith("REPAIR")
    assert "ash_observed" in repair


async def test_a_time_with_no_zone_word_is_missing_not_assumed() -> None:
    answer = indonesian(time_text=say("19:59", "pukul 19:59"))
    llm = ScriptedLlm([answer])
    reading = await read_notice(text_of("synthetic_id_ash_seen.txt"), llm, CATALOGUE)
    assert reading.status == "unverified"
    assert reading.vona is None
    assert "could not be read" in (reading.reason or "")
    assert llm.calls == 1  # nothing was claimed wrongly, so nothing to repair


async def test_silence_on_volcano_and_time_is_not_verified() -> None:
    reading = await read_notice(
        text_of("synthetic_id_ash_seen.txt"), ScriptedLlm([blank()]), CATALOGUE
    )
    assert reading.status == "unverified"
    assert "the notice names no catalogue volcano" in (reading.reason or "")
    assert "no date and clock time" in (reading.reason or "")


async def test_a_notice_time_in_the_future_is_rejected() -> None:
    with use_clock(FixedClock(datetime(2026, 10, 11, 10, 0, tzinfo=UTC))):
        reading = await read_notice(
            text_of("synthetic_id_ash_seen.txt"),
            ScriptedLlm([indonesian(), indonesian()]),
            CATALOGUE,
        )
    rejected(reading, "in the future")


async def test_a_verified_notice_that_is_silent_on_ash_stays_out_of_the_live_picture() -> None:
    answer = indonesian(ash_observed=FlagRead(), plume_height=HeightRead())
    reading = await read_notice(
        text_of("synthetic_id_ash_seen.txt"), ScriptedLlm([answer]), CATALOGUE
    )
    assert reading.verified
    assert reading.vona is None
    assert "nothing was added" in (reading.reason or "")


async def test_a_model_failure_is_ai_unavailable_and_nothing_is_substituted() -> None:
    llm = ScriptedLlm([None])
    reading = await read_notice(text_of("synthetic_id_ash_seen.txt"), llm, CATALOGUE)
    assert reading.status == "ai_unavailable"
    assert not reading.verified
    assert reading.reason == "AI UNAVAILABLE: api_error 503 UNAVAILABLE"
    assert reading.vona is None
    assert reading.fields == []
    assert reading.text == text_of("synthetic_id_ash_seen.txt")


async def test_the_stub_backend_reads_only_the_volcano_and_is_labelled() -> None:
    reading = await read_notice(text_of("synthetic_id_ash_seen.txt"), StubBackend(), CATALOGUE)
    assert reading.status == "unverified"
    assert reading.vona is None
    assert (reading.llm_backend, reading.model_id, reading.label) == ("stub", "stub", "NO MODEL")
    assert [field.name for field in reading.fields] == ["volcano"]
    assert reading.fields[0].evidence == "Ibu"


def test_notice_ids_ignore_spacing_and_full_width_forms() -> None:
    text = text_of("synthetic_id_ash_seen.txt")
    spaced = "  " + text.replace(" pukul ", "\n  pukul  ") + "\r\n"
    assert notice_id(spaced) == notice_id(text)
    assert notice_id("１２００ m") == notice_id("1200 m")  # noqa: RUF001
    assert notice_id(text) != notice_id(text + " Level III")


def test_the_prompt_tells_the_model_what_code_does_for_it() -> None:
    prompt = " ".join(PROMPT_PATH.read_text(encoding="utf-8").lower().split())
    for phrase in ("verbatim", "do not convert times to utc", "never a person's name"):
        assert phrase in prompt


# --- routes -----------------------------------------------------------------------------


@pytest.fixture
async def desk(tmp_path: Path) -> AsyncIterator[SimpleNamespace]:
    store = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    bus = EventBus()
    joined: list[Vona] = []

    async def add_verified_notice(vona: Vona) -> None:
        joined.append(vona)

    runtime = SimpleNamespace(
        store=store,
        bus=bus,
        catalogue=CATALOGUE,
        mode=RunMode.LIVE,
        llm=ScriptedLlm([]),
        add_verified_notice=add_verified_notice,
        joined=joined,
        live=SimpleNamespace(vonas={}),
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.dependency_overrides[require_desk] = lambda: SessionInfo(
        name="Ana K", expires_at=AT + timedelta(hours=1)
    )

    @app.exception_handler(ApiError)
    async def api_error(_: Any, exc: ApiError) -> Any:
        return _json(exc.body(), exc.status_code)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield SimpleNamespace(client=client, runtime=runtime, store=store, bus=bus)
    await store.aclose()


async def test_post_reads_stores_audits_and_publishes_the_notice(desk: SimpleNamespace) -> None:
    desk.runtime.llm = ScriptedLlm([indonesian()])
    text = text_of("synthetic_id_ash_seen.txt")
    response = await desk.client.post("/api/desk/notices", json={"text": text})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "verified"
    assert body["verified"] is True
    assert body["vona"]["volcano_name"] == "Ibu"

    stored = await desk.store.get(Collection.NOTICES, body["id"])
    assert stored is not None
    assert stored["status"] == "verified"
    entries = await audit.list_entries(desk.store)
    assert [e.action for e in entries] == [AuditAction.NOTICE_READ]
    assert entries[0].actor == "desk:Ana K"
    assert entries[0].input_hashes == [body["sha256"]]
    event = desk.bus.last(SseEvent.NOTICE)
    assert event is not None
    assert event.data["id"] == body["id"]
    assert [v.provenance.source_id for v in desk.runtime.joined] == [body["id"]]

    again = await desk.client.post("/api/desk/notices", json={"text": "  " + text + "\n"})
    assert again.status_code == 200
    assert again.json()["id"] == body["id"]
    assert desk.runtime.llm.calls == 1  # the same notice is not read twice
    assert len(desk.runtime.joined) == 2  # joining the picture is idempotent (a dict write)


async def test_post_answers_503_ai_unavailable_and_retries_later(desk: SimpleNamespace) -> None:
    desk.runtime.llm = ScriptedLlm([None, indonesian()])
    text = text_of("synthetic_id_ash_seen.txt")
    response = await desk.client.post("/api/desk/notices", json={"text": text})
    assert response.status_code == 503
    assert response.json()["error"] == "ai_unavailable"
    assert response.json()["detail"].startswith("AI UNAVAILABLE")
    stored = await desk.store.get(Collection.NOTICES, notice_id(text))
    assert stored is not None
    assert stored["status"] == "ai_unavailable"

    retry = await desk.client.post("/api/desk/notices", json={"text": text})
    assert retry.status_code == 200
    assert retry.json()["status"] == "verified"
    assert desk.runtime.llm.calls == 2


async def test_post_refuses_text_that_is_too_short_or_too_long(desk: SimpleNamespace) -> None:
    short = await desk.client.post("/api/desk/notices", json={"text": "Ibu erupsi"})
    assert short.status_code == 422
    assert short.json()["error"] == "validation_failed"
    long = await desk.client.post("/api/desk/notices", json={"text": "x" * 6001})
    assert long.status_code == 422
    assert desk.runtime.llm.calls == 0


async def test_post_needs_the_csrf_header_or_a_json_body(desk: SimpleNamespace) -> None:
    response = await desk.client.post(
        "/api/desk/notices", content="text=whatever", headers={"content-type": "text/plain"}
    )
    assert response.status_code == 403


async def test_get_lists_notices_newest_first_for_the_current_mode(desk: SimpleNamespace) -> None:
    desk.runtime.llm = ScriptedLlm([indonesian()])
    await desk.client.post("/api/desk/notices", json={"text": text_of("synthetic_id_ash_seen.txt")})
    listed = await desk.client.get("/api/notices")
    assert listed.status_code == 200
    notices = listed.json()["notices"]
    assert [n["status"] for n in notices] == ["verified"]
    assert re.fullmatch(r"NOTICE-[0-9a-f]{12}", notices[0]["id"])

    desk.runtime.mode = RunMode.REPLAY
    assert (await desk.client.get("/api/notices")).json()["notices"] == []
    assert (await desk.client.get("/api/notices", params={"limit": 0})).status_code == 422


async def test_get_lists_jma_reports_from_the_live_picture_as_verified_japanese(
    desk: SimpleNamespace,
) -> None:
    source = text_of("synthetic_id_ash_seen.txt")
    desk.runtime.llm = ScriptedLlm([indonesian()])
    await desk.client.post("/api/desk/notices", json={"text": source})
    pasted = desk.runtime.joined[0]
    jma = pasted.model_copy(
        update={
            "provenance": pasted.provenance.model_copy(update={"source_id": "JMA-VFVO52-20261009"}),
            "issued_at": pasted.issued_at + timedelta(hours=1),
        }
    )
    other = pasted.model_copy(
        update={"provenance": pasted.provenance.model_copy(update={"source_id": "MAGMA-1"})}
    )
    desk.runtime.live.vonas = {"JMA-VFVO52-20261009": jma, "MAGMA-1": other}
    notices = (await desk.client.get("/api/notices")).json()["notices"]
    assert len(notices) == 2  # the MAGMA record is not a JMA report
    assert [n["created_at"] for n in notices] == sorted(
        (n["created_at"] for n in notices), reverse=True
    )
    report = next(n for n in notices if n["id"] == "JMA-VFVO52-20261009")
    assert (report["language"], report["verified"], report["source_kind"]) == (
        "ja",
        True,
        "jma_xml",
    )
    assert report["model_id"] is None
    assert [n["source_kind"] for n in notices if n is not report] == ["pasted"]
