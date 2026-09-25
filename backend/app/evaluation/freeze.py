"""Write the held-out freeze record. Refuses to overwrite without a recorded reason."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.evaluation.cases import FREEZE, freeze_record, load_cases


def freeze(*, reason: str | None = None, reviewed_by: str) -> dict:
    cases = load_cases("heldout")
    previous = json.loads(FREEZE.read_text()) if FREEZE.is_file() else None
    if previous and not reason:
        raise SystemExit("held-out suite is already frozen; refreezing needs --reason")
    record = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": reviewed_by,
        "case_count": len(cases),
        "generated_cases": sum(case.corpus_kind == "generated" for case in cases),
        "hashes": freeze_record(),
        "history": [*(previous or {}).get("history", []), *([{"previous": previous["hashes"], "reason": reason}] if previous else [])],
    }
    FREEZE.write_text(json.dumps(record, indent=2) + "\n")
    return record
