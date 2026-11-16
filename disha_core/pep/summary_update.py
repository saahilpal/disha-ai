"""Proxy module redirecting to summary_baseline for backward compatibility."""

from __future__ import annotations

from disha_core.pep.summary_baseline import (
    SummaryBaselineUpdater,
    context_slice_summary,
    get_summary_baseline_updater,
    on_session_end_summary,
    on_turn_summary,
)

__all__ = [
    "SummaryBaselineUpdater",
    "get_summary_baseline_updater",
    "on_session_end_summary",
    "on_turn_summary",
    "context_slice_summary",
]
