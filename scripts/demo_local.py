"""Run the local demo: TEPHRA in REPLAY with every model step on Gemma via Ollama.

    uv run python scripts/demo_local.py            # check Ollama, print the run sheet, start
    uv run python scripts/demo_local.py --sheet    # only print the run sheet
    uv run python scripts/demo_local.py --fresh    # start from an empty local store
    uv run python scripts/demo_local.py --url http://spark:11434 --model gemma4:31b --parallel 4
                                                    # the models on a bigger machine

Reads data/demo/local-demo.json: the settings, the replay window and the beats to show.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from tephra.agents.ollama import ollama_ready
from tephra.config import Settings

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "data" / "demo" / "local-demo.json"


def run_sheet(plan: dict, base: str) -> str:
    lines = [plan["title"], ""]
    for beat in plan["beats"]:
        lines.append(f"{beat['at']:>5}  {base}{beat['page']}")
        lines.append(f"       do   {beat['do']}")
        lines.append(f"       see  {beat['see']}")
        lines.append(f"       say  {beat['say']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Gemma demo of TEPHRA.")
    parser.add_argument("--sheet", action="store_true", help="print the run sheet and stop")
    parser.add_argument("--fresh", action="store_true", help="delete the local demo store first")
    parser.add_argument("--url", help="Ollama on another machine, e.g. http://spark:11434")
    parser.add_argument("--model", help="an Ollama tag to use instead of the plan's")
    parser.add_argument(
        "--parallel", type=int, help="flights planned and requests sent at once (default 1)"
    )
    args = parser.parse_args()

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    base = f"http://localhost:{plan['port']}"
    print(run_sheet(plan, base))
    if args.sheet:
        return 0

    env = {
        **os.environ,
        **plan["env"],
        "TEPHRA_OLLAMA_URL": args.url or plan["ollama"]["url"],
        "PORT": str(plan["port"]),
        "TEPHRA_DESK_PIN": os.environ.get("TEPHRA_DESK_PIN", plan["desk_pin"]),
    }
    if args.model:
        env["TEPHRA_MODEL"] = env["TEPHRA_MODEL_LITE"] = args.model
    if args.parallel:
        env["TEPHRA_OLLAMA_PARALLEL"] = env["TEPHRA_PLAN_PARALLEL"] = str(args.parallel)
    settings = Settings(
        _env_file=None,
        llm="ollama",
        model=env["TEPHRA_MODEL"],
        model_lite=env["TEPHRA_MODEL_LITE"],
        ollama_url=env["TEPHRA_OLLAMA_URL"],
    )
    problem = asyncio.run(ollama_ready(settings))
    if problem is not None:
        print(f"Cannot start: {problem}.", file=sys.stderr)
        print(f"Run `ollama serve`, then `ollama pull {plan['ollama']['model']}`.", file=sys.stderr)
        return 1

    store = ROOT / env["TEPHRA_SQLITE_PATH"]
    env["TEPHRA_SQLITE_PATH"] = str(store)
    if args.fresh:
        for path in store.parent.glob(f"{store.name}*"):
            path.unlink()
    print(f"Gemma is ready. Wall {base}/  Desk {base}/desk (PIN {env['TEPHRA_DESK_PIN']})")
    warm_up = f"Let it run about {plan['warm_up_min']} minutes before you present."
    print(warm_up, plan["warm_up_why"])
    sys.stdout.flush()  # exec replaces the process; unflushed lines would be lost
    os.execvpe("uv", ["uv", "run", "tephra"], env)


if __name__ == "__main__":
    sys.exit(main())
