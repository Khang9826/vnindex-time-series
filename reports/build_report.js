/**
 * Sinh bao cao Word (.docx) cho du an "Phan tich du lieu chuoi thoi gian VN-Index".
 *
 * NGUYEN TAC: moi con so trong bao cao deu duoc DOC TRUC TIEP tu cac tep ket qua
 * trong results/ va data/raw/ do pipeline sinh ra. Khong co so lieu nao duoc go
 * tay vao tep nay. Neu mot thanh phan chua duoc thuc thi, bao cao danh dau ro
 * "CHUA DANH GIA / NOT YET EVALUATED".
 *
 * Chay:
 *   NODE_PATH=<duong_dan_node_modules> node reports/build_report.js
 */

const fs = require("fs");
const path = require("path");
const {
  AlignmentType, BorderStyle, Document, Footer, Header, HeadingLevel,
  ImageRun, LevelFormat, MathFraction, MathRun, MathSubScript,
  MathRadical, MathSubSuperScript, MathSuperScript, NumberFormat, PageBreak, PageNumber, Packer, Paragraph,
  SectionType, SequentialIdentifier, ShadingType, Table, TableCell, TableRow,
  TableOfContents, TextRun, VerticalAlign, WidthType,
} = require("docx");

// `docx` exports a class named `Math`, which would shadow the global Math
// object for the whole module. Alias it so both stay usable.
const DocxMath = require("docx").Math;

const ROOT = path.resolve(__dirname, "..");
const R = (p) => path.join(ROOT, p);

// ---------------------------------------------------------------------------
// Doc du lieu ket qua
// ---------------------------------------------------------------------------
const readJSON = (p) => JSON.parse(fs.readFileSync(R(p), "utf8"));

function readCSV(p) {
  const text = fs.readFileSync(R(p), "utf8").trim();
  const lines = text.split(/\r?\n/);
  const parse = (line) => {
    const out = [];
    let cur = "", q = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (c === '"') { if (q && line[i + 1] === '"') { cur += '"'; i++; } else q = !q; }
      else if (c === "," && !q) { out.push(cur); cur = ""; }
      else cur += c;
    }
    out.push(cur);
    return out;
  };
  const head = parse(lines[0]);
  return lines.slice(1).map((l) => {
    const cells = parse(l);
    return Object.fromEntries(head.map((h, i) => [h, cells[i]]));
  });
}

const meta = readJSON("data/raw/vnindex_raw_meta.json");
const quality = readJSON("results/data_quality_report.json");
const cross = readJSON("results/source_crosscheck.json");
const eda = readJSON("results/eda_results.json");
const acorr = readJSON("results/autocorrelation.json");
const desc = readCSV("results/descriptive_statistics.csv");
const norm = readCSV("results/normality_tests.csv");
const stat = readCSV("results/stationarity_tests.csv");
const ljung = readCSV("results/ljung_box_tests.csv");

// --- multi-series layer ----------------------------------------------------
const inventory = readJSON("results/series_inventory.json");
const squality = readJSON("results/series_quality.json");
const battery = readJSON("results/multiseries_battery.json");
const crossFam = readCSV("results/cross_family_checks.csv");

const BY = Object.fromEntries(battery.series.map((s) => [s.key, s]));
const matched1D = battery.matched_period_comparison["1D"];
const corr1D = battery.return_correlations["1D"];
const scaleVNI = Object.fromEntries(
  battery.frequency_scaling.VNINDEX.rows.map((r) => [r.timeframe, r])
);
const totalBars = Object.values(inventory).reduce((a, m) => a + m.n_rows, 0);
const nPrimary = battery.series.length;
const nTrimmed = Object.values(inventory).filter((m) => m.trim && m.trim.applied).length;
const nNonStationary = battery.series.filter((s) => s.level_verdict === "NON-STATIONARY").length;
const nNonNormal = battery.series.filter((s) => s.jarque_bera.reject_normal).length;
const nAmbiguous = battery.series.filter((s) => s.return_verdict !== "STATIONARY");

// ---------------------------------------------------------------------------
// Dinh dang so
// ---------------------------------------------------------------------------
const num = (v, d = 4) => {
  const x = Number(v);
  if (!isFinite(x)) return String(v);
  return x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
};
const int = (v) => Number(v).toLocaleString("en-US");
const pv = (v) => {
  const x = Number(v);
  if (x === 0) return "< 1e-300";
  if (x < 0.001) return x.toExponential(2).replace("e", "e");
  return x.toFixed(4);
};
const descBy = (name) => desc.find((r) => r.series === name);

// ---------------------------------------------------------------------------
// Helpers tao noi dung
// ---------------------------------------------------------------------------
const FONT = "Times New Roman";

const P = (text, opts = {}) =>
  new Paragraph({
    alignment: opts.align || AlignmentType.JUSTIFIED,
    spacing: { line: 360, after: opts.after === undefined ? 120 : opts.after },
    indent: opts.indent,
    children: [new TextRun({ text, bold: opts.bold, italics: opts.italics, size: opts.size || 26 })],
  });

const Rich = (runs, opts = {}) =>
  new Paragraph({
    alignment: opts.align || AlignmentType.JUSTIFIED,
    spacing: { line: 360, after: opts.after === undefined ? 120 : opts.after },
    children: runs,
  });

const T = (text, o = {}) => new TextRun({ text, bold: o.b, italics: o.i, size: o.size || 26 });

const H = (text, level) =>
  new Paragraph({
    heading: level,
    numbering: { reference: "heading-num", level: level === HeadingLevel.HEADING_1 ? 0 : level === HeadingLevel.HEADING_2 ? 1 : 2 },
    spacing: { before: level === HeadingLevel.HEADING_1 ? 360 : 240, after: 160, line: 360 },
    children: [new TextRun({ text, bold: true, size: level === HeadingLevel.HEADING_1 ? 32 : level === HeadingLevel.HEADING_2 ? 28 : 26 })],
  });

// Tieu de KHONG danh so (dung cho Tai lieu tham khao va Phu luc, vi chung
// khong phai la chuong noi dung). Van xuat hien trong muc luc.
const HPlain = (text, level) =>
  new Paragraph({
    heading: level,
    spacing: { before: level === HeadingLevel.HEADING_1 ? 360 : 240, after: 160, line: 360 },
    children: [new TextRun({ text, bold: true, size: level === HeadingLevel.HEADING_1 ? 32 : 28 })],
  });

const Bullet = (text) =>
  new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: 360, after: 80 },
    children: [new TextRun({ text, size: 26 })],
  });

// --- Danh so bang ----------------------------------------------------------
// Cac tham chieu "Bang N" trong than bai KHONG duoc go tay: chung duoc tra ra
// tu danh sach thu tu duoi day. Truong SEQ trong caption va bo dem nay cung
// chay theo thu tu tai lieu nen luon khop nhau; ham TabCaption kiem tra lai
// dieu do va nem loi neu thu tu bi lech.
const TABLE_ORDER = [
  "variables", "crossSource", "coverage", "session", "quality", "multiQuality",
  "descriptive", "normality", "tails", "stationarity", "acf", "ljung",
  "yearVol", "dow", "calendarTests", "extreme",
  "universal", "matched", "scaling", "corr1D", "fx", "crossFam",
  "status",
];
const TAB_NO = Object.fromEntries(TABLE_ORDER.map((id, i) => [id, i + 1]));
const tn = (id) => {
  if (!(id in TAB_NO)) throw new Error(`unknown table id: ${id}`);
  return TAB_NO[id];
};
let _tabSeen = 0;

// Caption cho hinh / bang, dung style "Caption" de sinh danh muc tu dong
const FigCaption = (text) =>
  new Paragraph({
    style: "Caption",
    alignment: AlignmentType.CENTER,
    spacing: { before: 80, after: 240, line: 276 },
    children: [
      new TextRun({ text: "Hình ", bold: true, size: 24 }),
      new SequentialIdentifier("Hình"),
      new TextRun({ text: ": " + text, size: 24 }),
    ],
  });

const TabCaption = (id, text) => {
  _tabSeen += 1;
  if (TABLE_ORDER[_tabSeen - 1] !== id) {
    throw new Error(
      `table order mismatch at position ${_tabSeen}: emitted "${id}" but ` +
      `TABLE_ORDER expects "${TABLE_ORDER[_tabSeen - 1]}". Update TABLE_ORDER ` +
      `so in-text "Bảng N" references stay correct.`
    );
  }
  return new Paragraph({
    style: "Caption",
    alignment: AlignmentType.CENTER,
    spacing: { before: 200, after: 80, line: 276 },
    children: [
      new TextRun({ text: "Bảng ", bold: true, size: 24 }),
      new SequentialIdentifier("Bảng"),
      new TextRun({ text: ": " + text, size: 24 }),
    ],
  });
};

const Figure = (file, ratioHeight) => {
  const width = 590;
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 160, after: 40 },
    children: [
      new ImageRun({
        type: "png",
        data: fs.readFileSync(R(path.join("figures", file))),
        transformation: { width, height: Math.round(width * ratioHeight) },
      }),
    ],
  });
};

const Note = (text) =>
  new Paragraph({
    alignment: AlignmentType.LEFT,
    spacing: { before: 60, after: 200, line: 276 },
    children: [new TextRun({ text, italics: true, size: 23 })],
  });

// Khoi canh bao "CHUA DANH GIA"
const NotEvaluated = (text) =>
  new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    spacing: { before: 160, after: 200, line: 320 },
    shading: { type: ShadingType.CLEAR, fill: "F2F2F2" },
    border: {
      top: { style: BorderStyle.SINGLE, size: 6, color: "888888" },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: "888888" },
      left: { style: BorderStyle.SINGLE, size: 6, color: "888888" },
      right: { style: BorderStyle.SINGLE, size: 6, color: "888888" },
    },
    children: [
      new TextRun({ text: "CHƯA ĐÁNH GIÁ / NOT YET EVALUATED — ", bold: true, size: 25 }),
      new TextRun({ text, size: 25 }),
    ],
  });

// --- Bang ------------------------------------------------------------------
const TOTAL_W = 9070; // DXA, vua khung in A4 le 3cm/2cm

function makeTable(header, rows, widths, opts = {}) {
  const sum = widths.reduce((a, b) => a + b, 0);
  const cols = widths.map((w) => Math.round((w / sum) * TOTAL_W));
  const cell = (text, i, isHead, alignRight) =>
    new TableCell({
      width: { size: cols[i], type: WidthType.DXA },
      shading: isHead ? { type: ShadingType.CLEAR, fill: "D9E2F3" } : undefined,
      verticalAlign: VerticalAlign.CENTER,
      margins: { top: 60, bottom: 60, left: 90, right: 90 },
      children: [
        new Paragraph({
          alignment: isHead ? AlignmentType.CENTER : (alignRight ? AlignmentType.RIGHT : AlignmentType.LEFT),
          spacing: { line: 240, before: 20, after: 20 },
          children: [new TextRun({ text: String(text), bold: isHead, size: opts.size || 22 })],
        }),
      ],
    });

  return new Table({
    width: { size: TOTAL_W, type: WidthType.DXA },
    columnWidths: cols,
    rows: [
      new TableRow({
        tableHeader: true,
        children: header.map((h, i) => cell(h, i, true)),
      }),
      ...rows.map((r) =>
        new TableRow({
          children: r.map((c, i) => cell(c, i, false, i > 0 && opts.numericFrom !== undefined && i >= opts.numericFrom)),
        })
      ),
    ],
  });
}

// --- Cong thuc toan --------------------------------------------------------
const sub = (base, s) => new MathSubScript({ children: [new MathRun(base)], subScript: [new MathRun(s)] });
const sup = (base, s) => new MathSuperScript({ children: [new MathRun(base)], superScript: [new MathRun(s)] });
// Ky hieu vua co chi tren vua co chi duoi, vi du sigma binh phuong tai thoi diem t
const subsup = (base, sb, sp) =>
  new MathSubSuperScript({
    children: [new MathRun(base)],
    subScript: [new MathRun(sb)],
    superScript: [new MathRun(sp)],
  });

const FormulaSimpleReturn = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 120, after: 160 },
  children: [
    new DocxMath({
      children: [
        sub("R", "t"), new MathRun(" = "),
        new MathFraction({
          numerator: [sub("P", "t"), new MathRun(" − "), sub("P", "t−1")],
          denominator: [sub("P", "t−1")],
        }),
      ],
    }),
  ],
});

const FormulaLogReturn = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 120, after: 160 },
  children: [
    new DocxMath({
      children: [
        sub("r", "t"), new MathRun(" = ln"),
        new MathFraction({ numerator: [sub("P", "t")], denominator: [sub("P", "t−1")] }),
        new MathRun(" = ln "), sub("P", "t"), new MathRun(" − ln "), sub("P", "t−1"),
      ],
    }),
  ],
});

const FormulaADF = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 120, after: 160 },
  children: [
    new DocxMath({
      children: [
        new MathRun("Δ"), sub("y", "t"), new MathRun(" = α + βt + γ"), sub("y", "t−1"),
        new MathRun(" + Σ "), sub("δ", "i"), new MathRun("Δ"), sub("y", "t−i"), new MathRun(" + "), sub("ε", "t"),
      ],
    }),
  ],
});

const FormulaACF = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 120, after: 160 },
  children: [
    new DocxMath({
      children: [
        sub("ρ", "k"), new MathRun(" = "),
        new MathFraction({
          numerator: [new MathRun("Cov("), sub("y", "t"), new MathRun(", "), sub("y", "t−k"), new MathRun(")")],
          denominator: [new MathRun("Var("), sub("y", "t"), new MathRun(")")],
        }),
      ],
    }),
  ],
});

const FormulaARMA = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 120, after: 160 },
  children: [
    new DocxMath({
      children: [
        sub("y", "t"), new MathRun(" = c + Σ "), sub("φ", "i"), sub("y", "t−i"),
        new MathRun(" + Σ "), sub("θ", "j"), sub("ε", "t−j"), new MathRun(" + "), sub("ε", "t"),
      ],
    }),
  ],
});

const FormulaGARCH = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 120, after: 160 },
  children: [
    new DocxMath({
      children: [
        subsup("σ", "t", "2"), new MathRun(" = ω + α"), subsup("ε", "t−1", "2"),
        new MathRun(" + β"), subsup("σ", "t−1", "2"),
      ],
    }),
  ],
});

const FormulaRMSE = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 120, after: 160 },
  children: [
    new DocxMath({
      children: [
        new MathRun("RMSE = "),
        new MathRadical({
          children: [
            new MathRun("(1/n) Σ ("), sub("y", "t"), new MathRun(" − "), sub("ŷ", "t"),
            new MathRun(")"), sup("", "2"),
          ],
        }),
      ],
    }),
  ],
});

const FormulaLjungBox = new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 120, after: 160 },
  children: [
    new DocxMath({
      children: [
        new MathRun("Q(h) = n(n+2) Σ "),
        new MathFraction({ numerator: [subsup("ρ̂", "k", "2")], denominator: [new MathRun("n − k")] }),
      ],
    }),
  ],
});

// ---------------------------------------------------------------------------
// Cac bang du lieu (doc tu ket qua thuc te)
// ---------------------------------------------------------------------------
const dLevel = descBy("VN-Index closing level (points)");
const dLog = descBy("Daily log return (%)");
const dSimple = descBy("Daily simple return (%)");
const dChange = descBy("Daily change (points)");
const dVol = descBy("Matched volume (shares)");

const tblDescriptive = makeTable(
  ["Thống kê", "Mức VN-Index (điểm)", "Thay đổi (điểm)", "Lợi suất giản đơn (%)", "Lợi suất log (%)"],
  [
    ["Số quan sát (n)", int(dLevel.n), int(dChange.n), int(dSimple.n), int(dLog.n)],
    ["Trung bình", num(dLevel.mean, 2), num(dChange.mean, 4), num(dSimple.mean, 4), num(dLog.mean, 4)],
    ["Trung vị", num(dLevel.median, 2), num(dChange.median, 4), num(dSimple.median, 4), num(dLog.median, 4)],
    ["Độ lệch chuẩn", num(dLevel.std, 2), num(dChange.std, 4), num(dSimple.std, 4), num(dLog.std, 4)],
    ["Phương sai", num(dLevel.variance, 2), num(dChange.variance, 2), num(dSimple.variance, 4), num(dLog.variance, 4)],
    ["Nhỏ nhất", num(dLevel.min, 2), num(dChange.min, 4), num(dSimple.min, 4), num(dLog.min, 4)],
    ["Lớn nhất", num(dLevel.max, 2), num(dChange.max, 4), num(dSimple.max, 4), num(dLog.max, 4)],
    ["Phân vị 25%", num(dLevel.q25, 2), num(dChange.q25, 4), num(dSimple.q25, 4), num(dLog.q25, 4)],
    ["Phân vị 75%", num(dLevel.q75, 2), num(dChange.q75, 4), num(dSimple.q75, 4), num(dLog.q75, 4)],
    ["Khoảng tứ phân vị", num(dLevel.iqr, 2), num(dChange.iqr, 4), num(dSimple.iqr, 4), num(dLog.iqr, 4)],
    ["Độ lệch (skewness)", num(dLevel.skewness, 4), num(dChange.skewness, 4), num(dSimple.skewness, 4), num(dLog.skewness, 4)],
    ["Độ nhọn vượt (excess kurtosis)", num(dLevel.excess_kurtosis, 4), num(dChange.excess_kurtosis, 4), num(dSimple.excess_kurtosis, 4), num(dLog.excess_kurtosis, 4)],
  ],
  [30, 18, 17, 17, 18], { numericFrom: 1 }
);

