"""
backend.pipeline — v2 signal-first pipeline, ported verbatim.

This package contains the full v2 lead-generation pipeline that produced
the 2026-04-18 14:36 UTC briefing (this-weeks-picks.json — Call Now /
Build Now / Strategic Holds format).

Port policy: each module in this package is ported from the /home/claude/
sellersignal_v2/ source tree verbatim, with modifications only where
strictly required for the v3 execution environment (Supabase persistence
vs. v2's flat-file JSON, env-based config vs. hardcoded paths).

Dependency layering within this package:

    schema.py              (lead_schema.py)    — data contracts
        ↓
    banding.py             (banding.py)        — band assignment
    rationality_index.py   (rationality_index.py) — expired-listing scoring
    signal_registry.py     (signal_registry.py)— signal family rules
        ↓
    evidence_resolution.py (evidence_resolution.py) — evidence → owner
        ↓
    obit_verification.py   (obit_verification.py)  — obit match verification
    decision_signals.py    (decision_signals.py)   — entity activity
        ↓
    candidate_search.py    (candidate_search.py)   — per-family search
        ↓
    candidate_review.py    (candidate_review.py)   — noise rejection
        ↓
    lead_builder.py        (lead_builder.py)       — synthesis into leads
        ↓
    pipeline.py            (pipeline.py)           — orchestrator
        ↓
    apply_banding.py       (apply_banding.py)      — post-pipeline banding
    apply_verification.py  (apply_verification.py) — verification-aware rebanding
        ↓
    weekly_selector.py     (weekly_selector.py)    — the 14:36 UTC briefing
"""
from backend.pipeline.schema import (
    # Type aliases
    SignalFamily,
    EvidenceRole,
    ReviewStatus,
    Confidence,
    LeadTier,
    # Constants
    ALL_SIGNAL_FAMILIES,
    # Dataclasses
    Evidence,
    CandidateReview,
    Lead,
    # Serializers
    review_to_dict,
    lead_to_dict,
)

__all__ = [
    "SignalFamily",
    "EvidenceRole",
    "ReviewStatus",
    "Confidence",
    "LeadTier",
    "ALL_SIGNAL_FAMILIES",
    "Evidence",
    "CandidateReview",
    "Lead",
    "review_to_dict",
    "lead_to_dict",
]
