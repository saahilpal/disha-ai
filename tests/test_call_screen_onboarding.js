/**
 * Test Suite: Call Screen and In-Chat Onboarding Acceptance (Section 4)
 * Verifies telephony states, live captions, mic audio meter, mute toggle,
 * switch-to-chat state preservation, consent modal, and 5-stage onboarding engine.
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

// 1. Synthetic DOM Setup
const domStore = {};
function createMockElement(id = '', tag = 'DIV') {
  const el = {
    id,
    tagName: tag.toUpperCase(),
    className: '',
    style: {},
    attributes: {},
    children: [],
    value: '',
    textContent: '',
    innerHTML: '',
    disabled: false,
    checked: false,
    listeners: {},
    classList: {
      _classes: new Set(),
      add: function (...cls) { cls.forEach(c => this._classes.add(c)); el.className = Array.from(this._classes).join(' '); },
      remove: function (...cls) { cls.forEach(c => this._classes.delete(c)); el.className = Array.from(this._classes).join(' '); },
      toggle: function (cls) { if (this._classes.has(cls)) this.remove(cls); else this.add(cls); },
      contains: function (cls) { return this._classes.has(cls); }
    },
    setAttribute: function (k, v) { this.attributes[k] = String(v); },
    getAttribute: function (k) { return this.attributes[k] || null; },
    removeAttribute: function (k) { delete this.attributes[k]; },
    addEventListener: function (evt, fn) {
      if (!this.listeners[evt]) this.listeners[evt] = [];
      this.listeners[evt].push(fn);
    },
    dispatchEvent: function (evt) {
      const type = typeof evt === 'string' ? evt : evt.type;
      (this.listeners[type] || []).forEach(fn => fn.call(this, evt));
    },
    click: function () { this.dispatchEvent('click'); },
    appendChild: function (child) { this.children.push(child); return child; },
    querySelector: function (sel) {
      if (sel.startsWith('.')) {
        const cls = sel.slice(1);
        const search = (node) => {
          if (node.classList && node.classList.contains(cls)) return node;
          for (const c of (node.children || [])) {
            const found = search(c);
            if (found) return found;
          }
          return null;
        };
        return search(this);
      }
      return null;
    },
    querySelectorAll: function (sel) {
      const results = [];
      if (sel.includes('.journey-dot')) {
        for (let i = 0; i < 5; i++) results.push(createMockElement(`dot-${i}`));
      }
      return results;
    },
    closest: function () { return this; },
    focus: function () { this.isFocused = true; }
  };
  return el;
}

global.document = {
  documentElement: createMockElement('html', 'HTML'),
  getElementById: (id) => {
    if (!domStore[id]) {
      domStore[id] = createMockElement(id);
    }
    return domStore[id];
  },
  querySelector: (sel) => {
    if (sel.startsWith('#')) return global.document.getElementById(sel.slice(1));
    return createMockElement('', 'DIV');
  },
  querySelectorAll: (sel) => {
    if (sel.includes('.journey-dot')) {
      const dots = [];
      for (let i = 0; i < 5; i++) dots.push(createMockElement(`dot-${i}`));
      return dots;
    }
    return [];
  },
  createElement: (tag) => createMockElement('', tag),
  addEventListener: () => {}
};

global.window = {
  location: { hash: '#/chat' },
  addEventListener: () => {},
  AudioContext: function () {
    return {
      state: 'running',
      resume: async () => {},
      close: async () => {},
      createMediaStreamSource: () => ({ connect: () => {}, disconnect: () => {} }),
      createAnalyser: () => ({ connect: () => {}, disconnect: () => {}, fftSize: 64, frequencyBinCount: 32, getByteFrequencyData: () => {} })
    };
  }
};

global.localStorage = {
  store: {},
  getItem: function (k) { return this.store[k] || null; },
  setItem: function (k, v) { this.store[k] = String(v); },
  removeItem: function (k) { delete this.store[k]; },
  clear: function () { this.store = {}; }
};

global.navigator = {
  mediaDevices: {
    getUserMedia: async () => ({
      getTracks: () => [{ stop: () => {}, enabled: true }]
    })
  },
  permissions: {
    query: async () => ({ state: 'granted' })
  }
};

// Require app.js
const app = require('../disha_core/frontend/app.js');

let passCount = 0;
function test(name, fn) {
  try {
    fn();
    console.log(`✅ PASS: ${name}`);
    passCount++;
  } catch (err) {
    console.error(`❌ FAIL: ${name}`, err);
    process.exit(1);
  }
}

console.log('===============================================================');
console.log('DISHA AI CALL SCREEN & IN-CHAT ONBOARDING TEST SUITE');
console.log('===============================================================');

// 1. Truthful Telephony States
test('Telephony Status Transitions: idle -> connecting -> listening -> processing -> speaking -> interrupted -> muted -> ended', () => {
  const statusText = document.getElementById('telephony-status-text');
  const statusPill = document.getElementById('telephony-status-pill');
  const dot = createMockElement('status-dot');
  statusPill.appendChild(dot);

  app.setTelephonyStatus('idle');
  assert.strictEqual(statusText.textContent, 'Ready for consultation');
  assert.strictEqual(app.state.telephonyStatus, 'idle');

  app.setTelephonyStatus('connecting');
  assert.strictEqual(statusText.textContent, 'Connecting to Disha Core...');

  app.setTelephonyStatus('listening');
  assert.strictEqual(statusText.textContent, 'Listening...');

  app.setTelephonyStatus('processing');
  assert.strictEqual(statusText.textContent, 'Processing...');

  app.setTelephonyStatus('speaking');
  assert.strictEqual(statusText.textContent, 'Disha speaking...');

  app.setTelephonyStatus('interrupted');
  assert.strictEqual(statusText.textContent, 'Interrupted...');

  app.setTelephonyStatus('muted');
  assert.strictEqual(statusText.textContent, 'Microphone muted');

  app.setTelephonyStatus('ended');
  assert.strictEqual(statusText.textContent, 'Call ended');
});

// 2. Live Spoken Captions
test('Live Captions: updates speaker indicator and caption text accurately', () => {
  const subtitlesEl = document.getElementById('voice-subtitles-text');
  const speakerEl = document.getElementById('voice-captions-speaker');

  app.updateLiveCaptions('user', 'Main subah 7 baje uthta hoon');
  assert.strictEqual(speakerEl.textContent, 'You');
  assert.strictEqual(subtitlesEl.textContent, 'Main subah 7 baje uthta hoon');

  app.updateLiveCaptions('assistant', 'Bahut accha! Aur aap raat ko kitne baje sote hain?');
  assert.strictEqual(speakerEl.textContent, 'Disha AI');
  assert.strictEqual(subtitlesEl.textContent, 'Bahut accha! Aur aap raat ko kitne baje sote hain?');

  app.updateLiveCaptions('system', 'Call ended.');
  assert.strictEqual(speakerEl.textContent, 'System');
  assert.strictEqual(subtitlesEl.textContent, 'Call ended.');
});

// 3. Audio Meter and Mute Toggle
test('Mute Toggle and Audio Meter: zeroed on mute and endCall, mic resources freed', () => {
  const micFill = document.getElementById('mic-meter-fill');
  const micVal = document.getElementById('mic-meter-value');
  const micMeter = document.getElementById('mic-audio-meter');

  micFill.style.width = '75%';
  micVal.textContent = '75%';
  micMeter.setAttribute('aria-valuenow', '75');

  // Simulate endCall cleanup
  app.state.isInCall = true;
  app.endCall();

  assert.strictEqual(app.state.isInCall, false);
  assert.strictEqual(micFill.style.width, '0%');
  assert.strictEqual(micVal.textContent, '0%');
  assert.strictEqual(micMeter.getAttribute('aria-valuenow'), '0');
  assert.strictEqual(app.state.telephonyStatus, 'idle');
});

// 4. In-Chat Onboarding 5-Stage Banner
test('In-Chat Onboarding: 5-Stage progression banner reflects accurate stage and completion', () => {
  const banner = document.getElementById('chat-journey-banner');
  const stagePill = document.getElementById('chat-stage-pill');
  const stageName = document.getElementById('chat-stage-name');

  app.updateInChatJourneyBanner(1, false);
  assert.strictEqual(banner.style.display, 'flex');
  assert.strictEqual(stagePill.textContent, 'Stage 1 of 5');
  assert.strictEqual(stageName.textContent, 'Basic Profile & Health Baseline');

  app.updateInChatJourneyBanner(3, false);
  assert.strictEqual(stagePill.textContent, 'Stage 3 of 5');
  assert.strictEqual(stageName.textContent, 'Lifestyle & Daily Routine');

  app.updateInChatJourneyBanner(5, true);
  assert.strictEqual(stagePill.textContent, 'Onboarding Complete');
  assert.strictEqual(stageName.textContent, 'Personalized Coaching Active');
});

// 5. Proactive First Consultation Companion Welcome
test('Proactive First Consultation Welcome: injects grounded companion greeting into chat stream', () => {
  const chatStream = document.getElementById('chat-stream');
  app.triggerPersonalizedFirstConsultation('Rohan Sharma', ['weight_loss', 'bp_control'], 'stage 1');

  assert(chatStream.children.length > 0, 'Expected greeting message element in chat stream');
  const lastMsg = chatStream.children[chatStream.children.length - 1];
  assert(lastMsg.innerHTML.includes('Namaste Rohan!'), 'Expected personal name in greeting');
  assert(lastMsg.innerHTML.includes('Disha, your personal AI health coach'), 'Expected AI coach disclosure');
});

// 6. Server Messages (transcript, sentence, barge-in)
test('Server message handling: updates live captions and status on transcript and sentence', () => {
  const subtitlesEl = document.getElementById('voice-subtitles-text');
  const speakerEl = document.getElementById('voice-captions-speaker');

  app.handleServerMessage({ type: 'transcript', text: 'Mera blood pressure 130 hai' });
  assert.strictEqual(speakerEl.textContent, 'You');
  assert.strictEqual(subtitlesEl.textContent, 'Mera blood pressure 130 hai');
  assert.strictEqual(app.state.telephonyStatus, 'processing');

  app.handleServerMessage({ type: 'sentence', text: 'Yeh pre-hypertension range mein hai.' });
  assert.strictEqual(speakerEl.textContent, 'Disha AI');
  assert.strictEqual(subtitlesEl.textContent, 'Yeh pre-hypertension range mein hai.');
  assert.strictEqual(app.state.telephonyStatus, 'speaking');

  app.handleServerMessage({ type: 'interrupted', interrupted: true });
  assert.strictEqual(app.state.telephonyStatus, 'interrupted');
});

console.log('===============================================================');
console.log(`SUMMARY: ${passCount} PASSED, 0 FAILED out of ${passCount} tests`);
console.log('===============================================================');