const tblNormality = makeTable(
  ["Chuỗi", "Kiểm định", "Thống kê", "p-value", "n"],
  norm.map((r) => [
    r.series === "Daily log return (%)" ? "Lợi suất log (%)" : "Lợi suất giản đơn (%)",
    r.test.replace("DAgostino-Pearson K2", "D'Agostino–Pearson K²")
          .replace("sub-sample", "mẫu con"),
    num(r.statistic, 4), pv(r.p_value), int(r.n),
  ]),
  [24, 30, 16, 18, 12], { numericFrom: 2 }
);

const tc = eda.tail_comparison_log_returns;
const tblTails = makeTable(
  ["Ngưỡng", "Số phiên quan sát", "Kỳ vọng nếu phân phối chuẩn", "Tỷ lệ quan sát / chuẩn"],
  [2, 3, 4, 5].map((k) => {
    const d = tc[`gt_${k}_sigma`];
    return [`|r| > ${k}σ`, int(d.observed_days), num(d.expected_days_if_normal, 2), `${num(d.ratio_observed_to_normal, 2)}×`];
  }),
  [22, 26, 32, 20], { numericFrom: 1 }
);

const viSeries = (s) => ({
  "VN-Index level (points)": "Mức VN-Index (điểm)",
  "log(VN-Index level)": "log(Mức VN-Index)",
  "First difference of level (points)": "Sai phân bậc 1 của mức (điểm)",
  "Daily log return (%)": "Lợi suất log hàng ngày (%)",
}[s] || s);

const tblStationarity = makeTable(
  ["Chuỗi", "Dạng hồi quy", "ADF", "p (ADF)", "KPSS", "p (KPSS)", "Kết luận"],
  stat.map((r) => [
    viSeries(r.series), r.regression, num(r.ADF_stat, 4), pv(r.ADF_p),
    num(r.KPSS_stat, 4), (Number(r.KPSS_p) <= 0.01 ? "≤ 0.01" : Number(r.KPSS_p) >= 0.1 ? "≥ 0.10" : num(r.KPSS_p, 4)),
    r.verdict === "STATIONARY" ? "DỪNG" : "KHÔNG DỪNG",
  ]),
  [24, 11, 11, 13, 11, 13, 17], { numericFrom: 2, size: 20 }
);

const acfRows = ["Daily log return (%)", "Absolute log return |r|", "Squared log return r^2"].map((k) => {
  const v = acorr.acf_pacf[k];
  const label = { "Daily log return (%)": "Lợi suất log r", "Absolute log return |r|": "Giá trị tuyệt đối |r|", "Squared log return r^2": "Bình phương r²" }[k];
  return [label, ...v.values.slice(0, 5).map((x) => num(x.acf, 4)), `${v.n_significant_acf_lags}/40`];
});
const tblACF = makeTable(
  ["Chuỗi", "ACF(1)", "ACF(2)", "ACF(3)", "ACF(4)", "ACF(5)", "Số độ trễ có ý nghĩa"],
  acfRows, [24, 12, 12, 12, 12, 12, 16], { numericFrom: 1, size: 21 }
);

const viLjung = (s) => ({
  "Daily log return (%)": "Lợi suất log r",
  "Absolute log return |r|": "Giá trị tuyệt đối |r|",
  "Squared log return r^2": "Bình phương r²",
}[s] || s);
const tblLjung = makeTable(
  ["Chuỗi", "Độ trễ h", "Thống kê Q(h)", "p-value", "Bác bỏ H₀ (α=0.05)"],
  ljung.map((r) => [viLjung(r.series), r.lag, num(r.statistic, 2), pv(r.p_value), r.reject_H0_at_5pct === "True" ? "Có" : "Không"]),
  [28, 14, 22, 20, 16], { numericFrom: 1, size: 21 }
);

const viDay = { Monday: "Thứ Hai", Tuesday: "Thứ Ba", Wednesday: "Thứ Tư", Thursday: "Thứ Năm", Friday: "Thứ Sáu" };
const tblDow = makeTable(
  ["Ngày trong tuần", "Số phiên", "Trung bình (%)", "Trung vị (%)", "Độ lệch chuẩn (%)"],
  eda.day_of_week_effect.group_summary.map((g) => [viDay[g.Weekday], int(g.count), num(g.mean, 4), num(g.median, 4), num(g.std, 4)]),
  [26, 16, 20, 19, 19], { numericFrom: 1 }
);

const tblCalendarTests = makeTable(
  ["Hiệu ứng", "Kiểm định", "Thống kê", "p-value", "Kết luận (α=0.05)"],
  [
    ...eda.day_of_week_effect.tests.map((t) => [
      "Ngày trong tuần", t.test.replace("One-way ANOVA", "ANOVA một chiều").replace("Kruskal-Wallis H", "Kruskal–Wallis H").replace("Levene (median-centred)", "Levene (tâm trung vị)"),
      num(t.statistic, 4), pv(t.p_value), Number(t.p_value) < 0.05 ? "Bác bỏ H₀" : "Không bác bỏ H₀",
    ]),
    ...eda.month_effect.tests.map((t) => [
      "Tháng trong năm", t.test.replace("One-way ANOVA", "ANOVA một chiều").replace("Kruskal-Wallis H", "Kruskal–Wallis H"),
      num(t.statistic, 4), pv(t.p_value), Number(t.p_value) < 0.05 ? "Bác bỏ H₀" : "Không bác bỏ H₀",
    ]),
  ],
  [22, 28, 16, 16, 18], { numericFrom: 2, size: 21 }
);

const years = eda.yearly_summary;
const tblYearVol = makeTable(
  ["Năm", "Số phiên", "Lợi suất năm (%)", "Độ lệch chuẩn ngày (%)", "Biến động quy năm (%)"],
  years.map((y) => [y.Year, int(y.sessions), num(y.year_return_pct, 2), num(y.sd_log_ret_pct, 4), num(y.annualised_vol_pct, 2)]),
  [14, 18, 24, 24, 24], { numericFrom: 1, size: 20 }
);

const em = eda.extreme_moves;
const tblExtreme = makeTable(
  ["Ngày", "VN-Index (điểm)", "Thay đổi (điểm)", "Lợi suất log (%)", "z"],
  [...em.largest_drops.slice(0, 8), ...em.largest_gains.slice(0, 8)]
    .map((x) => [x.Date, num(x.Close, 2), num(x.Change, 2), num(x.LogReturn_pct, 4), num(x.z, 3)]),
  [22, 22, 20, 20, 16], { numericFrom: 1 }
);

const gq = quality.gap_anomalies;
const tblQuality = makeTable(
  ["Hạng mục kiểm tra", "Kết quả"],
  [
    ["Số quan sát", int(quality.shape.n_rows) + " phiên"],
    ["Khoảng thời gian", `${quality.shape.first_date} – ${quality.shape.last_date}`],
    ["Giá trị khuyết", int(quality.missing.rows_with_any_missing) + " dòng"],
    ["Ngày trùng lặp", int(quality.duplicates.n_duplicated_dates)],
    ["Thứ tự thời gian tăng dần", quality.ordering.is_monotonic_increasing ? "Đúng" : "Sai"],
    ["Giá ≤ 0", int(quality.impossible_values.non_positive_price)],
    ["High < Low", int(quality.impossible_values.high_lt_low)],
    ["Close ngoài [Low, High]", int(quality.impossible_values.close_outside_high_low)],
    ["Open ngoài [Low, High]", int(quality.impossible_values.open_outside_high_low)],
    ["Khối lượng âm", int(quality.impossible_values.negative_volume)],
    ["Phiên khối lượng bằng 0", int(quality.impossible_values.zero_volume_sessions)],
    ["Phiên cuối tuần", int(quality.trading_calendar.n_weekend_sessions)],
    ["Tỷ lệ bao phủ ngày làm việc", num(quality.trading_calendar.pct_business_days_covered, 2) + "%"],
    ["Khoảng trống lịch (≥ 2 ngày làm việc)", int(gq.n_gaps_examined)],
    ["– phù hợp với ngày nghỉ lễ", int(gq.n_holiday_consistent)],
    ["– KHÔNG giải thích được", `${int(gq.n_unexplained)} (${gq.unexplained_gaps.map((g) => g.prev_session + " → " + g.next_session).join("; ")})`],
  ],
  [42, 58]
);

const tblCross = makeTable(
  ["Chỉ tiêu", "Giá trị"],
  [
    ["Số phiên chung", int(cross.n_common_sessions)],
    ["Hệ số tương quan giá đóng cửa", num(cross.close_correlation, 8)],
    ["Trung vị sai lệch tương đối tuyệt đối", Number(cross.median_abs_rel_diff).toExponential(2)],
    ["Sai lệch tương đối lớn nhất", num(cross.max_abs_rel_diff * 100, 3) + "%"],
    ["Số phiên chỉ có ở nguồn chính", int(cross.n_sessions_only_in_primary)],
    ["Số phiên chỉ có ở nguồn đối chiếu", int(cross.n_sessions_only_in_secondary)],
    ["Khoảng trống không giải thích được – nguồn chính", `${int(cross.primary.n_unexplained_gaps)} (${int(cross.primary.missing_business_days_in_unexplained_gaps)} ngày làm việc)`],
    ["Khoảng trống không giải thích được – nguồn đối chiếu", `${int(cross.secondary.n_unexplained_gaps)} (${int(cross.secondary.missing_business_days_in_unexplained_gaps)} ngày làm việc)`],
    ["Số phiên lệch > 0.1%", `${int(cross.disagreement_tiers["rel_diff_gt_0.001"].n_sessions)} (${num(cross.disagreement_tiers["rel_diff_gt_0.001"].pct_of_common_sessions, 2)}%)`],
    ["Số phiên lệch > 1%", `${int(cross.disagreement_tiers["rel_diff_gt_0.01"].n_sessions)} (${num(cross.disagreement_tiers["rel_diff_gt_0.01"].pct_of_common_sessions, 2)}%)`],
  ],
  [52, 48]
);

const tblVariables = makeTable(
  ["Biến", "Kiểu dữ liệu", "Đơn vị", "Mô tả"],
  [
    ["Date", "datetime64", "ngày", "Ngày giao dịch trên sàn HOSE"],
    ["Open", "float64", "điểm", "Giá trị mở cửa của chỉ số"],
    ["High", "float64", "điểm", "Giá trị cao nhất trong phiên"],
    ["Low", "float64", "điểm", "Giá trị thấp nhất trong phiên"],
    ["Close", "float64", "điểm", "Giá trị đóng cửa (biến phân tích chính)"],
    ["Volume", "int64", "cổ phiếu", "Khối lượng khớp lệnh"],
    ["Adjusted Close", "—", "—", "KHÔNG CÓ: VN-Index là chỉ số giá, không có chuỗi điều chỉnh"],
  ],
  [16, 18, 14, 52], { size: 21 }
);

const tblStatus = makeTable(
  ["Thành phần", "Trạng thái"],
  [
    ["Thu thập và nạp dữ liệu nguồn chính", "ĐÃ KIỂM CHỨNG"],
    ["Đối chiếu nguồn dữ liệu độc lập", "ĐÃ KIỂM CHỨNG"],
    ["Kiểm tra chất lượng dữ liệu", "ĐÃ KIỂM CHỨNG"],
    ["Tiền xử lý và tính lợi suất", "ĐÃ KIỂM CHỨNG"],
    ["Thống kê mô tả", "ĐÃ KIỂM CHỨNG"],
    ["Kiểm định tính chuẩn của lợi suất", "ĐÃ KIỂM CHỨNG"],
    ["Kiểm định tính dừng (ADF, KPSS)", "ĐÃ KIỂM CHỨNG"],
    ["Phân tích ACF/PACF và Ljung–Box", "ĐÃ KIỂM CHỨNG"],
    ["Phân tích biến động mô tả (rolling, phân rã theo năm)", "ĐÃ KIỂM CHỨNG"],
    ["Phân tích hiệu ứng lịch", "ĐÃ KIỂM CHỨNG"],
    ["Phân tích quan sát cực đoan", "ĐÃ KIỂM CHỨNG"],
    ["Đăng ký toàn bộ 19 tệp nguồn (catalog.py)", "ĐÃ KIỂM CHỨNG"],
    ["Nạp và kiểm tra chất lượng toàn bộ 19 chuỗi", "ĐÃ KIỂM CHỨNG"],
    ["Đối chiếu chéo giữa hai họ tệp dữ liệu", "ĐÃ KIỂM CHỨNG"],
    ["Bộ thống kê so sánh trên 13 chuỗi chính", "ĐÃ KIỂM CHỨNG"],
    ["Kiểm soát giai đoạn mẫu giữa các chỉ số", "ĐÃ KIỂM CHỨNG"],
    ["Phân tích theo tần suất lấy mẫu và cấu trúc trong phiên", "ĐÃ KIỂM CHỨNG"],
    ["Ma trận tương quan giữa các lớp tài sản", "ĐÃ KIỂM CHỨNG"],
    ["Bộ kiểm thử tự động (176 test)", "ĐÃ KIỂM CHỨNG"],
    ["Kiểm định ARCH-LM", "CHƯA TRIỂN KHAI"],
    ["Mô hình GARCH", "CHƯA TRIỂN KHAI"],
    ["Chia tập train/validation/test theo thời gian", "CHƯA TRIỂN KHAI"],
    ["Mô hình dự báo (naive, MA, ETS, ARIMA)", "CHƯA TRIỂN KHAI"],
    ["Đánh giá dự báo so với baseline (MAE/RMSE/MAPE/MASE)", "CHƯA TRIỂN KHAI"],
    ["Chẩn đoán phần dư của mô hình", "CHƯA TRIỂN KHAI"],
  ],
  [64, 36], { size: 21 }
);

// ---------------------------------------------------------------------------
// Bang cho phan phan tich da chuoi
// ---------------------------------------------------------------------------
const TF_VI = { "1D": "Ngày", H4: "Phiên nửa ngày", H1: "1 giờ", M30: "30 phút" };

const tblDatasetCoverage = makeTable(
  ["Chuỗi", "Tần suất", "Họ tệp", "Khối lượng", "Số quan sát", "Giai đoạn"],
  battery.series.map((s) => {
    const inv = inventory[s.key];
    return [
      s.symbol, TF_VI[s.timeframe] || s.timeframe, s.family,
      inv.has_volume ? "Có" : "Không", int(inv.n_rows),
      `${inv.first_date} – ${inv.last_date}`,
    ];
  }),
  [14, 16, 15, 12, 15, 28], { size: 20 }
);

const tblSessionStructure = makeTable(
  ["Tần suất", "Số thanh/phiên", "Giờ mở của các thanh", "Ghi chú"],
  [
    ["30 phút", "10", "09:00, 09:30, 10:00, 10:30, 11:00, 11:30, 13:00, 13:30, 14:00, 14:30",
     "Thanh 11:30 chỉ dài 15 phút"],
    ["1 giờ", "5", "09:00, 10:00, 11:00, 13:00, 14:00", "Thanh 11:00 chỉ dài 30 phút"],
    ["Phiên nửa ngày", "2", "09:00, 13:00", "Mỗi thanh là một phiên, không phải 4 giờ đồng hồ"],
    ["Ngày", "1", "09:00", "Một thanh cho cả ngày giao dịch"],
  ],
  [16, 13, 42, 29], { size: 20 }
);

const tblMultiQuality = makeTable(
  ["Hạng mục kiểm tra trên toàn bộ dữ liệu", "Kết quả"],
  (() => {
    const sum = (f) => Object.values(squality).reduce((a, r) => a + (r[f] || 0), 0);
    return [
      ["Số chuỗi được kiểm tra", String(Object.keys(squality).length)],
      ["Tổng số quan sát", int(totalBars)],
      ["Timestamp trùng lặp", int(sum("n_duplicate_timestamps"))],
      ["Dòng khuyết giá trị OHLC", int(sum("ohlcv_missing_rows"))],
      ["Giá ≤ 0", int(sum("non_positive_price"))],
      ["High < Low", int(sum("high_lt_low"))],
      ["Thanh OHLC mâu thuẫn nội tại", int(sum("ohlc_inconsistent_bars"))],
      ["Thanh rơi vào cuối tuần", int(sum("weekend_bars"))],
      ["Số đuôi dữ liệu chưa hoàn tất đã cắt bỏ", String(nTrimmed)],
    ];
  })(),
  [58, 42]
);

const tblUniversal = makeTable(
  ["Đặc trưng thống kê", "Số chuỗi thỏa mãn", "Tỷ lệ"],
  [
    ["Chuỗi mức KHÔNG dừng (ADF và KPSS đồng thuận)",
     `${nNonStationary}/${nPrimary}`, `${num(100 * nNonStationary / nPrimary, 1)}%`],
    ["Lợi suất KHÔNG tuân theo phân phối chuẩn (Jarque–Bera)",
     `${nNonNormal}/${nPrimary}`, `${num(100 * nNonNormal / nPrimary, 1)}%`],
    ["Có cụm biến động (Ljung–Box trên r², p < 0.05)",
     `${battery.series.filter((s) => s.ljung_box_sq_p10 < 0.05).length}/${nPrimary}`,
     `${num(100 * battery.series.filter((s) => s.ljung_box_sq_p10 < 0.05).length / nPrimary, 1)}%`],
  ],
  [58, 24, 18]
);

