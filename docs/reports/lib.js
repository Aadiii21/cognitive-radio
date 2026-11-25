// Shared helpers for the part reports (docx-js). A4, 1-inch margins.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, AlignmentType,
  HeadingLevel, WidthType, ShadingType, BorderStyle, LevelFormat, Header, Footer, PageNumber,
  PageBreak,
} = require("docx");

const ROOT = path.resolve(__dirname, "..", "..");
const CONTENT_W = 9026; // A4 11906 - 2 * 1440
const FONT = "Calibri";
const COLORS = { 0: "1F3864", 1: "2F5D8A", 2: "2E7D57", 3: "B8621B" };

function runs(text, base = {}) {
  // **bold** and `code` inline markup
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), font: "Consolas", size: 19, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

const P = (text, opts = {}) => new Paragraph({ children: runs(text), spacing: { after: 120 }, ...opts });
const H1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
const H2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
const B = (items) => items.map((t) => new Paragraph({ numbering: { reference: "bullets", level: 0 }, children: runs(t), spacing: { after: 60 } }));
const NUM = (items) => items.map((t) => new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: runs(t), spacing: { after: 60 } }));

function CODE(lines) {
  return lines.map((l, i) => new Paragraph({
    children: [new TextRun({ text: l || " ", font: "Consolas", size: 18 })],
    shading: { type: ShadingType.CLEAR, fill: "F3F3F3" },
    spacing: { after: i === lines.length - 1 ? 160 : 0 },
    indent: { left: 200 },
  }));
}

function NOTE(text, color = "FFF6E0") {
  return new Paragraph({
    children: runs(text), spacing: { before: 80, after: 160 },
    shading: { type: ShadingType.CLEAR, fill: color },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: "C98A1B", space: 8 } },
    indent: { left: 160, right: 160 },
  });
}

const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const borders = { top: border, bottom: border, left: border, right: border };

function T(headers, rows, fracs, part = 1) {
  const widths = fracs.map((f) => Math.floor(CONTENT_W * f));
  widths[widths.length - 1] = CONTENT_W - widths.slice(0, -1).reduce((a, b) => a + b, 0);
  const cell = (text, i, head) => new TableCell({
    borders, width: { size: widths[i], type: WidthType.DXA },
    shading: head ? { fill: COLORS[part], type: ShadingType.CLEAR } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: String(text).split("\n").map((line) => new Paragraph({
      children: runs(line, { size: 18, ...(head ? { bold: true, color: "FFFFFF" } : {}) }),
    })),
  });
  return [new Table({
    width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, i, true)) }),
      ...rows.map((r) => new TableRow({ children: r.map((c, i) => cell(c, i, false)) }))],
  }), new Paragraph({ spacing: { after: 120 }, children: [] })];
}

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

let figNo = 0;
function FIG(rel, caption, maxWIn = 6.27, maxHIn = 8.2) {
  const file = path.join(ROOT, rel);
  const { w, h } = pngSize(file);
  let wi = maxWIn, hi = (maxWIn * h) / w;
  if (hi > maxHIn) { hi = maxHIn; wi = (maxHIn * w) / h; }
  figNo += 1;
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(file),
        transformation: { width: Math.round(wi * 96), height: Math.round(hi * 96) },
        altText: { title: caption, description: caption, name: path.basename(rel) } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [new TextRun({ text: `Figure ${figNo}. `, bold: true, size: 18 }), ...runs(caption, { size: 18, italics: true })] }),
  ];
}

function cover(part, title, subtitle) {
  const c = COLORS[part];
  return [
    new Paragraph({ spacing: { before: 1800 }, children: [new TextRun({ text: "Cognitive Radio Project", size: 28, color: "666666" })] }),
    new Paragraph({ spacing: { before: 120 }, children: [new TextRun({ text: `Part ${part} Report`, size: 52, bold: true, color: c })] }),
    new Paragraph({ spacing: { before: 120, after: 240 }, children: [new TextRun({ text: title, size: 36, bold: true })] }),
    new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: c, space: 4 } }, children: [] }),
    new Paragraph({ spacing: { before: 240 }, children: runs(subtitle, { size: 22 }) }),
    new Paragraph({ spacing: { before: 600 }, children: [new TextRun({ text: "Project: ", bold: true }),
      new TextRun("Design and Implementation of a Cost-Aware Cognitive Radio Framework for Joint Channel Switching and Adaptive Modulation")] }),
    new Paragraph({ spacing: { before: 160 }, children: [new TextRun({ text: "Team member responsible: ", bold: true }), new TextRun("______________________________")] }),
    new Paragraph({ spacing: { before: 160 }, children: [new TextRun({ text: "Roll number: ", bold: true }), new TextRun("______________________________")] }),
    new Paragraph({ spacing: { before: 160 }, children: [new TextRun({ text: "Date: ", bold: true }), new TextRun("25 November 2026")] }),
    new Paragraph({ spacing: { before: 600 }, children: runs("The project is divided into three equal parts: **Part 1** simulation, cognitive control and ML analysis; **Part 2** physical layer, calibration, receivers and the DL classifier; **Part 3** SDR hardware integration and over-the-air experiments. This report covers Part " + part + ": the code it contains, the outputs it produces and what each output means.", { size: 20, color: "444444" }) }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

function build(part, outName, children) {
  const c = COLORS[part];
  const doc = new Document({
    creator: "Cognitive radio team", title: part ? `Part ${part} report` : "Master report",
    styles: {
      default: { document: { run: { font: FONT, size: 22 } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font: FONT, size: 32, bold: true, color: c },
          paragraph: { spacing: { before: 360, after: 160 }, keepNext: true, outlineLevel: 0 } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font: FONT, size: 26, bold: true, color: "333333" },
          paragraph: { spacing: { before: 240, after: 120 }, keepNext: true, outlineLevel: 1 } },
      ],
    },
    numbering: { config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
      { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    ] },
    sections: [{
      properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
      headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: part ? `Cognitive Radio Project  |  Part ${part}` : "Cognitive Radio Project  |  Master Report", size: 16, color: "888888" })] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES], size: 16, color: "888888" })] })] }) },
      children,
    }],
  });
  figNo = 0;
  return Packer.toBuffer(doc).then((buf) => {
    const out = path.join(__dirname, outName);
    fs.writeFileSync(out, buf);
    console.log("wrote", path.relative(ROOT, out));
  });
}

module.exports = { COLORS, runs, P, H1, H2, B, NUM, CODE, NOTE, T, FIG, cover, build, resetFig: () => { figNo = 0; } };
