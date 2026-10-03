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

function buildDoc({ title, subtitle, intro, items, withImages }) {
  const kids = [
    new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { after: 60 },
      children: [new TextRun({ text: title })] }),
    new Paragraph({ spacing: { after: 240 },
      children: [new TextRun({ text: subtitle, italics: true, color: '5A6270', size: 21 })] }),
    ...intro.map(t => p(t)),
    rule(),
  ];
  items.forEach((it, idx) => {
    if (idx > 0) kids.push(new Paragraph({ children: [new PageBreak()] }));
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
  return new Document({
    creator: 'P3S',
    lastModifiedBy: 'P3S',
    title: title,
    styles: { default: {
      document: { run: { font: 'Calibri', size: 22, color: '1A1D23' } },
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

const HEAD = 'Week 5 · Saturday October 3, 2026';

const QA_NOTE = "Every figure below is checked against the source data before it is written. Team grades, five-factor ranks and per-game scoring come from the 2026 PFF team grades and the season-to-date CFBData ranks; each player's role, share and production come from the 2026 PFF season files. Per-game scoring uses each team's own game count, which is three, four or five this week. Where a rank ends in .5 the teams are tied and it is written as “tied Nth”. All fifteen kickoffs are verified Saturday in Eastern time.";

const SOURCE_NOTE = "Ratings and the Five Factors come from the 2026 workbook: SP+, TAN, implied team totals and the season-to-date CFBData ranks, out of 138 teams. Player lines are 2026 PFF season to date. Records, ATS and over/under records are TeamRankings, 2026 to date. The PFF team grade file covers four games for 120 teams, three for ten and five for eight.";

const RECORD_NOTE = "Season to date: 18-23-2 and one void, down 7.91 units across 44 picks. Spreads 5-10 (-6.00u), totals 6-6-2 (-0.60u), props 7-7 and one void (-1.31u).";

const SAMPLE_NOTE = "On sample size, stated once: 44 graded picks is far too few to establish or refute an edge. Separating a genuine 55% win rate from breakeven at -110 takes roughly 1,400 bets. Read what follows as positions with their reasoning and their risks written down, not as a demonstrated advantage.";

const DOCS = [
  { file: 'Week5_Spreads.docx', withImages: true, items: C.spreads,
    title: 'Spreads to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE,
      'Five spreads chosen on agreement between independent measures rather than on the size of the disagreement with the market. The model number is the SP+ differential plus home field. The points check is built only from each team’s own 2026 point differential plus home field, and shares no input with SP+.',
      'The reasoning behind that choice: a large gap between a public rating and the market is about as likely to mean the market knows something — an injury, a situational factor, a number that has already moved — as it is to mean there is value sitting there. Two measures built from different inputs landing on the same side is harder to dismiss. Every pick below clears that test, and the distance each measure puts between its own number and the market is quoted so the thin ones are visible.',
      'Across the 49 rated Saturday games the model sits 0.4 points more toward the home favourite than the market does, so each gap is quoted net of that level. One exclusion carries over: do not lay a price into a team whose ATS record is running ahead of its rating, a shape that accounted for four losses in weeks 2 and 3. It removes nothing this week, because no selected game fades a team covering at 75% or better.',
      'Spreads are the weakest of the three categories on the season at 5-10 and -6.00 units. ' + SAMPLE_NOTE,
      SOURCE_NOTE] },

  { file: 'Week5_Totals.docx', withImages: true, items: C.totals,
    title: 'Totals to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE,
      'Five totals, ranked on the residual. The predicted total sums two team-total ratings that are not adjusted for the opponent, while the market is, and that single missing adjustment accounts for most of what a raw disagreement with the market actually measures.',
      'The size of it is measurable. Across these 49 games the correlation between a game’s average defensive Success Rate rank and the model’s Over lean is -0.66, after -0.13 in week 2, -0.46 in week 3 and -0.73 in week 4. The mean lean is +1.7 points toward the Over and 31 of 49 games lean Over. Where both defences rank inside the top 45 the model leans Over by 8.9 points; where both sit in the bottom 45 it leans Under by 2.9. The residual is what survives once that tilt is fitted out, and it is what these five are ranked on.',
      'A points-based expectation — each team’s own scoring blended with what its opponent allows — is reported for every pick. It is not used to overrule the residual, and the reason is on the record: in week 4 four totals were replaced after that check disagreed, the four removed went 3-1, the four kept went 1-2-1, and the swap cost 3.10 units. This week the question does not arise. All five picks below have the residual and the points check leaning the same way, which is not usually the case.',
      'The method’s limits, plainly. A -0.66 correlation across 49 games is a real structural feature rather than noise, but the residual has never been validated against results. Totals are 6-6-2 and -0.60 units on the season, the least bad of the three categories, which is not the same as an edge. ' + SAMPLE_NOTE,
      SOURCE_NOTE] },

  { file: 'Week5_Player_Props.docx', withImages: false, items: C.props,
    title: 'Player Props to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE,
      'Five props, each cleared through eight screens rather than taken off raw projected edge. A model edge of at least 20%; the player’s own 2026 production agreeing with the side by at least 20%; a real role, 20+ targets for receivers and 12+ carries a game for backs; 4+ targets a game for any receiving Over; no opponent or pace multiplier outside 0.6 to 1.6; a spread under 28 points with a rated opponent; at least two books posting the number; and the player’s own game count level with his team’s. 533 priced rows came in and six came out.',
      'That eighth screen is availability, and it was added after a prop was posted last week on a player who had not appeared in his team’s fourth game: the season line was identical to the week before, which is the tell. It removed 23 priced players this week whose game count sits behind their own team’s.',
      'One further filter is applied by hand and is worth stating. Where the model’s projection leans on a pace or script multiplier far from 1.0, the projection is discounted and the position has to stand on the player’s own rate instead. Two of the five below are in that situation and both say so.',
      'The sixth survivor, Chas Nimrod Over 47.5, is not here. A 60.7 route grade facing an 89.7 coverage grade is a usage bet into a secondary built to take usage away, and the 20.4% edge is the smallest of the six. It is a reasonable position; it is just the one of the six with the least behind it.',
      'Quarterback rushing props are excluded, as in weeks 3 and 4. Sacks count against rushing yards in official college statistics and not in PFF, so the model projects a stat the market is not pricing. Across the 41 quarterback rushing props on this board the mean model edge is +53.6% against +3.0% for running backs, and 90% lean Over. The market has this right and the model does not.',
      SAMPLE_NOTE, SOURCE_NOTE] },
];

(async () => {
  for (const d of DOCS) {
    const doc = buildDoc(d);
    const buf = await Packer.toBuffer(doc);
    fs.writeFileSync(path.join(OUT, d.file), buf);
    console.log(d.file, (buf.length / 1024 / 1024).toFixed(2), 'MB');
  }
})();
