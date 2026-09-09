"""Load the frozen 167-document snapshot back into `DocumentRow` objects."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from fonte.app_event_focus import DocumentRow  # noqa: E402

DEFAULT_SNAPSHOT = REPO_ROOT / "benchmark_openrouter" / "documents.json"


class SnapshotError(RuntimeError):
    pass


def load_documents(path: Path = DEFAULT_SNAPSHOT, limit: int | None = None
                   ) -> tuple[list[DocumentRow], dict]:
    """Return (documents, snapshot metadata).

    Ordered by asset_key so a run is deterministic and `--limit 3` always picks
    the same three documents — a smoke test you can compare across models.
    """
    if not path.exists():
        raise SnapshotError(
            f"No document snapshot at {path}. Build it with:\n"
            "    python -m benchmark_openrouter.build_documents"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("documents") or {}
    if not raw:
        raise SnapshotError(f"{path} contains no documents.")

    fields = set(DocumentRow.__dataclass_fields__)
    documents = [
        DocumentRow(**{k: v for k, v in record.items() if k in fields})
        for _key, record in sorted(raw.items())
    ]
    if limit is not None:
        documents = documents[:limit]

    meta = {k: v for k, v in payload.items() if k != "documents"}
    return documents, meta
