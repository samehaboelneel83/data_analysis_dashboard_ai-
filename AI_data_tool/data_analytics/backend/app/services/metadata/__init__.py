"""Layer 1 — the metadata plane.

Everything in this package derives facts ABOUT data rather than serving data.
It runs on a schedule against a local sample cache, not on a user's request
against a customer's database. See
docs/superpowers/specs/2026-08-24-layer1-connectors-ingestion-design.md.

The one rule that binds every module here: inference is a proposal, never a
fact. Write through `store`, which is the only place allowed to decide whether
a derived row may overwrite an existing one.
"""
