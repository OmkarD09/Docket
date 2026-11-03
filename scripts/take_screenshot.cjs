const path = require('path');
const puppeteer = require(path.resolve(__dirname, '..', 'frontend', 'node_modules', 'puppeteer-core'));
const fs = require('fs');

async function capture() {
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
  
  // 1. Overview Dashboard at 1440x900
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle0', timeout: 15000 });
  await new Promise(r => setTimeout(r, 1200));
  await page.screenshot({ path: path.join(outDir, 'final_overview_1440.png') });
  console.log('Saved final_overview_1440.png');

  // 2. Overview Dashboard at 1280x720
  await page.setViewport({ width: 1280, height: 720 });
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(outDir, 'final_overview_1280.png') });
  console.log('Saved final_overview_1280.png');

  // Reset to 1440x900
  await page.setViewport({ width: 1440, height: 900 });

  // Helper to click sidebar nav
  const clickNav = async (label) => {
    await page.evaluate((text) => {
      const btns = Array.from(document.querySelectorAll('.nav-link'));
      const target = btns.find(b => b.textContent.includes(text));
      if (target) target.click();
    }, label);
    await new Promise(r => setTimeout(r, 1000));
  };

  // 3. Navigate to Disputes Workspace
  await clickNav('Disputes');
  await page.screenshot({ path: path.join(outDir, 'final_disputes_1440.png') });
  console.log('Saved final_disputes_1440.png');

  // 4. Disputes Workspace at 1280x720
  await page.setViewport({ width: 1280, height: 720 });
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(outDir, 'final_disputes_1280.png') });
  console.log('Saved final_disputes_1280.png');

  // Reset to 1440x900
  await page.setViewport({ width: 1440, height: 900 });

  // 5. Click row with SCEN-01-INR-LABEL (Blocked Label Created scenario)
  try {
    const rows = await page.$$('.ag-row');
    if (rows && rows.length > 1) {
      await rows[1].click();
      await new Promise(r => setTimeout(r, 1200));
      await page.screenshot({ path: path.join(outDir, 'final_disputes_blocked_1440.png') });
      console.log('Saved final_disputes_blocked_1440.png');
    }
  } catch (err) {
    console.error('Error selecting blocked dispute:', err);
  }

  // 6. Navigate to Audit Ledger
  await clickNav('Audit Ledger');
  await page.screenshot({ path: path.join(outDir, 'final_audit_ledger_1440.png') });
  console.log('Saved final_audit_ledger_1440.png');

  // 7. Navigate to Benchmark Scorecard
  await clickNav('Benchmark Scorecard');
  await page.screenshot({ path: path.join(outDir, 'final_benchmark_1440.png') });
  console.log('Saved final_benchmark_1440.png');

  await browser.close();
}

capture().catch(err => {
  console.error('Screenshot error:', err);
  process.exit(1);
});
