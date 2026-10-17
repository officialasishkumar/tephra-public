"""A hosted airline's operator policy: the site's policy A with the airline's changes, its own
id and version, and the label its SRA acceptance allows (SPEC §3.6).

Each version holds every change from the base policy. The label is ILLUSTRATIVE until the
airline records acceptance of that very version under its SRA; TEPHRA does not check the
acceptance and says so. Recovery values are not editable: recovery re-planning is not built
for an airline's own network.
"""

from collections.abc import Sequence
from typing import Final

from tephra.airline import policy_check
from tephra.airline.models import PolicyChange
from tephra.hosted.models import (
    HostedRefused,
    PolicyCurrent,
    PolicyTab,
    PolicyValueRow,
    PolicyVersion,
    PolicyVersionRow,
    TenantRecord,
)
from tephra.models import OperatorPolicy
from tephra.store.base import Collection, Store

__all__ = [
    "EDITABLE",
    "ILLUSTRATIVE",
    "NOT_BUILT",
    "VERSIONS_SHOWN",
    "check_changes",
    "get_version",
    "label_for",
    "list_versions",
    "policy_tab",
    "put_version",
    "tenant_policy",
    "version_id",
]

ILLUSTRATIVE: Final = "ILLUSTRATIVE, not an airline SRA"
NOT_BUILT: Final = "Not built for your network"
EDITABLE: Final = policy_check.EDITABLE - policy_check.EDITABLE_RECOVERY
VERSIONS_SHOWN: Final = 20


def version_id(version: int) -> str:
    return f"{version:06d}"


def label_for(record: TenantRecord, version: int) -> str:
    sra = record.sra
    if sra is None or sra.version != version:
        return ILLUSTRATIVE
    return (
        f"Accepted under {record.name}'s SRA by {sra.accepted_by}, on "
        f"{sra.accepted_on:%d %b %Y} (recorded by the airline; TEPHRA does not check it)"
    )


def check_changes(base: OperatorPolicy, changes: Sequence[PolicyChange]) -> OperatorPolicy:
    """The base with ``changes``; a value that is not editable here or a result that breaks
    the policy file's rules is refused (422)."""
    for change in changes:
        if change.name not in EDITABLE:
            words = NOT_BUILT if change.name.startswith("recovery.") else "not editable"
            raise HostedRefused(422, "not_editable", f"{change.name}: {words}")
    try:
        return policy_check.apply_changes(base, changes)
    except policy_check.PolicyRefused as exc:
        raise HostedRefused(422, "policy_refused", str(exc)) from None


def tenant_policy(
    base: OperatorPolicy, version: PolicyVersion, record: TenantRecord
) -> OperatorPolicy:
    """The policy a hosted airline's runtime applies. The identity fields are set after the
    values are checked (``model_copy``): ``OperatorPolicy`` pins policy A's own version format
    and label, which an airline's policy does not share."""
    changed = check_changes(base, version.changes)
    sra = record.sra if record.sra is not None and record.sra.version == version.version else None
    return changed.model_copy(
        update={
            "policy_id": f"{record.icao}-POLICY-A",
            "version": f"{record.icao}-{version.version}",
            "title": f"{record.name} operator policy A",
            "label": label_for(record, version.version),
            "sra_ref": None if sra is None else sra.sra_ref,
        }
    )


async def put_version(store: Store, version: PolicyVersion) -> None:
    """``store`` is the airline's own."""
    await store.put(
        Collection.POLICY_VERSIONS, version_id(version.version), version.model_dump(mode="json")
    )


async def get_version(store: Store, version: int) -> PolicyVersion | None:
    doc = await store.get(Collection.POLICY_VERSIONS, version_id(version))
    return None if doc is None else PolicyVersion.model_validate(doc)


async def list_versions(store: Store, *, limit: int = VERSIONS_SHOWN) -> list[PolicyVersion]:
    """Newest first."""
    docs = await store.list_docs(
        Collection.POLICY_VERSIONS, limit=limit, order_by="version", descending=True
    )
    return [PolicyVersion.model_validate(doc) for doc in docs]


def policy_tab(
    base: OperatorPolicy, versions: Sequence[PolicyVersion], record: TenantRecord
) -> PolicyTab:
    """The Policy tab from the newest versions (the record's current one among them)."""
    current = next((v for v in versions if v.version == record.policy_version), None)
    if current is None:
        raise LookupError(f"policy version {record.policy_version} of {record.icao} is missing")
    applied = tenant_policy(base, current, record).named_values()
    base_values = base.named_values()
    values = [
        PolicyValueRow(
            name=name,
            value=value.value,
            base=base_values[name].value,
            unit=value.unit,
            editable=name in EDITABLE,
            not_built=NOT_BUILT if name.startswith("recovery.") else None,
        )
        for name, value in applied.items()
    ]
    return PolicyTab(
        current=PolicyCurrent(
            version=current.version,
            created=current.created,
            note=current.note,
            changes=current.changes,
        ),
        versions=[
            PolicyVersionRow(version=v.version, created=v.created, changed=_changed(v, versions))
            for v in versions
        ],
        values=values,
        label=label_for(record, current.version),
        confirmed=record.policy_confirmed
        if record.policy_confirmed is not None
        and record.policy_confirmed.version == current.version
        else None,
        sra=record.sra,
    )


def _changed(version: PolicyVersion, versions: Sequence[PolicyVersion]) -> list[str]:
    """The values this version set differently from the version before it."""
    before = next((v for v in versions if v.version == version.version - 1), None)
    then = {} if before is None else {c.name: c.value for c in before.changes}
    now = {c.name: c.value for c in version.changes}
    if before is None and version.version > 1:
        return sorted(now)
    return sorted(name for name in now.keys() | then.keys() if now.get(name) != then.get(name))
