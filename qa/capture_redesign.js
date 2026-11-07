const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const VIEWPORTS = [
  { name: '360', width: 360, height: 740 },
  { name: '390', width: 390, height: 844 },
  { name: '768', width: 768, height: 1024 },
  { name: '1280', width: 1280, height: 800 },
  { name: '1440', width: 1440, height: 900 }
];

const THEMES = ['light', 'dark'];
const ROUTES = ['home', 'consultation', 'settings'];
const OUT_DIR = path.join(__dirname, 'screenshots', 'redesign');

async function main() {
  if (!fs.existsSync(OUT_DIR)) {
    fs.mkdirSync(OUT_DIR, { recursive: true });
  }

  const browser = await chromium.launch();
  console.log('Starting Playwright visual crawler for redesigned Clinical Apothecary SPA...');

  for (const vp of VIEWPORTS) {
    for (const theme of THEMES) {
      for (const route of ROUTES) {
        const page = await browser.newPage({
          viewport: { width: vp.width, height: vp.height }
        });

        try {
          const targetUrl = `http://127.0.0.1:8080/#/${route}`;
          await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 8000 });

          // Apply theme attribute
          await page.evaluate((t) => {
            document.documentElement.setAttribute('data-theme', t);
          }, theme);

          await page.waitForTimeout(300);

          const outPath = path.join(OUT_DIR, `redesign_${route}_${vp.name}_${theme}.png`);
          await page.screenshot({ path: outPath, fullPage: false });
          console.log(`Saved screenshot: ${outPath}`);
        } catch (err) {
          console.error(`Failed on ${route} ${vp.name} ${theme}:`, err.message);
        } finally {
          await page.close();
        }
      }
    }
  }

  await browser.close();
  console.log('Redesign screenshot capture complete!');
}

main().catch((err) => {
  console.error('Crawler fatal error:', err);
  process.exit(1);
});

