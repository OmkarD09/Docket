const path = require('path');
const puppeteer = require(path.resolve(__dirname, '..', 'frontend', 'node_modules', 'puppeteer-core'));
const fs = require('fs');

async function run() {
  const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  const outDir = path.resolve(__dirname, '..', 'artifacts', 'screenshots');
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  const browser = await puppeteer.launch({
    executablePath: edgePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();

  // Helper to click sidebar nav
  const clickNav = async (label) => {
    await page.evaluate((text) => {
      const btns = Array.from(document.querySelectorAll('.nav-link'));
      const target = btns.find(b => b.textContent.includes(text));
      if (target) target.click();
    }, label);
    await new Promise(r => setTimeout(r, 800));
  };

  console.log('=== TEST 1: Overview Scrolling Verification ===');
  // 1A. 1440x900 Overview Top
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 1200));

  await page.screenshot({ path: path.join(outDir, 'overview_top_1440.png') });
  console.log('Saved overview_top_1440.png');

  // Test mouse-wheel scrolling
  const wheelResult = await page.evaluate(async () => {
    const container = document.querySelector('.page-scrollable');
    const startTop = container ? container.scrollTop : -1;
    return { startTop, scrollHeight: container?.scrollHeight, clientHeight: container?.clientHeight };
  });
  console.log('Overview 1440 initial state:', wheelResult);

  // Wheel down
  await page.mouse.move(700, 450);
  await page.mouse.wheel({ deltaY: 400 });
  await new Promise(r => setTimeout(r, 500));

  const afterWheel = await page.evaluate(() => {
    const container = document.querySelector('.page-scrollable');
    return { scrollTop: container?.scrollTop };
  });
  console.log('Overview after mouse-wheel 400px down:', afterWheel);

  // Scroll to absolute bottom and capture
  await page.evaluate(() => {
    const container = document.querySelector('.page-scrollable');
    if (container) container.scrollTop = container.scrollHeight;
  });
  await new Promise(r => setTimeout(r, 500));
  await page.screenshot({ path: path.join(outDir, 'overview_bottom_1440.png') });
  console.log('Saved overview_bottom_1440.png (verifying bottom table)');

  // 1B. 1280x720 Overview
  await page.setViewport({ width: 1280, height: 720 });
  await page.evaluate(() => {
    const container = document.querySelector('.page-scrollable');
    if (container) container.scrollTop = 0;
  });
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(outDir, 'overview_top_1280.png') });
  console.log('Saved overview_top_1280.png');

  // Scroll to bottom at 1280x720
  await page.evaluate(() => {
    const container = document.querySelector('.page-scrollable');
    if (container) container.scrollTop = container.scrollHeight;
  });
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(outDir, 'overview_bottom_1280.png') });
  console.log('Saved overview_bottom_1280.png');

  console.log('\n=== TEST 2: Disputes Workspace Declutter & Scrolling ===');
  await page.setViewport({ width: 1440, height: 900 });
  await clickNav('Disputes');
  await new Promise(r => setTimeout(r, 1200));

  // Check columns present in AG Grid
  const gridHeaders = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('.ag-header-cell-text')).map(el => el.textContent?.trim());
  });
  console.log('Rendered AG Grid column headers:', gridHeaders);

  await page.screenshot({ path: path.join(outDir, 'disputes_workspace_1440.png') });
  console.log('Saved disputes_workspace_1440.png');

  // 1280x720 Disputes Workspace
  await page.setViewport({ width: 1280, height: 720 });
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(outDir, 'disputes_workspace_1280.png') });
  console.log('Saved disputes_workspace_1280.png');

  // Reset to 1440x900
  await page.setViewport({ width: 1440, height: 900 });

  // Select blocked scenario SCEN-01-INR-LABEL (2nd row)
  const rows = await page.$$('.ag-row');
  if (rows && rows.length > 1) {
    await rows[1].click();
    await new Promise(r => setTimeout(r, 1000));
    await page.screenshot({ path: path.join(outDir, 'disputes_blocked_1440.png') });
    console.log('Saved disputes_blocked_1440.png (SCEN-01-INR-LABEL blocked detail)');

    // Test scrolling detail drawer
    const drawerScroll = await page.evaluate(() => {
      const drawer = document.querySelector('.detail-drawer');
      const canScroll = drawer && drawer.scrollHeight > drawer.clientHeight;
      if (drawer) drawer.scrollTop = drawer.scrollHeight;
      return {
        canScroll,
        drawerClientH: drawer?.clientHeight,
        drawerScrollH: drawer?.scrollHeight,
        finalScrollTop: drawer?.scrollTop,
      };
    });
    console.log('Detail drawer scroll test:', drawerScroll);
    await new Promise(r => setTimeout(r, 500));
    await page.screenshot({ path: path.join(outDir, 'disputes_panel_scrolled_1440.png') });
    console.log('Saved disputes_panel_scrolled_1440.png');
  }

  console.log('\n=== TEST 3: Audit Ledger and Benchmark Views ===');
  await clickNav('Audit Ledger');
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: path.join(outDir, 'audit_ledger_1440.png') });
  console.log('Saved audit_ledger_1440.png');

  await clickNav('Benchmark Scorecard');
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: path.join(outDir, 'benchmark_matrix_1440.png') });
  console.log('Saved benchmark_matrix_1440.png');

  await browser.close();
  console.log('\nAll visual usability checks successfully finished.');
}

run().catch(err => {
  console.error('Test execution failed:', err);
  process.exit(1);
});

