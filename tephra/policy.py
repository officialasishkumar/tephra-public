"""The operator policy file (``data/policy/policy_a.json``).

The composition root loads it once and passes values down; library code never reads the
file. JSON rather than YAML: the project has no YAML parser, and the airport and volcano
catalogues already load the same way.
"""

from pathlib import Path
from typing import Final

from tephra.models import OperatorPolicy

__all__ = ["POLICY_FILE", "load_policy"]

POLICY_FILE: Final = Path("policy") / "policy_a.json"
"""Relative to ``Settings.data_dir``. The planner already proposes level bands above or below
an affected area, but no code reads a preset, so a B file would change labels, not
behaviour; Policy B waits for code that gates over, under and through by preset."""


def load_policy(data_dir: Path) -> OperatorPolicy:
    return OperatorPolicy.model_validate_json((data_dir / POLICY_FILE).read_bytes())
