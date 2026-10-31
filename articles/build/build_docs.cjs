const fs = require('fs'), path = require('path');
const { Document, Packer, Paragraph, TextRun, HeadingLevel, ImageRun, PageBreak,
        Table, TableRow, TableCell, WidthType, ShadingType, AlignmentType,
        BorderStyle, PageOrientation } = require('docx');

const DIR = __dirname;
const OUT = '/home/user/P3S/articles';
fs.mkdirSync(OUT, { recursive: true });
const C = JSON.parse(fs.readFileSync(path.join(DIR, 'content.json'), 'utf8'));

const LETTER = { width: 12240, height: 15840 };
const MARGIN = 1080;                       // 0.75"
const CONTENT_DXA = LETTER.width - 2 * MARGIN;
const CONTENT_PX = Math.round(CONTENT_DXA / 1440 * 96);   // px at 96dpi

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
function image(file) {
  const { w, h } = pngSize(file);
  const width = CONTENT_PX, height = Math.round(CONTENT_PX * h / w);
  return new Paragraph({
    spacing: { before: 140, after: 140 },
    children: [new ImageRun({ type: 'png', data: fs.readFileSync(file),
                              transformation: { width, height } })],
  });
}
const p = (text, opts = {}) => new Paragraph({
  spacing: { after: 160, line: 276 },
  children: [new TextRun({ text, ...opts })],
});
const caption = (text) => new Paragraph({
  spacing: { after: 220 },
  children: [new TextRun({ text, italics: true, size: 17, color: '5A6270' })],
});

function factsTable(rows) {
  const L = Math.round(CONTENT_DXA * 0.38), R = CONTENT_DXA - L;
  const cell = (text, bold, width, shade) => new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: shade ? { type: ShadingType.CLEAR, fill: shade } : undefined,
    margins: { top: 60, bottom: 60, left: 120, right: 120 },
    children: [new Paragraph({ children: [new TextRun({ text, bold, size: 19 })] })],
  });
  return new Table({
    columnWidths: [L, R],
    width: { size: CONTENT_DXA, type: WidthType.DXA },
    rows: rows.map(([k, v], i) => new TableRow({
      children: [cell(k, false, L, i % 2 ? 'F4F5F7' : 'FFFFFF'),
                 cell(v, true, R, i % 2 ? 'F4F5F7' : 'FFFFFF')],
    })),
  });
}
const rule = () => new Paragraph({
  spacing: { before: 60, after: 240 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: 'C9CDD4', space: 1 } },
  children: [],
});

function sectionChildren({ title, intro, items, withImages }, isFirst) {
  const kids = [];
  if (!isFirst) kids.push(new Paragraph({ children: [new PageBreak()] }));
  kids.push(new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { after: 120 },
    children: [new TextRun({ text: title })] }));
  intro.forEach(t => kids.push(p(t)));
  kids.push(rule());
  items.forEach((it) => {
    kids.push(new Paragraph({ children: [new PageBreak()] }));
    kids.push(new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { after: 20 },
      children: [new TextRun({ text: it.game || it.player })] }));
    kids.push(new Paragraph({ heading: HeadingLevel.HEADING_3, spacing: { after: 200 },
      children: [new TextRun({ text: it.pick })] }));
    kids.push(factsTable(it.facts));
    kids.push(new Paragraph({ spacing: { after: 180 }, children: [] }));
    it.paras.forEach(t => kids.push(p(t)));
    if (withImages && it.img) {
      const a = path.join(DIR, `${it.img}_context.png`);
      const b = path.join(DIR, `${it.img}_matchups.png`);
      if (fs.existsSync(a)) {
        kids.push(image(a));
        kids.push(caption('Five Factors and power ratings, captured from the CFB Betting Hub.'));
      }
      if (fs.existsSync(b)) {
        kids.push(image(b));
        kids.push(caption('Unit matchups: each offensive unit grade against the opposing defensive unit. Edge = offense minus defense.'));
      }
    }
  });
  return kids;
}

