const puppeteer = require('../frontend/node_modules/puppeteer-core');
const path = require('path');
const fs = require('fs');

async function captureImproved() {
  const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  const outDir = path.resolve(__dirname, '..', 'artifacts', 'screenshots_improved');
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  const browser = await puppeteer.launch({
    executablePath: edgePath,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  // 1. Overview (1440)
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle0' });
  await new Promise((r) => setTimeout(r, 1200));
  await page.screenshot({ path: path.join(outDir, '01_overview_1440.png') });
  console.log('Captured 01_overview_1440.png');

  // Helper to click sidebar nav
  async function clickNav(textLabel) {
    const navLinks = await page.$$('.nav-link');
    for (const link of navLinks) {
      const text = await page.evaluate((el) => el.textContent, link);
      if (text && text.includes(textLabel)) {
        await link.click();
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 1200));
  }

  // 2. Disputes Workspace (1440)
  await clickNav('Disputes');
  await page.screenshot({ path: path.join(outDir, '02_disputes_1440.png') });
  console.log('Captured 02_disputes_1440.png');

  // 3. Audit Trail (1440)
  await clickNav('Audit Trail');
  await page.screenshot({ path: path.join(outDir, '03_audit_trail_1440.png') });
  console.log('Captured 03_audit_trail_1440.png');

  // 4. Benchmark Scorecard (1440)
  await clickNav('Benchmark Scorecard');
  await page.screenshot({ path: path.join(outDir, '04_benchmark_1440.png') });
  console.log('Captured 04_benchmark_1440.png');

  // Responsive 1280x720 Check
  await page.setViewport({ width: 1280, height: 720 });
  await page.screenshot({ path: path.join(outDir, '04_benchmark_1280.png') });
  console.log('Captured 04_benchmark_1280.png');

  await clickNav('Overview');
  await page.screenshot({ path: path.join(outDir, '01_overview_1280.png') });
  console.log('Captured 01_overview_1280.png');

  await browser.close();
  console.log('All improved screenshots captured successfully.');
}

captureImproved().catch((err) => {
  console.error(err);
  process.exit(1);
});