const tblMatched = makeTable(
  ["Chỉ số", "ACF(1) trên mẫu riêng", "ACF(1) trên giai đoạn chung", "Có ý nghĩa thống kê?"],
  ["VNINDEX", "VN30", "VN100"].map((sym) => [
    sym,
    num(BY[`${sym}_1D`].acf1_return, 4),
    num(matched1D.stats[sym].acf1, 4),
    matched1D.stats[sym].acf1_significant ? "Có" : "Không",
  ]),
  [20, 27, 30, 23], { numericFrom: 1 }
);

const tblScaling = makeTable(
  ["Tần suất", "Số thanh/ngày", "Độ lệch chuẩn (%)", "Quy về đơn vị ngày (%)", "Độ nhọn vượt"],
  ["M30", "H1", "H4", "1D"].filter((tf) => scaleVNI[tf]).map((tf) => {
    const r = scaleVNI[tf];
    return [TF_VI[tf], String(r.bars_per_day), num(r.sd_pct, 4),
            num(r.sd_scaled_to_daily_pct, 4), num(r.excess_kurtosis, 2)];
  }),
  [20, 16, 21, 24, 19], { numericFrom: 1 }
);

const tblCorr1D = makeTable(
  ["", ...corr1D.symbols],
  corr1D.symbols.map((a) => [a, ...corr1D.symbols.map((b) => num(corr1D.pearson[a][b], 4))]),
  [22, ...corr1D.symbols.map(() => Math.round(78 / corr1D.symbols.length))],
  { numericFrom: 1 }
);

const tblCrossFam = makeTable(
  ["Chuỗi chính", "Chuỗi đối chiếu", "Số thanh chung", "Tương quan", "Trung vị sai lệch", "Sai lệch > 0.1%"],
  crossFam.map((r) => [
    r.primary, r.crosscheck, int(r.n_common_bars),
    num(r.close_correlation, 8),
    Number(r.median_abs_rel_diff).toExponential(2),
    num(r["pct_bars_differing_gt_0.1pct"], 3) + "%",
  ]),
  [17, 19, 14, 18, 17, 15], { numericFrom: 2, size: 19 }
);

const uFX = BY["USDVND_1D"];
const tblFX = makeTable(
  ["Đặc trưng", "USD/VND", "Ba chỉ số cổ phiếu (ngày)"],
  [
    ["Độ nhọn vượt", num(uFX.excess_kurtosis, 2),
     ["VNINDEX", "VN30", "VN100"].map((s) => num(BY[`${s}_1D`].excess_kurtosis, 2)).join(" / ")],
    ["ACF(1) của lợi suất", num(uFX.acf1_return, 4),
     ["VNINDEX", "VN30", "VN100"].map((s) => num(BY[`${s}_1D`].acf1_return, 4)).join(" / ")],
    ["Tỷ lệ Open trùng Close phiên trước",
     num(squality.USDVND_1D.stale_open_share * 100, 1) + "%",
     ["VNINDEX", "VN30", "VN100"].map((s) => num(squality[`${s}_1D`].stale_open_share * 100, 1) + "%").join(" / ")],
    ["Kết luận tính dừng của lợi suất",
     uFX.return_verdict === "STATIONARY" ? "DỪNG" : uFX.return_verdict === "AMBIGUOUS" ? "MƠ HỒ" : "KHÔNG DỪNG",
     "DỪNG / DỪNG / DỪNG"],
    ["Số khoảng trống ≥ 2 ngày làm việc",
     String(squality.USDVND_1D.gaps_ge_2_business_days), "—"],
  ],
  [34, 22, 44], { size: 20 }
);

// ---------------------------------------------------------------------------
// Trang bia
// ---------------------------------------------------------------------------
const coverLine = (text, o = {}) =>
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: o.after === undefined ? 120 : o.after, line: 300 },
    children: [new TextRun({ text, bold: o.b, size: o.size || 26, allCaps: o.caps })],
  });

const cover = [
  // Ten truong suy ra tu duong dan du an (VLU); nguoi dung can kiem tra lai.
  // Ten khoa de trong vi khong co thong tin xac thuc.
  coverLine("TRƯỜNG ĐẠI HỌC VĂN LANG", { b: true, size: 28 }),
  coverLine("KHOA:  ......................................", { size: 26, after: 900 }),
  coverLine("BÁO CÁO ĐỒ ÁN", { b: true, size: 30 }),
  coverLine("HỌC PHẦN: PHÂN TÍCH CHUỖI THỜI GIAN", { size: 26, after: 700 }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 200, line: 400 },
    children: [new TextRun({ text: "PHÂN TÍCH DỮ LIỆU CHUỖI THỜI GIAN VN‑INDEX", bold: true, size: 40 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 900, line: 320 },
    children: [new TextRun({
      text: `Giai đoạn dữ liệu: ${meta.first_date} – ${meta.last_date} (${int(meta.n_rows)} phiên giao dịch)`,
      italics: true, size: 26,
    })],
  }),
  coverLine("Sinh viên thực hiện:  ......................................", { size: 26 }),
  coverLine("Mã số sinh viên:  ......................................", { size: 26 }),
  coverLine("Lớp:  ......................................", { size: 26 }),
  coverLine("Giảng viên hướng dẫn:  ......................................", { size: 26, after: 900 }),
  coverLine("TP. Hồ Chí Minh, năm 2026", { size: 26 }),
  new Paragraph({ children: [new PageBreak()] }),
];

// ---------------------------------------------------------------------------
// Muc luc / danh muc
// ---------------------------------------------------------------------------
const frontMatter = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [new TextRun({ text: "MỤC LỤC", bold: true, size: 32 })],
  }),
  new TableOfContents("Mục lục", { hyperlink: true, headingStyleRange: "1-3" }),
  new Paragraph({ children: [new PageBreak()] }),

  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [new TextRun({ text: "DANH MỤC HÌNH", bold: true, size: 32 })],
  }),
  new TableOfContents("Danh mục hình", { hyperlink: true, captionLabelIncludingNumbers: "Hình" }),
  new Paragraph({ children: [new PageBreak()] }),

  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [new TextRun({ text: "DANH MỤC BẢNG", bold: true, size: 32 })],
  }),
  new TableOfContents("Danh mục bảng", { hyperlink: true, captionLabelIncludingNumbers: "Bảng" }),
  new Paragraph({ children: [new PageBreak()] }),
];

// ---------------------------------------------------------------------------
// Noi dung cac chuong
// ---------------------------------------------------------------------------
const body = [];
const add = (...x) => body.push(...x);

// ===== CHUONG 1 =====
add(H("GIỚI THIỆU", HeadingLevel.HEADING_1));

add(H("Bối cảnh nghiên cứu", HeadingLevel.HEADING_2));
add(P("VN-Index là chỉ số tổng hợp của Sở Giao dịch Chứng khoán Thành phố Hồ Chí Minh (HOSE), được tính từ phiên giao dịch đầu tiên ngày 28/07/2000 với giá trị gốc 100 điểm. Sau hơn hai thập kỷ, chỉ số này trở thành thước đo trung tâm phản ánh diễn biến của thị trường cổ phiếu Việt Nam và là dữ liệu đầu vào quen thuộc cho các nghiên cứu định lượng về thị trường mới nổi."));
add(P("Chuỗi VN-Index là một chuỗi thời gian tài chính điển hình: dữ liệu được ghi nhận theo phiên giao dịch, không liên tục theo lịch dương (nghỉ cuối tuần và các ngày lễ), và các đặc trưng thống kê của nó thường khác biệt rõ rệt so với giả định chuẩn tắc thường gặp trong thống kê cổ điển. Việc mô tả chính xác các đặc trưng này là bước bắt buộc trước bất kỳ nỗ lực mô hình hóa nào."));

add(H("Lý do chọn đề tài", HeadingLevel.HEADING_2));
add(P("Phần lớn các bài tập phân tích VN-Index chuyển ngay sang bài toán dự báo giá mà bỏ qua bước kiểm tra các tính chất thống kê nền tảng. Cách làm này dễ dẫn tới việc áp dụng mô hình không phù hợp với dữ liệu: dùng mô hình yêu cầu chuỗi dừng cho chuỗi không dừng, giả định phân phối chuẩn cho chuỗi có đuôi dày, hoặc đưa vào thành phần mùa vụ khi không có bằng chứng thống kê ủng hộ."));
add(P("Đề tài này chọn hướng ngược lại: ưu tiên mô tả và kiểm định đặc trưng của chuỗi trước, và chỉ đề xuất mô hình khi kết quả kiểm định thực sự biện minh cho mô hình đó. Đây cũng là lý do báo cáo giữ nguyên tên đề tài là phân tích chuỗi thời gian, không phải dự báo giá."));

add(H("Vấn đề nghiên cứu", HeadingLevel.HEADING_2));
add(P("Vấn đề nghiên cứu được phát biểu như sau: chuỗi thời gian VN-Index có những đặc trưng thống kê và đặc trưng thời gian nào, và những đặc trưng đó ràng buộc như thế nào đối với việc lựa chọn mô hình chuỗi thời gian phù hợp?"));

add(H("Mục tiêu nghiên cứu", HeadingLevel.HEADING_2));
add(P("Nghiên cứu đặt ra các mục tiêu cụ thể sau:"));
[
  "Thu thập, kiểm tra và làm sạch bộ dữ liệu lịch sử VN-Index theo một quy trình tái lập được.",
  "Mô tả cấu trúc dữ liệu, chất lượng dữ liệu và những hạn chế thực tế của nguồn dữ liệu.",
  "Tính toán và phân tích chuỗi lợi suất giản đơn và lợi suất logarit.",
  "Kiểm định tính dừng của chuỗi mức chỉ số và chuỗi lợi suất.",
  "Phân tích tự tương quan (ACF) và tự tương quan riêng phần (PACF).",
  "Phân tích đặc trưng biến động, bao gồm hiện tượng cụm biến động.",
  "Kiểm định sự tồn tại của các hiệu ứng lịch (ngày trong tuần, tháng trong năm).",
  "Nhận diện và thảo luận các quan sát biến động cực đoan.",
  "Xác định lớp mô hình phù hợp dựa trên bằng chứng thống kê thu được.",
].forEach((t) => add(Bullet(t)));

add(H("Câu hỏi nghiên cứu", HeadingLevel.HEADING_2));
[
  "CH1: Chuỗi mức VN-Index và chuỗi lợi suất của nó có dừng hay không?",
  "CH2: Phân phối lợi suất hàng ngày của VN-Index có phù hợp với phân phối chuẩn hay không?",
  "CH3: Lợi suất VN-Index có thể hiện phụ thuộc chuỗi có ý nghĩa thống kê hay không?",
  "CH4: Biến động của VN-Index có hiện tượng cụm biến động hay không?",
  "CH5: Có bằng chứng thống kê về hiệu ứng lịch trong lợi suất VN-Index hay không?",
  "CH6: Các đặc trưng thống kê tìm được biện minh cho lớp mô hình nào?",
].forEach((t) => add(Bullet(t)));

add(H("Phạm vi nghiên cứu", HeadingLevel.HEADING_2));
add(Rich([
  T("Chuỗi nghiên cứu trọng tâm là VN-Index tần suất ngày trong giai đoạn từ "),
  T(meta.first_date, { b: true }), T(" đến "), T(meta.last_date, { b: true }),
  T(`, tương ứng ${int(meta.n_rows)} phiên giao dịch. Biến phân tích chính là giá trị đóng cửa (Close); khối lượng khớp lệnh được sử dụng để mô tả bối cảnh thanh khoản.`),
]));
add(Rich([
  T("Ngoài chuỗi trọng tâm, nghiên cứu sử dụng "),
  T("toàn bộ bộ dữ liệu nguồn", { b: true }),
  T(`, gồm ${Object.keys(inventory).length} tệp với tổng cộng `),
  T(int(totalBars) + " quan sát", { b: true }),
  T(": ba chỉ số cổ phiếu (VN-Index, VN30, VN100) ở bốn tần suất lấy mẫu (30 phút, 1 giờ, phiên nửa ngày, ngày) và một chuỗi tỷ giá USD/VND. Phần dữ liệu mở rộng này phục vụ ba mục đích: kiểm tra xem các kết luận rút ra từ VN-Index có đúng với các phân khúc thị trường khác hay không, xem chúng thay đổi thế nào theo tần suất lấy mẫu, và so sánh với một chuỗi tài chính khác lớp tài sản."),
]));
add(P("Nghiên cứu không phân tích cổ phiếu riêng lẻ và không sử dụng biến kinh tế vĩ mô. Giai đoạn phân tích của mỗi chuỗi kết thúc ở quan sát hoàn chỉnh cuối cùng mà nguồn dữ liệu cung cấp cho chuỗi đó; các mốc kết thúc khác nhau giữa hai họ tệp và được ghi rõ trong Chương 3."));

add(new Paragraph({ children: [new PageBreak()] }));

// ===== CHUONG 2 =====
add(H("CƠ SỞ LÝ THUYẾT", HeadingLevel.HEADING_1));
add(Note("Lưu ý: chương này chỉ trình bày phần lý thuyết thực sự được sử dụng trong phân tích đã thực hiện, hoặc cần thiết để hiểu các bước dự kiến triển khai tiếp theo."));

add(H("Dữ liệu chuỗi thời gian", HeadingLevel.HEADING_2));
add(P("Chuỗi thời gian là một dãy quan sát được sắp xếp theo thứ tự thời gian, trong đó thứ tự giữa các quan sát mang thông tin. Đặc điểm này phân biệt chuỗi thời gian với dữ liệu cắt ngang và kéo theo hai hệ quả phương pháp quan trọng: không được phép xáo trộn ngẫu nhiên thứ tự quan sát khi chia tập dữ liệu, và mọi ước lượng đều phải tránh sử dụng thông tin tương lai."));
add(P("Chuỗi thời gian tài chính theo phiên giao dịch có thêm một đặc thù: trục thời gian không liên tục theo lịch dương. Giữa hai phiên liên tiếp có thể cách nhau một ngày, ba ngày (cuối tuần) hoặc dài hơn (kỳ nghỉ lễ). Trong nghiên cứu này, chuỗi được xử lý như một dãy phiên giao dịch có thứ tự, không nội suy các ngày không giao dịch."));

add(H("Chỉ số VN-Index", HeadingLevel.HEADING_2));
add(P("VN-Index là chỉ số giá có trọng số theo giá trị vốn hóa của toàn bộ cổ phiếu niêm yết trên HOSE, lấy mốc 100 điểm tại phiên giao dịch đầu tiên. Vì là chỉ số giá, VN-Index không có chuỗi giá điều chỉnh (adjusted close) tương tự như cổ phiếu riêng lẻ; đây là lý do bộ dữ liệu sử dụng trong nghiên cứu không có biến này."));
add(P("Một đặc thù thể chế quan trọng là biên độ dao động giá áp dụng cho từng cổ phiếu thành phần trên HOSE. Biên độ này gián tiếp giới hạn mức biến động tối đa của chỉ số trong một phiên và sẽ được đối chiếu với dữ liệu thực nghiệm ở Chương 4."));

add(H("Lợi suất và lợi suất logarit", HeadingLevel.HEADING_2));
add(P("Do chuỗi mức giá thường không dừng, phân tích chuỗi thời gian tài chính thường chuyển sang chuỗi lợi suất. Lợi suất giản đơn được định nghĩa là:"));
add(FormulaSimpleReturn);
add(P("Lợi suất logarit (log return) được định nghĩa là:"));
add(FormulaLogReturn);
add(P("Lợi suất logarit có hai ưu điểm dùng trong nghiên cứu này: nó cộng dồn được theo thời gian, và nó tương đương với sai phân bậc một của chuỗi logarit giá — tức là phép biến đổi chuẩn để đạt tính dừng đối với chuỗi có nghiệm đơn vị."));

add(H("Tính dừng", HeadingLevel.HEADING_2));
add(P("Một chuỗi được gọi là dừng theo nghĩa yếu nếu kỳ vọng, phương sai và hiệp phương sai giữa hai thời điểm chỉ phụ thuộc vào độ trễ chứ không phụ thuộc vào thời điểm cụ thể. Tính dừng là điều kiện tiên quyết của họ mô hình ARMA."));
add(P("Kiểm định Augmented Dickey–Fuller (ADF) dựa trên hồi quy:"));
add(FormulaADF);
add(P("Giả thuyết gốc H₀ của ADF là chuỗi có nghiệm đơn vị (không dừng); bác bỏ H₀ là bằng chứng ỦNG HỘ tính dừng. Ngược lại, kiểm định KPSS có giả thuyết gốc H₀ là chuỗi dừng; bác bỏ H₀ của KPSS là bằng chứng CHỐNG LẠI tính dừng. Việc sử dụng đồng thời hai kiểm định có giả thuyết gốc trái ngược cho phép phân biệt giữa kết luận vững và kết luận mơ hồ."));

add(H("ACF và PACF", HeadingLevel.HEADING_2));
add(P("Hàm tự tương quan (ACF) tại độ trễ k đo mức tương quan tuyến tính giữa quan sát tại thời điểm t và quan sát cách đó k bước:"));
add(FormulaACF);
add(P("Hàm tự tương quan riêng phần (PACF) đo tương quan giữa hai thời điểm sau khi đã loại bỏ ảnh hưởng của các độ trễ trung gian. Trong thực hành, dạng cắt cụt của PACF gợi ý bậc AR, còn dạng cắt cụt của ACF gợi ý bậc MA."));
add(P("Kiểm định Ljung–Box tổng hợp thông tin của nhiều độ trễ để kiểm tra giả thuyết chuỗi là nhiễu trắng:"));
add(FormulaLjungBox);

