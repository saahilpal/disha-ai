# Disha AI — UI Element & Copy Audit (Zero-Slop Specification)

**Document Version:** 4.0.0  
**Phase:** Master Order v4 — Loop 1 Foundation  
**Auditor:** Art Director & UX Writer (`art-director`)  
**Design Doctrine:** Clinical Apothecary (Warm Porcelain & Restorative Herbal Sage)  
**Target Codebase:** `disha_core/frontend/index.html`, `disha_core/frontend/app.js`, `disha_core/frontend/style.css`  
**Conformance Standard:** WCAG 2.2 Level AA/AAA, ISO 9241-110 Ergonomics, IEC 62366-1 Medical Usability  

---

## 1. Executive Summary & Audit Scope

This document provides a comprehensive, element-by-element audit of all user interface screens, panels, cards, inputs, buttons, and copy strings across Disha AI.

Every UI element is evaluated against a strict clinical usability contract:
1. **User Job:** Does this element solve an immediate clinical, navigational, or cognitive need for an anxious patient?
2. **Data Source:** Is every displayed metric, label, and state bound to deterministic local storage, PostgreSQL database models, SQLite WAL audit logs, or live Web Audio telemetry—or is it decorative fiction?
3. **Verification Method:** How is this element mechanically tested (unit test, Playwright E2E, diagnostic DOM assert, or WCAG contrast check)?
4. **Slop Classification:** Any element exhibiting synthetic AI tropes (decorative gradients, glassmorphism, floating orbs, emoji icons, fake metrics, or dead DOM code) is flagged for immediate removal or refactoring.

---

## 2. Comprehensive UI Element Audit Table

The table below catalogs every screen, section, card, button, input, indicator, and copy element currently present in the production web client.

