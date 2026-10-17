"""Hosted airlines: each verified airline's own space on the shared site (feature ``hosted``).

The domain lives here (records, members, keys, policy, the checklist, the per-airline runtimes);
the HTTP routes are in ``tephra.api.routes_{tenant,hosted,admin}``. Import-light on purpose:
importing a submodule never starts anything.
"""
