const puppeteer = require('../frontend/node_modules/puppeteer-core');
const path = require('path');
const fs = require('fs');

async function capture() {
  const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  const outDir = path.resolve(__dirname, '..', 'artifacts', 'screenshots');
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  const browser = await puppeteer.launch({
    executablePath: edgePath,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  // 1. 1440x900 Desktop View
  const page1440 = await browser.newPage();
  await page1440.setViewport({ width: 1440, height: 900 });
  await page1440.goto('http://localhost:5173', { waitUntil: 'networkidle0' });

  // Click on Benchmark Scorecard in sidebar
  const navLinks = await page1440.$$('.nav-link');
  for (const link of navLinks) {
    const text = await page1440.evaluate((el) => el.textContent, link);
    if (text && text.includes('Benchmark Scorecard')) {
      await link.click();
      break;
    }
  }

  await page1440.waitForSelector('.benchmark-page-container', { timeout: 5000 });
  await page1440.waitForSelector('.ledger-table', { timeout: 5000 });
  await new Promise((r) => setTimeout(r, 1200));

  // Screenshot 1: Full Scorecard 2.0 View (1440x900)
  await page1440.screenshot({
    path: path.join(outDir, 'benchmark_scorecard_2_workspace_1440.png'),
  });
  console.log('Saved benchmark_scorecard_2_workspace_1440.png');

  // Screenshot 2: Click on the first scenario row to open the on-demand detail drawer
  const rows = await page1440.$$('.ledger-row');
  if (rows.length > 0) {
    await rows[0].click();
    await page1440.waitForSelector('.scenario-drawer-panel', { timeout: 5000 });
    await new Promise((r) => setTimeout(r, 800));
    await page1440.screenshot({
      path: path.join(outDir, 'benchmark_scorecard_2_drawer_1440.png'),
    });
    console.log('Saved benchmark_scorecard_2_drawer_1440.png');

    // Close the drawer
    const closeBtn = await page1440.$('.scenario-drawer-header button');
    if (closeBtn) {
      await closeBtn.click();
      await new Promise((r) => setTimeout(r, 500));
    }
  }

  // Screenshot 3: Click a confusion matrix cell (e.g. Expected BLOCK x Actual BLOCK)
  const matrixCells = await page1440.$$('.matrix-data-cell');
  // Row 3 Col 3 is cell index 8 (Expected BLOCK x Actual BLOCK)
  if (matrixCells.length >= 9) {
    await matrixCells[8].click();
    await new Promise((r) => setTimeout(r, 600));
    await page1440.screenshot({
      path: path.join(outDir, 'benchmark_scorecard_2_matrix_filter_1440.png'),
    });
    console.log('Saved benchmark_scorecard_2_matrix_filter_1440.png');

    // Reset filter
    const resetBtn = await page1440.$('.ledger-filter-strip button');
    if (resetBtn) {
      await resetBtn.click();
      await new Promise((r) => setTimeout(r, 400));
    }
  }

  // 2. 1280x720 Viewport
  const page1280 = await browser.newPage();
  await page1280.setViewport({ width: 1280, height: 720 });
  await page1280.goto('http://localhost:5173', { waitUntil: 'networkidle0' });

  const navLinks1280 = await page1280.$$('.nav-link');
  for (const link of navLinks1280) {
    const text = await page1280.evaluate((el) => el.textContent, link);
    if (text && text.includes('Benchmark Scorecard')) {
      await link.click();
      break;
    }
  }

  await page1280.waitForSelector('.benchmark-page-container', { timeout: 5000 });
  await page1280.waitForSelector('.ledger-table', { timeout: 5000 });
  await new Promise((r) => setTimeout(r, 1200));

  await page1280.screenshot({
    path: path.join(outDir, 'benchmark_scorecard_2_workspace_1280.png'),
  });
  console.log('Saved benchmark_scorecard_2_workspace_1280.png');

  await browser.close();
  console.log('All Benchmark Scorecard 2.0 screenshots captured successfully!');
}

capture().catch((err) => {
  console.error('Error during benchmark capture:', err);
  process.exit(1);
});