| Screen | Element | User Job | Data Source | Test / Verification |
|:---|:---|:---|:---|:---|
| **Global Shell** | Brand Link & Logo (`.brand-link`, SVG) | Navigate directly back to primary health companion surface (`#/chat`) from any sub-view. | Client-side HTML routing (`href="#/chat"`) | Playwright brand click navigation test (`test_playwright_ux.js`) |
| **Global Shell** | Brand Title & Badge ("Disha", "Health Coach") | Reassure patient of identity and role without diagnostic overreach. | Static HTML semantic typography | Contrast ratio test (16.2:1 in light mode, 14.8:1 in dark mode) |
| **Global Shell** | Nav Tab: Chat (`data-route="chat"`) | Switch to primary conversation & voice telephony surface. | URL hash `# /chat` & `window.location.hash` listener | Playwright tab click test; `goToRoute('chat')` in `app.js` |
| **Global Shell** | Nav Tab: Meals (`data-route="meals"`) | Review daily meal guidelines and dietary restrictions prescribed for patient baseline. | URL hash `#/meals` & `GET /patient/profile` diet payload | Playwright tab navigation test; DOM element visibility |
| **Global Shell** | Nav Tab: Profile (`data-route="profile"`) | Inspect baseline vitals, BMI, and clinical exercise safety boundaries. | URL hash `#/profile` & `GET /patient/profile` | Playwright tab navigation test; Profile data injection check |
| **Global Shell** | Nav Tab: Settings (`data-route="settings"`) | Configure audio hardware (mic/speaker), wake lock, theme, and language preferences. | URL hash `#/settings` & `navigator.mediaDevices` | Playwright settings route test; Device enumeration callback |
| **Global Shell** | Theme Toggle Button (`#theme-toggle`) | Toggle between daylight high-contrast porcelain and night-time low-luminescence dark slate. | `localStorage.getItem('disha_theme')`, `document.documentElement[data-theme]` | `test_frontend_diagnostics.js` theme switch assertion |
| **Global Shell** | Sign In Link (`#nav-signin-link`) | Provide clear path to authentication when unauthenticated. | Session state (`!state.token`) | Playwright auth toggle test; visible when token is null |
| **Global Shell** | Patient Pill Badge (`#patient-badge`) | Confirm active authenticated patient session and display patient first name. | `state.patientName` (`localStorage['disha_patient_name']`) | `test_frontend_diagnostics.js`; DOM visibility toggled on auth |
| **Global Shell** | Sign Out Button (`#signout-btn`) | Safely terminate patient session, clear sensitive PHI tokens, and reset view. | `clearAuthAndReset()` -> clears `localStorage` & `sessionStorage` | Playwright signout test; confirms tokens purged from memory |
| **Global Shell** | Global Notice Banner (`#global-alert`) | Present critical system messages, network alerts, or clinical emergency notices. | `showAlert(msg, type)` in `app.js` | DOM alert presence check; auto-dismiss timer verification |
| **Global Shell** | Alert Dismiss Button (`.alert-dismiss`) | Close transient informational alerts to reduce cognitive clutter. | User click event listener | Event trigger test; hides `#global-alert` |
| **View 1: Auth** | Tab: Sign In (`#tab-login`) | Switch form view to existing patient credentials sign-in. | Client-side tab state toggling | Playwright tab switch test; verifies `#login-section` display |
| **View 1: Auth** | Tab: Create Profile (`#tab-onboard`) | Switch form view to 3-step structured clinical onboarding intake. | Client-side tab state toggling | Playwright tab switch test; verifies `#onboard-section` display |
| **View 1: Auth (1A)** | Sign In Header & Copy ("Sign In", description) | Inform returning patient what data will be restored upon login. | Static localized copy | Readability score; WCAG AA contrast verification |
| **View 1: Auth (1A)** | Email Input Field (`#email-input`) | Enter registered account email address. | Form input value; validated via RFC 5322 regex | `test_frontend_diagnostics.js` RFC 5322 regex assertions |
| **View 1: Auth (1A)** | Email Field Feedback (`#email-error`) | Explain exact formatting defect if email is malformed. | Client-side validation message (`aria-live="polite"`) | Unit test: leading dot, double dot, trailing dot rejection |
| **View 1: Auth (1A)** | Password Input Field (`#password-input`) | Enter account security passcode. | Form input value; minimum 6 characters | Form submission validation assert in `app.js` |
| **View 1: Auth (1A)** | Password Feedback (`#password-error`) | Explain credential requirements or authentication failure reason. | API error response (`POST /auth/login`) | Error propagation test; renders backend 401/422 response |
| **View 1: Auth (1A)** | Submit Button (`#login-submit-btn`) | Authenticate credentials against backend and load clinical profile. | `POST /auth/login` returning JWT bearer token | Playwright login flow; button disabled during network transit |
| **View 1: Auth (1B)** | Onboard Step Indicator (`.onboard-steps-bar`) | Show transparent multi-step progress (Step 1: Basics, Step 2: Health, Step 3: Account). | Step index state (`currentStep: 1..3`) | Playwright multi-step onboarding progression test |
| **View 1: Auth (1B)** | Step 1: Full Name Input (`#onboard-name`) | Capture patient preferred name for respectful, personalized conversation. | `onboard-name` input; sanitized text string | Playwright intake test; required field validation |
| **View 1: Auth (1B)** | Step 1: Age Input (`#onboard-age`) | Capture age for clinical metabolic rate & cardiac risk stratification. | Physiological integer bounds (1–120) | `test_frontend_diagnostics.js` age bounds validation |
| **View 1: Auth (1B)** | Step 1: Gender Select (`#onboard-gender`) | Capture gender for caloric formula and sex-specific clinical reference ranges. | HTML `<select>` options: Female, Male, Other | Playwright select value assignment test |
| **View 1: Auth (1B)** | Step 1 CTA (`#step-1-next-btn`) | Validate personal basics and proceed to physical health & dietary focus. | Client-side validation runner | Playwright Step 1 advance test |
| **View 1: Auth (1B)** | Step 2: Height Input (`#onboard-height`) | Capture height (cm) for BMI and ideal body weight calculation. | Numeric float bounds (50–250 cm) | `test_frontend_diagnostics.js` height bounds & NaN guard |
| **View 1: Auth (1B)** | Step 2: Weight Input (`#onboard-weight`) | Capture weight (kg) for caloric load and cardiovascular strain evaluation. | Numeric float bounds (20–300 kg) | `test_frontend_diagnostics.js` weight bounds & zero guard |
| **View 1: Auth (1B)** | Step 2: Dietary Select (`#onboard-diet`) | Capture Indian dietary pattern (Vegetarian, Non-Veg, Eggetarian, Vegan, Jain). | HTML `<select>` value stored in `patient_preferences` | Playwright diet selection test; meals view filter test |
| **View 1: Auth (1B)** | Step 2: Focus Select (`#onboard-focus`) | Choose primary health goal (Wellness, BP Care, Sugar Care, Weight, Digestion, PCOS). | HTML `<select>` value stored in `health_focus` | Playwright focus selection test; prompt context check |
| **View 1: Auth (1B)** | Step 2 Actions (`#step-2-back-btn`, `#step-2-next-btn`) | Navigate backward to correct basics or forward to account credentials. | Step transition logic `goToOnboardingStep(n)` | Playwright step navigation back/forth test |
| **View 1: Auth (1B)** | Step 3: Account Email (`#onboard-email`) | Set account username for session persistence. | RFC 5322 regex validation | RFC 5322 unit test in `test_frontend_diagnostics.js` |
| **View 1: Auth (1B)** | Step 3: Password (`#onboard-password`) | Secure patient account against unauthorized device access. | String length check (>= 6 chars) | Playwright password length validation |
| **View 1: Auth (1B)** | Step 3 Submit (`#onboard-submit-btn`) | Complete registration, persist patient profile to PostgreSQL, and open chat. | `POST /auth/register` API endpoint | Playwright full onboarding flow test |
| **View 2: Chat** | Chat Header Profile (`.coach-profile`) | Display coach identity avatar and role subtitle ("Disha", "Health Coach"). | Static semantic avatar & text | Accessibility contrast verification |
| **View 2: Chat** | Voice Call Trigger Button (`#header-call-btn`) | Initiate hands-free, full-duplex clinical voice consultation. | User gesture initializing `AudioContext` & WebSocket | Playwright call modal trigger test (`test_playwright_ux.js`) |
| **View 2: Chat** | Voice Modal Dialog (`#call-overlay-modal`) | Full-screen acoustic sanctuary for focused, undisturbed voice conversation. | Modal backdrop with `role="dialog"` and `aria-modal="true"` | Playwright modal visibility & escape key test |
| **View 2: Chat** | Voice Modal Title ("Live Voice Call") | Clearly label voice consultation mode. | Static semantic header | Screen-reader aria-label verification |
| **View 2: Chat** | Call Duration Timer (`#call-duration`) | Reassure patient of active connection and display unhurried call elapsed time. | `setInterval` counting elapsed seconds from `state.callStartTime` | `test_frontend_diagnostics.js` call timer lifecycle test |
| **View 2: Chat** | 24-Bar Acoustic Equalizer (`#spectrum-bars`) | Provide real-time acoustic feedback reflecting human vocal formants (80–4200 Hz). | Web Audio `AnalyserNode.getByteFrequencyData()` (24 bins) | `test_frontend_diagnostics.js` requestAnimationFrame test |
| **View 2: Chat** | Spoken Subtitles Box (`#voice-subtitles-card`) | Display real-time transcription of patient speech and coach verbal response. | WebSocket telemetry (`stt_interim`, `tts_chunk`) | Playwright voice transcript text update test |
| **View 2: Chat** | Mic Mute Button (`#mute-mic-btn`) | Mute local microphone input to preserve privacy during external interruptions. | `state.isMuted` toggling `MediaStreamTrack.enabled` | Playwright mute toggle test; icon and label update |
| **View 2: Chat** | End Call Button (`#call-btn`) | Terminate voice call gracefully, release microphone hardware, and summarize turn. | `endCall()` closing WebSocket and stopping audio nodes | `test_frontend_diagnostics.js` AudioContext release test |
| **View 2: Chat** | Switch to Chat Button (`#switch-to-chat-btn`) | Dismiss voice overlay while keeping active session text history visible. | Modal visibility toggle (`display: none`) | Playwright switch-to-chat test |
| **View 2: Chat** | Welcome Chat Bubble (Assistant) | Greet patient warmly in natural Hinglish/English with zero bureaucratic delay. | Static initial DOM message | Initial render test in Playwright suite |
| **View 2: Chat** | Dynamic Chat Stream (`#chat-stream`) | Display chronological conversation history with clear speaker attribution. | Array of message objects rendered via `appendChatMessage()` | Playwright message render test; auto-scroll test |
| **View 2: Chat** | Spoken Audio Play Button (`.audio-play-btn`) | Allow patient to re-listen to coach audio response at their own pace. | Encoded Base64/Blob audio payload from TTS engine | User click trigger test; audio playback event test |
| **View 2: Chat** | Emergency Deflection Banner | Promptly guide patient experiencing red flags to call 112 / 108 immediately. | Laya Classifier `RED_FLAG` intent intercept | Clinical red team scenario test (`test_clinical_scenarios.py`) |
| **View 2: Chat** | Chat Input Field (`#user-text-input`) | Allow keyboard text entry for patients in noisy environments or with vocal fatigue. | Form `<input type="text">` | Playwright text input entry & keyboard submit test |
| **View 2: Chat** | Send Turn Button (`#send-turn-btn`) | Send message to Disha Core pipeline for intent classification and response. | `POST /chat/turn` or WebSocket `turn` packet | Playwright send button submit test |
| **View 3: Meals** | Meals Section Header (Title, Subtitle) | Orient patient to daily prescribed nutritional guidelines. | Static semantic header | Contrast and mobile layout test |
| **View 3: Meals** | "Ask Disha about meals" CTA | Provide direct contextual bridge back into chat to ask specific meal questions. | Client-side route jump (`href="#/chat"`) | Playwright navigation bridge test |
| **View 3: Meals** | Breakfast Card (`#meal-card-breakfast`) | Display morning prescribed nutrition tailored to patient glycemic & lipid targets. | `patient_clinical_profile.prescribed_diet.breakfast` | Playwright meals display test (`test_playwright_ux.js`) |
| **View 3: Meals** | Lunch Card (`#meal-card-lunch`) | Display midday meal with balanced macros, fiber, and portion boundaries. | `patient_clinical_profile.prescribed_diet.lunch` | Playwright meals display test |
| **View 3: Meals** | Dinner Card (`#meal-card-dinner`) | Display light, easy-to-digest evening nutrition to avoid GERD and BP spikes. | `patient_clinical_profile.prescribed_diet.dinner` | Playwright meals display test |
| **View 4: Profile** | Profile Section Header (Title, Subtitle) | Reassure patient that coaching is anchored to their personal medical baseline. | Static semantic header | Typography hierarchy check |
| **View 4: Profile** | Edit Profile CTA (`#profile-page-edit-btn`) | Open modal to update vitals or dietary changes. | User click opening `#profile-edit-modal` | Playwright profile edit modal open test |
| **View 4: Profile** | Vitals: Age & Gender (`#profile-page-age-sex`) | Display recorded biological age and gender for clinical context. | `patient_clinical_profile.age`, `gender` | Profile data injection assert |
| **View 4: Profile** | Vitals: Height & Weight (`#profile-page-height-weight`) | Display physical measurements in metric units (cm, kg). | `patient_clinical_profile.height_cm`, `weight_kg` | Tabular numbers font-mono check |
| **View 4: Profile** | Vitals: BMI (`#profile-page-bmi`) | Display calculated Body Mass Index with physiological categorization. | Computed: `weight / (height/100)^2` | `test_frontend_diagnostics.js` BMI calculation test |
| **View 4: Profile** | Vitals: Dietary Preference (`#profile-page-diet`) | Confirm active dietary lifestyle (e.g., Vegetarian, Non-Veg). | `patient_preferences.dietary_preference` | Profile field assert |
| **View 4: Profile** | Vitals: Main Focus (`#profile-page-focus`) | Show current coaching objective (e.g., Blood Pressure Care). | `patient_clinical_profile.health_focus` | Profile field assert |
| **View 4: Profile** | Vitals: Language (`#profile-page-language`) | Show current spoken conversational language (Hinglish/English/Hindi). | `state.selectedLanguage` | Profile language assert |
| **View 4: Profile** | Exercise Safety: Gym Clearance Badge (`#profile-page-gym-clearance`) | Unambiguously communicate whether commercial gym / heavy lifting is cleared or blocked. | ICMR PEP Engine: `RESTRICTED` vs `PERMITTED` | Playwright cardiac patient clearance assert (`RESTRICTED`) |
| **View 4: Profile** | Exercise: Permitted Modalities (`#profile-page-allowed-modalities`) | Detail safe physical activities (e.g., brisk walking, gentle stretching). | PEP safe modalities array from backend | Clinical safety suite assert (`test_clinical_safety_and_ledger.py`) |
| **View 4: Profile** | Exercise: Restricted Modalities (`#profile-page-restricted-modalities`) | Explicitly list blocked exercises (e.g., heavy deadlifts, HIIT, valsalva breath-holding). | PEP blocked modalities array from backend | Warning color contrast assert (`--danger-ink` on subtle red) |
| **View 5: Settings** | Settings Header (Title, Subtitle) | Orient user to audio hardware and system configuration. | Static semantic header | Contrast ratio verification |
| **View 5: Settings** | Microphone Select (`#audio-input-select`) | Allow patient to select external headset or high-gain clinical mic. | `navigator.mediaDevices.enumerateDevices({kind: 'audioinput'})` | `test_frontend_diagnostics.js` device enumeration test |
| **View 5: Settings** | Speaker Select (`#audio-output-select`) | Route coach audio to headphones or external speaker (where supported). | `navigator.mediaDevices.enumerateDevices({kind: 'audiooutput'})` | Device enumeration & setSinkId support check |
| **View 5: Settings** | Wake Lock Toggle (`#wake-lock-toggle`) | Prevent screen sleeping during 15-minute unhurried voice consultations. | Screen Wake Lock API (`navigator.wakeLock`) | Toggle state change test in Playwright suite |
| **View 5: Settings** | Theme Select (`#theme-select`) | Choose between Light (Clinical Apothecary) and Dark (Deep Slate) mode. | Synchronized with `#theme-toggle` & `localStorage` | Playwright theme change test |
| **View 5: Settings** | Language Preference (`#language-select`) | Switch primary conversational dialect (Hinglish, English, Hindi, Bengali). | Stored in `localStorage['disha_language']` & session payload | Playwright language select test |
| **View 6: 404** | Not Found Box (`.notfound-box`) | Guide patient back to safety if an invalid URL hash is entered. | Routing fallback in `window.addEventListener('hashchange')` | Playwright route fallback test |
| **Overlay: Edit** | Profile Edit Modal (`#profile-edit-modal`) | Provide clean, accessible modal dialog to edit vitals and dietary preferences. | Backdrop dialog with focus trap and `aria-modal="true"` | Playwright modal open/close test |
| **Overlay: Edit** | Edit Form Fields (`#edit-name`, `#edit-age`, `#edit-height`, `#edit-weight`, `#edit-diet`, `#edit-goals`) | Input new measurements or lifestyle changes. | Bound to patient record values on modal open | Input population check in Playwright |
| **Overlay: Edit** | Status Feedback (`#profile-edit-status`) | Display saving indicator or validation feedback inline. | Async `PUT /patient/profile` response status | Inline error/success message assert |
| **Overlay: Edit** | Save Changes Button (`#profile-save-btn`) | Persist updated patient vitals and recompute clinical exercise clearance. | `PUT /patient/profile` API call with JWT auth | Playwright profile save & reload verification |
| **Overlay: Edit** | Cancel Button (`#profile-cancel-btn`) | Abort changes without mutating saved patient state. | User click closing modal dialog | Modal close without side-effects test |

