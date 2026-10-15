"""CSP ``style-src``: the two pinned MapLibre stylesheet paths on unpkg and nothing wider."""

from tephra.api.server import CONTENT_SECURITY_POLICY


def test_csp_style_src_names_only_the_two_pinned_hosts() -> None:
    directives = {part.split()[0]: part.split()[1:] for part in CONTENT_SECURITY_POLICY.split("; ")}
    assert directives["style-src"] == [
        "'self'",
        "https://unpkg.com/maplibre-gl@4.7.1/",
        "https://unpkg.com/@maplibre/maplibre-gl-compare@0.5.0/",
    ]
