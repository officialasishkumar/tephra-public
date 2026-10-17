"""The hosted feature's throttles (SPEC §6.2) and the TEPHRA staff console's, registered in
``create_app`` beside the airline accounts' (``tephra.airline.sessions.THROTTLES``): the staff
ones whenever ``onboard`` is on (staff verify airlines with hosting off too), the hosted ones only
with ``hosted`` on. In process memory: every count starts again after a deploy or a restart. The
push gap per key is ``Settings.hosted_push_gap_s``."""

from typing import Final

__all__ = ["HOSTED_THROTTLES", "STAFF_THROTTLES"]

_MINUTE: Final = 60.0
_HOUR: Final = 3600.0
_DAY: Final = 86400.0

HOSTED_THROTTLES: Final[dict[str, tuple[int, float]]] = {
    "hosted_member_requests": (600, 5 * _MINUTE),  # per login key per airline
    "hosted_writes": (200, _DAY),  # per airline
    "hosted_key_sets": (10, _DAY),  # per airline
    "hosted_invites": (20, _DAY),  # per airline
    "hosted_exports": (1, _DAY),  # per airline
    "hosted_chain_checks": (1, _DAY),  # per airline
    "hosted_invite_reads": (30, _HOUR),  # per client
    "hosted_push": (30, _MINUTE),  # per airline
    "hosted_pilot_reports": (60, _HOUR),  # per airline
    "push_bad_key": (10, _MINUTE),  # per client
}
"""``app.state`` name -> (tries, window in seconds)."""

STAFF_THROTTLES: Final[dict[str, tuple[int, float]]] = {
    "operator_login": (5, 15 * _MINUTE),  # per client
    "operator_login_email": (10, 15 * _MINUTE),  # per email
    "operator_invites": (5, _DAY),  # site
    "operator_invite_reads": (30, _HOUR),  # per client
}
"""``app.state`` name -> (tries, window in seconds)."""