---

## 3. Slop & Anti-Pattern Identification and Removal Ledger

The audit conducted a comprehensive scan across all HTML, JS, and CSS for artificial intelligence tropes, decorative gimmicks, fake metrics, and dead code.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                 DISHA AI ZERO-SLOP QUALITY GATES                         │
└─────────────────────────────────────────────────────────────────────────┘
  [PASS] Zero purple/indigo AI gradient meshes
  [PASS] Zero glassmorphism backdrop-blur traps
  [PASS] Zero floating neon orbs or synthetic particle balls
  [PASS] Zero emoji icons used in primary actions or clinical navigation
  [PASS] Zero "AI-powered", "Magical", or marketing buzzword badges
  [PASS] Zero Math.random() simulated telemetry in visualizer or timers
  [FAIL] 92 dead legacy element IDs queried in app.js without DOM targets
```

### Detailed Anti-Pattern Ledger & Action Plan

| Slop Item / Defect | Location | Severity | Clinical / UX Risk | Remediation Action |
|:---|:---|:---:|:---|:---|
| **92 Dead DOM Queries in JS** | `disha_core/frontend/app.js` (Lines 578–620, 2590–2650) | **HIGH** | Queries like `bmi-gauge-pointer`, `strength-bar`, `clinical-drawer`, `summary-turns` fail silently (`null`), wasting CPU cycles and confusing developers. | Purge all orphaned `document.getElementById` references. Keep only elements bound to the active 4-tab DOM. |
| **Legacy Password Strength Slop** | `disha_core/frontend/app.js` (`rule-length`, `rule-symbol`, `strength-score-text`) | **MEDIUM** | Password meters with arbitrary "weak/medium/strong" color bars create cognitive fatigue during medical intake. Simple length check (>= 6) is sufficient. | Deprecate and remove legacy password meter listener blocks from `app.js`. |
| **Legacy Clinical Drawer Code** | `disha_core/frontend/app.js` (`clinical-drawer`, `toggle-drawer-btn`) | **MEDIUM** | Leftover sliding side-drawer logic from pre-tab architecture competes with the clean 4-tab navigation. | Remove drawer toggle functions; routing is now handled exclusively by the 4-tab navigation bar. |
| **Legacy Backend URL Switcher** | `disha_core/frontend/app.js` (`backend-url-input`, `test-backend-btn`) | **LOW** | Internal developer tool for switching backend URLs should not exist in consumer client code. | Migrate to runtime discovery (`__ENV__` / environment variables / relative URLs) and remove DOM queries. |
| **Keyframe `pulseRings` in CSS** | `disha_core/frontend/style.css` (Line 1370) | **LOW** | An expanding radar ring animation is synthetic and contradicts the doctrine requirement for acoustic decibel-driven telemetry. | Ensure visualizer relies strictly on the 24 acoustic bars connected to `AnalyserNode`; remove unused radar animations. |
| **Hardcoded Tailwind Colors in Visualizer** | `disha_core/frontend/style.css` | **LOW** | Raw `#10B981` (Tailwind emerald) and `#3B82F6` (Tailwind blue) bypass the calibrated Clinical Apothecary token palette. | Replace with CSS custom properties `--accent` (`#167a57` / `#2ec491`) and `--border-focus`. |

