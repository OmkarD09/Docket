const path = require('path');
const fs = require('fs');
const puppeteer = require(path.resolve(__dirname, '..', 'frontend', 'node_modules', 'puppeteer-core'));

const OUT_DIR = path.resolve(__dirname, '..', 'docs', 'assets', 'readme');
if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

async function capture() {
  const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  console.log('Launching browser via Edge...');
  const browser = await puppeteer.launch({
    executablePath: edgePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });

  // 1. Sign In Page
  console.log('1. Loading Sign In view...');
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(OUT_DIR, 'sign-in.png'), fullPage: false });
  console.log('   Saved sign-in.png');

  // Click "Continue to Demo Workspace"
  console.log('2. Signing in as Demo Persona...');
  const submitBtn = await page.$('.signin-submit-btn');
  if (submitBtn) {
    await submitBtn.click();
    await page.waitForSelector('.app-shell', { timeout: 10000 });
    await new Promise(r => setTimeout(r, 1500));
  } else {
    console.warn('   .signin-submit-btn not found, may already be signed in');
  }

  // 2. Overview Dashboard
  console.log('3. Capturing Overview Dashboard...');
  await page.keyboard.press('1');
  await new Promise(r => setTimeout(r, 1500));
  await page.screenshot({ path: path.join(OUT_DIR, 'overview.png'), fullPage: false });
  console.log('   Saved overview.png');

  // 3. Dispute Workspace (Table View)
  console.log('4. Capturing Disputes Workspace...');
  await page.keyboard.press('2');
  await new Promise(r => setTimeout(r, 1500));

  // If drawer is open, click close button to capture full grid view
  const closeBtn = await page.$('.detail-drawer .btn-secondary');
  if (closeBtn) {
    await closeBtn.click();
    await new Promise(r => setTimeout(r, 500));
  }
  await page.screenshot({ path: path.join(OUT_DIR, 'disputes.png'), fullPage: false });
  console.log('   Saved disputes.png');

  // 4. Evidence Drawer (Split Workspace with PP-R-NKI-10193390 selected)
  console.log('5. Capturing Evidence Drawer with PP-R-NKI-10193390...');
  // Click row with PP-R-NKI-10193390 in AG Grid
  const rowClicked = await page.evaluate(() => {
    const cells = Array.from(document.querySelectorAll('.ag-cell'));
    const targetCell = cells.find(c => c.textContent && c.textContent.includes('PP-R-NKI-10193390'));
    if (targetCell) {
      targetCell.click();
      return true;
    }
    // Fallback: click first row
    const firstRow = document.querySelector('.ag-row');
    if (firstRow) {
      firstRow.click();
      return true;
    }
    return false;
  });
  await new Promise(r => setTimeout(r, 2000));
  await page.screenshot({ path: path.join(OUT_DIR, 'evidence-drawer.png'), fullPage: false });
  console.log('   Saved evidence-drawer.png');

  // 5. Audit Trail
  console.log('6. Capturing Audit Trail...');
  await page.keyboard.press('3');
  await new Promise(r => setTimeout(r, 2000));
  await page.screenshot({ path: path.join(OUT_DIR, 'audit-trail.png'), fullPage: false });
  console.log('   Saved audit-trail.png');

  // 6. Benchmark Scorecard
  console.log('7. Capturing Benchmark Scorecard...');
  await page.keyboard.press('4');
  await new Promise(r => setTimeout(r, 2000));
  await page.screenshot({ path: path.join(OUT_DIR, 'benchmark-scorecard.png'), fullPage: false });
  console.log('   Saved benchmark-scorecard.png');

  await browser.close();
  console.log('All 6 screenshots successfully captured and saved in docs/assets/readme/');
}

capture().catch(err => {
  console.error('Error during capture:', err);
  process.exit(1);
});

