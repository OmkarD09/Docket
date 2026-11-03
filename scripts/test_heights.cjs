const path = require('path');
const puppeteer = require(path.resolve(__dirname, '..', 'frontend', 'node_modules', 'puppeteer-core'));

async function testResolution(width, height) {
  const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  const browser = await puppeteer.launch({
    executablePath: edgePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width, height });
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 1000));

  const result = await page.evaluate(() => {
    const scrollContainer = document.querySelector('.page-scrollable');
    if (!scrollContainer) return { error: 'No .page-scrollable found' };

    const initialTop = scrollContainer.scrollTop;
    // Scroll to bottom
    scrollContainer.scrollTop = scrollContainer.scrollHeight;
    const finalTop = scrollContainer.scrollTop;
    const maxScroll = scrollContainer.scrollHeight - scrollContainer.clientHeight;

    return {
      clientH: scrollContainer.clientHeight,
      scrollH: scrollContainer.scrollHeight,
      initialTop,
      finalTop,
      maxScroll,
      canScrollToBottom: finalTop >= maxScroll - 2,
    };
  });

  console.log(`Resolution ${width}x${height}:`, result);
  await browser.close();
}

async function run() {
  await testResolution(1440, 900);
  await testResolution(1280, 720);
}

run().catch(console.error);
