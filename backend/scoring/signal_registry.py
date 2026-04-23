"""
Re-export shim.

The canonical signal registry lives at backend/pipeline/signal_registry.py.
This module used to be a duplicate copy that drifted from the canonical;
it is now a thin re-export so that imports from both paths resolve to the
same objects.

No new code should be added here. All edits should go to
backend/pipeline/signal_registry.py.
"""
from backend.pipeline.signal_registry import *  # noqa: F401,F403
from backend.pipeline.signal_registry import (  # explicit re-exports for clarity
    SIGNAL_REGISTRY,
    SignalFamilySpec,
    get_spec,
    implementable_families,
    promotable_families,
)
