"""Run the golden QA set against a running API and report retrieval and answer metrics.

Usage: python evals/run_qa.py --api http://localhost:8000 [--file evals/golden_qa.yaml]
Exit code 1 when retrieval recall or answer accuracy drops below the thresholds.
"""

from __future__ import annotations

import argparse
import sys

import httpx
import yaml


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--file", default="evals/golden_qa.yaml")
    ap.add_argument("--min-recall", type=float, default=0.9)
    ap.add_argument("--min-answer", type=float, default=0.8)
    args = ap.parse_args()
    items = yaml.safe_load(open(args.file))
    client = httpx.Client(base_url=args.api, timeout=120)
    recall_hits = answer_hits = 0
    for it in items:
        s = client.post("/search", json={"query": it["question"], "k": 10}).json()
        cited = {h.get("doc_number") for h in s["hits"]}
        r_ok = all(d in cited for d in it["must_cite"])
        a = client.post("/chat", json={"question": it["question"]}).json()
        text = a.get("answer", "")
        a_ok = all(p.lower() in text.lower() for p in it["must_contain"]) and all(
            d in {c.get("doc_number") for c in a.get("citations", [])} for d in it["must_cite"]
        )
        recall_hits += r_ok
        answer_hits += a_ok
        print(f"{it['id']}: retrieval={'ok' if r_ok else 'MISS'} answer={'ok' if a_ok else 'MISS'}")
    n = len(items)
    recall, answer = recall_hits / n, answer_hits / n
    print(f"\nretrieval recall@10 = {recall:.2f}   answer accuracy = {answer:.2f}  (n={n})")
    return 0 if recall >= args.min_recall and answer >= args.min_answer else 1


if __name__ == "__main__":
    sys.exit(main())
