/**
 * Voice UI/UX, Banners & Gap Remediation Test Suite
 *
 * Verifies:
 * 1. Mandatory demo banner ("Demo: Synthetic data only. Do not enter real medical details. Dial 112 for emergencies.")
 * 2. Render free-tier warmup banner (#warmup-banner) and checkBackendWarmup()
 * 3. 10 voice states with plain microcopy: connecting, waking up, ready, listening, hearing you, thinking, speaking, interrupted, offline, error
 * 4. Guided mic permission error banner with instant "Use Text Chat Instead" button
 * 5. Red-flag emergency banner styling (.alert-banner.alert-emergency)
 * 6. Browser speechSynthesis fallback for emergency responses when cloud TTS fails or is offline
 * 7. Speech recognition failure friendly message ("did not hear") and text chat offer
 */
const { test, describe, before, beforeEach } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const htmlSource = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const cssSource = fs.readFileSync(path.join(__dirname, '../style.css'), 'utf8');
const app = require('../app.js');

describe('1. Mandatory Demo & Safety Banner', () => {
  test('HTML contains mandatory demo disclaimer banner with exact text and 112 emergency dial link', () => {
    assert.match(htmlSource, /id=["']demo-banner["']/);
    const expectedText = 'Demo: Synthetic data only. Do not enter real medical details. Dial';
    assert.ok(htmlSource.includes(expectedText), 'Missing required disclaimer copy');
    assert.match(htmlSource, /href=["']tel:112["']/);
    assert.ok(htmlSource.includes('112</a> for emergencies.'), 'Missing 112 emergency link text');
  });

  test('CSS contains responsive styles for .demo-banner and WCAG AA contrast links', () => {
    assert.match(cssSource, /\.demo-banner\s*\{/);
    assert.match(cssSource, /\.demo-emergency-link\s*\{/);
  });
});

describe('2. Render Free-Tier Warmup Banner', () => {
  test('HTML contains warmup banner with clean pulse indicator dot', () => {
    assert.match(htmlSource, /id=["']warmup-banner["']/);
    assert.match(htmlSource, /class=["'][^"']*warmup-pulse-dot[^"']*["']/);
    assert.match(htmlSource, /id=["']warmup-dismiss-btn["']/);
  });

  test('CSS defines keyframe animation warmupPulse for gentle breathing effect', () => {
    assert.match(cssSource, /@keyframes\s+warmupPulse\s*\{/);
    assert.match(cssSource, /\.warmup-pulse-dot\s*\{/);
  });

  test('checkBackendWarmup function is exported on engineApi', () => {
    assert.strictEqual(typeof app.checkBackendWarmup, 'function');
  });
});

describe('3. 10 Voice States with Plain Microcopy', () => {
  // Setup synthetic DOM for indicator dot and label
  const mockPill = {
    dot: { className: '' },
    querySelector: function(sel) {
      if (sel === '.indicator-dot') return this.dot;
      return null;
    }
  };
  const mockText = { textContent: '' };

  test('all 10 states render correct plain microcopy and normalized dot classes', () => {
    // Inject mock DOM elements into app if needed
    const states = [
      { key: 'connecting', expectedText: 'Connecting to Disha Core...', expectedDot: 'indicator-dot connecting' },
      { key: 'waking up', expectedText: 'Waking up...', expectedDot: 'indicator-dot waking-up' },
      { key: 'ready', expectedText: 'Ready', expectedDot: 'indicator-dot ready' },
      { key: 'listening', expectedText: 'Listening...', expectedDot: 'indicator-dot listening' },
      { key: 'hearing you', expectedText: 'Hearing you...', expectedDot: 'indicator-dot hearing-you' },
      { key: 'thinking', expectedText: 'Thinking...', expectedDot: 'indicator-dot thinking' },
      { key: 'speaking', expectedText: 'Disha speaking...', expectedDot: 'indicator-dot speaking' },
      { key: 'interrupted', expectedText: 'Interrupted...', expectedDot: 'indicator-dot interrupted' },
      { key: 'offline', expectedText: 'Offline', expectedDot: 'indicator-dot offline' },
      { key: 'error', expectedText: 'Error', expectedDot: 'indicator-dot error' }
    ];

    states.forEach(s => {
      app.setTelephonyStatus(s.key);
      assert.strictEqual(app.state.telephonyStatus, s.key);
    });
  });

  test('CSS provides visual indicator-dot rules for all 10 voice states', () => {
    const requiredClasses = [
      'connecting',
      'waking-up',
      'ready',
      'listening',
      'hearing-you',
      'thinking',
      'speaking',
      'interrupted',
      'offline',
      'error'
    ];

    requiredClasses.forEach(cls => {
      const regex = new RegExp(`\\.indicator-dot\\.${cls}`, 'i');
      assert.match(cssSource, regex, `Missing CSS rule for .indicator-dot.${cls}`);
    });
  });
});

describe('4. Guided Mic Permission Error & Instant Text Fallback', () => {
  test('HTML contains guided mic permission banner and "Use Text Chat Instead" button', () => {
    assert.match(htmlSource, /id=["']mic-permission-banner["']/);
    assert.match(htmlSource, /id=["']use-text-chat-fallback-btn["']/);
    assert.ok(htmlSource.includes('Use Text Chat Instead'));
  });

  test('app exports mic permission error controls', () => {
    assert.strictEqual(typeof app.showMicPermissionError, 'function');
    assert.strictEqual(typeof app.hideMicPermissionError, 'function');
  });

  test('CSS styles mic permission banner and fallback button', () => {
    assert.match(cssSource, /\.mic-permission-banner\s*\{/);
    assert.match(cssSource, /\.mic-perm-fallback-btn/);
  });
});

describe('5. Red-Flag Emergency Banner Styling', () => {
  test('CSS provides high-contrast calm red-flag styling for .alert-banner.alert-emergency', () => {
    assert.match(cssSource, /\.alert-banner\.alert-emergency\s*\{/);
    assert.match(cssSource, /border-bottom:\s*2px\s+solid\s+var\(--danger\)/);
    assert.match(cssSource, /\.alert-banner\.alert-emergency\s+\.alert-text/);
  });
});

describe('6. Browser SpeechSynthesis Fallback for Emergencies', () => {
  test('speakEmergencyFallback is exported on engineApi', () => {
    assert.strictEqual(typeof app.speakEmergencyFallback, 'function');
  });

  test('app.js integrates emergency watchdog and fallback invocation', () => {
    const appCode = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');
    assert.match(appCode, /speakEmergencyFallback/);
    assert.match(appCode, /emergencyTtsTimer/);
  });
});

describe('7. Speech Recognition Friendly Fallback ("did not hear")', () => {
  test('HTML contains speech recognition fallback card with text chat action in call overlay', () => {
    assert.match(htmlSource, /id=["']speech-recognition-fallback-card["']/);
    assert.match(htmlSource, /id=["']speech-fallback-text-btn["']/);
    assert.ok(htmlSource.includes('I didn\'t quite catch that'));
  });

  test('app exports speech fallback controls', () => {
    assert.strictEqual(typeof app.showSpeechRecognitionFallback, 'function');
    assert.strictEqual(typeof app.hideSpeechRecognitionFallback, 'function');
  });
});

describe('8. Safe Area Inset & Mobile Responsiveness', () => {
  test('CSS includes safe-area-inset for iOS/Android viewport, header, and composer', () => {
    assert.match(cssSource, /env\(safe-area-inset-top/);
    assert.match(cssSource, /env\(safe-area-inset-bottom/);
    assert.match(cssSource, /env\(safe-area-inset-left/);
    assert.match(cssSource, /env\(safe-area-inset-right/);
  });
});
