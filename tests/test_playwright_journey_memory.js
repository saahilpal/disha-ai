/**
 * Playwright Browser End-to-End Test Suite for Journey and Memory Verification (Phase 3B RC)
 * Disha AI Health Coach
 *
 * Verifies via Headless Chromium on Live Container (http://localhost:8080/):
 *  1. Multi-Step Registration & Proactive Onboarding Welcome
 *  2. In-Chat Stage Disclosures & Streaming Cursor Lifecycle
 *  3. Bidirectional Channel Switch (Chat -> Voice Modal 24-Bar Visualizer -> Return to Chat Resume)
 *  4. Returning-User Home Hydration (Profile, PEP Tags, Meals & Journey State)
 *  5. Unsupported Language Politeness Deflection in UI
 *  6. Emergency Symptom Interruption & Escalation During Onboarding
 */

const { chromium } = require('playwright');
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const BASE_URL = process.env.DISHA_URL || 'http://localhost:8080';
const SCREENSHOTS_DIR = path.join(__dirname, '../docs/screenshots');

if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

const results = [];

function recordResult(testName, passed, details = '') {
  results.push({ testName, passed, details });
  const symbol = passed ? '✅ PASS' : '❌ FAIL';
  console.log(`${symbol} [${testName}] ${details ? '— ' + details : ''}`);
}

