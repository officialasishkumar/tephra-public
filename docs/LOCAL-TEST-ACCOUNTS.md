# Local test accounts

Local test values only: they work on the server below and never on the live site.

```bash
uv run python scripts/local_test_server.py --fresh &    # hosting on: http://127.0.0.1:8080
uv run python scripts/local_test_seed.py --wait         # makes every login below
```

Hosting off (staff and the airline only; the dispatcher and viewer need hosting on):

```bash
uv run python scripts/local_test_server.py --hosting off --fresh &    # http://127.0.0.1:8081
uv run python scripts/local_test_seed.py --wait --url http://127.0.0.1:8081
```

`--port N` (server) and `--url http://127.0.0.1:N` (seed) pick another port. Re-running the seed
is safe. Recovery codes, the push key and invite links are printed and kept in
`.local-test/seeded-<port>.txt`.

| Role | Sign in at | Email or name | Password or PIN |
|---|---|---|---|
| TEPHRA staff | `/admin` | `m.tan@tephra.example` | `local test password 2026` |
| Ring of Fire Charter (RFB) ops manager, Ana Ops | `/signin` | `ops@rfb.example` | `local test password 2026` |
| RFB dispatcher, Dee Disp | `/signin` | `dee@rfb.example` | `local test password 2026` |
| RFB viewer, Vic View | `/signin` | `vic@rfb.example` | `local test password 2026` |
| Demo Desk (RFA dispatcher) | `/desk` | any name | PIN `4242` |

The RFB model key is a fake (`local-test-fake-model-key-0000000000000000`); the server runs the
stub model. The Desk PIN, session secret and task token are `ENV` in
`scripts/local_test_server.py`.
