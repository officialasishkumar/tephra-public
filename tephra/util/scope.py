"""Which hosted airline the current context works for.

Requests under ``/a/<ICAO>/``, a hosted runtime's ticks and tasks, and the registry's work
for one airline bind its ICAO here; the demo and every root route bind nothing. Logs, the
runtime's binding and the airline store's fail-closed check read it.

A request under ``/a/<ICAO>/api`` also holds a :class:`Charge`: once the caller is known to be
a member of that airline, what the request reads from the site's root store (members, logins,
the tenant record) is counted against that airline's own allowance instead of the demo's, so
an airline's people spend their own airline's share and never the site's.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

__all__ = ["Charge", "bind_charge", "bind_tenant", "charged_to", "current_tenant"]

_tenant: ContextVar[str | None] = ContextVar("tephra_tenant", default=None)


class Charge:
    """One request's meter attribution: None until the caller is known to be a member."""

    __slots__ = ("icao",)

    def __init__(self) -> None:
        self.icao: str | None = None


_charge: ContextVar[Charge | None] = ContextVar("tephra_charge", default=None)


def charged_to() -> str | None:
    """The airline this request's root-store operations are counted against, or None."""
    charge = _charge.get()
    return None if charge is None else charge.icao


@contextmanager
def bind_charge() -> Iterator[Charge]:
    """A fresh :class:`Charge` for one request; its holder sets ``icao`` once it may."""
    charge = Charge()
    token = _charge.set(charge)
    try:
        yield charge
    finally:
        _charge.reset(token)


def current_tenant() -> str | None:
    """The airline's ICAO bound in this context, or None (the demo, root routes)."""
    return _tenant.get()


@contextmanager
def bind_tenant(icao: str) -> Iterator[None]:
    """Work for ``icao`` in this context and the tasks and threads it starts, until exit."""
    if len(icao) != 3 or not icao.isascii() or not icao.isupper() or not icao.isalpha():
        raise ValueError(f"not an ICAO airline designator: {icao!r}")
    token = _tenant.set(icao)
    try:
        yield
    finally:
        _tenant.reset(token)
