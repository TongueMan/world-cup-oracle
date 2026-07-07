"""Evaluate Agent research answers against golden quality cases.

Usage:
  python -m backend.scripts.evaluate_agent_quality --golden backend/tests/golden/agent_research_cases.jsonl --answers outputs/agent_answers.jsonl

The answers JSONL format is:
  {"id": "benchmark_brazil_norway_preview", "answer": "...", "sources": [{"citationId": 1, "relevanceScore": 0.9}]}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", required=True)
    parser.add_argument("--answers", required=False)
    args = parser.parse_args()

    cases = _read_jsonl(Path(args.golden))
    if not args.answers:
        print(f"Loaded {len(cases)} golden cases. Provide --answers to score outputs.")
        return 0
    answers = {row["id"]: row for row in _read_jsonl(Path(args.answers))}
    failures = []
    for case in cases:
        answer_row = answers.get(case["id"])
        if not answer_row:
            failures.append((case["id"], "missing answer"))
            continue
        score, issues = score_case(case, answer_row)
        threshold = int(case.get("minScore", 24))
        if score < threshold:
            failures.append((case["id"], f"score {score} < {threshold}: {'; '.join(issues)}"))
        print(f"{case['id']}: {score}/30 {'PASS' if score >= threshold else 'FAIL'}")
    if failures:
        print("\nFailures:")
        for case_id, reason in failures:
            print(f"- {case_id}: {reason}")
        return 1
    return 0


def score_case(case: dict[str, Any], row: dict[str, Any]) -> tuple[int, list[str]]:
    answer = str(row.get("answer") or "")
    sources = row.get("sources") if isinstance(row.get("sources"), list) else []
    issues: list[str] = []
    score = 0

    must = [str(item) for item in case.get("mustContain", [])]
    covered = sum(1 for item in must if item and item in answer)
    score += 5 if not must else round(5 * covered / len(must))
    if covered < len(must):
        issues.append("missing required content")

    forbidden = [str(item) for item in case.get("mustNotContain", [])]
    if any(item and item in answer for item in forbidden) or re.search(r"https?://\S+", answer):
        issues.append("contains forbidden content")
    else:
        score += 5

    min_sources = int(case.get("minSources", 0))
    relevant_sources = [
        source for source in sources
        if float(source.get("relevanceScore") or source.get("relevance_score") or 0) >= 0.55
    ]
    if len(relevant_sources) >= min_sources:
        score += 5
    else:
        issues.append(f"only {len(relevant_sources)} relevant sources")

    if case.get("requiresCitation"):
        citation_ids = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
        available = {int(source.get("citationId") or source.get("citation_id") or 0) for source in sources}
        available.discard(0)
        if citation_ids and citation_ids.issubset(available):
            score += 5
        else:
            issues.append("citation coverage failed")
    else:
        score += 5

    headings = len(re.findall(r"(^|\n)(#{1,3}\s+|[^\n]{2,16}[:：])", answer))
    if headings >= 4:
        score += 5
    elif headings >= 2:
        score += 3
        issues.append("structure could be stronger")
    else:
        issues.append("weak structure")

    if 450 <= len(answer) <= 2400:
        score += 5
    elif 280 <= len(answer) < 450 or 2400 < len(answer) <= 3200:
        score += 3
        issues.append("length outside ideal range")
    else:
        issues.append("poor answer length")

    return score, issues


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


if __name__ == "__main__":
    sys.exit(main())
