"""The ash-policy page's check: which values an airline may change, and that the policy with its
changes still passes the policy file's own rules (``OperatorPolicy``).

Recovery values are read-only (recovery re-planning is not built for an airline's network),
except the airport closure radius, which the airline's own closure check reads.
"""

from collections.abc import Sequence
from typing import Final

from pydantic import ValidationError

from tephra.airline.models import PolicyChange
from tephra.models import OperatorPolicy, PolicyModel, PolicyValue

__all__ = ["EDITABLE", "PolicyRefused", "apply_changes", "named_value_keys"]

EDITABLE_RECOVERY: Final = frozenset({"recovery.airport_closure_radius_nm"})


class PolicyRefused(ValueError):
    """The changed policy fails ``OperatorPolicy``; the message names values, never input."""


def named_value_keys() -> frozenset[str]:
    """Every key of ``OperatorPolicy.named_values()``, read from the model's blocks."""
    keys: set[str] = set()
    for block, info in OperatorPolicy.model_fields.items():
        model = info.annotation
        if not (isinstance(model, type) and issubclass(model, PolicyModel)):
            continue
        fields = model.model_fields
        if fields and all(item.annotation is PolicyValue for item in fields.values()):
            keys.update(f"{block}.{name}" for name in fields)
    return frozenset(keys)


EDITABLE: Final = (
    frozenset(key for key in named_value_keys() if not key.startswith("recovery."))
    | EDITABLE_RECOVERY
)


def apply_changes(policy: OperatorPolicy, changes: Sequence[PolicyChange]) -> OperatorPolicy:
    """``policy`` with each changed value set; raises :class:`PolicyRefused` when the result
    breaks a rule of the policy file (a zero that switches a check off, an inverted pair)."""
    data = policy.model_dump(mode="json")
    for change in changes:
        block, name = change.name.split(".", 1)
        data[block][name]["value"] = change.value
    try:
        return OperatorPolicy.model_validate(data)
    except ValidationError as exc:
        message = str(exc.errors()[0].get("msg", "invalid"))
        raise PolicyRefused(message.removeprefix("Value error, ")) from None
