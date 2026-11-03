const path = require('path');
const puppeteer = require(path.resolve(__dirname, '..', 'frontend', 'node_modules', 'puppeteer-core'));

async function diagnose() {
  const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  const browser = await puppeteer.launch({
    executablePath: edgePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle0', timeout: 15000 });
  await new Promise(r => setTimeout(r, 1000));

  const diag = await page.evaluate(() => {
    const results = [];
    const walk = (el, depth = 0) => {
      const cs = window.getComputedStyle(el);
      const isScrollable = el.scrollHeight > el.clientHeight;
      const overflow = cs.overflowY;
      results.push({
        depth,
        tag: el.tagName,
        className: el.className,
        id: el.id,
        clientHeight: el.clientHeight,
        scrollHeight: el.scrollHeight,
        scrollTop: el.scrollTop,
        overflowY: overflow,
        height: cs.height,
        minHeight: cs.minHeight,
        maxHeight: cs.maxHeight,
        display: cs.display,
        isScrollable,
      });
      for (const child of el.children) {
        if (depth < 6) walk(child, depth + 1);
      }
    };
    walk(document.body);
    return results;
  });

  console.log('--- DOM HIERARCHY & SCROLL DIAGNOSTICS ---');
  for (const item of diag) {
    if (item.depth <= 4 || item.isScrollable || item.overflowY === 'auto' || item.overflowY === 'scroll' || item.overflowY === 'hidden') {
      const indent = '  '.repeat(item.depth);
      console.log(`${indent}${item.tag}.${item.className || '(no class)'}: clientH=${item.clientHeight}, scrollH=${item.scrollHeight}, scrollTop=${item.scrollTop}, overflowY=${item.overflowY}, display=${item.display}, isScrollable=${item.isScrollable}`);
    }
  }

  // Now test mouse wheel scrolling on the overview
  console.log('\n--- TESTING MOUSE WHEEL SCROLL ---');
  const initialScroll = await page.evaluate(() => {
    const scrollContainer = document.querySelector('div[style*="overflow-y: auto"]') || document.querySelector('div[style*="overflowY: auto"]') || document.body;
    return {
      windowScrollY: window.scrollY,
      containerScrollTop: scrollContainer ? scrollContainer.scrollTop : -1,
      containerClass: scrollContainer ? scrollContainer.className : null
    };
  });
  console.log('Initial scroll:', initialScroll);

  // Hover at center of overview and wheel down 300px
  await page.mouse.move(700, 450);
  await page.mouse.wheel({ deltaY: 300 });
  await new Promise(r => setTimeout(r, 500));

  const afterWheel = await page.evaluate(() => {
    const scrollContainer = Array.from(document.querySelectorAll('*')).find(el => el.scrollHeight > el.clientHeight && (window.getComputedStyle(el).overflowY === 'auto' || window.getComputedStyle(el).overflowY === 'scroll'));
    return {
      windowScrollY: window.scrollY,
      foundContainerTag: scrollContainer ? scrollContainer.tagName : null,
      foundContainerClass: scrollContainer ? scrollContainer.className : null,
      containerScrollTop: scrollContainer ? scrollContainer.scrollTop : -1,
      containerScrollHeight: scrollContainer ? scrollContainer.scrollHeight : -1,
      containerClientHeight: scrollContainer ? scrollContainer.clientHeight : -1
    };
  });
  console.log('After wheel:', afterWheel);

  await browser.close();
}

diagnose().catch(err => {
  console.error('Diagnosis failed:', err);
  process.exit(1);
});

