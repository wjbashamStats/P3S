const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const path = require('path');
const PAGE_PATH = path.join(__dirname, 'diversions_page.html');
const GAMES = [
  ['Eastern Michigan',   'Eastern_Michigan_at_UMass'],
  ['Virginia Cavaliers', 'Virginia_at_Florida_State'],
  ['Syracuse',           'Syracuse_at_UConn'],
  ['Western Michigan',   'Western_Michigan_at_Buffalo'],
  ['Ohio Bobcats',       'Ohio_at_Kent_State'],
  ['Stanford',           'Stanford_at_Wake_Forest'],
  ['California',         'California_at_UNLV'],
  ['Washington Huskies', 'Washington_at_USC'],
  ['Miami Hurricanes',   'Miami_at_Clemson'],
];
const SECTION_RANGES = [
  ['Five Factors', 'Power Ratings', 'context'],
  ['Unit Matchups', 'Starter Matchups', 'matchups'],
];
async function captureRange(page, fromText, toText, outPath) {
  const box = await page.evaluate(([fromText, toText]) => {
    const hs = Array.from(document.querySelectorAll('.section-h'));
    const fromH = hs.find(h => h.textContent.trim() === fromText);
    const toH = hs.find(h => h.textContent.trim() === toText);
    if (!fromH || !toH) return null;
    const fromDiv = fromH.closest('.modal-body > div');
    const toDiv = toH.closest('.modal-body > div');
    const card = document.querySelector('.modal-card');
    const c = card.getBoundingClientRect(), f = fromDiv.getBoundingClientRect(), t = toDiv.getBoundingClientRect();
    return { x: c.x, y: f.y, width: c.width, height: t.bottom - f.top };
  }, [fromText, toText]);
  if (!box || box.height <= 0) return false;
  await page.screenshot({ path: outPath, clip: { x: Math.max(0,box.x), y: Math.max(0,box.y), width: box.width, height: box.height } });
  return true;
}
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1000, height: 4200 }, deviceScaleFactor: 2 });
  await page.goto('file://' + PAGE_PATH);
  await page.waitForSelector('#rows tr');
  for (const [term, outName] of GAMES) {
    await page.fill('#searchBox', term);
    await page.waitForTimeout(150);
    const rows = await page.$$('#rows tr:not([hidden])');
    if (!rows.length) { console.error('NO MATCH', term); continue; }
    if (rows.length > 1) console.error('MULTI', term, rows.length, await Promise.all(rows.map(r=>r.innerText())));
    await rows[0].click();
    await page.waitForSelector('.modal-scrim:not([hidden])');
    await page.waitForTimeout(250);
    for (const [a,b,suffix] of SECTION_RANGES) {
      const ok = await captureRange(page, a, b, path.join(__dirname, `${outName}_${suffix}.png`));
      console.log(ok ? 'shot ' : 'FAIL ', outName, suffix);
    }
    await page.keyboard.press('Escape').catch(()=>{});
    await page.waitForTimeout(120);
    await page.fill('#searchBox', '');
    await page.waitForTimeout(80);
  }
  await browser.close();
})();
