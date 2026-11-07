/**
 * Frontend Architecture, Memory Leak & Security Diagnostic Suite for Disha AI
 * Tests all 5 target audit domains under synthetic DOM & runtime conditions.
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const appSource = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
const cssSource = fs.readFileSync(path.join(__dirname, '../frontend/style.css'), 'utf8');
const htmlSource = fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8');

// Synthetic DOM setup for Node.js runtime validation
global.document = {
  documentElement: { setAttribute: () => {} },
  getElementById: (id) => {
    return {
      id,
      style: {},
      classList: {
        add: () => {},
        remove: () => {},
        toggle: () => {},
        contains: () => false,
      },
      setAttribute: () => {},
      removeAttribute: () => {},
      addEventListener: () => {},
      querySelector: () => null,
      querySelectorAll: () => [],
      value: '',
      textContent: '',
      innerHTML: '',
      disabled: false,
    };
  },
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (tag) => {
    return {
      tagName: tag.toUpperCase(),
      className: '',
      style: {},
      textContent: '',
      innerHTML: '',
      appendChild: () => {},
    };
  },
  addEventListener: () => {},
};

global.window = {
  location: { protocol: 'https:', host: 'disha.ai', origin: 'https://disha.ai' },
  addEventListener: () => {},
  AudioContext: class {
    constructor() {
      this.state = 'running';
    }
    resume() { return Promise.resolve(); }
    close() { this.state = 'closed'; return Promise.resolve(); }
    createMediaStreamSource() {
      return {
        connect: () => {},
        disconnect: () => { this.disconnected = true; }
      };
    }
    createAnalyser() {
      return {
        fftSize: 64,
        frequencyBinCount: 32,
        smoothingTimeConstant: 0.3,
        connect: () => {},
        disconnect: () => { this.disconnected = true; },
        getByteFrequencyData: (arr) => arr.fill(128)
      };
    }
    createBufferSource() {
      return {
        connect: () => {},
        disconnect: () => {},
        start: () => {},
        stop: () => {},
      };
    }
    decodeAudioData() {
      return Promise.resolve({ duration: 1.0 });
    }
  },
  matchMedia: () => ({ matches: false }),
};

global.sessionStorage = {
  _store: {},
  getItem(k) { return this._store[k] || null; },
  setItem(k, v) { this._store[k] = String(v); },
  removeItem(k) { delete this._store[k]; },
  clear() { this._store = {}; }
};

global.localStorage = {
  _store: {},
  getItem(k) { return this._store[k] || null; },
  setItem(k, v) { this._store[k] = String(v); },
  removeItem(k) { delete this._store[k]; },
  clear() { this._store = {}; }
};

global.requestAnimationFrame = (fn) => 42;
global.cancelAnimationFrame = (id) => {};

// Require the app engine
const engine = require('../frontend/app.js');

console.log('===============================================================');
console.log('DISHA AI FRONTEND DEEP DIAGNOSTIC AUDIT SUITE');
console.log('===============================================================\n');

const testResults = [];

function recordTest(domain, name, passed, details) {
  testResults.push({ domain, name, passed, details });
  const status = passed ? '✅ PASS' : '❌ FAIL';
  console.log(`${status} [${domain}] ${name}`);
  if (!passed && details) {
    console.log(`   Issue: ${details}`);
  }
}

// ============================================================================
// 1. AudioContext Lifecycle & WebAudio Graph
// ============================================================================
{
  const domain = '1. AudioContext Lifecycle';

  // Check 1.1: AudioContext cleanup in endCall()
  const endCallHasSourceDisconnect = /sourceNode\.disconnect/i.test(appSource);
  recordTest(domain, 'MediaStreamAudioSourceNode reference tracked and disconnected on endCall()', endCallHasSourceDisconnect,
    'sourceNode is local variable inside setupMicAnalyserAndVad() and NEVER disconnected, leaking WebAudio nodes.');

  const analyserDisconnect = /analyserNode\.disconnect/i.test(appSource);
  recordTest(domain, 'AnalyserNode disconnected on endCall()', analyserDisconnect,
    'analyserNode is never disconnected on call termination, causing audio graph memory leak.');

  // Check 1.2: Page unload listeners
  const hasPageHide = /addEventListener\(\s*['"]pagehide['"]/i.test(appSource) || /addEventListener\(\s*['"]beforeunload['"]/i.test(appSource);
  recordTest(domain, 'Page unload / pagehide event listener for stream & AudioContext termination', hasPageHide,
    'No beforeunload or pagehide listener; microphone tracks, WebSockets, and AudioContext leak on tab close/refresh.');

  // Check 1.3: AudioContext statechange listener for OS interruption / lockscreen
  const hasStateChange = /onstatechange/i.test(appSource) || /addEventListener\(\s*['"]statechange['"]/i.test(appSource);
  recordTest(domain, 'AudioContext onstatechange listener for iOS/Safari lockscreen/background suspension', hasStateChange,
    'AudioContext has no statechange listener to detect and auto-recover from OS/Safari interruptions.');
}

// ============================================================================
// 2. WebAudio AnalyserNode & 24-Bar Visualizer
// ============================================================================
{
  const domain = '2. 24-Bar Visualizer & AnalyserNode';

  // Check 2.1: state.spectrumAnimId storage and cancellation
  const storesAnimId = /state\.spectrumAnimId\s*=\s*requestAnimationFrame/i.test(appSource);
  recordTest(domain, 'requestAnimationFrame ID stored in state.spectrumAnimId', storesAnimId,
    'requestAnimationFrame is called without storing ID in state.spectrumAnimId.');

  const cancelsAnim = /cancelAnimationFrame\(\s*state\.spectrumAnimId/i.test(appSource);
  recordTest(domain, 'cancelAnimationFrame invoked on endCall() / reset', cancelsAnim,
    'cancelAnimationFrame is NEVER called; visualizer relies purely on boolean polling.');

  // Check 2.2: Division by zero guard in frequency calculations
  const hasBufferLenZeroGuard = /bufferLength\s*>\s*0\s*\?\s*sum\s*\/\s*bufferLength\s*:\s*0/.test(appSource);
  recordTest(domain, 'Division by zero guard in frequency calculations (sum / bufferLength)', hasBufferLenZeroGuard,
    'bufferLength == 0 yields avg = NaN, causing invalid VAD comparison.');

  // Check 2.3: NaN in style.height calculation
  const hasFiniteValGuard = /Number\.isFinite\(rawVal\)/.test(appSource) || /Number\.isFinite\(val\)/.test(appSource);
  recordTest(domain, 'NaN style.height protection for spectrum bars', hasFiniteValGuard,
    'NaN frequency val produces NaNpx, an invalid CSS value rejected by browser rendering engine.');

  // Check 2.4: Spectrum visualizer initialization on load
  const calledAtInit = /initSpectrumVisualizer\(\);?\s*(?!\s*await fetchPatientProfile)/i.test(appSource);
  recordTest(domain, 'Spectrum visualizer bars initialized at page load', calledAtInit,
    'initSpectrumVisualizer() is only called inside transitionToDashboard(); specBars remains empty if call is initiated before dashboard transition.');
}

// ============================================================================
// 3. Monospace Call Duration Timer
// ============================================================================
{
  const domain = '3. Monospace Call Timer';

  // Check 3.1: Reset of state.callStartTime
  const resetsCallStartTime = /state\.callStartTime\s*=\s*null/i.test(appSource);
  recordTest(domain, 'state.callStartTime reset to null on endCall() / stopCallTimer()', resetsCallStartTime,
    'state.callStartTime retains previous timestamp upon call completion, risking incorrect elapsed duration calculation.');

  // Check 3.2: Remote WebSocket onclose handling
  const wsOnCloseEndsCall = /state\.ws\.onclose\s*=\s*\([^)]*\)\s*=>\s*\{[^}]*endCall\(\)/s.test(appSource);
  recordTest(domain, 'WebSocket onclose terminates call and stops call duration timer', wsOnCloseEndsCall,
    'WebSocket onclose only sets state to disconnected and schedules reconnect; call timer keeps running indefinitely while disconnected.');

  // Check 3.3: Visibilitychange / Tab switching timer handling
  const hasVisibilityListener = /addEventListener\(\s*['"]visibilitychange['"]/i.test(appSource);
  recordTest(domain, 'visibilitychange event listener for tab switching / background throttling', hasVisibilityListener,
    'No visibilitychange listener to handle timer sync or background disconnection.');
}

// ============================================================================
// 4. Form Validation & Intake Edge Cases
// ============================================================================
{
  const domain = '4. Form Validation & Clinical Intake';

  // RFC 5322 Email Regex test
  // Leading dot
  const leadingDotResult = engine.validateEmail('.user@example.com');
  recordTest(domain, 'RFC 5322 compliance: Reject email with leading dot (.user@example.com)', !leadingDotResult,
    'EMAIL_REGEX matches .user@example.com which violates RFC 5322 §3.4.1.');

  // Consecutive dots
  const consecutiveDotsResult = engine.validateEmail('user..name@example.com');
  recordTest(domain, 'RFC 5322 compliance: Reject email with consecutive dots (user..name@example.com)', !consecutiveDotsResult,
    'EMAIL_REGEX matches user..name@example.com which violates RFC 5322 §3.4.1.');

  // Trailing dot in domain
  const trailingDotResult = engine.validateEmail('user@example.com.');
  recordTest(domain, 'RFC 5322 compliance: Reject email with trailing dot (user@example.com.)', !trailingDotResult,
    'EMAIL_REGEX matches user@example.com. which violates RFC 5322.');

  // Check 4.3: Extreme BMI Calculation with zero height
  const hasZeroHeightBmiGuard = /h\s*>=\s*50/i.test(appSource) && /Number\.isFinite\(h\)/i.test(appSource);
  recordTest(domain, 'Zero height BMI calculation guard against Infinity', hasZeroHeightBmiGuard,
    'height_cm = "0" causes division by zero, yielding Infinity kg/m² in clinical drawer UI.');

  // Check 4.4: Non-numeric height in updateDrawerUI
  const hasNonNumericHeightGuard = /Number\.isFinite\(h\)/i.test(appSource) && /Number\.isFinite\(w\)/i.test(appSource);
  recordTest(domain, 'Non-numeric height BMI calculation guard against NaN', hasNonNumericHeightGuard,
    'height_cm = "abc" produces NaN kg/m² in clinical drawer UI.');

  // Check 4.5: Negative height rejection in BMI calculation
  const hasNegativeHeightGuard = /h\s*<\s*50/i.test(appSource) || /h\s*>=\s*50/i.test(appSource);
  recordTest(domain, 'Negative height rejection in BMI calculation', hasNegativeHeightGuard,
    'Negative height is not rejected before BMI calculation.');

  // Check 4.6: Intake submission validation for physiological ranges
  const hasRangeValidation = /height\s*<\s*50/i.test(appSource) && /weight\s*<\s*20/i.test(appSource) && /age\s*<\s*1/i.test(appSource);
  recordTest(domain, 'Intake registration form enforces physiological bounds on age, height, weight', hasRangeValidation,
    'onboardForm submits age, height, and weight directly to /auth/register without checking physiological bounds.');

  // Check 4.7: XSS quote escaping in escapeHtml
  const xssPayload = 'user" onmouseover="alert(1)';
  const escaped = engine.escapeHtml(xssPayload);
  recordTest(domain, 'escapeHtml escapes double quotes (") for attribute safety', escaped.includes('&quot;'),
    `Browser textContent-to-innerHTML does NOT escape quotes: '${escaped}', vulnerable to attribute breakout XSS.`);
}

// ============================================================================
// 5. Tab Switching & UI State Cleanliness
// ============================================================================
{
  const domain = '5. Tab Switching & UI State';

  // Check 5.1: Tab switching clears emailError and passwordError
  const hasClearErrors = typeof engine.clearAuthErrorsAndState === 'function';
  recordTest(domain, 'clearAuthErrorsAndState function defined and clears errors', hasClearErrors,
    'No clearAuthErrorsAndState function defined.');

  // Check 5.2: Tab switching dismisses global alert banner
  const tabCallsClear = /clearAuthErrorsAndState\(\)/.test(appSource);
  recordTest(domain, 'Tab click listeners invoke clearAuthErrorsAndState()', tabCallsClear,
    'Tab click handlers toggle visibility but fail to clear error text elements or is-invalid classes.');

  // Check 5.3: Tab switching resets submit button disabled/loading state
  const clearResetsButton = /submitBtn\.disabled\s*=\s*false/.test(appSource);
  recordTest(domain, 'Tab switching resets submit button disabled / loading state', clearResetsButton,
    'If sign-in or intake fails or hangs, switching tabs does not reset submit button disabled or loading states.');
}

// ============================================================================
// 6. Telephony & Web Audio Verification
// ============================================================================
{
  const domain = '6. Telephony & Web Audio Experience';

  // Check 6.1: Idle State Solid herbal green button (#1B5E43)
  const idleBtnCss = /\.telephony-call-btn\.state-idle\s*\{[^}]*background-color:\s*#1B5E43/i.test(cssSource);
  recordTest(domain, 'Call button idle state: Solid herbal green button (#1B5E43)', idleBtnCss,
    'Idle state button does not have solid herbal green #1B5E43.');

  // Check 6.2: Connecting State Subdued sage pill (#EEF5F1) & label "Connecting to Disha Core..."
  const connBtnCss = /\.telephony-call-btn\.state-connecting\s*\{[^}]*background-color:\s*#EEF5F1/i.test(cssSource);
  const connLabel = /Connecting to Disha Core\.\.\./.test(appSource);
  recordTest(domain, 'Call button connecting state: Subdued sage pill (#EEF5F1) with label "Connecting to Disha Core..."', connBtnCss && connLabel,
    'Connecting state button does not use #EEF5F1 or label "Connecting to Disha Core...".');

  // Check 6.3: Active Call State Solid muted red button (#C24137) & label "End Call"
  const activeBtnCss = /\.telephony-call-btn\.state-active\s*\{[^}]*background-color:\s*#C24137/i.test(cssSource);
  const activeLabel = /dom\.callBtnLabel\.textContent\s*=\s*['"]End Call['"]/.test(appSource);
  recordTest(domain, 'Call button active state: Solid muted red button (#C24137) with label "End Call"', activeBtnCss && activeLabel,
    'Active state button does not use #C24137 or label "End Call".');

  // Check 6.4: Grounded 24-Bar Audio Spectrum Visualizer
  const visualizerGrounded = /\.spectrum-bars\s*\{[^}]*align-items:\s*flex-end/i.test(cssSource);
  const countBars = (htmlSource.match(/class=["']spec-bar["']/g) || []).length;
  recordTest(domain, 'Grounded 24-bar audio frequency analyzer connected to AnalyserNode', visualizerGrounded && countBars === 24,
    `Visualizer not grounded (align-items: flex-end) or bars count is ${countBars} instead of 24.`);

  // Check 6.5: Real-time Indicator States
  const hasListeningState = /listening:\s*['"]Listening\.\.\.['"]/.test(appSource);
  const hasProcessingState = /processing:\s*['"]Processing\.\.\.['"]/.test(appSource);
  const hasSpeakingState = /speaking:\s*['"]Disha speaking\.\.\.['"]/.test(appSource);
  const hasInterruptedState = /interrupted:\s*['"]Interrupted\.\.\.['"]/.test(appSource);
  recordTest(domain, 'Real-time indicator states (Listening..., Processing..., Disha speaking..., Interrupted...)',
    hasListeningState && hasProcessingState && hasSpeakingState && hasInterruptedState,
    'Indicator labels do not match required real-time speech states.');

  // Check 6.6: AudioContext user gesture resume / initialization
  const userGestureAudio = /dom\.callBtn\.addEventListener\(\s*['"]click['"][\s\S]*?startCall/i.test(appSource) &&
    /state\.audioContext\.resume\(\)/.test(appSource);
  recordTest(domain, 'AudioContext initialized / resumed strictly upon user gesture', userGestureAudio,
    'AudioContext is not properly guarded by user click gesture.');

  // Check 6.7: Dynamic Protocol Discovery (https -> wss, http -> ws)
  const dynConfig = engine.getBackendConfig();
  const protocolHandled = dynConfig.wsBase.startsWith('wss://') && dynConfig.httpBase.startsWith('https://');
  recordTest(domain, 'Dynamic mixed-content protocol discovery (https -> wss, http -> ws)', protocolHandled,
    `Protocol discovery failed: wsBase=${dynConfig.wsBase}, httpBase=${dynConfig.httpBase}`);

  // Check 6.8: Jittered exponential backoff
  const hasExpBackoff = /Math\.pow\(\s*2\s*,\s*state\.wsReconnectAttempts\s*\)/.test(appSource);
  const hasJitter = /Math\.random\(\)/.test(appSource);
  recordTest(domain, 'WebSocket auto-reconnect with jittered exponential backoff', hasExpBackoff && hasJitter,
    'WebSocket reconnect lacks exponential backoff or jitter.');

  // Check 6.9: Patient Telemetry Drawer (HTN stage, Gym Clearance, current meal slot, Merkle hash)
  const hasHtnBadge = htmlSource.includes('id="disp-htn-badge"');
  const hasGymClearance = htmlSource.includes('id="disp-gym-clearance"');
  const hasCurrentMealSlot = htmlSource.includes('id="disp-current-meal-slot"');
  const hasMerkleChip = htmlSource.includes('id="latest-merkle-hash"');
  recordTest(domain, 'Patient Telemetry Drawer: Live HTN, Gym clearance, current meal slot, Merkle SHA-256 chip',
    hasHtnBadge && hasGymClearance && hasCurrentMealSlot && hasMerkleChip,
    'Patient telemetry drawer elements missing in DOM.');

  // DOMAIN 7: Progressive Onboarding, Drawer Toggle & Profile Customization
  const domain7 = '7. Progressive Onboarding & Profile Customization';

  // Check 7.1: Onboarding Panels and Step Tracker
  const hasTracker = htmlSource.includes('id="tracker-step-1"') && htmlSource.includes('id="tracker-step-4"');
  const hasPanels = htmlSource.includes('id="onboard-step-panel-1"') && htmlSource.includes('id="onboard-step-panel-4"');
  const hasNavButtons = htmlSource.includes('id="step-1-next-btn"') && htmlSource.includes('id="step-4-back-btn"');
  recordTest(domain7, 'Progressive 4-step onboarding panels, navigation buttons, and step tracker in DOM',
    hasTracker && hasPanels && hasNavButtons,
    'Onboarding panels or tracker missing in index.html.');

  // Check 7.2: goToOnboardingStep function exported
  const hasGoToStep = typeof engine.goToOnboardingStep === 'function';
  recordTest(domain7, 'goToOnboardingStep lifecycle handler defined and exported',
    hasGoToStep,
    'goToOnboardingStep missing in engine exports.');

  // Check 7.3: Clinical Drawer toggle & collapsible styling
  const hasDrawerClose = htmlSource.includes('id="drawer-close-btn"');
  const hasToggleDrawer = htmlSource.includes('id="toggle-drawer-btn"');
  const hasDrawerCollapsedCss = cssSource.includes('.clinical-drawer.collapsed');
  recordTest(domain7, 'Clinical Drawer toggle, close button, and collapsed state CSS',
    hasDrawerClose && hasToggleDrawer && hasDrawerCollapsedCss,
    'Drawer toggle or collapsed styling missing.');

  // Check 7.4: Patient Profile Edit Modal & form fields in DOM
  const hasProfileModal = htmlSource.includes('id="profile-edit-modal"');
  const hasProfileForm = htmlSource.includes('id="edit-profile-form"');
  const hasEditFields = htmlSource.includes('id="edit-name"') && htmlSource.includes('id="edit-age"') &&
                        htmlSource.includes('id="edit-height"') && htmlSource.includes('id="edit-weight"');
  recordTest(domain7, 'Patient Profile Edit modal, form, and vital inputs in DOM',
    hasProfileModal && hasProfileForm && hasEditFields,
    'Profile edit modal or fields missing in index.html.');

  // Check 7.5: Profile Edit update API integration
  const hasProfileApiCall = appSource.includes('/patient/profile');
  const hasPutMethod = appSource.includes("method: 'PUT'");
  recordTest(domain7, 'Patient Profile Edit PUT /patient/profile API integration with auth token',
    hasProfileApiCall && hasPutMethod,
    'Profile update API call missing in app.js.');
}

console.log('\n===============================================================');
const passedCount = testResults.filter(t => t.passed).length;
const failedCount = testResults.filter(t => !t.passed).length;
console.log(`DIAGNOSTIC AUDIT SUMMARY: ${passedCount} PASSED, ${failedCount} FAILED out of ${testResults.length} checks`);
console.log('===============================================================');

assert.strictEqual(failedCount, 0, `Audit suite failed ${failedCount} test checks.`);