add(H("Biến động", HeadingLevel.HEADING_2));
add(P("Biến động (volatility) được đo bằng độ lệch chuẩn của lợi suất. Đặc trưng thường gặp ở chuỗi tài chính là hiện tượng cụm biến động (volatility clustering): các giai đoạn biến động mạnh có xu hướng nối tiếp nhau, và các giai đoạn yên tĩnh cũng vậy. Dấu hiệu nhận biết là bản thân lợi suất gần như không tự tương quan, nhưng giá trị tuyệt đối và bình phương của lợi suất lại tự tương quan mạnh và dai dẳng."));
add(P("Khi có bằng chứng cụm biến động, lớp mô hình phương sai có điều kiện như ARCH/GARCH trở nên phù hợp. Dạng GARCH(1,1) có phương trình phương sai:"));
add(FormulaGARCH);

add(H("Các mô hình chuỗi thời gian dự kiến sử dụng", HeadingLevel.HEADING_2));
add(P("Họ mô hình ARMA(p, q) cho chuỗi dừng có dạng tổng quát:"));
add(FormulaARMA);
add(P("Trong đó AR(p) là thành phần tự hồi quy, MA(q) là thành phần trung bình trượt. Với chuỗi không dừng bậc d, mô hình mở rộng thành ARIMA(p, d, q). Thành phần mùa vụ (SARIMA) chỉ nên đưa vào khi có bằng chứng thống kê về tính mùa vụ."));
add(P("Nguyên tắc áp dụng trong nghiên cứu này là luôn thiết lập một mô hình cơ sở (baseline) đơn giản — thường là mô hình naive dự báo giá trị kế tiếp bằng giá trị hiện tại — trước khi xét đến các mô hình phức tạp hơn."));

add(H("Các phương pháp đánh giá", HeadingLevel.HEADING_2));
add(P("Các chỉ số đánh giá dự báo dự kiến sử dụng gồm MAE, RMSE, MAPE và MASE. Chỉ số RMSE được định nghĩa là:"));
add(FormulaRMSE);
add(P("Việc chia tập dữ liệu phải theo thứ tự thời gian: dữ liệu quá khứ dùng để huấn luyện, dữ liệu gần hơn dùng để kiểm định, và dữ liệu mới nhất dùng để kiểm tra cuối cùng. Tuyệt đối không xáo trộn ngẫu nhiên quan sát, vì điều đó tạo ra rò rỉ thông tin tương lai."));
add(P("Ngoài sai số dự báo, chất lượng mô hình còn phải được đánh giá qua chẩn đoán phần dư: phần dư của một mô hình phù hợp cần xấp xỉ nhiễu trắng, tức không còn cấu trúc tự tương quan có ý nghĩa."));

add(new Paragraph({ children: [new PageBreak()] }));

// ===== CHUONG 3 =====
add(H("DỮ LIỆU VÀ PHƯƠNG PHÁP NGHIÊN CỨU", HeadingLevel.HEADING_1));

add(H("Nguồn dữ liệu", HeadingLevel.HEADING_2));
add(Rich([
  T("Nguồn dữ liệu chính của nghiên cứu là bộ dữ liệu "), T(meta.source_name, { i: true }),
  T(", công bố tại "), T(meta.source_url, { i: true }),
  T(", giấy phép "), T(meta.source_license, { b: true }),
  T(`, cập nhật lần cuối ngày ${meta.upstream_last_updated}.`),
]));
add(P("Tệp nguồn được lưu kèm trong dự án tại data/raw/ thay vì tải trực tiếp khi chạy. Cách làm này bảo đảm mọi con số báo cáo đều truy xuất được về đúng phiên bản dữ liệu đã dùng, kể cả khi bộ dữ liệu gốc được cập nhật về sau."));
add(P("Ngoài ra, nghiên cứu sử dụng một nguồn thứ hai hoàn toàn độc lập là API biểu đồ công khai của DNSE/Entrade. Nguồn này KHÔNG được dùng để tạo ra bất kỳ con số nào trong báo cáo; vai trò duy nhất của nó là đối chiếu nhằm kiểm chứng độ tin cậy của nguồn chính."));

add(H("Mô tả dữ liệu", HeadingLevel.HEADING_2));
add(Rich([
  T("Bộ dữ liệu sau khi nạp gồm "), T(int(meta.n_rows), { b: true }),
  T(` phiên giao dịch, trải dài từ ${meta.first_date} đến ${meta.last_date}. Các biến được mô tả trong Bảng `),
  T("1", { b: true }), T("."),
]));
add(TabCaption("variables", "Mô tả các biến trong bộ dữ liệu VN-Index"));
add(tblVariables);
add(Note("Nguồn: data/raw/vnindex_raw_meta.json (sinh bởi src/data_loader.py)."));

add(P("Hai đặc tính của nguồn dữ liệu được xử lý một cách tường minh thay vì bỏ qua:"));
add(Rich([
  T("Thứ nhất, thanh dữ liệu cuối cùng trong tệp nguồn (ngày "),
  T(meta.trim.dropped_date, { b: true }),
  T(") là một phiên CHƯA HOÀN TẤT. Bộ dữ liệu được công bố vào giữa phiên giao dịch đó; khối lượng của thanh này chỉ đạt "),
  T(int(meta.trim.volume), { b: true }),
  T(" cổ phiếu so với trung vị 21 phiên gần nhất là "),
  T(int(Math_round(meta.trim.median_volume_last_21_bars)), { b: true }),
  T(" cổ phiếu. Thanh này đã bị loại bỏ và việc loại bỏ được ghi lại trong tệp siêu dữ liệu."),
]));
add(Rich([
  T("Thứ hai, biến Open trùng với giá đóng cửa phiên liền trước ở "),
  T(num(meta.share_of_rows_where_open_equals_previous_close * 100, 1) + "%", { b: true }),
  T(" số dòng. Đây là đặc tính của luồng dữ liệu gốc. Vì toàn bộ phân tích được xây dựng trên biến Close, đặc tính này được ghi nhận và công bố chứ không được \"sửa\"."),
]));

add(H("Đối chiếu với nguồn dữ liệu độc lập", HeadingLevel.HEADING_2));
add(P(`Do nguồn chính là bản phân phối lại bởi bên thứ ba chứ không phải công bố chính thức của HOSE, nghiên cứu thực hiện đối chiếu định lượng với nguồn độc lập. Kết quả được trình bày trong Bảng ${tn('crossSource')}.`));
add(TabCaption("crossSource", "Kết quả đối chiếu nguồn dữ liệu chính với nguồn độc lập"));
add(tblCross);
add(Note("Nguồn: results/source_crosscheck.json (sinh bởi src/data_crosscheck.py)."));
add(Rich([
  T("Hai nguồn dữ liệu mô tả cùng một chuỗi với mức trùng khớp rất cao: hệ số tương quan giá đóng cửa đạt "),
  T(num(cross.close_correlation, 8), { b: true }),
  T(" và trung vị sai lệch tương đối tuyệt đối chỉ ở mức "),
  T(Number(cross.median_abs_rel_diff).toExponential(2), { b: true }),
  T(", tức xấp xỉ sai số biểu diễn dấu phẩy động. Quan trọng hơn, nguồn chính chứa thêm "),
  T(int(cross.n_sessions_only_in_primary), { b: true }),
  T(" phiên mà nguồn đối chiếu thiếu, trong khi KHÔNG thiếu phiên nào mà nguồn đối chiếu có."),
]));
add(P("Phần sai lệch còn lại tập trung ở giai đoạn thị trường mỏng trước năm 2010 và được ghi nhận như một hạn chế của dữ liệu, không phải khiếm khuyết làm vô hiệu phân tích."));

add(H("Toàn bộ bộ dữ liệu nguồn", HeadingLevel.HEADING_2));
add(Rich([
  T(`Bộ dữ liệu nguồn gồm ${Object.keys(inventory).length} tệp CSV, được sử dụng đầy đủ trong nghiên cứu này với tổng cộng `),
  T(int(totalBars) + " quan sát", { b: true }),
  T(". Các tệp thuộc hai họ có lược đồ và mốc kết thúc khác nhau:"),
]));
[
  "Họ HOSE_DLY (6 tệp): có cột khối lượng, dữ liệu kéo dài tới 2025-12-12, nhưng chỉ cung cấp tần suất ngày và 30 phút.",
  "Họ HOSE (13 tệp): không có cột khối lượng, kết thúc ở 2024-12-09, nhưng cung cấp đủ bốn tần suất và là nguồn duy nhất của chuỗi USD/VND.",
].forEach((t) => add(Bullet(t)));
add(P(`Vì không họ nào bao phủ toàn bộ, nghiên cứu chọn một tệp CHÍNH cho mỗi cặp (chỉ số, tần suất) và giữ tệp trùng lặp của họ còn lại làm phiên bản ĐỐI CHIẾU độc lập. Họ HOSE_DLY được ưu tiên ở nơi nó tồn tại vì có khối lượng và dài hơn một năm; họ HOSE là nguồn chính cho tần suất 1 giờ, phiên nửa ngày và cho USD/VND. Bảng ${tn('coverage')} liệt kê toàn bộ các chuỗi chính.`));
add(TabCaption("coverage", "Các chuỗi dữ liệu chính được sử dụng trong nghiên cứu"));
add(tblDatasetCoverage);
add(Note("Nguồn: results/series_inventory.json (sinh bởi src/data_loader.py, đăng ký trong src/catalog.py)."));

add(H("Cấu trúc phiên giao dịch và hệ quả đối với dữ liệu trong phiên", HeadingLevel.HEADING_2));
add(P(`Cấu trúc phiên được xác định TỪ CHÍNH DỮ LIỆU (thời điểm mở của các thanh), không phải từ giả định. Sàn HOSE giao dịch buổi sáng 09:00–11:30 và buổi chiều 13:00–14:45 theo giờ Việt Nam. Bảng ${tn('session')} tóm tắt số thanh dữ liệu tương ứng mỗi phiên.`));
add(TabCaption("session", "Cấu trúc phiên giao dịch theo từng tần suất lấy mẫu"));
add(tblSessionStructure);
add(Note("Nguồn: src/catalog.py, đối chiếu với phân bố thời điểm thanh trong dữ liệu thực tế."));
add(P("Hai hệ quả được xử lý tường minh thay vì bỏ qua:"));
add(Rich([
  T("Thứ nhất, thanh cuối mỗi phiên là thanh cụt: thanh 11:30 ở tần suất 30 phút chỉ dài 15 phút, thanh 11:00 ở tần suất 1 giờ chỉ dài 30 phút. Tần suất gọi là \"4 giờ\" thực chất là "),
  T("một thanh cho mỗi phiên nửa ngày", { b: true }),
  T(", không phải thanh 4 giờ đồng hồ."),
]));
add(Rich([
  T("Thứ hai, trên lưới trong phiên các thanh liên tiếp "),
  T("KHÔNG cách đều nhau theo thời gian thực", { b: true }),
  T(". Thanh đầu tiên của một ngày bắc qua khoảng nghỉ đêm (khoảng 18 giờ) và thanh 13:00 bắc qua giờ nghỉ trưa. Nếu gộp chung, ta sẽ trộn một lợi suất một ngày vào mẫu các lợi suất 30 phút và làm sai lệch mọi ước lượng mô men. Vì vậy các thanh này được ĐÁNH DẤU và LOẠI khỏi thống kê trong phiên. Riêng ở tần suất phiên nửa ngày thì mọi thanh đều bắc qua một khoảng nghỉ, nên sự phân biệt này không còn ý nghĩa và toàn bộ thanh được sử dụng — điều này được nêu rõ chứ không xử lý ngầm."),
]));

add(H("Xử lý đuôi dữ liệu chưa hoàn tất", HeadingLevel.HEADING_2));
add(Rich([
  T("Các tệp họ HOSE_DLY được công bố vào giữa phiên giao dịch ngày 2025-12-12, nên quan sát cuối của chúng là quan sát dở dang. Quy tắc cắt bỏ được chọn theo tần suất: với thanh ngày, cắt thanh cuối khi khối lượng của nó tụt xuống dưới 60% trung vị gần nhất (tỷ lệ quan sát thực tế 0.40–0.47 ở cả ba chỉ số); với dữ liệu trong phiên, cắt cả NGÀY cuối cùng khi ngày đó có ít thanh hơn một phiên đầy đủ (quan sát thực tế: 7 trên 10 thanh). Tổng cộng "),
  T(nTrimmed + " đuôi dữ liệu", { b: true }),
  T(" đã được cắt bỏ. Họ HOSE kết thúc bằng các phiên hoàn chỉnh nên không bị cắt — điều này đã được kiểm chứng chứ không giả định."),
]));

add(H("Kiểm tra chất lượng dữ liệu", HeadingLevel.HEADING_2));
add(P(`Quy trình kiểm tra chất lượng chỉ thực hiện đo lường và báo cáo, không thay đổi dữ liệu. Kết quả được tổng hợp trong Bảng ${tn('quality')}.`));
add(TabCaption("quality", "Kết quả kiểm tra chất lượng dữ liệu thô"));
add(tblQuality);
add(Note("Nguồn: results/data_quality_report.json (sinh bởi src/data_quality.py)."));
add(Rich([
  T("Bộ dữ liệu không có giá trị khuyết, không có ngày trùng lặp, không có phiên cuối tuần và không có thanh OHLC mâu thuẫn nội tại. Trong số "),
  T(int(gq.n_gaps_examined), { b: true }),
  T(" khoảng trống lịch bỏ qua từ hai ngày làm việc trở lên, "),
  T(int(gq.n_holiday_consistent), { b: true }),
  T(" khoảng trống phù hợp với các kỳ nghỉ lễ Việt Nam (Tết Nguyên đán, Giỗ Tổ Hùng Vương, 30/4–1/5, Quốc khánh, Tết Dương lịch) và "),
  T(int(gq.n_unexplained), { b: true }),
  T(" khoảng trống không giải thích được. Quan sát lợi suất tính qua khoảng trống này được ĐÁNH DẤU chứ không bị loại bỏ."),
]));

add(P(`Quy trình kiểm tra tương tự được áp dụng cho TOÀN BỘ các chuỗi trong bộ dữ liệu, không riêng chuỗi trọng tâm. Kết quả tổng hợp trong Bảng ${tn('multiQuality')}.`));
add(TabCaption("multiQuality", "Kết quả kiểm tra chất lượng trên toàn bộ bộ dữ liệu"));
add(tblMultiQuality);
add(Note("Nguồn: results/series_quality.json (sinh bởi src/data_quality.py)."));
add(Rich([
  T("Trên "), T(int(totalBars), { b: true }),
  T(" quan sát của toàn bộ bộ dữ liệu, không phát hiện "),
  T("bất kỳ", { b: true }),
  T(" timestamp trùng lặp, giá trị khuyết, giá phi lý, thanh có High < Low, thanh OHLC mâu thuẫn nội tại hay thanh rơi vào cuối tuần nào. Đây là mức chất lượng cao bất thường đối với dữ liệu thị trường được phân phối lại bởi bên thứ ba, và là lý do bộ dữ liệu này được chấp nhận làm nguồn chính."),
]));
add(Rich([
  T("Một lưu ý quan trọng về phạm vi áp dụng: bộ phân loại khoảng trống lịch mã hóa lịch nghỉ lễ của sàn HOSE, nên nó CHỈ được áp dụng cho ba chỉ số cổ phiếu niêm yết trên HOSE. Chuỗi USD/VND giao dịch theo lịch hoàn toàn khác; với chuỗi này các khoảng trống vẫn được đếm nhưng "),
  T("không được gán kết luận", { b: true }),
  T(", vì gọi một khoảng trống của thị trường ngoại hối là \"không giải thích được\" khi đối chiếu với lịch nghỉ lễ chứng khoán Việt Nam là một phán quyết vô nghĩa."),
]));

add(H("Tiền xử lý dữ liệu", HeadingLevel.HEADING_2));
add(P("Quy trình tiền xử lý được xây dựng thành một pipeline tái lập được, với các quyết định sau, tất cả đều có thể kiểm tra lại:"));
[
  "Tệp dữ liệu thô không bao giờ bị chỉnh sửa; mọi bước sau đều ghi ra tệp mới trong data/processed/.",
  "Dữ liệu được sắp xếp tăng dần theo thời gian và loại bỏ trùng lặp theo ngày giao dịch.",
  "Các ngày không giao dịch KHÔNG được chèn thêm và KHÔNG được nội suy. Chèn thêm ngày nghỉ sẽ tạo ra lợi suất bằng 0 giả tạo và làm chệch mọi ước lượng phương sai xuống dưới giá trị thực.",
  "Các cột chỉ báo kỹ thuật có sẵn trong tệp nguồn (EMA 55/89/200) bị loại bỏ khi nạp vì chúng là biến dẫn xuất từ Close.",
  "Các quan sát cực đoan KHÔNG bị loại bỏ ở bước tiền xử lý; việc phân loại chúng thuộc về bước phân tích quan sát cực đoan.",
  "Quan sát lợi suất đầu tiên là NaN theo định nghĩa (không có quan sát liền trước) và không bao giờ được điền giá trị thay thế.",
].forEach((t) => add(Bullet(t)));

