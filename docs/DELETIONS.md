# Disha AI — Deletions Ledger (docs/DELETIONS.md)

This document tracks all intentionally deleted files, dead directories, and removed legacy assets along with the rationale and verified replacement.

| Deleted Target | Date | Rationale | Replacement / Superset |
|---|---|---|---|
| `disha_core/frontend/demo_buttons` | 2026-11-09 | Contained hardcoded demo password attributes (`data-pass="demo123"`), violating secret hygiene and production readiness | Standard user authentication fields via typed login API |
| `#profile-page-gym-clearance` DOM element | 2026-11-09 | Invented clinical clearance claim ("Gym Clearance: Approved") that misled users without physician authorization | Removed completely from UI; clinical conditions preserved in PEP store |
| Hardcoded Pricing Constants (`PRICE_1499`, `FREE_CONSULT`) | 2026-11-09 | Invented pricing claims; Disha AI is a free health coach with zero commercial tiers | Replaced with strict zero-pricing invariant (`PRICING_REPLACEMENT`) |
| Redundant test mocks in `test_frontend_diagnostics.js` | 2026-11-09 | Checked for obsolete gym clearance elements | Updated to assert no gym clearance claims exist in DOM |
