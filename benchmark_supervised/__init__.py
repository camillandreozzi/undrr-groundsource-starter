"""Supervised (non-LLM) event extractor for the UNDRR FONTE evaluation.

A trained pipeline — transformer NER, then MaxEnt classifiers for event
triggers, event coreference and time/place arguments — fitted on the blind
human event-level gold only and evaluated by leave-one-window-out
cross-validation on Experiment A's 45 windows. No LLM output is used to train
or run it.

See README.md for the design and the runbook.
"""