function buildOneDoc({ title, subtitle, lede, sections }) {
  const kids = [
    new Paragraph({ heading: HeadingLevel.TITLE, spacing: { after: 60 },
      children: [new TextRun({ text: title })] }),
    new Paragraph({ spacing: { after: 240 },
      children: [new TextRun({ text: subtitle, italics: true, color: '5A6270', size: 21 })] }),
    ...lede.map(t => p(t)),
    rule(),
  ];
  sections.forEach((sec, i) => kids.push(...sectionChildren(sec, false)));
  return new Document({
    creator: 'P3S',
    lastModifiedBy: 'P3S',
    title: title,
    styles: { default: {
      document: { run: { font: 'Calibri', size: 22, color: '1A1D23' } },
      title: { run: { font: 'Calibri', size: 52, bold: true, color: '11161F' } },
      heading1: { run: { font: 'Calibri', size: 40, bold: true, color: '11161F' } },
      heading2: { run: { font: 'Calibri', size: 28, bold: true, color: '11161F' } },
      heading3: { run: { font: 'Calibri', size: 32, bold: true, color: '1B4D8F' } },
    } },
    sections: [{
      properties: { page: { size: { width: LETTER.width, height: LETTER.height, orientation: PageOrientation.PORTRAIT },
                            margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
      children: kids,
    }],
  });
}

const HEAD = 'Week 9 \u00b7 Saturday October 31, 2026';

const QA_NOTE = "Every figure in this card is checked against the source data before it is written. Team grades, five-factor ranks and per-game scoring come from the 2026 PFF team grades and the season-to-date CFBData ranks; each player's role, share and production come from the 2026 PFF season files. Per-game scoring uses each team's own game count, which is seven, eight or nine this week. Where a rank ends in .5 the teams are tied and it is written as \u201ctied Nth\u201d. All ten kickoffs are verified Saturday in Eastern time, every prop player was checked against this morning's depth chart, and every venue against the National Weather Service forecast at kickoff.";

const SOURCE_NOTE = "Ratings and the Five Factors come from the 2026 workbook: SP+, TAN, implied team totals and the season-to-date CFBData ranks, out of 138 teams. Player lines are 2026 PFF season to date. Records, ATS and over/under records are TeamRankings, 2026 to date. The PFF team grade file covers seven games for 84 teams, eight for 52 and nine for 2. Futures prices are the week 9 pull except win totals, which are week 7.";

const RECORD_NOTE = "Season to date: 43-50-3 and two voids, down 12.69 units across 98 picks. Spreads 14-20-1 (-8.00u), totals 12-15-2 (-4.50u), props 17-15 and two voids (-0.19u). Week 8 was the first winning week of the season at 5-4 and +0.60 units, and the first card with no totals on it.";

const NO_TOTALS = "No totals again this week. Week 7's five went 0-5 with the three Overs missing by 19, 25 and 20.5 points in games where both selection measures agreed, and the category stays out until that test has been scored across every game of weeks 6 through 8 rather than the ten that were bet.";

const DOC = {
  file: 'Week9_Betting_Card.docx',
  title: 'Week 9 Betting Card',
  subtitle: HEAD,
  lede: [
    'Ten positions for Saturday: five spreads and five player props. The slate is 45 rated Saturday games with a posted spread and total, and every pick below is drawn from that pool.',
    NO_TOTALS,
    "Spreads are selected on two measures built for every game: the model number, which is the SP+ differential plus home field, and the points check, which uses nothing but each team's own 2026 scoring and home field and shares no input with SP+. Each is taken relative to where the whole slate sits. A game qualifies only when both land on the same side, and candidates are ranked by the weaker of the two. Twenty of the 45 games had the two agreeing this week.",
    QA_NOTE,
    RECORD_NOTE,
  ],
  sections: [
    { title: 'Spreads', withImages: true, items: C.spreads,
      intro: [
        'Five spreads where the two measures agree on a side, and a better week for them than last. The strongest agreement on the board is 10.2 points against 4.9 last week, and all five positions take points rather than lay them.',
        'Across the 45 rated Saturday games the model sits 0.3 points more toward the home side than the market does, so the raw and adjusted readings are close to identical again.',
        'The standing exclusion applies and nothing triggered it: do not lay a price into a team whose record against the spread is running ahead of its rating. Since every pick here takes points, it could not.',
        SOURCE_NOTE,
      ] },
    { title: 'Player Props', withImages: false, items: C.props,
      intro: [
        '321 priced rows went through the screens and 22 survived. The screens: a model edge of at least 20 percent; the player\u2019s own 2026 production agreeing with the side by at least 20 percent; a real role, 20+ targets for receivers and 12+ carries a game for backs; 4+ targets a game for any receiving Over; no opponent or pace multiplier outside 0.6 to 1.6; a spread under 28 points with a rated opponent; at least two books posting the number; the player\u2019s own game count level with his team\u2019s; and two added this week.',
        'The two new ones both concern Unders. Yardage Unders are now dropped outright: across the season Overs have gone 15-10 with two voids for +3.46 units while Unders have gone 2-5 for -3.65, and the asymmetry has a reason behind it rather than only a record. The screens ask that a player\u2019s own production agree with the side by 20 percent, which on an Over means he has been beating the number and on an Under means he has been falling short of it \u2014 something the market reads as easily as we do. An Over\u2019s downside also stops at zero while an Under\u2019s is one long catch away. The second screen, held in reserve for when Unders are allowed back, requires a receiving Under to carry an average depth of target below 12.',
        'All five below are Overs, all five clear on the player\u2019s own per-game rate before the model is consulted, and all five were checked against this morning\u2019s depth chart and are listed first string at their position.',
        'Quarterback rushing props remain excluded. Sacks count against rushing yards in official college statistics and not in PFF, so the model projects a stat the market is not pricing.',
        SOURCE_NOTE,
      ] },
  ],
};

(async () => {
  const doc = buildOneDoc(DOC);
  const buf = await Packer.toBuffer(doc);
  fs.writeFileSync(path.join(OUT, DOC.file), buf);
  console.log(DOC.file, (buf.length / 1024 / 1024).toFixed(2), 'MB');
})();
