"""Multi-model benchmark: prompt 5 held fixed, the model varied via OpenRouter.

Runs over the same 167 documents the human annotation queue covers, and emits
the exact `event_extractions` schema, so every existing scorer in the repo
accepts a run from here unchanged.
"""