add(H("Phương pháp phân tích khám phá dữ liệu", HeadingLevel.HEADING_2));
add(P("Phân tích khám phá được thực hiện song song trên hai đối tượng có ý nghĩa khác nhau: chuỗi mức chỉ số và chuỗi lợi suất. Với mỗi chuỗi, nghiên cứu tính các thống kê mô tả gồm trung bình, trung vị, phương sai, độ lệch chuẩn, cực trị, các phân vị, độ lệch (skewness) và độ nhọn vượt (excess kurtosis)."));
add(P("Tính chuẩn của phân phối lợi suất được kiểm định bằng ba kiểm định độc lập là Jarque–Bera, D'Agostino–Pearson K² và Shapiro–Wilk, thay vì kết luận bằng quan sát trực quan trên biểu đồ. Kiểm định Shapiro–Wilk được áp dụng trên mẫu con 5.000 quan sát do giới hạn độ chính xác của thuật toán; mẫu con được rút với hạt giống ngẫu nhiên cố định nên kết quả tái lập được."));
add(P("Ngoài kiểm định hình thức, nghiên cứu còn so sánh tần suất quan sát vượt các ngưỡng k lần độ lệch chuẩn với tần suất kỳ vọng dưới giả định phân phối chuẩn, nhằm định lượng mức độ dày của đuôi phân phối."));

add(H("Phương pháp kiểm định tính dừng", HeadingLevel.HEADING_2));
add(P("Nghiên cứu áp dụng đồng thời kiểm định ADF và KPSS trên sáu chuỗi: mức chỉ số (với hằng số và với hằng số kèm xu thế), logarit mức chỉ số (hai dạng tương ứng), sai phân bậc một của mức, và chuỗi lợi suất logarit. Bậc trễ của ADF được chọn tự động theo tiêu chuẩn AIC; băng thông của KPSS được chọn tự động theo phương pháp Newey–West. Mức ý nghĩa sử dụng thống nhất là α = 0.05."));
add(P("Kết luận chỉ được coi là vững khi hai kiểm định cho kết quả nhất quán theo hướng ngược chiều nhau về giả thuyết gốc; trường hợp cả hai cùng bác bỏ hoặc cùng không bác bỏ được ghi nhận là mơ hồ."));

add(H("Phương pháp phân tích ACF/PACF", HeadingLevel.HEADING_2));
add(P("ACF và PACF được ước lượng tới độ trễ 40 phiên. Do chỉ có ý nghĩa diễn giải trên chuỗi dừng, phân tích chính được thực hiện trên chuỗi lợi suất logarit; chuỗi mức chỉ số chỉ được đưa vào để đối chiếu, làm nổi bật hành vi nghiệm đơn vị. Hai chuỗi biến đổi |r| và r² được phân tích bổ sung vì đây là công cụ chuẩn để phát hiện cụm biến động."));
add(P("Kiểm định Ljung–Box được thực hiện tại các độ trễ 5, 10, 20 và 40 cho cả ba chuỗi lợi suất, giá trị tuyệt đối và bình phương lợi suất."));

add(H("Phương pháp phân tích biến động", HeadingLevel.HEADING_2));
add(P("Biến động được phân tích ở ba mức độ. Thứ nhất, độ lệch chuẩn trượt của lợi suất logarit được tính trên các cửa sổ 21, 63 và 252 phiên và quy đổi sang đơn vị năm với hệ số căn bậc hai của 252. Thứ hai, chuỗi giá trị tuyệt đối của lợi suất được khảo sát trực tiếp để quan sát hiện tượng cụm biến động. Thứ ba, biến động được phân rã theo từng năm dương lịch nhằm so sánh các giai đoạn yên tĩnh và giai đoạn nhiều biến động."));
add(P("Việc sử dụng mô hình phương sai có điều kiện (ARCH/GARCH) không được mặc định áp dụng. Quyết định này phụ thuộc vào bằng chứng thực nghiệm về cụm biến động, và bước kiểm định hình thức tương ứng (ARCH-LM) hiện chưa được triển khai."));

add(H("Phương pháp mô hình hóa", HeadingLevel.HEADING_2));
add(P("Dựa trên các đặc trưng thống kê thu được, lớp mô hình dự kiến gồm: mô hình cơ sở naive, trung bình trượt, san mũ, và họ ARIMA với bậc được lựa chọn từ cấu trúc ACF/PACF thực nghiệm. Mô hình mùa vụ SARIMA chỉ được đưa vào nếu có bằng chứng thống kê về tính mùa vụ."));
add(NotEvaluated("Toàn bộ bước ước lượng mô hình dự báo chưa được triển khai trong dự án tại thời điểm lập báo cáo này. Không có tham số mô hình, giá trị dự báo hay chỉ số sai số nào được ước lượng."));

add(H("Phương pháp chia tập dữ liệu theo thứ tự thời gian", HeadingLevel.HEADING_2));
add(P("Thiết kế dự kiến là chia tập theo thứ tự thời gian với tỷ lệ 70% dữ liệu sớm nhất dùng để huấn luyện, 15% tiếp theo dùng để kiểm định và 15% mới nhất dùng để kiểm tra. Các tham số tỷ lệ này đã được khai báo trong tệp cấu hình của dự án. Không sử dụng bất kỳ hình thức xáo trộn ngẫu nhiên nào."));
add(NotEvaluated("Việc chia tập train/validation/test chưa được thực thi vì chưa có mô hình nào được huấn luyện. Các tỷ lệ nêu trên mới chỉ là cấu hình, chưa phải kết quả."));

add(new Paragraph({ children: [new PageBreak()] }));

// ===== CHUONG 4 =====
add(H("KẾT QUẢ VÀ THẢO LUẬN", HeadingLevel.HEADING_1));
add(Note(`Toàn bộ số liệu trong chương này được sinh ra từ việc thực thi thực tế mã nguồn của dự án trên bộ dữ liệu ${meta.first_date} – ${meta.last_date}, và được đọc trực tiếp từ các tệp trong thư mục results/ khi tạo báo cáo này.`));

add(H("Thống kê mô tả", HeadingLevel.HEADING_2));
add(P(`Bảng ${tn('descriptive')} trình bày thống kê mô tả của chuỗi mức chỉ số và các chuỗi lợi suất. Cần nhấn mạnh rằng thống kê mô tả của chuỗi mức và chuỗi lợi suất có ý nghĩa diễn giải hoàn toàn khác nhau: các thống kê của chuỗi mức chỉ mô tả vị trí của chỉ số trong giai đoạn quan sát và không phải là đại lượng ổn định theo thời gian.`));
add(TabCaption("descriptive", "Thống kê mô tả chuỗi VN-Index và chuỗi lợi suất"));
add(tblDescriptive);
add(Note("Nguồn: results/descriptive_statistics.csv."));
add(Rich([
  T("Chuỗi mức chỉ số dao động từ "), T(num(dLevel.min, 2), { b: true }),
  T(" điểm đến "), T(num(dLevel.max, 2), { b: true }),
  T(" điểm, với trung bình "), T(num(dLevel.mean, 2), { b: true }),
  T(" điểm và trung vị "), T(num(dLevel.median, 2), { b: true }),
  T(" điểm. Chênh lệch giữa trung bình và trung vị cùng với độ lệch dương "),
  T(num(dLevel.skewness, 4), { b: true }),
  T(" phản ánh việc chỉ số dành phần lớn thời gian ở vùng giá trị thấp và chỉ đạt các mức cao trong những giai đoạn tăng mạnh gần đây."),
]));
add(Rich([
  T("Chuỗi lợi suất logarit có trung bình "), T(num(dLog.mean, 4), { b: true }),
  T("% mỗi phiên và độ lệch chuẩn "), T(num(dLog.std, 4), { b: true }),
  T("%. Độ lệch âm ("), T(num(dLog.skewness, 4), { b: true }),
  T(") cho thấy các phiên giảm mạnh có xu hướng cực đoan hơn các phiên tăng mạnh. Độ nhọn vượt "),
  T(num(dLog.excess_kurtosis, 4), { b: true }),
  T(" lớn hơn 0 rất nhiều, là dấu hiệu định lượng đầu tiên của phân phối đuôi dày."),
]));
add(Rich([
  T("Một quan sát đáng chú ý: biên độ lợi suất giản đơn nằm trong khoảng từ "),
  T(num(dSimple.min, 4), { b: true }), T("% đến "), T(num(dSimple.max, 4), { b: true }),
  T("%. Biên độ bị chặn quanh ngưỡng ±7% này nhất quán với cơ chế biên độ dao động giá áp dụng cho cổ phiếu thành phần trên HOSE đã đề cập ở Chương 2. Đây là một ràng buộc thể chế, không phải đặc tính ngẫu nhiên của chuỗi."),
]));

add(H("Diễn biến của VN-Index theo thời gian", HeadingLevel.HEADING_2));
add(P("Hình 1 trình bày giá trị đóng cửa của VN-Index cùng khối lượng khớp lệnh trên toàn bộ giai đoạn nghiên cứu."));
add(Figure("01_vnindex_close_and_volume.png", 932 / 1427));
add(FigCaption("Giá trị đóng cửa VN-Index và khối lượng khớp lệnh theo thời gian"));
add(P("Biểu đồ cho thấy chuỗi không dao động quanh một mức trung bình cố định mà trải qua nhiều chu kỳ tăng giảm với biên độ khác nhau, kèm theo sự gia tăng rõ rệt của khối lượng giao dịch trong thập kỷ gần đây. Đặc điểm trực quan này đã gợi ý chuỗi mức nhiều khả năng không dừng, và giả thuyết đó được kiểm định hình thức ở mục sau."));
add(P("Hình 2 phóng to biên độ dao động trong phiên và giá đóng cửa của giai đoạn gần nhất, nhằm minh họa cấu trúc dữ liệu OHLC ở mức chi tiết."));
add(Figure("02_vnindex_ohlc_recent.png", 701 / 1404));
add(FigCaption("Biên độ cao – thấp trong phiên và giá đóng cửa của VN-Index, giai đoạn gần nhất"));

add(H("Phân tích chuỗi lợi suất và phân phối lợi suất", HeadingLevel.HEADING_2));
add(P("Hình 3 trình bày chuỗi lợi suất logarit hàng ngày trên toàn giai đoạn."));
add(Figure("03_daily_log_returns.png", 644 / 1382));
add(FigCaption("Lợi suất logarit hàng ngày của VN-Index theo thời gian"));
add(P("Khác với chuỗi mức, chuỗi lợi suất dao động quanh mức gần 0 trên toàn giai đoạn — một dấu hiệu trực quan của tính dừng. Tuy nhiên biên độ dao động rõ ràng không đồng nhất theo thời gian: có những giai đoạn biên độ mở rộng mạnh và những giai đoạn biên độ thu hẹp. Đây chính là biểu hiện của phương sai thay đổi theo thời gian."));
add(P("Hình 4 khảo sát phân phối của chuỗi lợi suất bằng ba góc nhìn: biểu đồ tần suất đối chiếu với phân phối chuẩn khớp, cùng biểu đồ đó ở thang mật độ logarit để quan sát phần đuôi, và biểu đồ Q-Q chuẩn."));
add(Figure("04_return_distribution.png", 595 / 1934));
add(FigCaption("Phân phối lợi suất logarit hàng ngày của VN-Index"));
add(P(`Trên biểu đồ Q-Q, các quan sát ở hai đầu lệch rõ khỏi đường chuẩn, cho thấy cả hai đuôi đều dày hơn phân phối chuẩn. Tuy nhiên, quan sát trực quan không đủ để kết luận; kết quả kiểm định hình thức được trình bày trong Bảng ${tn('normality')}.`));
add(TabCaption("normality", "Kết quả kiểm định tính chuẩn của phân phối lợi suất"));
add(tblNormality);
add(Note("Nguồn: results/normality_tests.csv. Cả ba kiểm định đều có H₀: mẫu tuân theo phân phối chuẩn."));
add(Rich([
  T("Cả ba kiểm định đều bác bỏ giả thuyết gốc ở mọi mức ý nghĩa thông thường. Với chuỗi lợi suất logarit, thống kê Jarque–Bera đạt "),
  T(num(norm[0].statistic, 2), { b: true }), T(" với p-value "), T(pv(norm[0].p_value), { b: true }),
  T("; thống kê D'Agostino–Pearson K² đạt "), T(num(norm[1].statistic, 2), { b: true }),
  T(" với p-value "), T(pv(norm[1].p_value), { b: true }),
  T("; thống kê Shapiro–Wilk trên mẫu con 5.000 quan sát đạt W = "),
  T(num(norm[2].statistic, 4), { b: true }), T(" với p-value "), T(pv(norm[2].p_value), { b: true }), T("."),
]));
add(P("Kết luận: ở mức ý nghĩa α = 0.05, bác bỏ giả thuyết phân phối chuẩn. Đây là câu trả lời cho câu hỏi nghiên cứu CH2. Hệ quả phương pháp là mọi khoảng tin cậy hoặc kiểm định dựa trên giả định chuẩn tắc áp dụng trực tiếp cho lợi suất VN-Index đều cần được diễn giải thận trọng."));
add(P(`Bảng ${tn('tails')} định lượng mức độ dày của đuôi bằng cách so sánh số phiên vượt ngưỡng k lần độ lệch chuẩn với kỳ vọng dưới phân phối chuẩn.`));
add(TabCaption("tails", "So sánh tần suất quan sát ở đuôi với kỳ vọng dưới phân phối chuẩn"));
add(tblTails);
add(Note("Nguồn: results/eda_results.json, mục tail_comparison_log_returns."));
add(Rich([
  T("Mức độ lệch tăng rất nhanh khi đi ra xa: ở ngưỡng 3σ, số phiên quan sát ("),
  T(int(tc.gt_3_sigma.observed_days), { b: true }), T(") gấp "),
  T(num(tc.gt_3_sigma.ratio_observed_to_normal, 2) + " lần", { b: true }),
  T(" kỳ vọng chuẩn; ở ngưỡng 4σ, tỷ lệ này lên tới "),
  T(num(tc.gt_4_sigma.ratio_observed_to_normal, 2) + " lần", { b: true }),
  T(". Nói cách khác, các biến cố cực đoan trên thị trường Việt Nam xuất hiện thường xuyên hơn nhiều so với mức mà mô hình chuẩn tắc dự đoán."),
]));
add(P("Hình 5 bổ sung góc nhìn phân phối theo từng năm và theo ngày trong tuần."));
add(Figure("05_return_boxplots.png", 660 / 1935));
add(FigCaption("Biểu đồ hộp của lợi suất logarit theo năm và theo ngày trong tuần"));

add(H("Kết quả kiểm định tính dừng", HeadingLevel.HEADING_2));
add(P(`Bảng ${tn('stationarity')} trình bày kết quả kiểm định ADF và KPSS trên sáu chuỗi.`));
add(TabCaption("stationarity", "Kết quả kiểm định tính dừng ADF và KPSS (α = 0.05)"));
add(tblStationarity);
add(Note("Nguồn: results/stationarity_tests.csv. Ký hiệu c = hằng số, ct = hằng số và xu thế. Giá trị p của KPSS bị chặn trong khoảng bảng tra [0.01, 0.10]."));
add(P("Cách đọc kết quả như sau. Với chuỗi mức chỉ số, kiểm định ADF KHÔNG bác bỏ được giả thuyết nghiệm đơn vị, đồng thời kiểm định KPSS BÁC BỎ giả thuyết chuỗi dừng. Hai kiểm định có giả thuyết gốc trái ngược nhau cùng chỉ về một hướng, nên kết luận chuỗi mức không dừng là kết luận vững, không phải kết quả mơ hồ."));
add(Rich([
  T("Cụ thể, với dạng hằng số, thống kê ADF của chuỗi mức là "), T(num(stat[0].ADF_stat, 4), { b: true }),
  T(" với p-value "), T(num(stat[0].ADF_p, 4), { b: true }),
  T(", lớn hơn nhiều so với 0.05; thống kê KPSS là "), T(num(stat[0].KPSS_stat, 4), { b: true }),
  T(", vượt xa giá trị tới hạn 5% là "), T(num(stat[0]["KPSS_crit_5%"], 4), { b: true }),
  T(". Việc bổ sung thành phần xu thế xác định cũng không làm thay đổi kết luận."),
]));
add(Rich([
  T("Ngược lại, sau khi lấy sai phân bậc một, kết luận đảo chiều hoàn toàn. Với chuỗi lợi suất logarit, thống kê ADF là "),
  T(num(stat[5].ADF_stat, 4), { b: true }), T(" với p-value "), T(pv(stat[5].ADF_p), { b: true }),
  T(" (bác bỏ mạnh giả thuyết nghiệm đơn vị), trong khi thống kê KPSS chỉ là "),
  T(num(stat[5].KPSS_stat, 4), { b: true }),
  T(", thấp hơn giá trị tới hạn nên không bác bỏ giả thuyết dừng. Cả hai kiểm định cùng ủng hộ tính dừng."),
]));
add(P("Kết luận cho câu hỏi nghiên cứu CH1: chuỗi mức VN-Index hành xử như một quá trình tích hợp bậc một, ký hiệu I(1); chuỗi lợi suất logarit là chuỗi dừng. Về mặt phương pháp, điều này xác nhận rằng phân tích và mô hình hóa phải được tiến hành trên chuỗi lợi suất chứ không phải chuỗi mức."));

