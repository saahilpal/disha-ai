# ADR 001: Canonical Frontend Architecture & Monolith Deconstruction

**Status:** Accepted  
**Deciders:** Principal AI Engineer, Staff Full-Stack Engineer, Principal Product Designer  
**Date:** 2026-11-07  

---

## Context
1. **The Monolith Problem:** Previously, the frontend consisted of two duplicate hand-synced directories (`frontend/` and `disha_core/frontend/`), each containing a 1,400-line `app.js` and a 1,500-line `style.css`. Any bug fix had to be copied between the two directories manually, leading to drift, test fragility, and high maintenance overhead.
2. **Missing Product Information Architecture:** The old UI packed all elements (authentication, clinical intake, consultation call dock, diet drawer, telemetry) into a single DOM page, toggling sections using class names. There was no deep-linkable router, no dedicated post-call summary view, no audio input/output device picker, no medical consent gate, and no offline/server-waking state.
3. **Packaging Ingress:** Vercel was deployed as an isolated static host without backend proxying, causing 404s on `/auth/login`.

---

## Decision
1. **Single Canonical Source of Truth:**
   * Consolidate into ONE canonical frontend codebase located at `frontend/`.
   * Configure Docker to build and bundle static assets directly from `frontend/`, eliminating `disha_core/frontend/` duplicates forever.
2. **Modular Architecture & SPA Router:**
   * Implement a lightweight, zero-dependency, ultra-fast client-side router (`Router`) with hash and path history support (`/#/`, `/#/signin`, `/#/home`, `/#/consultation`, `/#/summary`, `/#/history`, `/#/settings`, `/#/privacy`).
   * Route guards: Unauthenticated access to protected routes redirects to `/#/signin?returnTo=...`. Active call guard: navigating away while in call triggers a confirm modal ("Active consultation in progress. End call before leaving?").
   * Skip-to-content accessibility link (`#main-content`) with programmatic focus management on view change.
3. **Voice Engine & Audio Architecture:**
   * Clean separation of concerns:
     - `audio-engine.js`: Manages `AudioContext`, `MediaStream`, `AnalyserNode` 24-band frequency calculation, mic level metering, Bluetooth/device switches, and echoCancellation.
     - `ws-client.js`: WebSocket connection management with exponential jittered backoff, heartbeat pings, and barge-in frame dispatch.
     - `api-client.js`: Typed API client handling `/auth/login`, `/auth/register`, `/patient/profile`, and `/client-errors`.
4. **Design Tokens & System:**
   * Enforce Concept A ("Clinical Apothecary") via `tokens.css` with 100% WCAG AAA contrast, zero glow halos, and 1px crisp neutral hairline borders.

