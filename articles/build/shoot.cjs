const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const path = require('path');
const PAGE_PATH = path.join(__dirname, 'diversions_page.html');
const GAMES = [
  ['UMass Minutemen',           'UMass_at_Buffalo'],
  ['Notre Dame',                'Notre_Dame_at_BYU'],
  ['Mississippi State Bulldogs','Mississippi_State_at_LSU'],
  ['Missouri Tigers',           'Missouri_at_Ole_Miss'],
  ['Northern Illinois',         'Northern_Illinois_at_Wyoming'],
  ['Wisconsin',                 'Wisconsin_at_UCLA'],
  ['Nebraska',                  'Nebraska_at_Oregon'],
  ['Oklahoma State',            'Oklahoma_State_at_Houston'],
  ['Georgia Tech',              'Georgia_Tech_at_Virginia_Tech'],
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
