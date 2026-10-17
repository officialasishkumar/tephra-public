"""The map's colour rules (docs/UI-DESIGN.md 3.1, 5; theme "Basalt & Paper", 17 Oct 2026).

Red is for real alarms only (feeds, database, connection): a closed airport is the plan a
dispatcher decides on, drawn in --c-closed as a white bar on a dark disc, never in --c-serious.
The picked flight's ring is the plan's white too (C.reroute).
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "tephra" / "web"
MAP_JS = ("wall/map.js", "wall/images.js", "wall/basemap.js", "wall/ext-map.js", "desk/map.js")


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _layer(source: str, layer_id: str) -> str:
    """One addLayer call, from its id to the next addLayer (some span two lines)."""
    start = re.search(r"""map\.addLayer\(\{ id: ['"]""" + re.escape(layer_id) + "['\"]", source)
    assert start, layer_id
    end = source.find("map.addLayer(", start.end())
    return source[start.start() : end if end > 0 else len(source)]


def test_no_map_layer_or_image_reads_the_alarm_red() -> None:
    for rel in MAP_JS:
        source = _read(rel)
        assert "C.serious" not in source, rel
        assert "--c-serious" not in source, rel


def test_closed_airports_are_drawn_in_the_closed_colour() -> None:
    wall = _read("wall/map.js")
    for layer_id in ("closure-area", "closure-ring", "airport-closed-code"):
        assert "C.closed" in _layer(wall, layer_id), layer_id
    assert '"icon-image": "closed-airport"' in _layer(wall, "airport-closed-bar")
    desk = _read("desk/map.js")
    assert "C.closed" in _layer(desk, "d-closure-ring")
    assert "'icon-image': 'closed-airport'" in _layer(desk, "d-airports")
    images = _read("wall/images.js")
    assert "closed: closedAirport(C.closed, C.halo)" in images
    assert "boxClosed: labelBox(C.closed, C.halo)" in images


def test_the_picked_ring_is_the_plans_white() -> None:
    assert '"circle-stroke-color": C.reroute' in _layer(_read("wall/map.js"), "aircraft-picked")
    assert "'circle-stroke-color': C.reroute" in _layer(_read("desk/map.js"), "d-sel-ring")


def test_map_code_holds_no_stale_palette_literals() -> None:
    """Map colours come from tokens.css; the old palette's hexes must not linger in map code."""
    old = ("#ff7a6e", "#2dd4bf", "#38bdf8", "#e8dcc6", "#aab4be", "#7a8796", "#a9b8c8")
    old += ("#6d7b8a", "#eaf1f7", "#0b1220", "#2a3442")
    for rel in (*MAP_JS, "wall/board-view.js"):
        source = _read(rel).lower()
        for hex_ in old:
            assert hex_ not in source, (rel, hex_)


def test_the_satellite_box_is_not_the_plans_white() -> None:
    """White is the plan (reroute, closed airport, picked ring); the satellite box is cobalt."""
    wall = _read("wall.css")
    assert "--c-sat: #4088c4;" in wall
    assert "--c-sat: var(--map-label)" not in wall
    ext = _read("wall/ext-map.js")
    assert '"sat-box-casing"' in ext


def test_the_desk_plane_is_amber_only_when_tephra_flags_it() -> None:
    desk = _read("desk/map.js")
    assert "'icon-color': ['case', ['get', 'flag'], C.tephra" in desk
    assert "(!sel.picked || sel.exposed)" in desk
