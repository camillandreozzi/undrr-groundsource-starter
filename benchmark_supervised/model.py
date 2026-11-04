"""Four MaxEnt classifiers and the event assembly that decodes them.

    trigger   P(this hazard mention reports a concrete occurrence)
    coref     P(two positive mentions report the same occurrence)
    year      P(this year is in the event's span | the event's mentions)
    place     P(this place is directly affected | the event's mentions)

Pipeline at prediction time:

  1. Score every lexicon trigger; keep those with P > THRESHOLD.
  2. Cluster the kept mentions into events: average-linkage agglomerative
     clustering on 1 - P(coref), cut at 1 - THRESHOLD, so two groups merge
     only while their mentions are on average more likely the same event
     than not.
  3. For each event, keep every year and every place with P > THRESHOLD.
  4. Emit the event; it is verifiable (a record, for the scorer) only with at
     least one year and one place — prompt 5's own bar.

The argument classifiers are trained on the gold events' mention clusters and
applied to the predicted ones: the usual pipeline mismatch, kept because it
is what a deployed pipeline would face.

Hyperparameters are fixed, not tuned: L2-regularised logistic regression with
C = 1, features max-abs scaled, and one decision threshold of 0.5 everywhere
("more likely than not"). With the gold as the only labelled data, any tuning
would be tuning on the test set.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional

import numpy as np

from benchmark_ner.hazard_lexicon import join_labels
from benchmark_ner.ner_extract import admin_level_for, impact_sentences
from benchmark_supervised.features import (
    Candidate, Doc, Trigger, argument_features, coref_features, gold_assignment,
    gold_clusters, place_label, trigger_features, year_label,
)
from eval.event_matching import GoldEvent, _loc_match

C = 1.0
THRESHOLD = 0.5
MAX_LOCATIONS = 10
MAX_SNIPPETS = 3
MAX_IMPACTS = 5


class MaxEnt:
    """DictVectorizer -> MaxAbsScaler -> L2 logistic regression."""

    def __init__(self) -> None:
        self.constant: Optional[float] = None

    def fit(self, X: list[dict], y: list[int]) -> "MaxEnt":
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import MaxAbsScaler
        if len(set(y)) < 2:
            # A training set with one class has nothing to learn; predict it.
            self.constant = float(y[0]) if y else 0.0
            return self
        self.vec = DictVectorizer(sparse=True)
        self.scale = MaxAbsScaler()
        M = self.scale.fit_transform(self.vec.fit_transform(X))
        self.lr = LogisticRegression(C=C, max_iter=5000).fit(M, y)
        return self

    def proba(self, X: list[dict]) -> np.ndarray:
        if not X:
            return np.zeros(0)
        if self.constant is not None:
            return np.full(len(X), self.constant)
        return self.lr.predict_proba(self.scale.transform(self.vec.transform(X)))[:, 1]


@dataclass
class TrainingWindow:
    doc: Doc
    gold: list[GoldEvent]


@dataclass
class Examples:
    X: list[dict]
    y: list[int]

    @classmethod
    def empty(cls) -> "Examples":
        return cls([], [])

    def add(self, x: dict, label: int) -> None:
        self.X.append(x)
        self.y.append(int(label))

    @property
    def positives(self) -> int:
        return sum(self.y)


CLASSIFIERS = ("trigger", "coref", "year", "place")


def window_examples(w: TrainingWindow) -> dict[str, Examples]:
    """One window's training examples. They depend on that window's text and
    gold only, so a cross-validation run builds them once and pools them per
    fold; the vectorisers and classifiers are still fitted per fold."""
    ex = {name: Examples.empty() for name in CLASSIFIERS}
    doc = w.doc
    assign = gold_assignment(doc, w.gold)
    for t in doc.triggers:
        ex["trigger"].add(trigger_features(doc, t), t.idx in assign)
    positives = [t for t in doc.triggers if t.idx in assign]
    for a, b in combinations(positives, 2):
        ex["coref"].add(coref_features(doc, a, b), assign[a.idx] == assign[b.idx])
    clusters = gold_clusters(doc, assign)
    by_id = {g.gold_event_id: g for g in w.gold}
    for gid, cluster in clusters.items():
        g = by_id[gid]
        for cand in doc.years:
            ex["year"].add(argument_features(doc, cluster, cand, list(clusters.values()),
                                             doc.years), year_label(cand, g))
        for cand in doc.places:
            ex["place"].add(argument_features(doc, cluster, cand, list(clusters.values()),
                                              doc.places), place_label(cand, g))
    return ex


def pool_examples(per_window: list[dict[str, Examples]]) -> dict[str, Examples]:
    return {name: Examples([x for ex in per_window for x in ex[name].X],
                           [y for ex in per_window for y in ex[name].y])
            for name in CLASSIFIERS}


def cluster_mentions(doc: Doc, mentions: list[Trigger], coref: MaxEnt) -> list[list[Trigger]]:
    if len(mentions) < 2:
        return [mentions] if mentions else []
    from scipy.cluster.hierarchy import fcluster, linkage
    pairs = list(combinations(range(len(mentions)), 2))
    p = coref.proba([coref_features(doc, mentions[i], mentions[j]) for i, j in pairs])
    # `pairs` is in condensed-matrix order, which is what `linkage` reads.
    tree = linkage(1.0 - p, method="average")
    labels = fcluster(tree, t=1.0 - THRESHOLD, criterion="distance")
    groups: dict[int, list[Trigger]] = {}
    for label, t in zip(labels, mentions):
        groups.setdefault(int(label), []).append(t)
    return sorted(groups.values(), key=lambda g: g[0].start)


@dataclass
class Extractor:
    trigger: MaxEnt
    coref: MaxEnt
    year: MaxEnt
    place: MaxEnt
    counts: dict[str, tuple[int, int]]

    @classmethod
    def fit(cls, windows: list[TrainingWindow]) -> "Extractor":
        return cls.from_examples(pool_examples([window_examples(w) for w in windows]))

    @classmethod
    def from_examples(cls, ex: dict[str, Examples]) -> "Extractor":
        return cls(**{name: MaxEnt().fit(e.X, e.y) for name, e in ex.items()},
                   counts={name: (len(e.y), e.positives) for name, e in ex.items()})

    def predict(self, doc: Doc) -> tuple[list[dict], list[dict]]:
        """Events in `to_output_rows` form, and a per-event detail trail."""
        p_trig = self.trigger.proba([trigger_features(doc, t) for t in doc.triggers])
        trig_p = {t.idx: float(p) for t, p in zip(doc.triggers, p_trig)}
        kept = [t for t in doc.triggers if trig_p[t.idx] > THRESHOLD]
        clusters = cluster_mentions(doc, kept, self.coref)

        events, detail = [], []
        for cluster in clusters:
            years = self._arguments(doc, cluster, clusters, doc.years, self.year)
            places = self._arguments(doc, cluster, clusters, doc.places, self.place)
            chosen_places: list[tuple[Candidate, float]] = []
            for cand, p in places:
                if p > THRESHOLD and not any(_loc_match(cand.value, c.value) for c, _ in chosen_places):
                    chosen_places.append((cand, p))
            chosen_places = chosen_places[:MAX_LOCATIONS]
            chosen_years = sorted(c.value for c, p in years if p > THRESHOLD)

            ranked = sorted(cluster, key=lambda t: -trig_p[t.idx])[:MAX_SNIPPETS]
            snippets = list(dict.fromkeys(doc.snippet(t) for t in sorted(ranked, key=lambda t: t.start)))
            missing = [what for what, have in (("no year", chosen_years),
                                               ("no location", chosen_places)) if not have]
            events.append({
                "event_hazard": join_labels(t.label for t in cluster),
                "event_dates": chosen_years,
                "affected_locations": [c.value for c, _ in chosen_places],
                "location_admin_levels": [admin_level_for(c.value, c.mentions[0].ner)
                                          for c, _ in chosen_places],
                "key_impacts": impact_sentences(snippets)[:MAX_IMPACTS],
                "event_confidence": None,
                "evidence_snippets": snippets,
                "missing_information": missing,
            })
            detail.append({
                "mentions": [{"text": t.surface, "label": t.label, "start": t.start,
                              "p": round(trig_p[t.idx], 4)} for t in cluster],
                "years": {c.value: round(p, 4) for c, p in years if p > 0.05},
                "places": {c.value: round(p, 4) for c, p in places if p > 0.05},
            })
        return events, detail

    @staticmethod
    def _arguments(doc: Doc, cluster: list[Trigger], clusters: list[list[Trigger]],
                   pool: list[Candidate], clf: MaxEnt) -> list[tuple[Candidate, float]]:
        p = clf.proba([argument_features(doc, cluster, c, clusters, pool) for c in pool])
        return sorted(zip(pool, (float(x) for x in p)), key=lambda x: -x[1])
