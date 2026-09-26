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
    kids.push(new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { after: 40 },
      children: [new TextRun({ text: it.pick })] }));
    kids.push(new Paragraph({ spacing: { after: 200 },
      children: [new TextRun({ text: it.game || it.player, color: '5A6270', size: 21 })] }));
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
    styles: { default: {
      document: { run: { font: 'Calibri', size: 22, color: '1A1D23' } },
      heading1: { run: { font: 'Calibri', size: 40, bold: true, color: '11161F' } },
      heading2: { run: { font: 'Calibri', size: 30, bold: true, color: '11161F' } },
    } },
    sections: [{
      properties: { page: { size: { width: LETTER.width, height: LETTER.height, orientation: PageOrientation.PORTRAIT },
                            margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
      children: kids,
    }],
  });
}

const HEAD = 'Week 4 \u00b7 Saturday September 26, 2026';
const QA_NOTE = "Every figure here is checked against the underlying data before it is written: grade, rank and per-game scoring claims are re-derived from team_pff_grades_2026.csv and the built board, and each player's role, carry or target share and production from the 2026 PFF season files. Kickoffs verified: all picks are Saturday in Eastern time, including the two that read Sunday in UTC.";
const SOURCE_NOTE = "Ratings and the Five Factors come from the 2026 workbook (SP+, TAN, team totals, and the CFBData26 season-to-date ranks, out of 138 teams). Player lines are 2026 PFF season to date. Records, ATS and over/under are TeamRankings, 2026 to date. The PFF team grade file was refreshed this week and now covers the same three games as the records, so points for and against are quoted per game.";
const RECORD_NOTE = "Season to date: 13-16-1, down 4.85 units across 30 picks. Spreads 3-7 (-4.70u), totals 5-4-1 (+0.60u), props 5-5 (-0.75u).";

const DOCS = [
  { file: 'Week4_Spreads.docx', withImages: true, items: C.spreads,
    title: 'Spreads to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE,
            'Five spreads where the book and the 2026 power ratings disagree most. The model number is SP+ differential plus home field edge; the gap is the distance between it and the market.',
            'Two things shape the selection. First, the slate has a level: across the 49 rated games the model sits 1.57 points more toward the home favorite than the book does, so each gap is quoted both raw and after that level is removed. Second, the pattern in the losses is explicit. Seven of the ten spread picks so far have lost, and four of those seven were the same shape: laying a price against a team whose ATS record was running ahead of its rating. Georgia State beat that fade twice and Middle Tennessee once. Jacksonville State -7.0 was the largest de-meaned gap on this board and is not here, because it is a fade of a 3-0 ATS Middle Tennessee. Northern Illinois +10.5 is not here for the same reason.',
            'All five were cross-checked against a second measure built only from each team\u2019s own 2026 point differential plus home field, independent of SP+. All five agree with the model on direction, which is not true of the totals board.',
            SOURCE_NOTE] },
  { file: 'Week4_Totals.docx', withImages: true, items: C.totals,
    title: 'Totals to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE,
            'Four totals rather than five, because a fifth is not supported this week. That is the finding, not a formatting choice.',
            'The predicted total sums two team-total ratings that are not adjusted for the opponent, while the market is. The consequence is measurable: across this slate the correlation between a game\u2019s average defensive Success Rate rank and the size of the model\u2019s Over lean is -0.73, and it was -0.13 in week 2 and -0.46 in week 3, so the bias is growing as offensive rates accumulate. The model leans Over by 4.1 points in games with two top-45 defenses and Under by 3.1 where both are bottom-45. That is one missing adjustment showing up many times, and it is what produced Over 45.5 into a 6th-ranked defense at New Mexico/Oklahoma for a game that landed on 20.',
            'Each candidate is therefore put through four checks: the residual, which is the part of the model\u2019s disagreement with the book that the defensive tilt does not explain; a points-based expectation blending each team\u2019s own scoring with what the opponent allows; the two teams\u2019 own over/under records; and tempo. Exactly one game on the 49-game board passes all four, and it leads this card. Three more pass three of four or carry the two strongest signals. Nothing else clears, so nothing else is here.',
            'Iowa at Michigan is the largest raw gap on the slate at 15.4 points and is not on this card. Its residual is the highest at +7.3, but the points-based check puts the game at 40.8 against a book total of 38.5, both defenses rank inside the top 20, and Michigan is scoring 27.3 a game. That is the profile the correction exists to catch rather than to rescue.',
            'Honest caveat on the method: the residual is diagnosed from the slate structure, where -0.73 across 49 games is not noise, but it is not validated against results. On the ten graded totals it moves the correlation with the closing margin from +0.17 to +0.21 and leaves direction at 5 of 10, which at that sample says nothing either way. The other three checks are ordinary football arithmetic and are there precisely because the residual alone is unproven.',
            SOURCE_NOTE] },
  { file: 'Week4_Player_Props.docx', withImages: false, items: C.props,
    title: 'Player Props to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE,
            'Five props, each cleared through seven screens rather than taken off raw projected edge. A model edge of at least 20%; the player\u2019s own 2026 production agreeing with the side by at least 20%; a real role, 20+ routes for receivers and 12+ carries for backs; 4+ targets a game for any receiving Over; no opponent or pace multiplier outside 0.6 to 1.6; a spread under 28 points with a rated opponent; and at least two books posting the number. 623 priced rows came in, 28 came out. All five production figures below were re-derived directly from the PFF season files as a final check.',
            'Quarterback rushing props are excluded, as they were in week 3, and this week\u2019s numbers confirm why. Sacks count against rushing yards in official college statistics and not in PFF, so the model is projecting a stat the book is not pricing. Across the 48 QB rushing props on this board the mean model edge is +54.4% against +6.1% for running backs, and 83% lean Over. Subtracting sack yardage at seven yards a sack cuts the average gap between PFF production and the posted line from 13.2 yards to 3.6 while leaving the correlation at 0.83. The market is pricing this correctly and the model is not.',
            'Passing yardage has the opposite problem and is also worth knowing about. Across 69 priced quarterbacks the model projects 42.6 yards a game below each passer\u2019s own 2026 rate while the book sits 8.4 below it, so the model\u2019s pass-yards Unders are mostly the blend shrinking toward a thin prior rather than a read on the passer. The 2026-production screen is what catches this, and only Unders whose own season rate already sits below the line get through.',
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
