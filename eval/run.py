"""Quality and speed check of the AI answers on fixed, deliberately inaccessible pages (eval/cases).

The page data comes from the real extension code (eval/extract.js, jsdom, no screenshots) and goes
through the real coordinator and prompts. Each answer is checked against keywords, or the element
it picked, and timed, so a prompt or model change can be compared with the last run.

Needs `npm install` at the repo root and, unless --dry-run, an Anthropic API key (NVDA settings
or ANTHROPIC_API_KEY). Every run calls the API once per case.

    coordinator\\.venv\\Scripts\\python eval\\run.py [--model MODEL] [--only CASE_ID] [--dry-run]
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "coordinator"))

import llm  # noqa: E402
from host import Coordinator  # noqa: E402

REQUESTS = {
	"explain": lambda c: {"type": "explain", "elementId": c["targetId"]},
	"form": lambda c: {"type": "form", "elementId": c["targetId"]},
	"table": lambda c: {"type": "table", "elementId": c["targetId"]},
	"summarize": lambda c: {"type": "summarize"},
	"find": lambda c: {"type": "find", "query": c["query"]},
	"sections": lambda c: {"type": "sections"},
	"report": lambda c: {"type": "report", "elementId": c["targetId"]},
	"guide": lambda c: {"type": "guide", "query": c["query"]},
}


def check(case, reply):
	"""(passed, detail) for one answer."""
	if reply.get("status") in ("error", "info"):
		return False, f"{reply.get('code')}: {reply.get('message') or reply.get('text')}"
	expect = case["expect"]
	if case["task"] in ("find", "guide"):
		return reply.get("elementId") == case["expectId"], f"picked {reply.get('elementId')}, expected {case['expectId']}: {reply.get('text')}"
	if case["task"] == "sections":
		titles = [s["title"] for s in reply.get("sections", [])]
		return len(titles) >= expect["minSections"], "; ".join(titles)
	text = reply.get("text", "")
	lower = text.lower()
	missing = ["|".join(group) for group in expect.get("allOf", []) if not any(k in lower for k in group)]
	forbidden = [k for k in expect.get("none", []) if k in lower]
	problems = [f"missing {m}" for m in missing] + [f"forbidden {f}" for f in forbidden]
	return not problems, "; ".join(problems) or text


def dry_run_coordinator(ask):
	"""No API calls: checks that every case's data reaches the model step."""
	return Coordinator(
		ask,
		explain=lambda data, shot, task: f"dry run: {len(json.dumps(data))} chars",
		choose=lambda data, shot, query, choices: (choices[0], f"dry run: {len(choices)} choices"),
		sections=lambda data, shot, choices: [(i, f"part {n}") for n, i in enumerate(choices[:3])],
		guide=lambda data, shot, goal, steps, choices: (choices[0], f"dry run: {len(choices)} choices", False),
	)


def main():
	parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
	parser.add_argument("--model", help=f"model to test instead of {llm.MODEL}")
	parser.add_argument("--only", help="run one case")
	parser.add_argument("--dry-run", action="store_true", help="check the cases without calling the API")
	args = parser.parse_args()
	if args.model:
		llm.MODEL = args.model
	cases = json.loads(subprocess.run(["node", str(ROOT / "eval" / "extract.js")], check=True, capture_output=True, text=True, encoding="utf-8").stdout)
	cases = [c for c in cases if not args.only or c["id"] == args.only]
	if not cases:
		sys.exit(f"no case {args.only}")
	results = []
	for case in cases:
		replies = case["replies"]
		ask = lambda msg, replies=replies: json.loads(json.dumps(replies[msg["type"]]))  # noqa: E731
		coordinator = dry_run_coordinator(ask) if args.dry_run else Coordinator(ask)
		start = time.monotonic()
		reply = coordinator.handle({**REQUESTS[case["task"]](case), "settings": {"language": "tr"}})
		seconds = time.monotonic() - start
		passed, detail = (True, "dry run") if args.dry_run else check(case, reply)
		results.append((passed, seconds))
		print(f"{'PASS' if passed else 'FAIL'}  {seconds:5.1f}s  {case['id']}: {detail}")
	passed = sum(p for p, _ in results)
	times = [s for _, s in results]
	print(f"\n{passed}/{len(results)} passed, model {llm.MODEL}, median {statistics.median(times):.1f}s, max {max(times):.1f}s")
	sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
	main()
