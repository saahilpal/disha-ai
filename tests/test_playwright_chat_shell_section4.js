/**
 * Section 4 Chat Shell Verification Suite
 * Verifies responsive layout (360, 390, 768, 1280), light & dark themes,
 * zero console errors, no horizontal overflow, and Section 4 features.
 */

const { chromium } = require('playwright');
const assert = require('assert');

const BASE_URL = process.env.DISHA_URL || 'http://localhost:8080';
const VIEWPORTS = [
  { width: 360, height: 740, name: '360px mobile small' },
  { width: 390, height: 844, name: '390px mobile medium' },
  { width: 768, height: 1024, name: '768px tablet' },
  { width: 1280, height: 800, name: '1280px desktop' }
];

async function run() {
  console.log('--- STARTING SECTION 4 CHAT SHELL VERIFICATION ---');
  const browser = await chromium.launch({ headless: true });
  let totalTests = 0;
  let passedTests = 0;

  function test(name, fn) {
    totalTests++;
    try {
      fn();
      passedTests++;
      console.log(`  ✅ PASS: ${name}`);
    } catch (e) {
      console.error(`  ❌ FAIL: ${name} ->`, e.message);
      throw e;
    }
  }

  try {
    for (const vp of VIEWPORTS) {
      for (const theme of ['light', 'dark']) {
        console.log(`\nTesting Viewport ${vp.name} (${vp.width}x${vp.height}) [Theme: ${theme}]`);
        const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
        const page = await context.newPage();

        const consoleErrors = [];
        page.on('console', msg => {
          if (msg.type() === 'error') {
            consoleErrors.push(msg.text());
          }
        });

        // Seed authentication token to directly open dashboard
        await page.addInitScript(({ th }) => {
          localStorage.setItem('disha_token', 'test-token-section4');
          localStorage.setItem('disha_patient_id', 'p_test_sec4');
          localStorage.setItem('disha_patient_name', 'Rahul Sharma');
          localStorage.setItem('disha_theme', th);
        }, { th: theme });

        await page.goto(`${BASE_URL}/#/chat`, { waitUntil: 'networkidle' });
        await page.waitForTimeout(400);

        // Ensure theme class is applied
        await page.evaluate((th) => {
          document.documentElement.setAttribute('data-theme', th);
        }, theme);

        test(`[${vp.width}px ${theme}] Zero console errors on load`, () => {
          assert.strictEqual(consoleErrors.length, 0, `Found console errors: ${consoleErrors.join(', ')}`);
        });

        // Check horizontal overflow
        const overflow = await page.evaluate(() => {
          const docEl = document.documentElement;
          const body = document.body;
          const stream = document.getElementById('chat-stream');
          return {
            docOverflow: docEl.scrollWidth > docEl.clientWidth + 1,
            bodyOverflow: body.scrollWidth > body.clientWidth + 1,
            streamOverflow: stream ? stream.scrollWidth > stream.clientWidth + 1 : false,
            docScrollWidth: docEl.scrollWidth,
            docClientWidth: docEl.clientWidth
          };
        });

        test(`[${vp.width}px ${theme}] Zero horizontal overflow`, () => {
          assert(!overflow.docOverflow, `Doc horizontal overflow: ${overflow.docScrollWidth} > ${overflow.docClientWidth}`);
          assert(!overflow.bodyOverflow, 'Body has horizontal overflow');
          assert(!overflow.streamOverflow, 'Chat stream has horizontal overflow');
        });

        // Verify readable column max-width ~44rem (704px)
        const chatColumnStyle = await page.evaluate(() => {
          const col = document.querySelector('.chat-container');
          if (!col) return null;
          const computed = window.getComputedStyle(col);
          const rect = col.getBoundingClientRect();
          return {
            maxWidth: computed.maxWidth,
            width: rect.width
          };
        });

        test(`[${vp.width}px ${theme}] Centred readable column within ~44rem`, () => {
          assert(chatColumnStyle, 'chat-container found in DOM');
          // 44rem at 16px font-size is 704px. On screens < 704px it should fit screen width.
          assert(chatColumnStyle.width <= 704 + 10, `Column width ${chatColumnStyle.width}px exceeds 44rem`);
        });

        // Verify unboxed assistant message styling vs user message styling
        const messageStyles = await page.evaluate(() => {
          // Add a user and assistant message for styling inspection
          const stream = document.getElementById('chat-stream');
          const userBubble = document.querySelector('.chat-message.user .msg-bubble');
          const assistantBubble = document.querySelector('.chat-message.assistant .msg-bubble');
          const userStyle = userBubble ? window.getComputedStyle(userBubble) : null;
          const assistantStyle = assistantBubble ? window.getComputedStyle(assistantBubble) : null;
          return {
            userAlign: userBubble ? userStyle.marginLeft : null,
            userBg: userBubble ? userStyle.backgroundColor : null,
            assistantBg: assistantBubble ? assistantStyle.backgroundColor : null,
            assistantBorder: assistantBubble ? assistantStyle.borderStyle : null
          };
        });

        test(`[${vp.width}px ${theme}] Unboxed assistant text directly on canvas (transparent / no box)`, () => {
          assert(messageStyles.assistantBg === 'rgba(0, 0, 0, 0)' || messageStyles.assistantBg === 'transparent',
            `Expected assistant msg to have transparent background, got ${messageStyles.assistantBg}`);
          assert(messageStyles.assistantBorder === 'none', 'Assistant message should have no box border');
        });

        // Verify composer elements: textarea auto-grow, stop button, jump to latest pill
        const composerStatus = await page.evaluate(() => {
          const input = document.getElementById('user-text-input');
          const stopBtn = document.getElementById('stop-stream-btn');
          const jumpPill = document.getElementById('jump-to-latest-btn');
          const stream = document.getElementById('chat-stream');
          return {
            isTextarea: input && input.tagName === 'TEXTAREA',
            hasStopBtn: !!stopBtn,
            hasJumpPill: !!jumpPill,
            streamAriaLive: stream ? stream.getAttribute('aria-live') : null,
            streamRole: stream ? stream.getAttribute('role') : null
          };
        });

        test(`[${vp.width}px ${theme}] Auto-growing composer textarea present`, () => {
          assert(composerStatus.isTextarea, 'user-text-input is a textarea');
        });

        test(`[${vp.width}px ${theme}] Stop button and Jump-to-latest pill in DOM`, () => {
          assert(composerStatus.hasStopBtn, 'Stop button present');
          assert(composerStatus.hasJumpPill, 'Jump pill present');
        });

        test(`[${vp.width}px ${theme}] Accessible aria-live log stream`, () => {
          assert.strictEqual(composerStatus.streamAriaLive, 'polite');
          assert.strictEqual(composerStatus.streamRole, 'log');
        });

        // Test auto-grow height on newline
        const heightCheck = await page.evaluate(async () => {
          const ta = document.getElementById('user-text-input');
          ta.value = 'Line 1';
          ta.dispatchEvent(new Event('input', { bubbles: true }));
          const h1 = ta.offsetHeight;
          ta.value = 'Line 1\nLine 2\nLine 3\nLine 4';
          ta.dispatchEvent(new Event('input', { bubbles: true }));
          const h2 = ta.offsetHeight;
          return { h1, h2, grew: h2 > h1 };
        });

        test(`[${vp.width}px ${theme}] Textarea auto-grows dynamically with multi-line input`, () => {
          assert(heightCheck.grew, `Textarea did not grow: h1=${heightCheck.h1}, h2=${heightCheck.h2}`);
        });

        await context.close();
      }
    }

    console.log(`\n===============================================================`);
    console.log(`SECTION 4 VERIFICATION RESULTS: ${passedTests}/${totalTests} PASSED`);
    console.log(`===============================================================`);
  } catch (e) {
    console.error('Test failed:', e);
    await browser.close();
    process.exit(1);
  }

  await browser.close();
}

run();
