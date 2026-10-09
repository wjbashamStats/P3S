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

const HEAD = 'Week 6 · Saturday October 10, 2026';

const QA_NOTE = "Every figure below is checked against the source data before it is written. Team grades, five-factor ranks and per-game scoring come from the 2026 PFF team grades and the season-to-date CFBData ranks; each player's role, share and production come from the 2026 PFF season files. Per-game scoring uses each team's own game count, which is four, five or six this week. Where a rank ends in .5 the teams are tied and it is written as “tied Nth”. All fifteen kickoffs are verified Saturday in Eastern time.";

const SOURCE_NOTE = "Ratings and the Five Factors come from the 2026 workbook: SP+, TAN, implied team totals and the season-to-date CFBData ranks, out of 138 teams. Player lines are 2026 PFF season to date. Records, ATS and over/under records are TeamRankings, 2026 to date. The PFF team grade file covers five games for 103 teams, four for 25 and six for 10.";

const RECORD_NOTE = "Season to date: 25-30-2 and two voids, down 8.69 units across 59 picks. Spreads 7-13 (-7.30u), totals 9-8-2 (+0.20u), props 9-9 and two voids (-1.59u). Week 5 went 7-7 with a void, -0.78 units, the best week so far.";

const METHOD_NOTE = "A change this week, forced by the first proper test of the method. Every game of weeks 4 and 5 now has a verified final score, recovered by differencing the PFF points-for and points-against columns, so each signal could be scored on all 93 games rather than only the fifteen that were bet. The residual — the measure this card selected totals on for three weeks — went 42-49 across those games and lost money at every threshold. It is the worst of the three signals tested and it is no longer used for selection. It is still reported on every pick, because it was the stated method and because hiding a measure that disagrees would be the wrong lesson to take.";

const DOCS = [
  { file: 'Week6_Spreads.docx', withImages: true, items: C.spreads,
    title: 'Spreads to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE,
      'Five spreads where two measures built from different inputs agree on a side. The model number is the SP+ differential plus home field. The points check uses only each team’s own 2026 point differential plus home field, and shares no input with SP+. Candidates are ranked by the weaker of the two distances, so nothing qualifies on one strong reading alone.',
      'Across the 44 rated Saturday games the model sits 0.8 points more toward the away side than the market does, and each gap is quoted net of that level. The standing exclusion applies: do not lay a price into a team whose ATS record is running ahead of its rating. It removed James Madison -7.5 this week, which was otherwise the fifth pick — Georgia Southern are 4-1 against the spread, and that is the shape that cost this card four times in weeks 2 and 3. UCF +10.5 takes its place.',
      'The record demands a plain statement. Spreads are 7-13 and -7.30 units, the worst of the three categories, and the same 93-game test that condemned the totals residual found nothing in the spread signals either: the model gap net of slate level went 13-12 at the threshold this card bets, and the points check 31-29. Both are coin flips. These five are the least-bad application of a method with no demonstrated edge, and they are sized like everything else rather than backed with any confidence that the category works.',
      SOURCE_NOTE] },

  { file: 'Week6_Totals.docx', withImages: true, items: C.totals,
    title: 'Totals to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE, METHOD_NOTE,
      'What replaces it: the points check and the model gap, each with the slate’s own level removed, required to agree on a side and ranked by the weaker of the two. De-meaning matters more than it sounds. The raw points check runs +3.2 across this slate and is positive in 36 of 44 games, so ranking on it unadjusted would simply find the biggest Overs — and blind Overs went 51-40 across weeks 4 and 5, which is the same 56% the unadjusted check posted. Subtracting the slate level is what separates a signal from the base rate.',
      'The opponent-blindness the residual was built to correct is real and still growing. The correlation between a game’s average defensive Success Rate rank and the model’s Over lean is -0.77 this week, after -0.13, -0.46, -0.73 and -0.66 in weeks 2 through 5, and the slope has steepened every single week. The bias exists. Removing it also removed whatever signal sat alongside it, which is the finding, and it suggests the market over-adjusts for defensive quality rather than the model under-adjusting.',
      'Honest about the sample: 93 games across two weeks, and nothing tested reached statistical significance. The strongest result had a one-in-nine chance of arising from coin flips. What the test does establish is a ranking, and the residual is last. Totals are 9-8-2 and +0.20 units on the season, the only category in the black.',
      SOURCE_NOTE] },

  { file: 'Week6_Player_Props.docx', withImages: false, items: C.props,
    title: 'Player Props to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE,
      'Five props, each cleared through eight screens rather than taken off raw projected edge. A model edge of at least 20%; the player’s own 2026 production agreeing with the side by at least 20%; a real role, 20+ targets for receivers and 12+ carries a game for backs; 4+ targets a game for any receiving Over; no opponent or pace multiplier outside 0.6 to 1.6; a spread under 28 points with a rated opponent; at least two books posting the number; and the player’s own game count level with his team’s. 273 priced rows came in and eleven came out.',
      'Every one of the eleven survivors carries a pace multiplier above 1.0, between 1.16 and 1.41, so the whole board is script-inflated this week. Each projection below is therefore discounted and every position is stated against the player’s own per-game rate instead. All five clear on that rate alone, before the model is consulted.',
      'Last week’s props are the reason that paragraph exists. Jadan Baugh was taken at 118.0 off a 145.0 average and a 1.471 multiplier and went for 13 yards on 12 carries. A back with a 52% breakaway share has exactly that downside, and the write-up said so. Adam Mohammed was a void: California played, he did not, and his season line is unchanged. The availability screen checks a player against his team at the moment of posting and cannot catch a late scratch, which is a limit of the screen rather than a failure of it.',
      'Quarterback rushing props remain excluded. Sacks count against rushing yards in official college statistics and not in PFF, so the model projects a stat the market is not pricing.',
      SOURCE_NOTE] },
];

(async () => {
  for (const d of DOCS) {
    const doc = buildDoc(d);
    const buf = await Packer.toBuffer(doc);
    fs.writeFileSync(path.join(OUT, d.file), buf);
    console.log(d.file, (buf.length / 1024 / 1024).toFixed(2), 'MB');
  }
})();
