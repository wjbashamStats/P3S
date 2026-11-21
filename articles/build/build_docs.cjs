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

const HEAD = 'Week 12 \u00b7 Saturday November 21, 2026';

const QA_NOTE = "Every figure in this card is checked against the source data before it is written. Team grades, five-factor ranks and per-game scoring come from the 2026 PFF team grades and the season-to-date CFBData ranks; each player's role, share and production come from the 2026 PFF season files. Per-game scoring uses each team's own game count, which is nine, ten or eleven this week. Where a rank ends in .5 the teams are tied and it is written as \u201ctied Nth\u201d. Every kickoff on this card is verified Saturday in Eastern time, every prop player was checked against this morning's depth chart, and every venue against the National Weather Service forecast at kickoff.";

const SOURCE_NOTE = "Ratings and the Five Factors come from the 2026 workbook: SP+, TAN, implied team totals and the season-to-date CFBData ranks, out of 138 teams. Player lines are 2026 PFF season to date. Records, ATS and over/under records are TeamRankings, 2026 to date. The PFF team grade file covers ten games for 121 teams, eleven for 15 and nine for 2. Futures prices are the week 12 pull except win totals, which are week 7 and are no longer published.";

const RECORD_NOTE = "Season to date: 61-65-5 and two voids, down 11.19 units across 133 graded picks. Spreads 20-29-3 (-11.90u), totals 13-18-2 (-6.80u), props 27-18 and two voids (+6.51u), first-half spreads 1-0 (+1.00u). Props have won five weeks running. Week 11 went 3-2-1 and gained 0.80 units.";

const NO_TOTALS = "Totals return for the first time since week 7, which went 0-5. The category is 13-18-2 and down 6.80 units for the season and was retired for cause, so these two were put through a filter the earlier ones were not: both the model and the points check must agree, and the same points check run on each side's last four games must agree as well. Three candidates that cleared the first two tests were dropped because recent scoring contradicted them. Quarterback availability is reported in each pick's table where a starter has missed time, and is not used to remove picks: doing that in week 11 removed two winners.";

const DOC = {
  file: 'Week12_Betting_Card.docx',
  title: 'Week 12 Betting Card',
  subtitle: HEAD,
  lede: [],
  sections: [
    { title: 'Spreads', withImages: true, items: C.spreads,
      intro: [],
    },
    { title: 'Totals', withImages: false, items: C.totals || [],
      intro: [],
    },
    { title: 'Player Props', withImages: false, items: C.props,
      intro: [],
    },
  ],
};

(async () => {
  const doc = buildOneDoc(DOC);
  const buf = await Packer.toBuffer(doc);
  fs.writeFileSync(path.join(OUT, DOC.file), buf);
  console.log(DOC.file, (buf.length / 1024 / 1024).toFixed(2), 'MB');
})();