add(H("Kết quả phân tích ACF và PACF", HeadingLevel.HEADING_2));
add(P("Hình 6 đối chiếu cấu trúc tự tương quan của chuỗi mức và chuỗi lợi suất."));
add(Figure("08_acf_pacf_level_and_returns.png", 948 / 1771));
add(FigCaption("ACF và PACF của chuỗi mức VN-Index và chuỗi lợi suất logarit"));
add(Rich([
  T("Chuỗi mức có ACF suy giảm cực kỳ chậm, với ACF(1) = "),
  T(num(acorr.acf_pacf["VN-Index level (points)"].values[0].acf, 4), { b: true }),
  T(" và toàn bộ 40 độ trễ đều có ý nghĩa thống kê, trong khi PACF cắt cụt gần như ngay sau độ trễ 1. Đây là dạng đặc trưng của quá trình có nghiệm đơn vị, hoàn toàn nhất quán với kết quả kiểm định ở mục trước."),
]));
add(P(`Chuỗi lợi suất có cấu trúc khác hẳn. Bảng ${tn('acf')} trình bày năm độ trễ đầu tiên của ACF cho ba chuỗi liên quan.`));
add(TabCaption("acf", "Hệ số tự tương quan ACF tại năm độ trễ đầu tiên"));
add(tblACF);
add(Note(`Nguồn: results/autocorrelation.json. Dải nhiễu trắng 95% là ±${num(acorr.acf_pacf["Daily log return (%)"].white_noise_band_95, 4)}.`));
add(Rich([
  T("Lợi suất có ACF(1) = "), T(num(acorr.acf_pacf["Daily log return (%)"].values[0].acf, 4), { b: true }),
  T(", vượt rõ dải nhiễu trắng, nhưng giảm mạnh ngay ở độ trễ 2 xuống còn "),
  T(num(acorr.acf_pacf["Daily log return (%)"].values[1].acf, 4), { b: true }),
  T(". Tổng cộng có "), T(`${acorr.acf_pacf["Daily log return (%)"].n_significant_acf_lags}/40`, { b: true }),
  T(" độ trễ có ý nghĩa. Mức tự tương quan bậc một dương và đáng kể này là đặc trưng thường thấy ở các thị trường mới nổi, nơi thông tin được phản ánh vào giá chậm hơn."),
]));
add(P(`Bảng ${tn('ljung')} trình bày kết quả kiểm định Ljung–Box.`));
add(TabCaption("ljung", "Kết quả kiểm định Ljung–Box tại các độ trễ 5, 10, 20 và 40"));
add(tblLjung);
add(Note("Nguồn: results/ljung_box_tests.csv. H₀: không có tự tương quan tới độ trễ h."));
add(Rich([
  T("Giả thuyết nhiễu trắng bị bác bỏ ở mọi độ trễ được kiểm tra. Với chuỗi lợi suất, Q(10) = "),
  T(num(ljung[1].statistic, 2), { b: true }), T(" với p-value "), T(pv(ljung[1].p_value), { b: true }),
  T(". Đây là câu trả lời cho câu hỏi nghiên cứu CH3: lợi suất VN-Index CÓ phụ thuộc chuỗi có ý nghĩa thống kê, tuy mức độ khiêm tốn và tập trung ở độ trễ ngắn."),
]));
add(Rich([
  T("CẢNH BÁO QUAN TRỌNG VỀ CÁCH DIỄN GIẢI. ", { b: true }),
  T("Giá trị ACF(1) = "),
  T(num(acorr.acf_pacf["Daily log return (%)"].values[0].acf, 4), { b: true }),
  T(" nêu trên được tính trên TOÀN BỘ mẫu 2000–2025. Phân tích đa chuỗi ở mục 4.9 cho thấy con số này phần lớn phản ánh giai đoạn thị trường mỏng 2000–2013 chứ không phải đặc tính hiện tại của VN-Index: khi đo trên giai đoạn 2014–2025, hệ số này giảm xuống còn "),
  T(num(matched1D.stats.VNINDEX.acf1, 4), { b: true }),
  T(". Mọi phát biểu về mức độ phụ thuộc chuỗi của VN-Index chỉ dựa trên con số toàn mẫu mà bỏ qua lưu ý này đều gây hiểu nhầm."),
]));

add(H("Kết quả phân tích biến động", HeadingLevel.HEADING_2));
add(P("Hình 7 trình bày biến động trượt quy đổi theo năm trên ba cửa sổ khác nhau, cùng với chuỗi giá trị tuyệt đối của lợi suất."));
add(Figure("06_rolling_volatility.png", 1035 / 1635));
add(FigCaption("Biến động trượt quy đổi theo năm và giá trị tuyệt đối của lợi suất logarit"));
add(P("Biểu đồ cho thấy biến động không phải là hằng số mà thay đổi mạnh theo thời gian, và các phiên biến động lớn có xu hướng tụ lại thành cụm thay vì phân tán ngẫu nhiên. Bằng chứng định lượng cho nhận định này nằm ở cấu trúc tự tương quan của các đại lượng đại diện cho biến động, trình bày ở Hình 8."));
add(Figure("09_acf_pacf_volatility_proxies.png", 948 / 1771));
add(FigCaption("ACF và PACF của giá trị tuyệt đối và bình phương lợi suất logarit"));
add(Rich([
  T("Đây là kết quả đáng chú ý nhất của phân tích tự tương quan. Trong khi bản thân lợi suất chỉ có tự tương quan yếu, thì giá trị tuyệt đối |r| có ACF(1) = "),
  T(num(acorr.acf_pacf["Absolute log return |r|"].values[0].acf, 4), { b: true }),
  T(" và bình phương r² có ACF(1) = "),
  T(num(acorr.acf_pacf["Squared log return r^2"].values[0].acf, 4), { b: true }),
  T(". Quan trọng hơn, cả hai chuỗi đều có ý nghĩa thống kê ở TOÀN BỘ 40 độ trễ được khảo sát, tức là mức biến động của hôm nay vẫn còn thông tin dự báo cho mức biến động của gần hai tháng giao dịch sau đó."),
]));
add(Rich([
  T("Kiểm định Ljung–Box khẳng định điều này với mức độ áp đảo: Q(10) đạt "),
  T(num(ljung[5].statistic, 0), { b: true }), T(" cho |r| và "),
  T(num(ljung[9].statistic, 0), { b: true }), T(" cho r², so với chỉ "),
  T(num(ljung[1].statistic, 2), { b: true }),
  T(" cho chuỗi lợi suất gốc. Đây là câu trả lời cho câu hỏi nghiên cứu CH4: VN-Index CÓ hiện tượng cụm biến động rõ rệt."),
]));
add(P(`Bảng ${tn('yearVol')} phân rã biến động theo từng năm dương lịch, cho phép so sánh định lượng giữa các giai đoạn yên tĩnh và các giai đoạn nhiều biến động.`));
add(TabCaption("yearVol", "Lợi suất và biến động quy đổi theo năm của VN-Index"));
add(tblYearVol);
add(Note("Nguồn: results/eda_results.json, mục yearly_summary. Biến động quy đổi theo năm = độ lệch chuẩn lợi suất ngày × căn bậc hai của 252."));
add(P("Bảng này cho thấy khoảng cách giữa năm yên tĩnh nhất và năm biến động nhất trong mẫu là rất lớn, củng cố kết luận rằng giả định phương sai không đổi là không phù hợp với chuỗi này."));
add(NotEvaluated("Kiểm định ARCH-LM và việc ước lượng mô hình GARCH chưa được triển khai. Do đó báo cáo KHÔNG đưa ra bất kỳ tham số mô hình phương sai có điều kiện nào. Bằng chứng về cụm biến động trình bày ở trên là bằng chứng mô tả và bằng chứng tự tương quan, đủ để biện minh cho việc triển khai GARCH ở bước tiếp theo, nhưng chưa phải là kết quả ước lượng GARCH."));

add(H("Kết quả phân tích hiệu ứng lịch", HeadingLevel.HEADING_2));
add(P("Hình 9 trình bày lợi suất trung bình theo ngày trong tuần, theo tháng trong năm và lợi suất tích lũy theo năm."));
add(Figure("07_calendar_effects.png", 585 / 1935));
add(FigCaption("Lợi suất trung bình theo ngày trong tuần, theo tháng và lợi suất tích lũy theo năm"));
add(P(`Bảng ${tn('dow')} trình bày thống kê mô tả theo ngày trong tuần và Bảng ${tn('calendarTests')} trình bày kết quả kiểm định hình thức.`));
add(TabCaption("dow", "Thống kê lợi suất logarit theo ngày trong tuần"));
add(tblDow);
add(Note("Nguồn: results/eda_results.json, mục day_of_week_effect."));
add(TabCaption("calendarTests", "Kết quả kiểm định hiệu ứng lịch"));
add(tblCalendarTests);
add(Note("Nguồn: results/eda_results.json. H₀ của ANOVA và Kruskal–Wallis: các nhóm có phân phối/trung bình như nhau. H₀ của Levene: phương sai các nhóm bằng nhau."));
add(Rich([
  T("Đối với hiệu ứng ngày trong tuần, kiểm định ANOVA cho F = "),
  T(num(eda.day_of_week_effect.tests[0].statistic, 4), { b: true }), T(" với p-value "),
  T(pv(eda.day_of_week_effect.tests[0].p_value), { b: true }),
  T(" và kiểm định phi tham số Kruskal–Wallis cho H = "),
  T(num(eda.day_of_week_effect.tests[1].statistic, 4), { b: true }), T(" với p-value "),
  T(pv(eda.day_of_week_effect.tests[1].p_value), { b: true }),
  T(". Cả hai đều bác bỏ H₀ ở mức α = 0.05. Kiểm định Levene cũng bác bỏ giả thuyết phương sai bằng nhau giữa các ngày."),
]));
add(Rich([
  T("Đối với hiệu ứng tháng, kết quả ngược lại: ANOVA cho F = "),
  T(num(eda.month_effect.tests[0].statistic, 4), { b: true }), T(" với p-value "),
  T(num(eda.month_effect.tests[0].p_value, 4), { b: true }),
  T(" và Kruskal–Wallis cho H = "), T(num(eda.month_effect.tests[1].statistic, 4), { b: true }),
  T(" với p-value "), T(num(eda.month_effect.tests[1].p_value, 4), { b: true }),
  T(". KHÔNG kiểm định nào bác bỏ được H₀ ở mức α = 0.05."),
]));
add(P("Đây là câu trả lời cho câu hỏi nghiên cứu CH5, và cần được phát biểu một cách thận trọng. Có bằng chứng thống kê về sự khác biệt giữa các ngày trong tuần, nhưng KHÔNG có bằng chứng về hiệu ứng tháng. Ba điểm cần phân biệt rõ:"));
[
  "Bằng chứng thống kê: sự khác biệt giữa các ngày trong tuần có ý nghĩa ở mức α = 0.05. Đây là kết quả thực nghiệm.",
  "Tính mùa vụ theo nghĩa chuỗi thời gian: một hiệu ứng ngày trong tuần KHÔNG tương đương với thành phần mùa vụ tuần hoàn trong mô hình SARIMA. Việc không có hiệu ứng tháng cho thấy không có cơ sở để đưa thành phần mùa vụ vào mô hình.",
  "Ý nghĩa kinh tế: chênh lệch trung bình giữa các ngày chỉ ở mức phần trăm nhỏ mỗi phiên, và báo cáo này CHƯA kiểm tra liệu hiệu ứng đó có tồn tại sau khi kiểm soát biến động và phân kỳ mẫu hay không. Do đó không được diễn giải kết quả này như một quy luật giao dịch có thể khai thác.",
].forEach((t) => add(Bullet(t)));

add(H("Phân tích quan sát biến động cực đoan", HeadingLevel.HEADING_2));
add(Rich([
  T("Nghiên cứu xác định các phiên có lợi suất vượt ngưỡng ±4 độ lệch chuẩn. Có "),
  T(int(em.n_beyond_threshold), { b: true }), T(" phiên như vậy, chiếm "),
  T(num(em.pct_of_sample_beyond_threshold, 3) + "%", { b: true }),
  T(` tổng số quan sát. Bảng ${tn('extreme')} liệt kê tám phiên giảm mạnh nhất và tám phiên tăng mạnh nhất.`),
]));
add(TabCaption("extreme", "Các phiên biến động cực đoan nhất của VN-Index"));
add(tblExtreme);
add(Note("Nguồn: results/eda_results.json, mục extreme_moves. z là số lần độ lệch chuẩn so với trung bình lợi suất."));
add(Rich([
  T("Phân bố theo năm của các phiên vượt ngưỡng 4σ rất mất cân đối: "),
  T(Object.entries(em.beyond_threshold_by_year).map(([y, n]) => `năm ${y}: ${n} phiên`).join(", "), { b: true }),
  T(". Việc phần lớn các quan sát cực đoan tập trung vào năm 2001 phản ánh bối cảnh thị trường giai đoạn đầu, khi HOSE chỉ có rất ít cổ phiếu niêm yết nên chỉ số nhạy cảm bất thường với biến động của từng mã."),
]));
add(Rich([
  T("Điểm quan trọng về mặt chất lượng dữ liệu: KHÔNG có phiên cực đoan nào trùng với thanh OHLC mâu thuẫn nội tại hay với khoảng trống lịch không giải thích được (đã kiểm tra: "),
  T(int(em.n_beyond_threshold_flagged_ohlc) + " phiên", { b: true }),
  T("). Do đó không có quan sát cực đoan nào được quy cho lỗi dữ liệu đã biết, và nghiên cứu KHÔNG loại bỏ bất kỳ quan sát cực đoan nào."),
]));
add(P("Quyết định giữ lại toàn bộ quan sát cực đoan được biện minh như sau: các phiên này là biến động thị trường thực, và chúng chính là phần thông tin quan trọng nhất của chuỗi đối với bài toán quản trị rủi ro. Loại bỏ chúng sẽ làm giảm giả tạo ước lượng biến động và làm sai lệch kết luận về độ dày đuôi phân phối."));

add(H("Kết quả phân tích so sánh trên toàn bộ bộ dữ liệu", HeadingLevel.HEADING_2));
add(Rich([
  T("Các mục trước tập trung vào VN-Index tần suất ngày. Mục này sử dụng toàn bộ "),
  T(nPrimary + " chuỗi chính", { b: true }),
  T(" để trả lời ba câu hỏi mà một chuỗi đơn lẻ không thể trả lời: các kết luận trên có đúng với những phân khúc thị trường khác không, chúng thay đổi thế nào theo tần suất lấy mẫu, và một chuỗi tài chính khác lớp tài sản có hành xử tương tự không."),
]));

add(P(`Trước hết là những đặc trưng ĐÚNG VỚI MỌI CHUỖI, được trình bày trong Bảng ${tn('universal')}.`));
add(TabCaption("universal", "Các đặc trưng thống kê phổ quát trên toàn bộ các chuỗi chính"));
add(tblUniversal);
add(Note("Nguồn: results/multiseries_battery.json (sinh bởi src/multiseries.py)."));
add(P("Cả ba đặc trưng cốt lõi tìm được ở VN-Index đều không phải là đặc thù riêng của chỉ số này: tính không dừng của chuỗi mức, tính phi chuẩn của phân phối lợi suất và hiện tượng cụm biến động xuất hiện ở tất cả các chuỗi, bất kể phân khúc thị trường, tần suất lấy mẫu hay lớp tài sản. Đây là các tính chất của thị trường chứ không phải của một chỉ số cụ thể."));

add(H("Kiểm soát giai đoạn mẫu: một kết quả cần đính chính", HeadingLevel.HEADING_2));
add(Rich([
  T("So sánh trực tiếp giữa các chỉ số cho một kết quả trông rất ấn tượng: VN-Index ngày có ACF(1) = "),
  T(num(BY["VNINDEX_1D"].acf1_return, 4), { b: true }),
  T(" trong khi VN30 chỉ đạt "), T(num(BY["VN30_1D"].acf1_return, 4), { b: true }),
  T(" và VN100 đạt "), T(num(BY["VN100_1D"].acf1_return, 4), { b: true }),
  T(" — gấp khoảng năm lần. Cách đọc tự nhiên là chỉ số rộng có mức phụ thuộc chuỗi cao hơn hẳn vì nó chứa nhiều cổ phiếu thanh khoản thấp, phản ánh thông tin vào giá chậm hơn."),
]));
add(Rich([
  T("Cách đọc đó KHÔNG đứng vững trước kiểm soát. ", { b: true }),
  T("VN-Index ngày bắt đầu từ năm 2000, VN30 từ 2012 và VN100 từ 2014, nên phép so sánh thô đã trộn lẫn hai yếu tố: phân khúc thị trường và giai đoạn mẫu. Khi giới hạn cả ba chuỗi về đúng "),
  T(int(matched1D.n_common) + " phiên", { b: true }),
  T(` mà cả ba cùng có (${matched1D.start} – ${matched1D.end}), kết quả đảo chiều như Bảng ${tn('matched')}.`),
]));
add(TabCaption("matched", "Tự tương quan bậc một: mẫu riêng của từng chỉ số so với giai đoạn chung"));
add(tblMatched);
add(Note("Nguồn: results/multiseries_battery.json, mục matched_period_comparison. Mọi chỉ số được đo trên đúng cùng một tập quan sát."));
add(Rich([
  T("Khoảng cách thu hẹp từ khoảng năm lần xuống còn khoảng 1,7 lần. Mức tự tương quan cao của VN-Index chủ yếu là "),
  T("hiệu ứng giai đoạn", { b: true }),
  T(", nằm ở thị trường mỏng và biên độ hẹp của những năm 2000–2013, chứ không phải khác biệt cấu trúc giữa các phân khúc ở hiện tại. Kết quả này được trình bày ở đây chính vì nó đính chính một kết luận mà phép so sánh thô sẽ dẫn tới."),
]));
add(Figure("12_matched_period_and_correlation.png", 645 / 1800));
add(FigCaption("Tự tương quan bậc một trước và sau khi kiểm soát giai đoạn mẫu, cùng ma trận tương quan lợi suất ngày"));

