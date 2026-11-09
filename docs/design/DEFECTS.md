# Current UI Baseline Defects

**Captured:** 2026-11-09, local working tree, Playwright 1.65.0 + Google Chrome headless.
**Artifacts:** [live screenshot set](baseline/live/) and [viewport/error metrics](baseline/live/baseline-metrics.json).
**Purpose:** pre-rebuild evidence, not a claim that the current UI is ready.

## What was actually exercised

The real `disha_core/frontend` HTML, CSS, and JavaScript were served on temporary loopback port 8765 and opened by Chrome. No registration, profile update, chat answer, or other write reached the persistent Postgres database. For authenticated screens the browser used a synthetic localStorage token and intercepted `/patient/profile`; the voice WebSocket was intercepted and microphone access used Chrome's fake media device.

The baseline includes sign-in, first onboarding screen, chat, meals, profile, settings, and 404 at all eight widths (320, 360, 390, 768, 1024, 1280, 1440, 1920) in light and dark themes. Onboarding's later form steps and validation-blocked states were captured at 320, 768, 1440, and 1920 in both themes. The voice attempt was captured at 360 and 1440 in both themes; the modal did not open at 360 light but did open at 360 dark and at 1440 in both themes. Mocked meal loading, profile failure, session expiry, chat request failure, and offline screens were captured at 390 light only.

This does not cover every requested state at every width. The browser used a static frontend server, not a running API; the voice path did not reach STT/TTS or a real call server. The mobile viewport was emulated; no operating-system keyboard was shown. No axe or measured contrast audit was run.

## Reproduced defects

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| B-01 | P1 | **Frontend startup throws `updateBmi is not defined`.** It appears in the browser page-error log for sign-in and authenticated routes. This checkout had removed the function while a caller/export still referenced it. | [sign-in, 320 light](baseline/live/signin_320_light.png); [metrics and console errors](baseline/live/baseline-metrics.json) |
| B-02 | P1 | **Authenticated startup hits a temporal-dead-zone error: `Cannot access 'views' before initialization`.** It reproduced on all 16 authenticated chat viewport/theme combinations. | [chat, 320 light](baseline/live/chat_320_light.png); [metrics and console errors](baseline/live/baseline-metrics.json) |
| B-03 | P1 | **Signup says age is optional but cannot continue without it.** With only a name entered, Continue stays on Basics and displays “Please enter a valid age”. After age and gender, the next step similarly blocks without height and weight, despite their optional labels. | [blocked at age, 320 light](baseline/live/onboarding_requires_basics_320_light.png); [blocked at measurements, 320 light](baseline/live/onboarding_requires_measurements_320_light.png) |
| B-04 | P1 | **Voice can open without a consent screen.** The call overlay opened after the Voice Call action in the fake-media browser, and no consent or AI/data-use disclosure appeared. The referenced consent element is absent from the page. | [voice attempt, 1440 light](baseline/live/voice_attempt_1440_light.png); [voice attempt, 360 dark](baseline/live/voice_attempt_360_dark.png) |
| B-05 | P1 | **Mobile header content is clipped outside the viewport.** At widths 320–390, the nav, theme button, and signed-in profile/actions extend beyond the right edge. The app clips this content while document `scrollWidth` remains equal to the viewport, so there is no horizontal scrollbar to reveal it. | [chat, 320 light](baseline/live/chat_320_light.png); [profile, 390 light](baseline/live/profile_390_light.png); per-element bounds in [metrics](baseline/live/baseline-metrics.json) |
| B-06 | P1 | **Voice controls are too low and partially clipped on a narrow screen.** The 360px call overlay screenshot cuts off the bottom action row, including the primary end-call control. | [voice attempt, 360 dark](baseline/live/voice_attempt_360_dark.png) |
| B-07 | P1 | **Profile/API failure is presented as “No approved plan available”.** A mocked 503 and a mocked expired-session 401 both show the same empty meal state as a successful profile with no plan. There is no retry or sign-in recovery action. The delayed response also shows no distinct loading treatment. | [503 state](baseline/live/meal_profile_error_390_light.png); [401 state](baseline/live/meal_profile_expired_390_light.png); [delayed state](baseline/live/meal_profile_delay_390_light.png) |
| B-08 | P1 | **Failed chat request loses the composer text and has no retry control.** The text appears as a sent user bubble, then “Service unavailable” appears; the input is empty. The request was intercepted and aborted before reaching a backend. | [chat request error, 390 light](baseline/live/chat_request_error_390_light.png) |
| B-09 | P1 | **Offline state has no visible indicator.** After loading the chat shell and setting the browser offline, the screenshot is visually indistinguishable from the connected empty chat. No offline queue or save-state message was exercised. | [chat offline, 390 light](baseline/live/chat_offline_390_light.png) |
| B-10 | P2 | **Many tap targets are smaller than 44px.** The automated bounds scan found sub-44px controls across the captured routes: examples include a 28×36px theme control, 36×36px send button, 20×29px close control, and 33px-high composer input. This scan reports geometry only, not a complete WCAG audit. | [chat, 320 light](baseline/live/chat_320_light.png); exact visible target measurements in [metrics](baseline/live/baseline-metrics.json) |
| B-11 | P2 | **Chat starts with a large unused vertical gap on phone-sized screens.** At 320–390px, the chat header and composer sit in the lower part of the viewport, leaving roughly a quarter of the screen blank above the conversation. | [chat, 320 light](baseline/live/chat_320_light.png); [chat, 390 light](baseline/live/chat_390_light.png) |
| B-12 | P2 | **No first-visit landing or in-chat onboarding flow is present.** The first visit opens the account form. The captured signup is a three-screen form; it does not offer the requested one-question chat/voice stage experience or an onboarding resume cursor. | [sign-in, 320 light](baseline/live/signin_320_light.png); [onboarding basics, 320 light](baseline/live/onboarding_basics_320_light.png) |
| B-13 | P2 | **Voice UI does not have a verified end-to-end call path in this baseline.** The modal screenshot used fake microphone media and an intercepted WebSocket; STT/TTS, real captions, reconnect, and actual channel continuity remain unverified. The visible subtitle stays at its initial “Listening… speak naturally.” text in the capture. | [voice attempt, 1440 light](baseline/live/voice_attempt_1440_light.png) |

## Geometry and console summary

- 153 screenshots were created in the primary matrix; three additional meal-state screenshots capture loading, 503, and 401 responses.
- 160 metric rows were written during the primary capture. The document itself reported no horizontal scroll, but 57 rows contained visible elements whose bounding boxes extended outside the viewport. Those are clipped elements, not a claim that all 57 views have document overflow.
- Sub-44px interactive elements were detected in 153 metric rows; the list includes controls that are below the target and should be reviewed in the redesign.
- 48 browser page errors were recorded: 32 `updateBmi is not defined` and 16 `Cannot access 'views' before initialization`. One console 404 was also recorded; its request URL was not collected, so its source is unknown.
- The profile, voice, chat-error, and offline responses were intercepted test fixtures. They are useful for UI state behavior only and do not prove API or database behavior.

## Not verified

- Full onboarding completion via chat or voice, cross-channel resume, and actual PEP database writes.
- Live STT/TTS, a real WebSocket session, microphone denial on a user device, iOS keyboard behavior, or Cloudflare ingress.
- Contrast ratios, screen-reader behavior, keyboard-only traversal, and axe checks.
- The requested offline queue, session-expiry redirect, and language behavior in English, Hindi, and Hinglish.
- Voice call layout at all eight widths and all themes; only 360px and 1440px were attempted.
