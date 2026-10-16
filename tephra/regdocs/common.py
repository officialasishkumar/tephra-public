"""Small pieces both drafts share: the labels every document carries and the band text."""

from tephra.config import NO_MODEL_LABEL
from tephra.geo.units import ft_to_fl
from tephra.models import LlmBackendName, SystemState

__all__ = ["band_text", "document_labels"]


def document_labels(state: SystemState, *, backend: LlmBackendName | None) -> list[str]:
    """Fictional airline (the demo's), decision support, REPLAY and NO MODEL: never left off a
    document. An airline's own TEPHRA says decision support only."""
    airline = state.airline
    labels = [state.disclaimer]
    if airline.fictional:
        labels.insert(0, f"ILLUSTRATIVE AIRLINE ({airline.name.upper()}, FICTIONAL)")
    if state.replay is not None:
        labels.append(state.replay.banner)
    if backend == "stub":
        labels.append(NO_MODEL_LABEL)
    return labels


def band_text(base_ft: int, top_ft: int) -> str:
    base = "SFC" if base_ft <= 0 else f"FL{ft_to_fl(base_ft):03d}"
    return f"{base}/FL{ft_to_fl(top_ft):03d}"
