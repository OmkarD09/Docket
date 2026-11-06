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

  // 1. 1440x900 Viewport
  const page1440 = await browser.newPage();
  await page1440.setViewport({ width: 1440, height: 900 });
  await page1440.goto('http://localhost:5173', { waitUntil: 'networkidle0' });

  // Click on Audit Trail in sidebar
  const navLinks = await page1440.$$('.nav-link');
  for (const link of navLinks) {
    const text = await page1440.evaluate((el) => el.textContent, link);
    if (text && text.includes('Audit Trail')) {
      await link.click();
      break;
    }
  }

  await page1440.waitForSelector('.audit-workspace-container', { timeout: 5000 });
  await page1440.waitForSelector('.audit-row', { timeout: 5000 });
  await new Promise((r) => setTimeout(r, 1200));

  await page1440.screenshot({
    path: path.join(outDir, 'audit_trail_workspace_1440.png'),
  });
  console.log('Saved audit_trail_workspace_1440.png');

  // Scroll the detail drawer down to show Payload & Timeline
  const drawer = await page1440.$('.audit-drawer');
  if (drawer) {
    await page1440.evaluate((el) => {
      el.scrollTop = 380;
    }, drawer);
    await new Promise((r) => setTimeout(r, 600));
    await page1440.screenshot({
      path: path.join(outDir, 'audit_trail_drawer_scrolled_1440.png'),
    });
    console.log('Saved audit_trail_drawer_scrolled_1440.png');
    // Scroll drawer back to top
    await page1440.evaluate((el) => {
      el.scrollTop = 0;
    }, drawer);
  }

  // Test Filtering: filter by DUPLICATE_WEBHOOK_RECEIVED
  const selectFilter = await page1440.$('.audit-select');
  if (selectFilter) {
    await page1440.select('.audit-select', 'DUPLICATE_WEBHOOK_RECEIVED');
    await new Promise((r) => setTimeout(r, 600));
    await page1440.screenshot({
      path: path.join(outDir, 'audit_trail_filtered_duplicate_1440.png'),
    });
    console.log('Saved audit_trail_filtered_duplicate_1440.png');

    // Reset filter
    const clearBtn = await page1440.$('.audit-toolbar-left button');
    if (clearBtn) {
      await clearBtn.click();
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
    if (text && text.includes('Audit Trail')) {
      await link.click();
      break;
    }
  }

  await page1280.waitForSelector('.audit-workspace-container', { timeout: 5000 });
  await page1280.waitForSelector('.audit-row', { timeout: 5000 });
  await new Promise((r) => setTimeout(r, 1200));

  await page1280.screenshot({
    path: path.join(outDir, 'audit_trail_workspace_1280.png'),
  });
  console.log('Saved audit_trail_workspace_1280.png');

  await browser.close();
  console.log('Finished capturing all screenshots!');
}

capture().catch((err) => {
  console.error('Error during capture:', err);
  process.exit(1);
});
