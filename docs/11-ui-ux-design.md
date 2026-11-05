# 11 — UI/UX Design System & Interface Specification

This document defines the visual design system, interaction patterns, and component specifications for the **Disha AI Clinical Studio & Voice Simulator**, developed in compliance with the **`ui-ux-pro-max`** design intelligence framework and Swiss Minimalist clinical standards.

---

## 1. Visual Identity & Design Principles

### 1.1 Design Doctrine: "Clean Clinical Swiss Minimalism"
- **Purpose-Driven:** Every visual element directly serves clinical safety, dialogue comprehension, or telemetry inspection. No generic AI aesthetic, no decorative gradients without utility.
- **Trust & Authority:** Grounded in clinical reliability using deep slate navy (`#0F172A`), clinical indigo (`#4338CA`), and calm emerald (`#059669`).
- **Safety Prominence:** Acute emergencies use high-contrast crimson (`#DC2626`) with explicit 112 triage iconography.

### 1.2 Color Token Palette

```css
:root {
  /* Brand & Navigation */
  --color-primary: #0f172a;           /* Deep Slate Navy (Header & Hero) */
  --color-primary-accent: #4338ca;    /* Clinical Indigo */
  
  /* Clinical Safety & Guardrails */
  --color-success: #059669;           /* Emerald (Passed checks, Verified rules) */
  --color-success-bg: #ecfdf5;        /* Emerald tint */
  --color-emergency: #dc2626;         /* Crimson (Acute cardiac/respiratory triage) */
  --color-emergency-bg: #fef2f2;      /* Crimson tint */
  --color-intercept: #d97706;         /* Amber (Sanitizer rewrite, boundary enforced) */
  --color-intercept-bg: #fffbeb;      /* Amber tint */

  /* Neutral Backgrounds & Surfaces */
  --color-bg-base: #f8fafc;           /* Slate 50 base canvas */
  --color-surface-card: #ffffff;      /* Pure white card container */
  --color-border-subtle: #e2e8f0;     /* Slate 200 border */
  
  /* Typography */
  --color-text-main: #0f172a;         /* High-contrast body text */
  --color-text-muted: #64748b;        /* Slate 500 secondary text */
}
```

---

## 2. Typography Scale (Figtree & Noto Sans)

Configured via Google Fonts:
- **Primary Display & Headings:** `Figtree` (Weights: 400, 500, 600, 700) — clean, modern geometric sans-serif optimized for medical SaaS clarity.
- **Body & Dialogue Text:** `Noto Sans` (Weights: 400, 500) — excellent multilingual legibility across Romanized Hinglish terms and Hindi script.
- **Telemetry & Monospace Metrics:** `ui-monospace, SFMono-Regular, Menlo, Monaco` — tabular numbers for sub-millisecond latencies.

| Role | Font Family | Size | Weight | Line Height |
|---|---|---|---|---|
| Page Header Title | Figtree | 20px (1.25rem) | 700 (Bold) | 1.2 |
| Section Header | Figtree | 16px (1.00rem) | 600 (Semi-bold) | 1.3 |
| Body / Chat Bubble | Noto Sans | 14px (0.875rem) | 400 / 500 | 1.5 |
| Micro-telemetry & Badges | Figtree / Mono | 11px (0.6875rem) | 600 / 700 | 1.2 |
| Latency Numbers | Monospace | 12px (0.75rem) | 700 (Bold) | 1.0 |

---

## 3. Core Component Specifications

### 3.1 Quick-Failure Scenario Chips
- **Purpose:** Allows instant one-click testing of the 8 production failure modes from `problem statment.d`.
- **States:**
  - *Default:* Slate 100 background, Slate 300 border, Slate 700 text, 44px min touch target.
  - *Hover/Focus:* Indigo 50 background, Indigo 600 border, visible 2px outline for keyboard accessibility.
  - *Emergency Variant (Chips #5 & #5B):* Rose 50 background, Rose 300 border, Rose 800 font, alert badge.

### 3.2 Dialogue Transcript Window
- **User Bubble:** Right-aligned, indigo background (`#4338CA`), white text, crisp rounded border with top-right corner anchor.
- **AI Coach Bubble:** Left-aligned, white card with subtle slate border, emerald avatar pill (`D`), clear speaker label with turn latency indicator.
- **Emergency Triage Bubble:** Left-aligned, 2px solid crimson border (`#DC2626`), rose-50 fill, pulsing ambulance badge, explicit **112 EMERGENCY TRIAGE** header, bypass latency marker.

### 3.3 Real-Time Latency Waterfall Gauge
- **Visual:** Progress bar with color transitions:
  - `<1,200ms (P95 SLA Target):` Vibrant Emerald (`#059669`)
  - `1,200ms – 1,800ms:` Warning Amber (`#D97706`)
  - `>1,800ms:` SLA Breach Rose (`#DC2626`)
- **Stage Breakdown Pills:** Displays exact latency for Guardrail (`0.015ms`), RAG (`2.0ms`), LLM TTFT, and Sanitizer (`0.03ms`).

### 3.4 Interactive Audio Waveform & Speech Player
- **Visual:** Dynamic SVG audio bars animating during active neural speech playback.
- **Controls:** Embedded HTML5 `<audio>` player with auto-play, pause, and volume controls streaming directly from `/api/v1/simulation/tts`.

---

## 4. Responsive Breakpoints & Accessibility (WCAG 2.1 AA)

- **Mobile Viewport (375px – 640px):** Single-column stacked layout, collapsible telemetry drawer, full-width scenario chips.
- **Tablet / Laptop (768px – 1024px):** 12-column grid with 7-column dialogue panel and 5-column telemetry inspector.
- **Desktop (1024px – 1440px+):** Max-width 7xl container with generous padding, fixed navigation, and non-overlapping modal states.
- **Contrast Ratios:** All text elements exceed the 4.5:1 minimum contrast requirement against their respective backgrounds (main body text achieves 12.8:1).
- **Reduced Motion Support:** Respects `@media (prefers-reduced-motion: reduce)` by disabling pulsing effects and transitions.

