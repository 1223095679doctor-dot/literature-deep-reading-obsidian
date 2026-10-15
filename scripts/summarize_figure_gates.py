#!/usr/bin/env python3
"""Validate compact per-Figure gates and emit a lightweight manifest.

The script intentionally prints only status, review flags, and anomalies. Figure
prose remains in local draft files and is not copied into the parent context.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


FIGURE_STEM = re.compile(r"^(Figure-S?\d+|Unit-[A-Za-z0-9-]+)$", re.I)


def gate_status(data: dict) -> str:
    for key in ("status", "final_status", "gate_status"):
        value = data.get(key)
        if isinstance(value, str) and value.upper() in {"PASS", "FAIL"}:
            return value.upper()
    history = data.get("status_history")
    if isinstance(history, list) and history:
        last = str(history[-1]).upper()
        if last in {"PASS", "FAIL"}:
            return last
    return "UNKNOWN"


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items() if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def find_gate(draft_dir: Path, stem: str) -> Path | None:
    candidates = (
        draft_dir / f"{stem}.gate-status.json",
        draft_dir / f"{stem}-gate-status.json",
        draft_dir / f"{stem}-gate.json",
    )
    return next((path for path in candidates if path.is_file()), None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("draft_dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    root = args.draft_dir.resolve()
    if not root.is_dir():
        print(f"ERROR: draft directory does not exist: {root}")
        return 2

    drafts = sorted(
        path for path in root.glob("*.md") if FIGURE_STEM.fullmatch(path.stem)
    )
    rows: list[dict] = []
    errors: list[str] = []

    for draft in drafts:
        gate = find_gate(root, draft.stem)
        if gate is None:
            errors.append(f"missing gate: {draft.name}")
            continue
        try:
            data = json.loads(gate.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid gate {gate.name}: {exc}")
            continue

        status = gate_status(data)
        anomalies = (
            as_list(data.get("anomalies"))
            + as_list(data.get("issues"))
            + as_list(data.get("problems"))
            + as_list(data.get("source_conflicts_or_limits"))
            + as_list(data.get("source_discrepancies"))
        )
        reasons = as_list(data.get("full_review_reasons"))
        rework_count = int(data.get("rework_count") or 0)
        requires_full = (
            bool(data.get("requires_full_review"))
            or bool(reasons)
            or bool(anomalies)
            or rework_count > 0
        )
        if anomalies and not reasons:
            reasons.append("source anomaly or evidence limit recorded")
        if rework_count > 0:
            reasons.append(f"reworked {rework_count} time(s)")
        if status != "PASS":
            requires_full = True
            reasons.append(f"gate status is {status}")
            errors.append(f"non-PASS gate: {draft.stem}={status}")

        rows.append(
            {
                "figure": data.get("figure", draft.stem.replace("-", " ", 1)),
                "draft": draft.name,
                "gate": gate.name,
                "status": status,
                "requires_full_review": requires_full,
                "full_review_reasons": reasons,
                "anomalies": anomalies,
                "rework_count": rework_count,
            }
        )

    if not drafts:
        errors.append("no Figure or Unit Markdown drafts found")

    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    flagged = [row for row in rows if row["requires_full_review"] or row["anomalies"]]
    print(
        f"SUMMARY: drafts={len(drafts)} gates={len(rows)} "
        f"pass={sum(row['status'] == 'PASS' for row in rows)} "
        f"full_review_or_anomaly={len(flagged)} errors={len(errors)}"
    )
    for row in flagged:
        detail = row["full_review_reasons"] + row["anomalies"]
        print(f"REVIEW: {row['figure']} | " + " ; ".join(detail[:6]))
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
