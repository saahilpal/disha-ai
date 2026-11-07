# Disha AI — Clinical Design System & Token Architecture

**Version:** 2.0.0  
**Specification:** Concept A — "Clinical Apothecary"  
**Conformance:** WCAG 2.2 Level AAA, ISO 9241-110 Ergonomics  

---

## 1. Design Tokens Specification

All design tokens are defined as CSS Custom Properties in a single, authoritative source file. Re-theming is achieved purely by swapping variable definitions in `:root` and `[data-theme="dark"]`.

### A. Surface & Background Tokens
| Token Name | Light Value | Dark Value | Purpose |
|:---|:---:|:---:|:---|
| `--surface-canvas` | `#FBFBF9` | `#0F1412` | Primary viewport backdrop (warm alabaster / graphite slate) |
| `--surface-card` | `#FFFFFF` | `#18201C` | Elevated card container surface |
| `--surface-nested` | `#F4F6F4` | `#1F2823` | Recessed / nested panel surface |
| `--surface-input` | `#FFFFFF` | `#131A16` | Form input and text container background |
| `--surface-sage-wash` | `#EEF5F1` | `#15261E` | Soft herbal celadon wash for pills and badges |

### B. Neutral Hairline Border Tokens
| Token Name | Light Value | Dark Value | Purpose |
|:---|:---:|:---:|:---|
| `--border-hairline` | `#E6EAE7` | `#232E28` | Crisp 1px structural separator |
| `--border-subtle` | `#D9E0DC` | `#2D3A33` | Interactive input border default |
| `--border-hover` | `#CCD4CF` | `#3A4B42` | Interactive input hover state |
| `--border-focus` | `#1B5E43` | `#2D7A5B` | Keyboard focus ring & active field border |
| `--border-sage-active` | `#E2EEE7` | `#243B2E` | Active state border on sage wash containers |

### C. Clinical Accent & Semantic Status Tokens
| Token Name | Light Value | Dark Value | Purpose | Contrast Ratio |
|:---|:---:|:---:|:---|:---:|
| `--accent-emerald` | `#1B5E43` | `#2D7A5B` | Primary call button, branding, active selection | 7.8:1 (AAA) |
| `--accent-emerald-hover` | `#144833` | `#358E6B` | Primary interactive hover | 10.2:1 (AAA) |
| `--accent-celadon-tint` | `#EEF5F1` | `#15261E` | Connecting state, active filter pill | Background wash |
| `--status-emergency` | `#C24137` | `#D64F45` | Emergency deflection, end call, alert banner | 5.2:1 (AAA large) |
| `--status-emergency-wash` | `#FDF2F1` | `#2B1513` | Emergency guidance container fill | Low-saturation fill |
| `--status-warning` | `#B45309` | `#D97706` | PEP restriction warning, caution state | 5.1:1 (AAA large) |
| `--status-warning-wash` | `#FEF7EE` | `#291A0C` | PEP notice container fill | Low-saturation fill |
| `--status-active` | `#2D7A5B` | `#388E6C` | Active call in progress, normal clinical vitals | 4.8:1 (AA/AAA) |

### D. Typography Hierarchy
* **Primary Sans Stack:** `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
* **Monospace Tabular Stack:** `"JetBrains Mono", ui-monospace, Menlo, Monaco, Consolas, monospace`
* **Type Scale (Strict 1.250 Major Third Scale):**
  - `--text-display`: `2rem` (32px), `letter-spacing: -0.025em`, `line-height: 1.2`, `font-weight: 700`
  - `--text-title`: `1.5rem` (24px), `letter-spacing: -0.02em`, `line-height: 1.25`, `font-weight: 700`
  - `--text-subtitle`: `1.125rem` (18px), `letter-spacing: -0.01em`, `line-height: 1.35`, `font-weight: 600`
  - `--text-body`: `0.9375rem` (15px), `line-height: 1.5`, `font-weight: 400`
  - `--text-body-bold`: `0.9375rem` (15px), `line-height: 1.5`, `font-weight: 600`
  - `--text-caption`: `0.8125rem` (13px), `line-height: 1.4`, `font-weight: 500`
  - `--text-micro`: `0.6875rem` (11px), `letter-spacing: 0.04em`, `text-transform: uppercase`, `font-weight: 600`

### E. Spacing Scale (Strict 4pt / 8pt Grid)
* `--space-1`: `4px`
* `--space-2`: `8px`
* `--space-3`: `12px`
* `--space-4`: `16px`
* `--space-5`: `20px`
* `--space-6`: `24px`
* `--space-8`: `32px`
* `--space-10`: `40px`
* `--space-12`: `48px`
* `--space-16`: `64px`

### F. Radii, Elevation & Motion
* **Radii:**
  - `--radius-sm`: `4px` (input controls, badges, chips)
  - `--radius-md`: `8px` (nested cards, dropdowns, visualizer box)
  - `--radius-lg`: `12px` (outer cards, stage card, modals)
  - `--radius-full`: `9999px` (call buttons, status pills)
* **Elevation (Zero Neon Glow, Pure Optical Separation):**
  - `--shadow-card`: `0 1px 3px rgba(0, 0, 0, 0.04)` (Light) / `0 1px 3px rgba(0, 0, 0, 0.25)` (Dark)
  - `--shadow-sm`: `0 1px 2px rgba(0, 0, 0, 0.03)`
* **Motion Curves & Durations:**
  - Standard Curve: `cubic-bezier(0.16, 1, 0.3, 1)` (Gentle deceleration)
  - Micro-Transition: `120ms` (hover, active press `transform: scale(0.98)`)
  - State Transition: `180ms` (tab switches, indicator badge changes)
  - Drawer Transition: `240ms` (responsive layout transitions)
  - `prefers-reduced-motion: reduce`: All transition durations automatically drop to `0.001ms`.

