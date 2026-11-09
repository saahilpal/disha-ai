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
const OUT_DIR = path.join(__dirname, 'screenshots', 'baseline');

async function main() {
  if (!fs.existsSync(OUT_DIR)) {
    fs.mkdirSync(OUT_DIR, { recursive: true });
  }

  const browser = await chromium.launch();
  console.log('Browser launched. Starting baseline crawl against http://127.0.0.1:8080 ...');

  for (const vp of VIEWPORTS) {
    for (const theme of THEMES) {
      const page = await browser.newPage({
        viewport: { width: vp.width, height: vp.height }
      });

      try {
        await page.goto('http://127.0.0.1:8080/', { waitUntil: 'networkidle', timeout: 10000 });
        
        // Apply theme
        await page.evaluate((t) => {
          document.documentElement.setAttribute('data-theme', t);
        }, theme);

        await page.waitForTimeout(300);

        const outPath = path.join(OUT_DIR, `baseline_${vp.name}_${theme}.png`);
        await page.screenshot({ path: outPath, fullPage: false });
        console.log(`Saved screenshot: ${outPath}`);
      } catch (err) {
        console.error(`Failed on ${vp.name} ${theme}:`, err.message);
      } finally {
        await page.close();
      }
    }
  }

  await browser.close();
  console.log('Baseline screenshot crawl complete.');
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});

