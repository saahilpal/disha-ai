/**
 * Playwright End-to-End Browser Automated UX & Product Quality Suite
 * Disha AI Health Coach — Comprehensive Quality Verification
 *
 * Workflows Tested on Live Container (http://localhost:8080/):
 *  1. Sign in & Demo Quick-Fill
 *  2. Multi-Step Conversational Onboarding (3 Steps)
 *  3. Real Text Chat Exchange with Real-Time Streaming Output
 *  4. Voice Modal Activation, 24-Bar Visualizer, Return-to-Chat & Clean End
 *  5. Meals View Display (Daily Nutrition Prescriptions)
 *  6. Profile View & Profile Edit Modal Save
 *  7. Settings Tab Toggles (Dark/Light Mode & Language Selection)
 *  8. Mobile Responsive Layout (390px iPhone 14 Viewport & Zero Horizontal Overflow)
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
  console.log('DISHA AI — PLAYWRIGHT BROWSER AUTOMATED UX VERIFICATION SUITE');
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

  // Log browser console messages and uncaught exceptions
  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.warn('  [Browser Error]:', msg.text());
    }
  });

  page.on('pageerror', err => {
    console.error('  [Browser PageError]:', err.message);
  });

  try {
    // -------------------------------------------------------------------------
    // TEST 1: Sign in & Demo Quick-Fill
    // -------------------------------------------------------------------------
    console.log('--- Executing Test 1: Sign In & Demo Quick-Fill ---');
    await page.goto(`${BASE_URL}/#/signin`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(300);

    const demoBtns = await page.$$('.demo-btn');
    assert(demoBtns.length >= 3, `Expected at least 3 demo buttons, found ${demoBtns.length}`);

    // Click demo button for Vikram Malhotra (cardiac@disha.ai)
    await demoBtns[0].click();
    await page.waitForTimeout(1000);

    const currentUrlAfterLogin = page.url();
    assert(currentUrlAfterLogin.includes('#/chat'), `Expected URL to include #/chat, got ${currentUrlAfterLogin}`);

    const patientNameEl = await page.$('#patient-display-name');
    const patientNameText = patientNameEl ? (await patientNameEl.textContent()).trim() : '';
    assert(patientNameText.includes('Vikram'), `Expected patient name to contain Vikram, got: "${patientNameText}"`);

    const dashboardViewDisplay = await page.evaluate(() => {
      const el = document.getElementById('dashboard-view');
      return window.getComputedStyle(el).display;
    });
    assert(dashboardViewDisplay === 'flex', `Dashboard view display should be flex, got: ${dashboardViewDisplay}`);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01_demo_login.png') });
    recordResult('1. Sign In & Demo Quick-Fill', true, `Authenticated as "${patientNameText}" -> #/chat view active`);

    // -------------------------------------------------------------------------
    // TEST 2: Multi-step Onboarding Flow (3 Steps)
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 2: Multi-step Conversational Onboarding ---');
    // Clear session to test fresh registration
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.goto(`${BASE_URL}/#/signin`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(300);

    // Switch to Create Profile tab
    await page.click('#tab-onboard');
    await page.waitForTimeout(300);

    // Verify Step 1 is active
    const step1Active = await page.evaluate(() => {
      const p1 = document.getElementById('onboard-step-panel-1');
      return p1 && window.getComputedStyle(p1).display !== 'none';
    });
    assert(step1Active, 'Step 1 panel should be visible');

    // Fill Step 1 (Identity & Demographics)
    await page.fill('#onboard-name', 'Ananya Verma');
    await page.fill('#onboard-age', '31');
    await page.selectOption('#onboard-gender', 'Female');
    await page.click('#step-1-next-btn');
    await page.waitForTimeout(300);

    // Verify Step 2 is active
    const step2Active = await page.evaluate(() => {
      const p2 = document.getElementById('onboard-step-panel-2');
      return p2 && window.getComputedStyle(p2).display !== 'none';
    });
    assert(step2Active, 'Step 2 panel should be visible after Step 1 Continue');

    // Fill Step 2 (Vitals, Diet & Clinical Focus)
    await page.fill('#onboard-height', '168');
    await page.fill('#onboard-weight', '62');
    await page.selectOption('#onboard-diet', 'Vegetarian');
    await page.selectOption('#onboard-focus', 'Blood Pressure Care');
    await page.click('#step-2-next-btn');
    await page.waitForTimeout(300);

    // Verify Step 3 is active
    const step3Active = await page.evaluate(() => {
      const p3 = document.getElementById('onboard-step-panel-3');
      return p3 && window.getComputedStyle(p3).display !== 'none';
    });
    assert(step3Active, 'Step 3 panel should be visible after Step 2 Continue');

    // Fill Step 3 (Account & Security Passcode)
    const testEmail = `ananya_${Date.now()}@disha.test`;
    await page.fill('#onboard-email', testEmail);
    await page.fill('#onboard-password', 'password123');
    await page.click('#onboard-submit-btn');

    // Wait for registration completion & dashboard transition
    await page.waitForFunction(() => {
      return window.location.hash.includes('chat') &&
             document.getElementById('dashboard-view').style.display !== 'none';
    }, { timeout: 10000 });

    const newPatientName = await page.evaluate(() => document.getElementById('patient-display-name')?.textContent);
    assert(newPatientName && newPatientName.includes('Ananya'), `Expected Ananya in patient pill, got: ${newPatientName}`);

    // Verify proactive companion welcome message
    const welcomeMsg = await page.evaluate(() => {
      const stream = document.getElementById('chat-stream');
      return stream ? stream.innerText : '';
    });
    assert(welcomeMsg.includes('Namaste Ananya'), `Expected proactive greeting for Ananya, got: ${welcomeMsg}`);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '02_onboarding_complete.png') });
    recordResult('2. Multi-step Onboarding', true, `Successfully registered Ananya Verma (${testEmail}) with proactive greeting`);

    // -------------------------------------------------------------------------
    // TEST 3: Real Text Chat Exchange with Real-Time Streaming Output
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 3: Real Text Chat Exchange with Streaming Output ---');
    await page.fill('#user-text-input', 'Namaste Disha! Mujhe daily sodium intake aur BP control ke liye guidance chahiye.');
    await page.click('#send-turn-btn');

    // Verify user message appears immediately in DOM
    const hasUserMsg = await page.evaluate(() => {
      const userMsgs = document.querySelectorAll('.chat-message.user .msg-text');
      return Array.from(userMsgs).some(m => m.textContent.includes('sodium intake'));
    });
    assert(hasUserMsg, 'User message was not rendered into chat stream');

    // Wait for assistant response to stream in
    await page.waitForFunction(() => {
      const assistantMsgs = document.querySelectorAll('.chat-message.assistant .msg-text');
      if (assistantMsgs.length < 2) return false;
      const latest = assistantMsgs[assistantMsgs.length - 1];
      return latest.textContent.trim().length > 20 && !latest.classList.contains('streaming-cursor');
    }, { timeout: 20000 });

    const latestAssistantResponse = await page.evaluate(() => {
      const assistantMsgs = document.querySelectorAll('.chat-message.assistant .msg-text');
      return assistantMsgs[assistantMsgs.length - 1].textContent.trim();
    });

    assert(latestAssistantResponse.length > 20, 'Assistant response should be streaming multi-sentence text');

    // Check message wrapping and absence of overflow
    const messageWrapValid = await page.evaluate(() => {
      const assistantMsgs = document.querySelectorAll('.chat-message.assistant');
      const latest = assistantMsgs[assistantMsgs.length - 1];
      const bubble = latest.querySelector('.msg-bubble');
      return bubble.scrollWidth <= bubble.clientWidth + 2; // No horizontal scroll
    });
    assert(messageWrapValid, 'Chat bubble has horizontal overflow');

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '03_chat_streaming.png') });
    recordResult('3. Text Chat Exchange with Streaming Output', true, `Received response (${latestAssistantResponse.length} chars): "${latestAssistantResponse.slice(0, 70)}..."`);

    // -------------------------------------------------------------------------
    // TEST 4: Voice Call Modal Activation, Visualizer & Return-to-Chat
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 4: Voice Call Modal & Barge-In / Return-to-Chat ---');
    await page.click('#header-call-btn');
    await page.waitForTimeout(1000);

    const callModalVisible = await page.evaluate(() => {
      const modal = document.getElementById('call-overlay-modal');
      return modal && window.getComputedStyle(modal).display === 'flex';
    });
    assert(callModalVisible, 'Voice call overlay modal should be displayed with display: flex');

    // Check 24 spectrum visualizer bars
    const specBarsCount = await page.evaluate(() => {
      return document.querySelectorAll('#spectrum-bars .spec-bar').length;
    });
    assert(specBarsCount === 24, `Expected 24 spectrum visualizer bars, found: ${specBarsCount}`);

    // Verify Call Timer is active
    const timerText = await page.evaluate(() => document.getElementById('call-duration')?.textContent);
    assert(timerText && timerText.includes(':'), `Expected monospace timer mm:ss, got: ${timerText}`);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '04_voice_modal_active.png') });

    // Test Return-to-Chat button
    await page.click('#switch-to-chat-btn');
    await page.waitForTimeout(400);

    const callModalHiddenAfterSwitch = await page.evaluate(() => {
      const modal = document.getElementById('call-overlay-modal');
      return modal && window.getComputedStyle(modal).display === 'none';
    });
    assert(callModalHiddenAfterSwitch, 'Voice modal should be hidden after clicking Return to Chat');

    // Reopen modal via header call button
    await page.click('#header-call-btn');
    await page.waitForTimeout(400);

    const callModalReopened = await page.evaluate(() => {
      const modal = document.getElementById('call-overlay-modal');
      return modal && window.getComputedStyle(modal).display === 'flex';
    });
    assert(callModalReopened, 'Voice modal should reopen upon clicking header call button');

    // End call cleanly
    await page.click('#call-btn');
    await page.waitForTimeout(600);

    const callModalClosedAfterEnd = await page.evaluate(() => {
      const modal = document.getElementById('call-overlay-modal');
      return modal && window.getComputedStyle(modal).display === 'none';
    });
    assert(callModalClosedAfterEnd, 'Voice modal should close on call end');

    // Verify call end notification pill rendered into chat stream
    const hasCallEndPill = await page.evaluate(() => {
      const pill = document.querySelector('.chat-call-end-pill');
      return pill && pill.textContent.includes('Voice call ended');
    });
    assert(hasCallEndPill, 'Call end pill was not appended to chat stream');

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '04_voice_call_ended.png') });
    recordResult('4. Voice Call Modal & Return-to-Chat', true, 'Full lifecycle validated: opened, visualizer active, return-to-chat, reopened, clean end with pill');

    // -------------------------------------------------------------------------
    // TEST 5: Meals View Display
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 5: Meals View Display ---');
    await page.click('a[href="#/meals"]');
    await page.waitForTimeout(500);

    const currentUrlMeals = page.url();
    assert(currentUrlMeals.includes('#/meals'), `Expected URL to include #/meals, got: ${currentUrlMeals}`);

    const mealsViewVisible = await page.evaluate(() => {
      const v = document.getElementById('view-meals');
      return v && window.getComputedStyle(v).display !== 'none';
    });
    assert(mealsViewVisible, 'Meals view should be visible');

    const breakfastText = await page.evaluate(() => document.getElementById('meals-page-breakfast')?.textContent.trim());
    const lunchText = await page.evaluate(() => document.getElementById('meals-page-lunch')?.textContent.trim());
    const dinnerText = await page.evaluate(() => document.getElementById('meals-page-dinner')?.textContent.trim());

    assert(breakfastText && breakfastText.length > 5, 'Breakfast recommendation should not be empty');
    assert(lunchText && lunchText.length > 5, 'Lunch recommendation should not be empty');
    assert(dinnerText && dinnerText.length > 5, 'Dinner recommendation should not be empty');

    const mealsTabActive = await page.evaluate(() => {
      const tab = document.querySelector('.nav-tab[data-route="meals"]');
      return tab && tab.classList.contains('active');
    });
    assert(mealsTabActive, 'Meals nav tab should have active class');

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '05_meals_view.png') });
    recordResult('5. Meals View Display', true, `Prescriptions loaded: Breakfast ("${breakfastText.slice(0, 30)}..."), Lunch ("${lunchText.slice(0, 30)}..."), Dinner ("${dinnerText.slice(0, 30)}...")`);

    // -------------------------------------------------------------------------
    // TEST 6: Profile View & Profile Edit Modal Save
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 6: Profile View & Profile Edit Modal Save ---');
    await page.click('a[href="#/profile"]');
    await page.waitForTimeout(500);

    const profileViewVisible = await page.evaluate(() => {
      const v = document.getElementById('view-profile');
      return v && window.getComputedStyle(v).display !== 'none';
    });
    assert(profileViewVisible, 'Profile view should be visible');

    const ageSexVal = await page.evaluate(() => document.getElementById('profile-page-age-sex')?.textContent.trim());
    assert(ageSexVal.includes('31'), `Expected age 31 in profile, got: ${ageSexVal}`);

    // Open Edit Profile Modal
    await page.click('#profile-page-edit-btn');
    await page.waitForTimeout(400);

    const profileModalVisible = await page.evaluate(() => {
      const m = document.getElementById('profile-edit-modal');
      return m && window.getComputedStyle(m).display === 'flex';
    });
    assert(profileModalVisible, 'Profile edit modal should be displayed');

    // Modify profile data
    await page.fill('#edit-name', 'Ananya Verma Singhania');
    await page.fill('#edit-weight', '60.5');
    await page.selectOption('#edit-diet', 'Vegan');
    await page.click('#profile-save-btn');

    // Wait for modal to close and state to update
    await page.waitForFunction(() => {
      const m = document.getElementById('profile-edit-modal');
      return m && window.getComputedStyle(m).display === 'none';
    }, { timeout: 8000 });

    const updatedDisplayName = await page.evaluate(() => document.getElementById('patient-display-name')?.textContent.trim());
    assert(updatedDisplayName.includes('Ananya Verma Singhania'), `Expected updated name in header, got: ${updatedDisplayName}`);

    const updatedDiet = await page.evaluate(() => document.getElementById('profile-page-diet')?.textContent.trim());
    assert(updatedDiet === 'Vegan', `Expected updated diet Vegan, got: ${updatedDiet}`);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '06_profile_edit_saved.png') });
    recordResult('6. Profile View & Edit Modal Save', true, `Updated name to "${updatedDisplayName}", weight to 60.5 kg, diet to "${updatedDiet}"`);

    // -------------------------------------------------------------------------
    // TEST 7: Settings Tab Toggles (Dark/Light Mode & Language Selection)
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 7: Settings Tab Toggles ---');
    await page.click('a[href="#/settings"]');
    await page.waitForTimeout(500);

    const settingsViewVisible = await page.evaluate(() => {
      const v = document.getElementById('view-settings');
      return v && window.getComputedStyle(v).display !== 'none';
    });
    assert(settingsViewVisible, 'Settings view should be visible');

    // Toggle to Dark Mode
    await page.selectOption('#theme-select', 'dark');
    await page.waitForTimeout(300);
    const themeAttrDark = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    assert(themeAttrDark === 'dark', `Expected data-theme to be dark, got: ${themeAttrDark}`);

    // Toggle to Light Mode
    await page.selectOption('#theme-select', 'light');
    await page.waitForTimeout(300);
    const themeAttrLight = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    assert(themeAttrLight === 'light', `Expected data-theme to be light, got: ${themeAttrLight}`);

    // Change Language to Hindi
    await page.selectOption('#language-select', 'hi');
    await page.waitForTimeout(300);
    const storedLang = await page.evaluate(() => localStorage.getItem('disha_language'));
    assert(storedLang === 'hi', `Expected stored language to be hi, got: ${storedLang}`);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '07_settings_toggled.png') });
    recordResult('7. Settings Tab Toggles', true, 'Dark/light theme toggle and language preference persistence verified');

    // -------------------------------------------------------------------------
    // TEST 8: Mobile Responsive Layout (390px iPhone Viewport)
    // -------------------------------------------------------------------------
    console.log('\n--- Executing Test 8: Mobile Responsive Layout (390px Viewport) ---');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(400);

    // Verify all 4 tabs on mobile without overflow
    const mobileRoutes = ['chat', 'meals', 'profile', 'settings'];
    for (const r of mobileRoutes) {
      await page.click(`a[data-route="${r}"]`);
      await page.waitForTimeout(300);

      const hasHorizontalOverflow = await page.evaluate(() => {
        return document.documentElement.scrollWidth > document.documentElement.clientWidth;
      });
      assert(!hasHorizontalOverflow, `Horizontal scroll overflow detected on mobile for view #${r}`);
    }

    // Return to chat on mobile
    await page.click('a[data-route="chat"]');
    await page.waitForTimeout(300);

    const composerWidth = await page.evaluate(() => {
      const comp = document.querySelector('.chat-composer-bar');
      return comp ? comp.clientWidth : 0;
    });
    assert(composerWidth <= 390 && composerWidth >= 350, `Composer width out of bounds on mobile: ${composerWidth}`);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '08_mobile_responsive_390px.png') });
    recordResult('8. Mobile Responsive Layout (390px)', true, 'All 4 views validated on 390x844 viewport with 0 horizontal overflow');

  } catch (err) {
    console.error('\n❌ TEST SUITE EXECUTION FAILED:', err);
    recordResult('FATAL ERROR', false, err.message);
  } finally {
    await browser.close();
  }

  console.log('\n===============================================================');
  const passedCount = results.filter(r => r.passed).length;
  const failedCount = results.filter(r => !r.passed).length;
  console.log(`AUTOMATED TEST RESULTS: ${passedCount} PASSED, ${failedCount} FAILED out of ${results.length} tests`);
  console.log('===============================================================');

  if (failedCount > 0) {
    process.exit(1);
  } else {
    process.exit(0);
  }
}

runTestSuite();