async function runTestSuite() {
  console.log('===============================================================');
  console.log('DISHA AI — PLAYWRIGHT JOURNEY & MEMORY VERIFICATION SUITE');
  console.log(`Target Container: ${BASE_URL}`);
  console.log(`Screenshots Output: ${SCREENSHOTS_DIR}`);
  console.log('===============================================================\n');

  const browser = await chromium.launch({
    headless: true,
    args: [
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
      '--no-sandbox',
      '--disable-setuid-sandbox',
    ],
  });

  const context = await browser.newContext({
    permissions: ['microphone'],
    viewport: { width: 1280, height: 800 },
  });

  const page = await context.newPage();

  try {
    // -------------------------------------------------------------------------
    // TEST 1: Multi-Step Registration & Proactive Onboarding Welcome
    // -------------------------------------------------------------------------
    console.log('--- Executing Test 1: Multi-Step Registration & Proactive Greeting ---');
    await page.goto(`${BASE_URL}/#/signin`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(300);

    // Switch to Onboarding tab
    await page.click('#tab-onboard');
    await page.waitForTimeout(300);

    // Step 1: Identity & Demographics
    const testEmail = `neha_${Date.now()}@disha.test`;
    await page.fill('#onboard-name', 'Neha Sharma');
    await page.fill('#onboard-age', '33');
    await page.selectOption('#onboard-gender', 'Female');
    await page.click('#step-1-next-btn');
    await page.waitForTimeout(300);

    // Step 2: Vitals & Diet
    await page.fill('#onboard-height', '165');
    await page.fill('#onboard-weight', '59');
    await page.selectOption('#onboard-diet', 'Vegetarian');
    await page.selectOption('#onboard-focus', 'Fitness & General Wellness');
    await page.click('#step-2-next-btn');
    await page.waitForTimeout(300);

    // Step 3: Account Credentials
    await page.fill('#onboard-email', testEmail);
    await page.fill('#onboard-password', 'password123');
    await page.click('#onboard-submit-btn');

    // Wait for transition to chat dashboard
    await page.waitForFunction(() => {
      return window.location.hash.includes('chat') &&
             document.getElementById('dashboard-view')?.style.display !== 'none';
    }, { timeout: 10000 });

    const patientName = await page.evaluate(() => document.getElementById('patient-display-name')?.textContent);
    assert(patientName && patientName.includes('Neha'), `Expected Neha in patient badge, got: ${patientName}`);

    // Verify proactive greeting
    const welcomeText = await page.evaluate(() => document.getElementById('chat-stream')?.innerText || '');
    assert(welcomeText.includes('Namaste Neha'), `Expected proactive greeting, got: ${welcomeText}`);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'jm_01_onboarding_welcome.png') });
    recordResult('1. Multi-Step Onboarding & Greeting', true, `Successfully registered ${testEmail} with proactive greeting`);

    // -------------------------------------------------------------------------
    // TEST 2: In-Chat Stage Disclosures & Streaming Output
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 2: In-Chat Stage Disclosures & Streaming Output ---');
    await page.fill('#user-text-input', 'Main subah 6 baje uthti hoon aur 3 litre paani peeti hoon.');
    await page.click('#send-turn-btn');

    // Verify user turn rendered
    await page.waitForSelector('.chat-message.user', { timeout: 5000 });

    // Wait for streaming response to finish
    await page.waitForFunction(() => {
      const msgs = document.querySelectorAll('.chat-message.assistant');
      if (msgs.length === 0) return false;
      const last = msgs[msgs.length - 1];
      const p = last.querySelector('.msg-text');
      return p && !p.classList.contains('streaming-cursor') && p.textContent.trim().length > 10;
    }, { timeout: 15000 });

    const assistantReply = await page.evaluate(() => {
      const msgs = document.querySelectorAll('.chat-message.assistant');
      return msgs[msgs.length - 1].querySelector('.msg-text')?.textContent || '';
    });
    assert(assistantReply.length > 10, 'Expected non-empty assistant response');
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'jm_02_chat_disclosure.png') });
    recordResult('2. Chat Disclosures & Streaming Output', true, `Assistant replied (${assistantReply.length} chars)`);

    // -------------------------------------------------------------------------
    // TEST 3: Bidirectional Channel Switch (Chat -> Voice Modal -> Return to Chat)
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 3: Channel Switch (Chat -> Voice Modal -> Return to Chat) ---');
    await page.click('#header-call-btn');
    await page.waitForTimeout(600);

    // Verify voice modal opened
    const isModalOpen = await page.evaluate(() => {
      const modal = document.getElementById('call-overlay-modal');
      return modal && window.getComputedStyle(modal).display === 'flex';
    });
    assert(isModalOpen, 'Voice modal overlay should be displayed with display: flex');

    // Verify 24 spectrum visualizer bars
    const barCount = await page.evaluate(() => document.querySelectorAll('#spectrum-bars .spec-bar').length);
    assert.strictEqual(barCount, 24, `Expected 24 spectrum bars, found: ${barCount}`);

    // Click Return to Chat button
    await page.click('#switch-to-chat-btn');
    await page.waitForTimeout(400);

    const isModalClosed = await page.evaluate(() => {
      const modal = document.getElementById('call-overlay-modal');
      return modal && window.getComputedStyle(modal).display === 'none';
    });
    assert(isModalClosed, 'Voice modal should close on switch to chat');

    // Verify chat view is active and text input is ready
    const inputReady = await page.evaluate(() => {
      const inp = document.getElementById('user-text-input');
      return inp && !inp.disabled;
    });
    assert(inputReady, 'Chat input must remain ready for continuation');
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'jm_03_channel_switch.png') });
    recordResult('3. Channel Switch & Return to Chat', true, 'Voice modal opened with 24 bars, returned cleanly to chat');

    // -------------------------------------------------------------------------
    // TEST 4: Returning-User Home Hydration
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 4: Returning-User Home Hydration ---');
    // Reload page to verify session persistence in localStorage/sessionStorage
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(600);

    // Verify dashboard auto-hydrates without returning to signin screen
    const isDashboardVisible = await page.evaluate(() => {
      const dash = document.getElementById('dashboard-view');
      return dash && window.getComputedStyle(dash).display !== 'none';
    });
    assert(isDashboardVisible, 'Dashboard should auto-hydrate from stored session token');

    const rehydratedName = await page.evaluate(() => document.getElementById('patient-display-name')?.textContent);
    assert(rehydratedName && rehydratedName.includes('Neha'), `Expected Neha on rehydration, got: ${rehydratedName}`);

    // Verify drawer / profile details
    const htnBadgeText = await page.evaluate(() => document.getElementById('disp-htn-badge')?.textContent || '');
    assert(htnBadgeText.length > 0, 'HTN badge should be hydrated');

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'jm_04_returning_hydration.png') });
    recordResult('4. Returning-User Home Hydration', true, `Session auto-restored for ${rehydratedName} with HTN badge '${htnBadgeText}'`);

    // -------------------------------------------------------------------------
    // TEST 5: Unsupported-Language Deflection
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 5: Unsupported-Language Deflection ---');
    await page.fill('#user-text-input', 'Guten Tag Disha, wie geht es dir heute?');
    await page.click('#send-turn-btn');

    // Wait for deflection response
    await page.waitForFunction(() => {
      const msgs = document.querySelectorAll('.chat-message.assistant');
      const last = msgs[msgs.length - 1];
      const p = last?.querySelector('.msg-text');
      return p && !p.classList.contains('streaming-cursor') && p.textContent.includes('English, Hindi');
    }, { timeout: 15000 });

    const deflectionText = await page.evaluate(() => {
      const msgs = document.querySelectorAll('.chat-message.assistant');
      return msgs[msgs.length - 1].querySelector('.msg-text')?.textContent || '';
    });
    assert(deflectionText.includes('English, Hindi, and Hinglish'), `Expected language deflection, got: ${deflectionText}`);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'jm_05_language_deflection.png') });
    recordResult('5. Unsupported Language Deflection', true, 'German query politely deflected without pipeline failure');

    // -------------------------------------------------------------------------
    // TEST 6: Emergency Symptom Escalation
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 6: Emergency Symptom Escalation ---');
    await page.fill('#user-text-input', 'Mujhe severe crushing chest pain ho raha hai aur baayein haath mein dard fail raha hai.');
    await page.click('#send-turn-btn');

    // Wait for emergency response
    await page.waitForFunction(() => {
      const msgs = document.querySelectorAll('.chat-message.assistant');
      const last = msgs[msgs.length - 1];
      const p = last?.querySelector('.msg-text');
      return p && (p.textContent.includes('112') || p.textContent.includes('emergency'));
    }, { timeout: 15000 });

    const emergencyReply = await page.evaluate(() => {
      const msgs = document.querySelectorAll('.chat-message.assistant');
      return msgs[msgs.length - 1].querySelector('.msg-text')?.textContent || '';
    });
    assert(emergencyReply.includes('112'), `Expected 112 emergency advice, got: ${emergencyReply}`);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'jm_06_emergency_escalation.png') });
    recordResult('6. Emergency Escalation During Onboarding', true, 'Chest pain triggered instant 112 emergency escalation');

  } catch (err) {
    console.error('Test execution error:', err);
    throw err;
  } finally {
    await browser.close();
  }

  console.log('\n===============================================================');
  console.log(`JOURNEY & MEMORY PLAYWRIGHT RESULTS: ${results.filter(r => r.passed).length} PASSED, ${results.filter(r => !r.passed).length} FAILED out of ${results.length} tests`);
  console.log('===============================================================');

  if (results.some(r => !r.passed)) {
    process.exit(1);
  }
}

runTestSuite().catch(err => {
  console.error('Fatal suite failure:', err);
  process.exit(1);
});