add(H("Ảnh hưởng của tần suất lấy mẫu", HeadingLevel.HEADING_2));
add(P(`Bảng ${tn('scaling')} trình bày các đặc trưng của VN-Index ở bốn tần suất lấy mẫu.`));
add(TabCaption("scaling", "Đặc trưng lợi suất VN-Index theo tần suất lấy mẫu"));
add(tblScaling);
add(Note("Nguồn: results/multiseries_battery.json, mục frequency_scaling. Mỗi dòng được đo trên giai đoạn mẫu riêng của tần suất đó, nên bảng mang tính gợi ý chứ không phải một kiểm định có kiểm soát."));
add(Rich([
  T("Hai quy luật hiện ra. Thứ nhất, độ lệch chuẩn quy về đơn vị ngày (nhân với căn bậc hai số thanh mỗi ngày) tương đối ổn định ở VN30 và VN100 (0,94–1,16 so với mức ngày 1,19), tức là biến động xấp xỉ tuân theo quy tắc căn bậc hai của thời gian. Thứ hai, và rõ rệt hơn: "),
  T("độ nhọn vượt giảm đơn điệu khi thanh dữ liệu rộng dần", { b: true }),
  T(`, từ ${num(scaleVNI.M30.excess_kurtosis, 2)} ở tần suất 30 phút xuống ${num(scaleVNI["1D"].excess_kurtosis, 2)} ở tần suất ngày. Đây là hiệu ứng "tiệm cận chuẩn khi tổng hợp" (aggregational Gaussianity) quen thuộc trong tài chính thực nghiệm: lợi suất tần suất càng cao thì đuôi phân phối càng dày.`),
]));
add(Figure("13_distribution_by_timeframe.png", 380 / 1400));
add(FigCaption("Phân phối lợi suất chuẩn hóa của VN-Index ở bốn tần suất, đối chiếu với phân phối chuẩn"));
add(Figure("11_frequency_scaling.png", 420 / 1300));
add(FigCaption("Biến động, độ dày đuôi và tự tương quan theo tần suất lấy mẫu"));

add(H("Cấu trúc trong phiên", HeadingLevel.HEADING_2));
add(P("Dữ liệu tần suất 30 phút cho phép quan sát cấu trúc theo thời điểm trong ngày, điều mà dữ liệu ngày không thể hiện được."));
add(Figure("14_intraday_pattern.png", 460 / 1900));
add(FigCaption("Lợi suất trung bình và biến động của VN-Index theo thời điểm trong ngày (tần suất 30 phút)"));
add(P("Biến động đạt đỉnh ở thanh mở cửa 09:00, giảm dần trong phiên sáng, rồi tăng trở lại ở thanh 14:00 trước giờ đóng cửa — dạng chữ U quen thuộc của thị trường cổ phiếu. Thanh 11:30 có biến động thấp nhất trong ngày, nhưng đây là một ĐẶC ĐIỂM KỸ THUẬT chứ không phải phát hiện kinh tế: thanh này chỉ dài 15 phút thay vì 30 phút, nên đương nhiên tích lũy ít biến động hơn. Việc nêu rõ điều này là cần thiết để tránh diễn giải sai một tạo tác của cấu trúc dữ liệu thành một quy luật thị trường."));

add(H("So sánh giữa các lớp tài sản", HeadingLevel.HEADING_2));
add(Rich([
  T(`Bảng ${tn('corr1D')} trình bày ma trận tương quan lợi suất ngày trên `),
  T(int(corr1D.n_overlapping_bars) + " phiên chung", { b: true }),
  T(` (${corr1D.overlap_start} – ${corr1D.overlap_end}).`),
]));
add(TabCaption("corr1D", "Ma trận tương quan Pearson của lợi suất logarit ngày"));
add(tblCorr1D);
add(Note("Nguồn: results/multiseries_battery.json, mục return_correlations."));
add(Rich([
  T("Ba chỉ số cổ phiếu gần như chuyển động cùng nhau (VN30–VN100 đạt "),
  T(num(corr1D.pearson.VN30.VN100, 3), { b: true }),
  T("), điều này hợp lý vì VN30 là tập con của VN100 và cả hai đều nằm trong VN-Index. Ngược lại, USD/VND có tương quan âm nhẹ với cả ba chỉ số (khoảng "),
  T(num(corr1D.pearson.VNINDEX.USDVND, 2), { b: true }),
  T("): giai đoạn đồng Việt Nam mất giá có xu hướng trùng với giai đoạn thị trường cổ phiếu yếu, tuy mức độ liên hệ là yếu và báo cáo này không kiểm định quan hệ nhân quả."),
]));
add(Figure("10_index_and_fx_comparison.png", 700 / 1100));
add(FigCaption("Ba chỉ số cổ phiếu quy về gốc 100 và tỷ giá USD/VND trên cùng giai đoạn"));

add(H("USD/VND là một chuỗi khác biệt về bản chất", HeadingLevel.HEADING_2));
add(P(`Chuỗi tỷ giá được đưa vào để so sánh, nhưng kết quả cho thấy nó không thể được đối xử như một chuỗi ngang hàng với ba chỉ số cổ phiếu. Bảng ${tn('fx')} đối chiếu trực tiếp.`));
add(TabCaption("fx", "So sánh đặc trưng của USD/VND với ba chỉ số cổ phiếu tần suất ngày"));
add(tblFX);
add(Note("Nguồn: results/multiseries_battery.json và results/series_quality.json."));
add(Rich([
  T("Độ nhọn vượt "), T(num(uFX.excess_kurtosis, 2), { b: true }),
  T(" cao hơn một bậc độ lớn so với các chỉ số cổ phiếu, và tự tương quan bậc một "),
  T(num(uFX.acf1_return, 4), { b: true }),
  T(" mang dấu ÂM — ngược dấu hoàn toàn với mọi chuỗi cổ phiếu. Các con số này nhất quán với đặc thù của một tỷ giá được điều hành và niêm yết theo đơn vị đồng chẵn: chuỗi đứng yên trong thời gian dài rồi nhảy bậc, điều này vừa tạo ra độ nhọn rất lớn vừa tạo ra hiệu ứng hồi quy về trung bình trong sai phân bậc một."),
]));
add(Rich([
  T("Chất lượng dữ liệu của chuỗi này cũng yếu hơn hẳn: giá mở cửa trùng với giá đóng cửa phiên trước ở "),
  T(num(squality.USDVND_1D.stale_open_share * 100, 1) + "%", { b: true }),
  T(" số dòng, và chuỗi có "),
  T(String(squality.USDVND_1D.gaps_ge_2_business_days) + " khoảng trống", { b: true }),
  T(" từ hai ngày làm việc trở lên, trong đó phần lớn nằm ở giai đoạn trước năm 2007. Phần dữ liệu trước 2007 do đó KHÔNG nên được coi là một chuỗi ngày sạch. Báo cáo trình bày chuỗi này kèm đầy đủ các cảnh báo trên thay vì xếp ngang hàng với các chỉ số cổ phiếu."),
]));

add(H("Đối chiếu chéo giữa hai họ tệp dữ liệu", HeadingLevel.HEADING_2));
add(P(`Sáu cặp chuỗi trùng lặp giữa hai họ tệp cho phép một phép kiểm chứng nội bộ, độc lập với nguồn đối chiếu bên ngoài ở mục 3.3. Kết quả trong Bảng ${tn('crossFam')}.`));
add(TabCaption("crossFam", "Đối chiếu giữa chuỗi chính (HOSE_DLY) và phiên bản trùng lặp (HOSE)"));
add(tblCrossFam);
add(Note("Nguồn: results/cross_family_checks.csv (sinh bởi src/multiseries.py)."));
add(P("VN100 tần suất ngày khớp nhau tới độ chính xác biểu diễn số thực. VN-Index và VN30 tần suất ngày lệch trên 0,1% ở lần lượt khoảng 1,9% và 2,8% số thanh, và các sai lệch này tập trung gần như toàn bộ vào giai đoạn 2012–2013 (111 trên 112 trường hợp đối với VN-Index). Đây là một điểm yếu đã xác định được vị trí của bộ dữ liệu và được ghi nhận như một hạn chế, chứ không phải một khiếm khuyết lan tỏa."));

add(H("Những kết luận còn mơ hồ", HeadingLevel.HEADING_2));
add(Rich([
  T("Không phải mọi chuỗi đều cho kết luận dứt khoát. Với "),
  T(String(nAmbiguous.length) + " chuỗi", { b: true }),
  T(" — " + nAmbiguous.map((s) => s.key).join(", ") +
    " — kiểm định tính dừng của chuỗi lợi suất cho kết quả MƠ HỒ: cả ADF và KPSS đều bác bỏ giả thuyết gốc của chính mình. Báo cáo ghi nhận đúng tình trạng mơ hồ này thay vì chọn một hướng kết luận gọn gàng hơn nhưng không có cơ sở."),
]));

add(H("Kết quả mô hình dự báo", HeadingLevel.HEADING_2));
add(NotEvaluated("Chưa có mô hình dự báo nào được huấn luyện trong dự án. Không có tham số ước lượng, không có giá trị dự báo, và báo cáo này không trình bày bất kỳ kết quả mô hình nào."));

add(H("So sánh với mô hình cơ sở", HeadingLevel.HEADING_2));
add(NotEvaluated("Chưa thực hiện. Do chưa có mô hình nào được huấn luyện, cũng chưa có so sánh nào với mô hình cơ sở naive."));

add(H("Các chỉ số đánh giá dự báo", HeadingLevel.HEADING_2));
add(NotEvaluated("Chưa thực hiện. Không có giá trị MAE, RMSE, MAPE, sMAPE hay MASE nào được tính toán trong dự án."));

add(H("Chẩn đoán phần dư", HeadingLevel.HEADING_2));
add(NotEvaluated("Chưa thực hiện. Chẩn đoán phần dư chỉ có nghĩa khi đã có mô hình được ước lượng."));

add(H("Thảo luận tổng hợp", HeadingLevel.HEADING_2));
add(P("Các kết quả thực nghiệm ở trên hội tụ thành một bức tranh nhất quán về chuỗi VN-Index."));
add(P("Thứ nhất, chuỗi mức chỉ số là chuỗi I(1). Kết luận này được hai kiểm định có giả thuyết gốc đối lập cùng xác nhận, đồng thời phù hợp với dạng ACF suy giảm cực chậm quan sát được. Hệ quả trực tiếp là mọi mô hình hóa phải tiến hành trên chuỗi lợi suất."));
add(P("Thứ hai, phân phối lợi suất lệch trái và có đuôi dày hơn phân phối chuẩn một cách rõ rệt. Điều này có ý nghĩa thực tiễn quan trọng: các mô hình rủi ro dựa trên giả định chuẩn tắc sẽ đánh giá thấp một cách hệ thống xác suất xảy ra các phiên tổn thất lớn."));
add(P("Thứ ba, tồn tại tự tương quan bậc một dương có ý nghĩa thống kê trong chuỗi lợi suất, nhưng mức độ khiêm tốn và tập trung ở độ trễ ngắn. Điều này biện minh cho việc thử nghiệm mô hình trung bình dạng AR(1) hoặc ARMA bậc thấp, nhưng không đủ cơ sở để kỳ vọng khả năng dự báo cao."));
add(P("Thứ tư, và là đặc trưng nổi bật nhất, chuỗi thể hiện cụm biến động rất mạnh và dai dẳng. Sự tương phản giữa tự tương quan yếu của lợi suất và tự tương quan mạnh của |r| và r² là lập luận thực nghiệm trực tiếp cho việc sử dụng mô hình phương sai có điều kiện ở giai đoạn tiếp theo."));
add(P("Thứ năm, không có bằng chứng về tính mùa vụ theo tháng. Đây là một kết quả âm nhưng có giá trị phương pháp: nó loại trừ lớp mô hình SARIMA khỏi danh sách ứng viên dựa trên dữ liệu chứ không dựa trên cảm tính."));
add(Rich([
  T("Thứ sáu, phân tích mở rộng trên toàn bộ bộ dữ liệu cho thấy bốn đặc trưng đầu tiên KHÔNG phải là đặc thù của VN-Index: tính không dừng, tính phi chuẩn và cụm biến động xuất hiện ở cả "),
  T(nPrimary + "/" + nPrimary + " chuỗi", { b: true }),
  T(", bất kể phân khúc thị trường, tần suất lấy mẫu hay lớp tài sản. Điều này làm tăng đáng kể độ tin cậy của các kết luận, vì chúng được xác nhận lặp lại trên nhiều mẫu độc lập chứ không chỉ trên một chuỗi."),
]));
add(Rich([
  T("Thứ bảy, và quan trọng về mặt phương pháp: mức tự tương quan cao của VN-Index là "),
  T("hiệu ứng giai đoạn chứ không phải hiệu ứng phân khúc", { b: true }),
  T(". Nếu không thực hiện kiểm soát giai đoạn mẫu, nghiên cứu sẽ kết luận sai rằng chỉ số rộng có mức phụ thuộc chuỗi cao gấp năm lần các chỉ số vốn hóa lớn. Đây là minh họa cụ thể cho nguyên tắc: khi so sánh các chuỗi có giai đoạn quan sát khác nhau, bắt buộc phải kiểm soát giai đoạn trước khi quy sự khác biệt cho bản chất của đối tượng."),
]));
add(P("Tổng hợp lại, các đặc trưng tìm được trả lời câu hỏi nghiên cứu CH6 như sau: lớp mô hình phù hợp là mô hình trung bình bậc thấp trên chuỗi lợi suất, kết hợp với mô hình phương sai có điều kiện; mô hình mùa vụ không được dữ liệu ủng hộ. Việc kiểm chứng hiệu quả thực tế của các mô hình này vẫn còn ở phía trước."));

add(new Paragraph({ children: [new PageBreak()] }));

// ===== CHUONG 5 =====
add(H("KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN", HeadingLevel.HEADING_1));

add(H("Các phát hiện chính", HeadingLevel.HEADING_2));
add(Rich([
  T(`Nghiên cứu đã phân tích ${int(meta.n_rows)} phiên giao dịch của VN-Index trong giai đoạn ${meta.first_date} – ${meta.last_date} và thu được các phát hiện sau, tất cả đều dựa trên thực thi thực tế:`),
]));
[
  `Chuỗi mức VN-Index không dừng và là chuỗi tích hợp bậc một I(1); chuỗi lợi suất logarit là chuỗi dừng. Kết luận được ADF và KPSS đồng thời xác nhận.`,
  `Phân phối lợi suất hàng ngày không tuân theo phân phối chuẩn. Cả ba kiểm định Jarque–Bera, D'Agostino–Pearson và Shapiro–Wilk đều bác bỏ H₀ với p-value cực nhỏ. Độ lệch âm ${num(dLog.skewness, 4)} và độ nhọn vượt ${num(dLog.excess_kurtosis, 4)}.`,
  `Đuôi phân phối dày hơn phân phối chuẩn một cách rõ rệt: số phiên vượt 4σ là ${int(tc.gt_4_sigma.observed_days)}, gấp khoảng ${num(tc.gt_4_sigma.ratio_observed_to_normal, 0)} lần kỳ vọng chuẩn.`,
  `Lợi suất có tự tương quan bậc một dương ACF(1) = ${num(acorr.acf_pacf["Daily log return (%)"].values[0].acf, 4)} và kiểm định Ljung–Box bác bỏ giả thuyết nhiễu trắng ở mọi độ trễ khảo sát.`,
  `Hiện tượng cụm biến động rất mạnh: ACF(1) đạt ${num(acorr.acf_pacf["Absolute log return |r|"].values[0].acf, 4)} với |r| và ${num(acorr.acf_pacf["Squared log return r^2"].values[0].acf, 4)} với r², có ý nghĩa thống kê ở toàn bộ 40 độ trễ.`,
  `Có bằng chứng thống kê về hiệu ứng ngày trong tuần (ANOVA p = ${pv(eda.day_of_week_effect.tests[0].p_value)}), nhưng KHÔNG có bằng chứng về hiệu ứng tháng (ANOVA p = ${num(eda.month_effect.tests[0].p_value, 4)}).`,
  `Có ${int(em.n_beyond_threshold)} phiên biến động vượt 4σ, tập trung chủ yếu ở năm 2001; không phiên nào quy được cho lỗi dữ liệu và không phiên nào bị loại bỏ.`,
].forEach((t) => add(Bullet(t)));

