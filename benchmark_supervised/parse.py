"""Parse Experiment A's windows once, with two OntoNotes NER models -> JSON cache.

    python -m benchmark_supervised.parse            # reuses cached parses
    python -m benchmark_supervised.parse --force    # re-parses everything

Reads window texts only — never the gold — so the cache is identical whichever
windows end up in training or test.

COORDINATES
-----------
Each window is parsed after whitespace normalisation
(`human_annotation_app._normalise_ws`), not raw. Two reasons:

  1. `eval/event_matching.window_hay` is that same string casefolded, and gold
     support spans index it. Casefolding is per character, so a parse offset
     maps onto the hay by counting folded lengths (`features.Doc.to_hay`);
     they differ only after a ligature (ﬁ -> fi), which PDF text is full of.
  2. PDF text carries a hard line break every ~80 characters. OntoNotes has
     none, and an entity split by a newline token is an entity the model was
     never trained to see.

MODELS
------
  en_core_web_trf  RoBERTa-base fine-tuned on OntoNotes 5: tokens, sentences,
                   dependency parse, morphology and NER. The primary model.
  en_core_web_lg   CNN + static vectors on OntoNotes 5: NER only. A second,
                   weaker opinion; its entities are extra place candidates,
                   and which model found a candidate is a feature.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from eval.human_annotation_app import _normalise_ws, load_document_store, read_csv  # noqa: E402

LOG = logging.getLogger("benchmark_supervised.parse")

EVAL = REPO_ROOT / "eval"
WINDOWS = EVAL / "event_level_windows.csv"
STORES = (EVAL / "annotation_documents.json", EVAL / "annotation_documents_document_sample.json")
CACHE = REPO_ROOT / "benchmark_supervised" / "outputs" / "parsed"

PRIMARY_MODEL = "en_core_web_trf"
SECONDARY_MODEL = "en_core_web_lg"
#: OntoNotes labels kept. Places: GPE (countries, cities, states), LOC
#: (non-GPE locations: regions, rivers, seas), FAC (named facilities). DATE is
#: kept as context for year mentions.
KEPT_LABELS = frozenset({"GPE", "LOC", "FAC", "DATE"})


@dataclass
class Parsed:
    """One window, parsed. Plain lists so it round-trips through JSON."""
    key: str
    text: str
    #: (start, end) character spans, in document order.
    sents: list[tuple[int, int]]
    #: Per token: [start, end, lower, fine tag, coarse POS, head index, is past tense].
    tokens: list[list]
    #: Per entity: [start, end, OntoNotes label, model name].
    ents: list[list]
    models: dict[str, str]

    @classmethod
    def load(cls, path: Path) -> "Parsed":
        data = json.loads(path.read_text(encoding="utf-8"))
        data["sents"] = [tuple(s) for s in data["sents"]]
        return cls(**data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding="utf-8")


def window_keys(windows_path: Path = WINDOWS) -> list[str]:
    """Annotated Experiment A windows, in review order."""
    _, rows = read_csv(windows_path)
    done = [r for r in rows if str(r.get("window_status", "")).strip().lower() == "done"]
    return [r["asset_key"] for r in sorted(done, key=lambda r: int(r.get("review_rank") or 0))]


def window_texts(keys: list[str], stores=STORES) -> dict[str, str]:
    texts: dict[str, str] = {}
    for path in stores:
        documents, _ = load_document_store(Path(path))
        texts.update({k: v.get("text", "") for k, v in documents.items() if k in keys})
    missing = [k[:12] for k in keys if not texts.get(k)]
    if missing:
        raise SystemExit(f"No window text for: {', '.join(missing)}")
    return {k: _normalise_ws(texts[k]) for k in keys}


def _model_tag(nlp) -> str:
    return f"{nlp.meta['lang']}_{nlp.meta['name']}-{nlp.meta['version']}"


def parse_window(key: str, text: str, primary, secondary) -> Parsed:
    doc = primary(text)
    tokens = [[t.idx, t.idx + len(t.text), t.lower_, t.tag_, t.pos_, t.head.i,
               "Past" in t.morph.get("Tense")] for t in doc]
    ents = [[e.start_char, e.end_char, e.label_, PRIMARY_MODEL]
            for e in doc.ents if e.label_ in KEPT_LABELS]
    ents += [[e.start_char, e.end_char, e.label_, SECONDARY_MODEL]
             for e in secondary(text).ents if e.label_ in KEPT_LABELS]
    return Parsed(key=key, text=text,
                  sents=[(s.start_char, s.end_char) for s in doc.sents],
                  tokens=tokens, ents=sorted(ents),
                  models={PRIMARY_MODEL: _model_tag(primary),
                          SECONDARY_MODEL: _model_tag(secondary)})


def cache_path(key: str, text: str, cache: Path = CACHE) -> Path:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return cache / f"{key[:16]}_{digest}.json"


def load_all(keys: list[str], cache: Path = CACHE) -> dict[str, Parsed]:
    texts = window_texts(keys)
    out = {}
    for key in keys:
        path = cache_path(key, texts[key], cache)
        if not path.exists():
            raise SystemExit(f"Not parsed yet: {key[:12]}. Run: make supervised-parse")
        out[key] = Parsed.load(path)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cache", type=Path, default=CACHE)
    p.add_argument("--force", action="store_true", help="re-parse cached windows")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    warnings.filterwarnings("ignore", category=FutureWarning)

    import spacy
    keys = window_keys()
    texts = window_texts(keys)
    todo = [k for k in keys if args.force or not cache_path(k, texts[k], args.cache).exists()]
    LOG.info("%d windows, %d to parse", len(keys), len(todo))
    if not todo:
        return 0
    primary = spacy.load(PRIMARY_MODEL)
    secondary = spacy.load(SECONDARY_MODEL, exclude=["tagger", "parser", "attribute_ruler",
                                                     "lemmatizer", "senter"])
    for n, key in enumerate(todo, 1):
        parsed = parse_window(key, texts[key], primary, secondary)
        parsed.save(cache_path(key, texts[key], args.cache))
        LOG.info("[%d/%d] %s  %d sents  %d ents", n, len(todo), key[:12],
                 len(parsed.sents), len(parsed.ents))
    return 0


if __name__ == "__main__":
    sys.exit(main())
