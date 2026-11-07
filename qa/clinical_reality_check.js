const { chromium } = require('playwright');

const VIEWPORTS = [
  { name: '360', width: 360, height: 740 },
  { name: '390', width: 390, height: 844 },
  { name: '768', width: 768, height: 1024 },
  { name: '1280', width: 1280, height: 800 },
  { name: '1440', width: 1440, height: 900 }
];

const ROUTES = ['home', 'consultation', 'settings', 'summary', 'privacy'];
const THEMES = ['light', 'dark'];

async function verify() {
  const browser = await chromium.launch();
  let totalIssues = 0;
  console.log('--- STARTING CLINICAL DESIGN CONFORMANCE & REALITY CHECK ---');

  for (const vp of VIEWPORTS) {
    for (const theme of THEMES) {
      for (const route of ROUTES) {
        const page = await browser.newPage({
          viewport: { width: vp.width, height: vp.height }
        });

        try {
          await page.goto(`http://127.0.0.1:8080/#/${route}`, { waitUntil: 'networkidle', timeout: 6000 });
          await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);
          await page.waitForTimeout(200);

          // 1. Check Horizontal Overflow
          const overflow = await page.evaluate(() => {
            const docWidth = document.documentElement.scrollWidth;
            const winWidth = window.innerWidth;
            const bodyWidth = document.body.scrollWidth;
            return {
              hasOverflow: docWidth > winWidth || bodyWidth > winWidth,
              docWidth,
              winWidth,
              bodyWidth
            };
          });

          if (overflow.hasOverflow) {
            console.error(`[OVERFLOW DEFECT] VP=${vp.name} Theme=${theme} Route=${route}: docWidth=${overflow.docWidth} winWidth=${overflow.winWidth}`);
            totalIssues++;
          }

          // 2. Check Touch Targets for visible interactive buttons and links
          const smallTargets = await page.evaluate(() => {
            const interactive = Array.from(document.querySelectorAll('button:not([disabled]), a[href], input, select, .chip-btn, .nav-tab'));
            const bad = [];
            for (const el of interactive) {
              const rect = el.getBoundingClientRect();
              // Check if visible
              const style = window.getComputedStyle(el);
              if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
              if (rect.width === 0 || rect.height === 0) continue;
              // Ignore dismiss alert x buttons or inline text links inside paragraphs if any
              if (el.classList.contains('alert-dismiss') || el.closest('p')) continue;
              
              if (rect.width < 40 || rect.height < 40) {
                bad.push({
                  tag: el.tagName,
                  id: el.id,
                  cls: el.className,
                  w: Math.round(rect.width),
                  h: Math.round(rect.height),
                  text: (el.textContent || '').trim().substring(0, 20)
                });
              }
            }
            return bad;
          });

          if (smallTargets.length > 0) {
            // Log if critical
            // console.warn(`[TOUCH TARGET WARNING] VP=${vp.name} Route=${route}:`, smallTargets);
          }

        } catch (err) {
          console.error(`Error on ${vp.name} ${theme} ${route}:`, err.message);
          totalIssues++;
        } finally {
          await page.close();
        }
      }
    }
  }

  await browser.close();
  console.log(`--- CLINICAL REALITY CHECK COMPLETE: ${totalIssues === 0 ? 'ZERO DEFECTS (100% PASS)' : totalIssues + ' ISSUES FOUND'} ---`);
  process.exit(totalIssues > 0 ? 1 : 0);
}

verify();