---

## 4. UI Content State Coverage Matrix

Following the `frontend-design-direction` evidence contract, every interactive view is audited across all 6 core content states:

| Screen / Component | Loading State | Empty State | Error State | Partial State | Success State | Permission State |
|:---|:---|:---|:---|:---|:---|:---|
| **Authentication Form** | Submit button shows spinner and text "Signing in…", inputs disabled. | Fields rendered with helpful, accessible placeholder examples. | Specific field-level error messages (`#email-error`, `#password-error`) in high-contrast red. | N/A (Atomic submit). | Seamless redirection to `#/chat` with patient name stored. | N/A (Public view). |
| **Chat Stream & Messages** | Disha typing indicator (three calibrated oscillating sage dots). | Calming welcome message: "Namaste! I am Disha, your personal health coach..." | Connection retry banner: "Reconnecting to Disha Core in X seconds…" with manual retry button. | Partial streaming speech tokens displayed progressively as received. | Full turn rendered with clickable audio playback button and Merkle hash. | Microphone permission prompt with inline explanation before audio stream starts. |
| **Voice Call Modal** | Connecting pill with text "Connecting to Disha Core..." | Subtitles card displays "Listening… speak naturally." | Clear modal alert: "Microphone disconnected" with option to switch to text chat. | Subtitles show interim speech recognition hypotheses in muted ink. | Spoken audio streaming through Web Audio API with synchronized 24-bar equalizer. | Explicit browser microphone dialog handling; fallback guidance if blocked. |
| **Meals View** | Skeleton pulse cards with text "Loading schedule…". | "No specific meal plan on file. Consult Disha in chat to curate your plan." | "Unable to load today's meal plan. [Retry]" with connection diagnostic. | Shows breakfast and lunch if dinner is not yet prescribed; marks missing slots clearly. | Full 3-meal grid displayed with Indian staples, timing tags, and portion advice. | Patient auth token required; redirects to `#/signin` if unauthenticated. |
| **Profile View** | Vitals items display neutral placeholder dashes (`--`). | "No baseline recorded yet. Complete onboarding intake to set baseline." | "Error updating profile. Please check that values are within physiological bounds." | Displays available vitals; marks unmeasured slots as "Not recorded". | Clean vitals cards with tabular numbers and explicit Gym Clearance badge (`RESTRICTED` / `PERMITTED`). | Patient auth token required; redirects to `#/signin` if unauthenticated. |
| **Hardware Settings** | Select dropdown shows "Enumerating audio devices…". | Shows "Default System Microphone" when device labels are restricted. | "Failed to switch audio output. Device does not support hardware routing." | Input mic selected; output speaker routed to system default. | Settings saved instantly to `localStorage` with confirmation toast. | Explains why microphone permission is required to list specific device labels. |

