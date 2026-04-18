"""
SellerSignal v2 — Core data schema.

Every object in the pipeline has a definite shape.
No narrative is generated without an underlying Evidence trail.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════
# SIGNAL FAMILIES — human seller situations, NOT data categories
# ═══════════════════════════════════════════════════════════════════════
SignalFamily = Literal[
    "death_inheritance",
    "absentee_oos_disposition",
    "high_equity_long_tenure",
    "divorce_unwinding",
    "retirement_downsize",
    "relocation_executive",
    "financial_stress",
    "failed_sale_attempt",
    "investor_disposition",
    "pre_listing_structuring",
]

ALL_SIGNAL_FAMILIES: tuple[SignalFamily, ...] = (
    "death_inheritance",
    "absentee_oos_disposition",
    "high_equity_long_tenure",
    "divorce_unwinding",
    "retirement_downsize",
    "relocation_executive",
    "financial_stress",
    "failed_sale_attempt",
    "investor_disposition",
    "pre_listing_structuring",
)


# ═══════════════════════════════════════════════════════════════════════
# EVIDENCE TYPOLOGY — the core correction over v1
# ═══════════════════════════════════════════════════════════════════════
EvidenceRole = Literal[
    "trigger",       # WHY this candidate surfaced under this signal family
    "support",       # makes the signal hypothesis more plausible
    "context",       # informative, not predictive
    "contradiction", # weakens the hypothesis
    "resolution",    # proves the opportunity already resolved — fatal
]


@dataclass
class Evidence:
    role: EvidenceRole
    source: str          # e.g. "kc_deed_chain", "serp:everloved.com", "owner_db"
    description: str     # human-readable what-this-is
    observed_at: Optional[str] = None    # ISO date of the underlying event
    data_ref: Optional[dict] = None      # raw reference for audit (deed row, URL, etc.)
    weight: float = 1.0                  # magnitude, only matters within a family

    def __str__(self) -> str:
        when = f" ({self.observed_at})" if self.observed_at else ""
        return f"[{self.role}] {self.description}{when} — {self.source}"


# ═══════════════════════════════════════════════════════════════════════
# CANDIDATE REVIEW — the core review object
# ═══════════════════════════════════════════════════════════════════════
ReviewStatus = Literal["confirmed", "weak", "rejected"]
Confidence = Literal["high", "medium", "low"]


@dataclass
class CandidateReview:
    signal_family: SignalFamily
    parcel_id: str
    owner_name: str
    address: str

    evidence: list[Evidence] = field(default_factory=list)

    # Derived at review time
    candidate_status: ReviewStatus = "weak"
    confidence: Confidence = "low"
    reason: str = ""                  # why confirmed / weak / rejected
    next_step: Optional[str] = None

    # Property facts for downstream use (filled at review time)
    value: Optional[int] = None
    tenure_years: Optional[float] = None
    last_transfer_date: Optional[str] = None

    # ------------------------------------------------------------------
    @property
    def triggers(self) -> list[Evidence]:
        return [e for e in self.evidence if e.role == "trigger"]

    @property
    def supports(self) -> list[Evidence]:
        return [e for e in self.evidence if e.role == "support"]

    @property
    def contradictions(self) -> list[Evidence]:
        return [e for e in self.evidence if e.role == "contradiction"]

    @property
    def resolutions(self) -> list[Evidence]:
        return [e for e in self.evidence if e.role == "resolution"]

    @property
    def supporting_evidence(self) -> list[Evidence]:
        """Alias used by the v2 directive's CandidateReview contract."""
        return self.triggers + self.supports

    @property
    def contradicting_evidence(self) -> list[Evidence]:
        """Alias used by the v2 directive's CandidateReview contract."""
        return self.contradictions + self.resolutions


# ═══════════════════════════════════════════════════════════════════════
# LEAD — only built from confirmed CandidateReviews
# ═══════════════════════════════════════════════════════════════════════
LeadTier = Literal["act_this_week", "active_window", "long_horizon"]


@dataclass
class Lead:
    parcel_id: str
    address: str
    value: Optional[int]
    current_owner: str

    signal_family: SignalFamily
    lead_tier: LeadTier

    evidence: list[Evidence]
    supporting_evidence: list[Evidence]
    contradicting_evidence: list[Evidence]   # kept for transparency even though confirmed
    confidence: Confidence

    why_now: str
    situation: str
    approach: str
    recommended_channel: str
    timing_window_days: int

    # Audit
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source_review: Optional[CandidateReview] = None


# ═══════════════════════════════════════════════════════════════════════
# JSON SERIALIZATION
# ═══════════════════════════════════════════════════════════════════════
def _evidence_to_dict(e: Evidence) -> dict:
    return {
        "role": e.role, "source": e.source, "description": e.description,
        "observed_at": e.observed_at, "weight": e.weight,
        "data_ref": e.data_ref,
    }


def review_to_dict(r: CandidateReview) -> dict:
    return {
        "signal_family": r.signal_family,
        "parcel_id": r.parcel_id,
        "owner_name": r.owner_name,
        "address": r.address,
        "candidate_status": r.candidate_status,
        "confidence": r.confidence,
        "reason": r.reason,
        "next_step": r.next_step,
        "value": r.value,
        "tenure_years": r.tenure_years,
        "last_transfer_date": r.last_transfer_date,
        "evidence": [_evidence_to_dict(e) for e in r.evidence],
    }


def lead_to_dict(ld: Lead) -> dict:
    return {
        "parcel_id": ld.parcel_id, "address": ld.address,
        "value": ld.value, "current_owner": ld.current_owner,
        "signal_family": ld.signal_family, "lead_tier": ld.lead_tier,
        "confidence": ld.confidence,
        "why_now": ld.why_now, "situation": ld.situation, "approach": ld.approach,
        "recommended_channel": ld.recommended_channel,
        "timing_window_days": ld.timing_window_days,
        "supporting_evidence": [_evidence_to_dict(e) for e in ld.supporting_evidence],
        "contradicting_evidence": [_evidence_to_dict(e) for e in ld.contradicting_evidence],
        "generated_at": ld.generated_at,
    }
