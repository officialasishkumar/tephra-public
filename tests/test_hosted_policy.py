"""A hosted airline's policy (SPEC §3.6): versions of changes from policy A, the refusals of
the policy file's rules, recovery values not editable, and the label switching between
ILLUSTRATIVE and the airline's recorded SRA acceptance."""

from datetime import date

import pytest

from tephra.airline.models import PolicyChange, Stamp
from tephra.hosted import policy
from tephra.hosted.models import HostedRefused, PolicyVersion, SraAcceptance, TenantRecord
from tephra.models import PolicySummary
from tests.test_hosted_tenants import base_policy, wall

BY = "Ana Ops#MB-1a2b3c4d5e"


def record(**update: object) -> TenantRecord:
    return TenantRecord(
        icao="RFB",
        airline_id="AL-0123456789ab",
        name="Ring of Fire Charter",
        version=1,
        state="setup",
        state_since=wall(),
        created=Stamp(by=BY, at=wall()),
        ops_managers=["MB-1a2b3c4d5e"],
    ).model_copy(update=update)


def version(n: int, *changes: tuple[str, int]) -> PolicyVersion:
    base = base_policy()
    return PolicyVersion(
        version=n,
        base_policy_id=base.policy_id,
        base_version=base.version,
        changes=[
            PolicyChange(name=name, value=value, reason="Company SOP 4.2 asks for it.")
            for name, value in changes
        ],
        created=Stamp(by=BY, at=wall()),
    )


def test_the_airlines_policy_has_its_own_identity_and_is_illustrative() -> None:
    applied = policy.tenant_policy(
        base_policy(), version(3, ("exposure.vertical_margin_ft", 3000)), record()
    )
    assert applied.policy_id == "RFB-POLICY-A"
    assert applied.version == "RFB-3"
    assert applied.title == "Ring of Fire Charter operator policy A"
    assert applied.label == policy.ILLUSTRATIVE
    assert applied.exposure.vertical_margin_ft.value == 3000
    summary = PolicySummary.of(applied)
    assert (summary.version, summary.label) == ("RFB-3", policy.ILLUSTRATIVE)


def test_an_acceptance_of_this_version_changes_the_label_and_a_new_version_does_not() -> None:
    accepted = SraAcceptance(
        version=3,
        accepted_by="Ana Ops, Head of Flight Ops",
        accepted_on=date(2026, 10, 17),
        sra_ref="SRA-VA-2026-03",
        recorded=Stamp(by=BY, at=wall()),
    )
    held = record(sra=accepted, policy_version=3)
    applied = policy.tenant_policy(base_policy(), version(3), held)
    assert applied.label == (
        "Accepted under Ring of Fire Charter's SRA by Ana Ops, Head of Flight Ops, on "
        "17 Oct 2026 (recorded by the airline; TEPHRA does not check it)"
    )
    assert applied.sra_ref == "SRA-VA-2026-03"
    newer = policy.tenant_policy(
        base_policy(), version(4), held.model_copy(update={"policy_version": 4})
    )
    assert newer.label == policy.ILLUSTRATIVE
    assert newer.sra_ref is None


def test_recovery_values_are_not_editable_here() -> None:
    with pytest.raises(HostedRefused) as refused:
        policy.check_changes(
            base_policy(),
            [PolicyChange(name="recovery.airport_closure_radius_nm", value=40, reason="Wider.")],
        )
    assert (refused.value.status, refused.value.code) == (422, "not_editable")
    assert "Not built for your network" in refused.value.detail
    with pytest.raises(HostedRefused, match="not_editable"):
        policy.check_changes(
            base_policy(), [PolicyChange(name="exposure.no_such_value", value=1, reason="Why.")]
        )


def test_a_change_that_breaks_the_policy_files_rules_is_refused() -> None:
    hold = base_policy().planner.hold_within_min.value
    with pytest.raises(HostedRefused) as refused:
        policy.check_changes(
            base_policy(),
            [PolicyChange(name="planner.divert_within_min", value=hold + 5, reason="Too far.")],
        )
    assert refused.value.code == "policy_refused"
    assert "divert_within_min" in refused.value.detail


def test_the_policy_tab_lists_values_versions_and_what_each_changed() -> None:
    versions = [
        version(3, ("exposure.vertical_margin_ft", 3000), ("reroute.buffer_nm", 25)),
        version(2, ("reroute.buffer_nm", 25)),
        version(1),
    ]
    tab = policy.policy_tab(base_policy(), versions, record(policy_version=3))
    assert tab.current.version == 3
    assert [(row.version, row.changed) for row in tab.versions] == [
        (3, ["exposure.vertical_margin_ft"]),
        (2, ["reroute.buffer_nm"]),
        (1, []),
    ]
    values = {row.name: row for row in tab.values}
    margin = values["exposure.vertical_margin_ft"]
    assert (margin.value, margin.base, margin.unit, margin.editable) == (3000, 2000, "ft", True)
    closure = values["recovery.airport_closure_radius_nm"]
    assert closure.editable is False
    assert closure.not_built == "Not built for your network"
    assert tab.label == policy.ILLUSTRATIVE
    assert tab.confirmed is None
