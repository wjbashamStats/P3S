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

const HEAD = 'Week 5 · Saturday October 3, 2026';

const QA_NOTE = "Every figure here is checked against the underlying data before it is written. Grades, ranks and per-game scoring are re-derived from team_pff_grades_2026.csv and the built board; each player's role, carry or target share and production come from the 2026 PFF season files; the model numbers, residuals and points checks are recomputed from diversions_2026wk5.json rather than carried over from the draft. That check caught real errors this week: a record off by a game, a set of truncated per-game averages, two carry shares that were wrong, and five spread cross-check figures that had been computed two different ways. All are corrected below. Kickoffs verified: all 15 picks are Saturday in Eastern time, including Fresno State at Washington State, which reads Sunday 01:30 in UTC and is 21:30 Saturday in Eastern. None had kicked off when the board was built.";

const SOURCE_NOTE = "Ratings and the Five Factors come from the 2026 workbook (SP+, TAN, team totals, and the CFBData26 season-to-date ranks, out of 138 teams). Player lines are 2026 PFF season to date. Records, ATS and over/under are TeamRankings, 2026 to date. The PFF team grade file now covers four games for 120 teams, three for ten and five for eight, so points for and against are quoted per game against each team's own count. Where a rank ends in .5 the teams are tied and it is written as “tied Nth”.";

const RECORD_NOTE = "Season to date: 18-23-2 and one void, down 7.91 units across 44 picks. Spreads 5-10 (-6.00u), totals 6-6-2 (-0.60u), props 7-7 and one void (-1.31u).";

const DOCS = [
  { file: 'Week5_Spreads.docx', withImages: true, items: C.spreads,
    title: 'Spreads to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE,
      'Five spreads where the book and the 2026 power ratings disagree most. The model number is SP+ differential plus home field edge; the gap is the distance between it and the market.',
      'Across the 49 rated Saturday games the model sits 0.4 points more toward the home favorite than the book does, so each gap is quoted raw and after that level is removed. Last week the same figure was 1.57. This slate is close to neutral, and the de-meaning barely reorders anything.',
      'The selection rule is explicit. Candidates are ranked by the model gap once the slate level is out, and a second measure — built only from each team’s own 2026 point differential plus home field, independent of SP+ — has to agree on which side. It screens direction and nothing else; it is not allowed to reorder the card. Two candidates fail it and are not here: Texas Tech -13.0, where the points measure has them by 7.8 rather than 13, and Memphis -20.5, where it has them by 9.8 rather than 20.5. Last week’s exclusion also stands — do not lay a price into a team whose ATS record is running ahead of its rating, which cost this card four times in weeks 2 and 3 — and this week it removes nothing, because none of the top candidates is that shape.',
      'The honest caveat is the record. Spreads are the worst category on this card at 5-10 and -6.00 units, and the rule behind them has changed more than once already this season. What is different about this one is that it is written down before the results arrive and the number that drives it is reported for every pick, including the one where it says there is nothing to win.',
      SOURCE_NOTE] },

  { file: 'Week5_Totals.docx', withImages: true, items: C.totals,
    title: 'Totals to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE,
      'Five totals, ranked by residual. The predicted total sums two team-total ratings that are not adjusted for the opponent, while the market is, and that single missing adjustment is most of what the model’s disagreement with the book actually measures.',
      'The size of it is measurable. Across these 49 games the correlation between a game’s average defensive Success Rate rank and the model’s Over lean is -0.66, after -0.13 in week 2, -0.46 in week 3 and -0.73 in week 4. The model’s mean lean is +1.7 points toward the Over and 31 of 49 games lean Over. In the two games where both defenses rank inside the top 45 it leans Over by 8.9 points; in the eight where both sit in the bottom 45 it leans Under by 2.9. The residual is what is left of each gap once that tilt is fitted out, and it is what this card selects on.',
      'A points-based expectation — each team’s own scoring blended with what its opponent allows — is reported for every pick and acted on for none. Week 4 tested the other way round: four totals were replaced after that check disagreed with the residual, the four removed went 3-1, the four kept went 1-2-1, and the swap cost 3.10 units. Three of those four substitutions were simply wrong. So the check is here as information, and where it disagrees the card says so and takes the residual anyway. One of the five below is a pick the check argues against outright, and a second sits within half a point of neutral.',
      'Honest caveat on the method: -0.66 across 49 games is a real structural feature, not noise, but the residual is still not validated against results. Totals are 6-6-2 and -0.60 units on the season, the least bad of the three categories, which is not the same as a demonstrated edge.',
      SOURCE_NOTE] },

  { file: 'Week5_Player_Props.docx', withImages: false, items: C.props,
    title: 'Player Props to Target', subtitle: HEAD,
    intro: [QA_NOTE, RECORD_NOTE,
      'Five props, each cleared through eight screens rather than taken off raw projected edge. A model edge of at least 20%; the player’s own 2026 production agreeing with the side by at least 20%; a real role, 20+ targets for receivers and 12+ carries a game for backs; 4+ targets a game for any receiving Over; no opponent or pace multiplier outside 0.6 to 1.6; a spread under 28 points with a rated opponent; at least two books posting the number; and the player’s own game count level with his team’s. 533 priced rows came in and six came out, so this card is the survivor list almost in full.',
      'The eighth screen is new and it exists because of a void. Hollywood Smothers Over 52.0 was posted last week for a player who had not played in his team’s fourth game: his season line was identical to the week before and nobody checked. Availability is now a hard screen, and this week it removed 23 priced players whose game count sits behind their own team’s.',
      'The sixth survivor, Asaad Waseem Over 61.5, is not on the card. It carries a larger edge than three of the five that are, and it was passed over because this card already holds two positions in that same game on the other side of it. The reasoning is written out under Chas Nimrod below rather than hidden here, because it is a portfolio decision and not an argument about the player.',
      'Quarterback rushing props are excluded, as in weeks 3 and 4, and this week’s numbers confirm why again. Sacks count against rushing yards in official college statistics and not in PFF, so the model is projecting a stat the book is not pricing. Across the 41 QB rushing props on this board the mean model edge is +53.6% against +3.0% for running backs, and 90% lean Over. The market is pricing this correctly and the model is not.',
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