add(P("Các phát hiện từ phân tích mở rộng trên toàn bộ bộ dữ liệu:"));
[
  `Tính không dừng của chuỗi mức, tính phi chuẩn của lợi suất và hiện tượng cụm biến động đúng với cả ${nPrimary}/${nPrimary} chuỗi chính, tức là chúng là tính chất của thị trường chứ không phải đặc thù của VN-Index.`,
  `Mức tự tương quan cao của VN-Index là hiệu ứng giai đoạn: ACF(1) giảm từ ${num(BY["VNINDEX_1D"].acf1_return, 4)} trên toàn mẫu xuống ${num(matched1D.stats.VNINDEX.acf1, 4)} khi đo trên ${int(matched1D.n_common)} phiên chung với VN30 và VN100.`,
  `Độ dày đuôi phân phối giảm đơn điệu khi tổng hợp thời gian: độ nhọn vượt từ ${num(scaleVNI.M30.excess_kurtosis, 2)} ở tần suất 30 phút xuống ${num(scaleVNI["1D"].excess_kurtosis, 2)} ở tần suất ngày.`,
  `Biến động trong phiên có dạng chữ U: cao nhất ở thanh mở cửa 09:00 và tăng trở lại trước giờ đóng cửa.`,
  `Ba chỉ số cổ phiếu tương quan rất cao với nhau (VN30–VN100 đạt ${num(corr1D.pearson.VN30.VN100, 3)}), trong khi USD/VND tương quan âm nhẹ với cả ba (khoảng ${num(corr1D.pearson.VNINDEX.USDVND, 2)}).`,
  `USD/VND khác biệt về bản chất so với các chỉ số cổ phiếu: độ nhọn vượt ${num(uFX.excess_kurtosis, 2)} và ACF(1) = ${num(uFX.acf1_return, 4)} mang dấu âm.`,
  `Chất lượng dữ liệu trên toàn bộ ${int(totalBars)} quan sát: không phát hiện bất kỳ lỗi nào thuộc các hạng mục đã kiểm tra.`,
].forEach((t) => add(Bullet(t)));

add(H("Ý nghĩa của kết quả", HeadingLevel.HEADING_2));
add(P("Về mặt phương pháp, kết quả nghiên cứu cho thấy việc chuyển thẳng sang mô hình dự báo trên chuỗi mức VN-Index là sai về mặt kỹ thuật, vì chuỗi mức không dừng. Đồng thời, kết quả cũng cho thấy việc áp dụng mô hình mùa vụ cho chuỗi này là không có cơ sở thực nghiệm."));
add(P("Về mặt thực tiễn, đặc trưng đuôi dày và cụm biến động có hàm ý trực tiếp cho quản trị rủi ro: các thước đo rủi ro giả định phân phối chuẩn và phương sai không đổi sẽ đánh giá thấp rủi ro thực tế của thị trường Việt Nam, đặc biệt trong các giai đoạn thị trường căng thẳng."));
add(P("Về mặt quy trình, việc đối chiếu hai nguồn dữ liệu độc lập cho thấy dữ liệu thị trường Việt Nam từ các nhà cung cấp khác nhau có thể không trùng khớp hoàn toàn. Đây là một hạn chế cần được công bố minh bạch trong mọi nghiên cứu định lượng sử dụng dữ liệu này."));

add(H("Hạn chế của nghiên cứu", HeadingLevel.HEADING_2));
[
  "Nguồn dữ liệu chính là bản phân phối lại bởi bên thứ ba trên Kaggle, không phải công bố chính thức của HOSE. Mặc dù đã đối chiếu với một nguồn độc lập, vẫn tồn tại sai lệch giữa hai nguồn, tập trung ở giai đoạn thị trường mỏng trước năm 2010.",
  `Bộ dữ liệu còn một khoảng trống lịch không giải thích được (${gq.unexplained_gaps.map((g) => g.prev_session + " → " + g.next_session).join("; ")}). Quan sát lợi suất tương ứng đã được đánh dấu nhưng vẫn nằm trong mẫu phân tích.`,
  "Biến Open trùng với giá đóng cửa phiên trước ở một tỷ lệ đáng kể số dòng, nên các phân tích dựa trên giá mở cửa sẽ không đáng tin cậy. Nghiên cứu vì vậy chỉ sử dụng giá đóng cửa.",
  "Giai đoạn nghiên cứu kết thúc ở ngày cuối cùng có dữ liệu đầy đủ của nguồn chính, nên không bao gồm các diễn biến thị trường sau thời điểm đó.",
  "Cấu trúc thị trường Việt Nam thay đổi rất lớn trong giai đoạn quan sát (số lượng cổ phiếu niêm yết, biên độ dao động giá, chu kỳ thanh toán). Nghiên cứu chưa kiểm định điểm gãy cấu trúc, nên các thống kê tính trên toàn mẫu cần được hiểu là giá trị trung bình qua nhiều chế độ thị trường khác nhau.",
  "Hiệu ứng ngày trong tuần chưa được kiểm tra sau khi kiểm soát biến động và phân kỳ mẫu, nên chưa thể kết luận về tính bền vững của hiệu ứng này.",
  "Phần mô hình hóa, dự báo và đánh giá chưa được thực hiện, nên nghiên cứu chưa đưa ra kết luận nào về khả năng dự báo của VN-Index.",
  "Hai họ tệp trong bộ dữ liệu lệch nhau trên 0,1% ở khoảng 1,9–2,8% số thanh đối với VN-Index và VN30 tần suất ngày, tập trung ở giai đoạn 2012–2013. Nghiên cứu sử dụng họ HOSE_DLY làm nguồn chính nhưng không có cơ sở độc lập để khẳng định họ nào đúng trong giai đoạn đó.",
  `Các chuỗi có giai đoạn bắt đầu và kết thúc khác nhau (VN-Index từ 2000, VN30 từ 2012, VN100 từ 2014; dữ liệu 1 giờ và phiên nửa ngày dừng ở 2024-12-09). Phép so sánh giữa các tần suất trong Bảng ${tn('scaling')} do đó mang tính gợi ý chứ chưa phải một kiểm định có kiểm soát giai đoạn đầy đủ.`,
  "Chuỗi USD/VND có chất lượng thấp hơn hẳn: giá mở cửa lặp lại giá đóng cửa phiên trước ở phần lớn số dòng và dữ liệu trước năm 2007 rất thưa. Các kết luận về chuỗi này chỉ nên được coi là mô tả sơ bộ.",
  "Dữ liệu trong phiên chỉ có từ 2016–2017 trở đi, nên không cho phép khảo sát cấu trúc trong phiên ở các giai đoạn thị trường trước đó.",
].forEach((t) => add(Bullet(t)));

add(H("Hướng nghiên cứu tiếp theo", HeadingLevel.HEADING_2));
add(P("Các bước tiếp theo được đề xuất theo thứ tự ưu tiên, bám sát bằng chứng thực nghiệm đã thu được:"));
[
  "Thực hiện kiểm định ARCH-LM để xác nhận hình thức sự tồn tại của hiệu ứng ARCH, trước khi ước lượng bất kỳ mô hình GARCH nào.",
  "Ước lượng mô hình GARCH(1,1) và các biến thể bất đối xứng, với phân phối sai số có đuôi dày phù hợp với đặc trưng đã phát hiện.",
  "Thiết lập mô hình cơ sở naive và ước lượng các mô hình ARIMA bậc thấp trên chuỗi lợi suất, với bậc được chọn từ cấu trúc ACF/PACF thực nghiệm.",
  "Chia tập theo thứ tự thời gian và đánh giá dự báo bằng MAE, RMSE, MAPE và MASE, luôn so sánh với mô hình cơ sở.",
  "Thực hiện chẩn đoán phần dư đầy đủ, bao gồm kiểm định Ljung–Box trên phần dư và kiểm tra phương sai thay đổi.",
  "Kiểm định điểm gãy cấu trúc và lặp lại phân tích trên các giai đoạn con để kiểm tra tính ổn định của các kết luận.",
  "Đối chiếu bổ sung với dữ liệu công bố chính thức của HOSE nhằm thu hẹp phần sai lệch giữa các nguồn.",
].forEach((t) => add(Bullet(t)));

add(new Paragraph({ children: [new PageBreak()] }));

// ===== TAI LIEU THAM KHAO =====
add(HPlain("TÀI LIỆU THAM KHẢO", HeadingLevel.HEADING_1));
add(Note("Danh mục này chỉ liệt kê những nguồn ĐÃ THỰC SỰ được sử dụng trong quá trình thực hiện dự án. Không có tài liệu nào được liệt kê mà chưa được truy cập và sử dụng."));

add(HPlain("Nguồn dữ liệu", HeadingLevel.HEADING_2));
add(P(`[1] keithvo. "Vietnam Stock Intraday (VNINDEX, VN30, VN100)". Bộ dữ liệu Kaggle, tệp HOSE_DLY_VNINDEX1D.csv. Giấy phép: ${meta.source_license}. Cập nhật lần cuối: ${meta.upstream_last_updated}. Truy cập tại: ${meta.source_url}`, { indent: { left: 400, hanging: 400 } }));
add(P("[2] DNSE / Entrade. API biểu đồ công khai, endpoint chỉ số. Truy cập tại: https://services.entrade.com.vn/chart-api/v2/ohlcs/index — sử dụng duy nhất cho mục đích đối chiếu nguồn dữ liệu.", { indent: { left: 400, hanging: 400 } }));

add(HPlain("Công cụ phần mềm đã sử dụng", HeadingLevel.HEADING_2));
add(P("[3] Python 3.11.9.", { indent: { left: 400, hanging: 400 } }));
add(P("[4] pandas 3.0.1 — xử lý và biến đổi dữ liệu.", { indent: { left: 400, hanging: 400 } }));
add(P("[5] NumPy 1.26.4 — tính toán số học.", { indent: { left: 400, hanging: 400 } }));
add(P("[6] SciPy 1.17.0 — các kiểm định thống kê (Jarque–Bera, Shapiro–Wilk, D'Agostino–Pearson, ANOVA, Kruskal–Wallis, Levene).", { indent: { left: 400, hanging: 400 } }));
add(P("[7] statsmodels 0.15.0 — kiểm định ADF, KPSS, ACF/PACF, Ljung–Box.", { indent: { left: 400, hanging: 400 } }));
add(P("[8] Matplotlib 3.10.8 — trực quan hóa dữ liệu.", { indent: { left: 400, hanging: 400 } }));

add(Rich([
  T("Ghi chú về tài liệu học thuật: ", { b: true }),
  T("Báo cáo này KHÔNG trích dẫn sách giáo khoa hay bài báo khoa học, vì trong giai đoạn thực hiện hiện tại chưa có tài liệu học thuật nào được truy cập và sử dụng trực tiếp. Việc bổ sung tài liệu tham khảo học thuật sẽ được thực hiện khi các nguồn đó thực sự được tham khảo, nhằm bảo đảm nguyên tắc không tạo ra trích dẫn không có thật."),
]));

add(new Paragraph({ children: [new PageBreak()] }));

// ===== PHU LUC =====
add(HPlain("PHỤ LỤC", HeadingLevel.HEADING_1));

add(HPlain("Phụ lục A — Trạng thái thực thi các thành phần", HeadingLevel.HEADING_2));
add(P(`Bảng ${tn('status')} liệt kê trạng thái thực thi của từng thành phần trong dự án tại thời điểm lập báo cáo.`));
add(TabCaption("status", "Trạng thái thực thi các thành phần của dự án"));
add(tblStatus);

add(HPlain("Phụ lục B — Cấu trúc dự án", HeadingLevel.HEADING_2));
add(P("Dự án được tổ chức theo cấu trúc tách biệt dữ liệu thô, dữ liệu đã xử lý, mã nguồn, kết quả và hình ảnh:"));
[
  "data/raw/kaggle/ — toàn bộ 19 tệp nguồn được lưu kèm nguyên trạng. Không bao giờ bị chỉnh sửa bởi các bước sau.",
  "data/processed/ — dữ liệu sau làm sạch và bảng đặc trưng, được sinh lại hoàn toàn từ dữ liệu thô.",
  "src/ — mã nguồn dạng mô-đun: config.py, catalog.py, data_loader.py, data_crosscheck.py, data_quality.py, preprocessing.py, analysis.py, stationarity.py, autocorrelation.py, multiseries.py, plots.py, plots_multiseries.py và run_all.py.",
  "results/ — toàn bộ kết quả thống kê ở định dạng JSON và CSV.",
  "figures/ — các hình trong báo cáo, độ phân giải 150 dpi.",
  "tests/ — bộ kiểm thử tự động gồm 19 test.",
  "reports/ — báo cáo và mã sinh báo cáo.",
].forEach((t) => add(Bullet(t)));

add(HPlain("Phụ lục C — Hướng dẫn tái lập kết quả", HeadingLevel.HEADING_2));
add(P("Toàn bộ kết quả trong báo cáo có thể được tái lập bằng các lệnh sau, chạy từ thư mục gốc của dự án:"));
[
  "pip install -r requirements.txt",
  "python src/run_all.py",
  "python -m pytest tests -q",
].forEach((t) => add(new Paragraph({
  spacing: { after: 60, line: 276 },
  indent: { left: 400 },
  children: [new TextRun({ text: t, font: "Consolas", size: 22 })],
})));
add(P("Pipeline chạy hoàn toàn từ tệp dữ liệu lưu kèm, không cần kết nối mạng. Hạt giống ngẫu nhiên được cố định ở giá trị 42 cho bước lấy mẫu con của kiểm định Shapiro–Wilk; không bước nào khác sử dụng yếu tố ngẫu nhiên. Vì nguồn dữ liệu là tệp tĩnh chứ không phải API trực tuyến, việc chạy lại pipeline sẽ tái tạo chính xác các con số trong báo cáo này."));

add(HPlain("Phụ lục D — Danh mục tệp kết quả", HeadingLevel.HEADING_2));
add(P("Các con số trong báo cáo được đọc trực tiếp từ những tệp sau:"));
[
  "data/raw/vnindex_raw_meta.json — xuất xứ dữ liệu, số quan sát, khoảng thời gian, ghi nhận thanh dữ liệu bị loại.",
  "results/data_quality_report.json — kết quả kiểm tra chất lượng và phân loại khoảng trống lịch.",
  "results/source_crosscheck.json — kết quả đối chiếu hai nguồn dữ liệu.",
  "results/descriptive_statistics.csv — thống kê mô tả.",
  "results/normality_tests.csv — kiểm định tính chuẩn.",
  "results/stationarity_tests.csv — kiểm định ADF và KPSS.",
  "results/autocorrelation.json — hệ số ACF/PACF.",
  "results/ljung_box_tests.csv — kiểm định Ljung–Box.",
  "results/eda_results.json — so sánh đuôi phân phối, hiệu ứng lịch, quan sát cực đoan, tổng hợp theo năm.",
  "results/series_inventory.json — danh mục và siêu dữ liệu của toàn bộ 19 chuỗi.",
  "results/series_quality.json — kết quả kiểm tra chất lượng từng chuỗi.",
  "results/multiseries_battery.json — bộ thống kê so sánh, kiểm soát giai đoạn, tần suất và tương quan.",
  "results/cross_family_checks.csv — đối chiếu giữa hai họ tệp dữ liệu.",
].forEach((t) => add(Bullet(t)));

// helper dung o tren (khai bao sau khi dung trong template string can hoisting)
function Math_round(x) { return Math.round(Number(x)); }

// ---------------------------------------------------------------------------
// Tao tai lieu
// ---------------------------------------------------------------------------
const doc = new Document({
  creator: "VN-Index Time Series Project",
  title: "Phân tích dữ liệu chuỗi thời gian VN-Index",
  description: "Báo cáo phân tích chuỗi thời gian VN-Index",
  styles: {
    default: {
      document: { run: { font: FONT, size: 26 }, paragraph: { spacing: { line: 360 } } },
      heading1: { run: { font: FONT, size: 32, bold: true, color: "000000" }, paragraph: { spacing: { before: 360, after: 160 } } },
      heading2: { run: { font: FONT, size: 28, bold: true, color: "000000" }, paragraph: { spacing: { before: 240, after: 140 } } },
      heading3: { run: { font: FONT, size: 26, bold: true, color: "000000" }, paragraph: { spacing: { before: 200, after: 120 } } },
    },
    paragraphStyles: [
      {
        id: "Caption", name: "Caption", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 24, italics: false },
        paragraph: { alignment: AlignmentType.CENTER, spacing: { before: 80, after: 160 } },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "heading-num",
        levels: [
          { level: 0, format: LevelFormat.DECIMAL, text: "CHƯƠNG %1.", alignment: AlignmentType.START,
            style: { paragraph: { indent: { left: 0, hanging: 0 } }, run: { bold: true } } },
          { level: 1, format: LevelFormat.DECIMAL, text: "%1.%2.", alignment: AlignmentType.START,
            style: { paragraph: { indent: { left: 0, hanging: 0 } }, run: { bold: true } } },
          { level: 2, format: LevelFormat.DECIMAL, text: "%1.%2.%3.", alignment: AlignmentType.START,
            style: { paragraph: { indent: { left: 0, hanging: 0 } }, run: { bold: true } } },
        ],
      },
      {
        reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 600, hanging: 240 } } } },
        ],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          margin: { top: 1134, right: 1134, bottom: 1134, left: 1701 },
        },
      },
      children: cover,
    },
    {
      properties: {
        type: SectionType.CONTINUOUS,
        page: {
          margin: { top: 1134, right: 1134, bottom: 1134, left: 1701 },
          pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL },
        },
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            spacing: { after: 60 },
            border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "999999" } },
            children: [new TextRun({ text: "Phân tích dữ liệu chuỗi thời gian VN-Index", italics: true, size: 20 })],
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ children: ["Trang ", PageNumber.CURRENT, " / ", PageNumber.TOTAL_PAGES], size: 20 })],
          })],
        }),
      },
      children: [...frontMatter, ...body],
    },
  ],
});

const OUT = R(path.join("reports", "BaoCao_PhanTichChuoiThoiGian_VNIndex.docx"));
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log("Written:", OUT);
  console.log("Size:", (buf.length / 1024).toFixed(1), "KB");
  console.log("Data period:", meta.first_date, "->", meta.last_date, `(${meta.n_rows} sessions)`);
});
