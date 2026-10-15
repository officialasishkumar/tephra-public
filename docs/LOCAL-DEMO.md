# Local demo: TEPHRA on Gemma, on this laptop

No API key, no quota: every model step runs on `gemma4:e4b` served by Ollama.

## Start

```bash
ollama serve                                   # if it is not already running
ollama pull gemma4:e4b                         # once, 6.6 GB
uv run python scripts/demo_local.py --fresh    # checks Ollama, prints the run sheet, starts
```

Wall http://localhost:8080 · Desk http://localhost:8080/desk (Dispatcher, PIN `2468`).
Let it run about 15 minutes before you present: the first loop of the replay asks Gemma
everything; later loops reuse its kept answers, so the board moves at full speed.

The case is `demo-agung-20261014`: **synthetic demo data** on real places (Agung erupts and Bali
closes; Sakurajima erupts while Tokyo's advisory still says the ash dissipated), with every
source TEPHRA reads except satellite pictures. Every page says it is synthetic. Regenerate it
with `uv run python scripts/make_demo_case.py`.

`--sheet` only prints the run sheet. The plan is `data/demo/local-demo.json`.

## On a bigger machine (DGX Spark)

A 16 GB Mac tops out near 30 tokens/s whatever runs in parallel (measured), so the assistant's
queue grows and the Mac slows down. Serve the model from the Spark and run TEPHRA anywhere:

```bash
# on the Spark
OLLAMA_HOST=0.0.0.0:11434 OLLAMA_NUM_PARALLEL=4 ollama serve
ollama pull gemma4:31b                         # or gemma4:e4b; a bigger Gemma plans better
# on the Mac (or ssh -L 11434:localhost:11434 spark and use http://127.0.0.1:11434)
uv run python scripts/demo_local.py --fresh --url http://<spark>:11434 --model gemma4:31b --parallel 4
```

`--parallel 4` plans four flights at once and sends four requests at once
(`TEPHRA_PLAN_PARALLEL`, `TEPHRA_OLLAMA_PARALLEL`).

## How it fits together

```
demo feeds: SIGMET, Darwin + Tokyo VAA, VONA, JMA,            data/replay/demo-agung-20261014
            TAF/METAR, winds, aircraft
        │  every replay minute (real time, 07:05-07:30Z, looping)
        ▼
code: disagreements, official area, exposed flights           tephra/reconcile, tephra/geo
        │
        ▼
Coordinator (ADK agent) ── hands out the work ──┐               tephra/agents/duty_officer.py
        │                                       │
        ├─ Plume reader  → TEPHRA's estimate (may only widen)   plume_reader.py
        ├─ Flight planner (ADK agent, tools) → action per flight exposure_planner.py
        └─ Drafter → advisory DRAFT                              dispatch_drafter.py
        │
        ▼
Desk: a person approves → hash-chained record                  tephra/desk
```

Every box marked agent or reader calls Gemma through `tephra/agents/ollama.py`
(`TEPHRA_LLM=ollama`). One request at a time; a person's question on the Desk goes first.

## Where to see TEPHRA Assistant working

| Where | What |
|---|---|
| Wall › top chip "TEPHRA Assistant" | on / paused; its tooltip says "Gemma, on this computer" |
| `/assistant` (press A) | the board: each step the Coordinator handed out, timed; Play to replay it |
| Wall › click an amber plane | the plan and draft, marked "Drafted by TEPHRA Assistant" |
| Wall › Details › TEPHRA's estimate | the Plume reader's reading |
| Wall › Details › Runs on | Model access: Gemma on this computer (Ollama) |
| Desk › Ask | the Ask agent, answering from TEPHRA's own data |
| Terminal | one `llm backend=ollama` line per model call, with its time |

## Good to know

- Gemma is a small model: some answers fail TEPHRA's checks. Those show as "gave no result"
  with the reason; nothing is invented in their place.
- The Plume reader thinks before it answers (about a minute); agent turns take 1-15 s.
- Voice is off: Gemma here takes no audio and has no speech.