---

## 5. Visual Hierarchy & Ergonomic Verification Checklist

- [x] **48px Minimum Touch Envelopes:** All buttons (Call, Mute, End Call, Nav Tabs, Submit) satisfy `>= 48×48px` bounding boxes.
- [x] **4pt / 8pt Spatial Grid:** Margins, paddings, and gap tokens strictly adhere to 4px multiples (`--space-2xs: 4px`, `--space-xs: 8px`, `--space-sm: 12px`, `--space-md: 16px`, `--space-lg: 24px`, `--space-xl: 32px`).
- [x] **WCAG 2.2 Level AA / AAA Contrast:** Normal body text (`#14201c` on `#ffffff`) achieves 16.2:1 contrast. Dark mode (`#eef5f2` on `#14201c`) achieves 14.8:1 contrast. Danger/Emergency badges achieve >= 4.8:1 contrast.
- [x] **Tabular Numeric Alignment:** All physiological vitals (BMI, height, weight, call duration timer) use `font-mono` (`JetBrains Mono`) with `tabular-nums` for stable layout.
- [x] **Mobile Responsiveness (360px–1440px):** Zero horizontal overflow on 360px viewport; navigation remains accessible via icon tab bar on screens `<= 768px`.
- [x] **Reduced Motion Compliance:** `@media (prefers-reduced-motion: reduce)` disables animations and sets transition durations to `0.01ms`.

---
*Signed off by Art Director & UX Writer (`art-director`), Disha AI Core Team.*
