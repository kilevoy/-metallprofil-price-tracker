from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "input"
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"

TARGET_PAGE = 4
SECTION_TITLE = "\u041f\u0420\u041e\u0424\u0418\u041b\u0418\u0420\u041e\u0412\u0410\u041d\u041d\u042b\u0419 \u0418 \u041f\u041b\u041e\u0421\u041a\u0418\u0419 \u041b\u0418\u0421\u0422 \u0421 \u041f\u041e\u041b\u0418\u041c\u0415\u0420\u041d\u042b\u041c \u041f\u041e\u041a\u0420\u042b\u0422\u0418\u0415\u041c"


@dataclass(frozen=True)
class PriceColumn:
    index: int
    class_name: str
    coating_type: str
    thickness: str


CLASS_STANDARD = "STANDARD"
CLASS_ECONOM = "ECONOM"
CLASS_RETAIL = "RETAIL"

COLUMNS: list[PriceColumn] = [
    PriceColumn(1, CLASS_STANDARD, "VikingMP/COLOR 30", "0.45"),
    PriceColumn(2, CLASS_STANDARD, "VikingMP 30", "0.45"),
    PriceColumn(3, CLASS_STANDARD, "Polyester DS 25/25", "0.45"),
    PriceColumn(4, CLASS_STANDARD, "Polyester 25", "0.45"),
    PriceColumn(5, CLASS_STANDARD, "Polyester 25", "0.65"),
    PriceColumn(6, CLASS_STANDARD, "Polyester/COLOR 25", "0.7"),
    PriceColumn(7, CLASS_STANDARD, "Polyester matte DS", "0.8"),
    PriceColumn(8, CLASS_STANDARD, "Steelmatt Polyester 25", "0.9"),
    PriceColumn(9, CLASS_STANDARD, "Steelmatt Polyester 25", "1.0"),
    PriceColumn(10, CLASS_ECONOM, "Polyester 25", "0.4"),
    PriceColumn(11, CLASS_ECONOM, "Polyester/COLOR 25", "0.4"),
    PriceColumn(12, CLASS_ECONOM, "Polyester matte DS", "0.4"),
    PriceColumn(13, CLASS_ECONOM, "Steelmatt Polyester 25", "0.4"),
    PriceColumn(14, CLASS_RETAIL, "ST**", "ST**"),
]


def parse_uploaded_label(path: Path) -> str:
    name = path.stem
    full = re.search(r"(\d{2})\.(\d{2})\.(\d{2,4})", name)
    if full:
        day, month, year = full.groups()
        if len(year) == 2:
            year = f"20{year}"
        return f"{day}.{month}.{year}"

    short = re.search(r"(\d{2})\.(\d{2})", name)
    if short:
        day, month = short.groups()
        year = str(datetime.fromtimestamp(path.stat().st_mtime).year)
        return f"{day}.{month}.{year}"

    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y")


def parse_uploaded_datetime(path: Path) -> datetime:
    return datetime.strptime(parse_uploaded_label(path), "%d.%m.%Y")


def parse_money(raw: str) -> int | None:
    value = raw.strip()
    if not value or value == "-":
        return None
    return int(value.replace(" ", ""))


def normalize_thickness(text: str) -> str:
    return text.replace(" (2)", "")


def is_main_row(tokens: list[str]) -> bool:
    if len(tokens) < 8:
        return False
    if not tokens[0].isdigit():
        return False
    return bool(re.match(r"^\d+,\d+$", tokens[2])) and bool(re.match(r"^\d+,\d+$|-", tokens[3]))


def is_additional_row(tokens: list[str]) -> bool:
    if len(tokens) < 5 or len(tokens) > 6:
        return False
    if not tokens[0].isdigit():
        return False
    return tokens[2] == "-" and parse_money(tokens[4]) is not None


def parse_rows(page: fitz.Page) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    additions: list[dict] = []

    for block in page.get_text("blocks"):
        text = str(block[4] or "").strip()
        if not text:
            continue

        tokens = [line.strip() for line in text.splitlines() if line.strip()]
        if not tokens:
            continue

        if is_main_row(tokens):
            row_no = int(tokens[0])
            product_name = tokens[1]
            coef_film = tokens[2]
            coef_anti = tokens[3]
            width = tokens[4]
            unit = tokens[5]

            price_tokens = tokens[6:]
            if len(price_tokens) < len(COLUMNS):
                price_tokens = price_tokens + ["-"] * (len(COLUMNS) - len(price_tokens))
            elif len(price_tokens) > len(COLUMNS):
                price_tokens = price_tokens[: len(COLUMNS)]

            prices = []
            for column, raw_price in zip(COLUMNS, price_tokens):
                prices.append(
                    {
                        "class_name": column.class_name,
                        "coating_type": column.coating_type,
                        "thickness": column.thickness,
                        "thickness_value": normalize_thickness(column.thickness),
                        "price_raw": raw_price,
                        "price": parse_money(raw_price),
                    }
                )

            rows.append(
                {
                    "row_no": row_no,
                    "product_name": product_name,
                    "coef_film": coef_film,
                    "coef_anti_condensate": coef_anti,
                    "width": width,
                    "unit": unit,
                    "prices": prices,
                }
            )
            continue

        if is_additional_row(tokens):
            additions.append(
                {
                    "row_no": int(tokens[0]),
                    "name": tokens[1],
                    "unit": tokens[3],
                    "price": parse_money(tokens[4]),
                }
            )

    rows.sort(key=lambda item: item["row_no"])
    additions.sort(key=lambda item: item["row_no"])
    return rows, additions


def build_records(rows: list[dict]) -> list[dict]:
    records: list[dict] = []
    for row in rows:
        for price_cell in row["prices"]:
            records.append(
                {
                    "product_row_no": row["row_no"],
                    "product_name": row["product_name"],
                    "profile_width_full_mm": row["width"],
                    "class_name": price_cell["class_name"],
                    "coating_type": price_cell["coating_type"],
                    "thickness": price_cell["thickness"],
                    "thickness_value": price_cell["thickness_value"],
                    "unit": row["unit"],
                    "price_raw": price_cell["price_raw"],
                    "price": price_cell["price"],
                }
            )
    return records


def build_date_radios(snapshots: list[dict]) -> str:
    radios = []
    for idx, snap in enumerate(snapshots):
        checked = " checked" if idx == len(snapshots) - 1 else ""
        label = snap["uploaded_label"]
        radios.append(
            f'<label class="date-radio"><input type="radio" name="price-date" value="{idx}"{checked}><span class="date-label">{label}</span></label>'
        )
    return "".join(radios)


def build_html(payload: dict) -> str:
    snapshots_json = json.dumps(payload["price_history"], ensure_ascii=False)
    date_radios_html = build_date_radios(payload["price_history"])

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>\u041f\u0440\u043e\u0444\u043d\u0430\u0441\u0442\u0438\u043b \u0438 \u043f\u043b\u043e\u0441\u043a\u0438\u0439 \u043b\u0438\u0441\u0442 - \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0430 4</title>
  <style>
    :root {{
      --font-ui: "Segoe UI", Tahoma, Arial, sans-serif;
      --font-head: Georgia, "Times New Roman", serif;
      --bg: #edf1f6;
      --bg-accent: #dce5f2;
      --surface: #ffffff;
      --text: #17212f;
      --muted: #576173;
      --line: #d8e0eb;
      --accent: #1f4e79;
      --accent-soft: #e6edf6;
      --table-head: #f3f7fc;
      --input-bg: #ffffff;
      --input-text: #17212f;
      --shadow: 0 12px 34px rgba(10, 24, 40, 0.08);
    }}
    [data-theme="steel"] {{
      --font-ui: "Segoe UI", Tahoma, Arial, sans-serif;
      --font-head: Georgia, "Times New Roman", serif;
      --bg: #eef2f5;
      --bg-accent: #dde6ed;
      --surface: #ffffff;
      --text: #1b2734;
      --muted: #5b6876;
      --line: #d2dbe4;
      --accent: #0b5f8a;
      --accent-soft: #e4f0f6;
      --table-head: #f1f7fb;
      --input-bg: #f9fcff;
      --input-text: #1b2734;
      --shadow: 0 10px 30px rgba(15, 32, 48, 0.1);
    }}
    [data-theme="graphite"] {{
      --font-ui: "Segoe UI", Tahoma, Arial, sans-serif;
      --font-head: Georgia, "Times New Roman", serif;
      --bg: #eceff2;
      --bg-accent: #d6dbe1;
      --surface: #ffffff;
      --text: #1d2026;
      --muted: #5d6470;
      --line: #d7dce3;
      --accent: #3b4f67;
      --accent-soft: #e8ecf2;
      --table-head: #f4f6f9;
      --input-bg: #ffffff;
      --input-text: #1d2026;
      --shadow: 0 12px 32px rgba(22, 28, 36, 0.09);
    }}
    [data-theme="premium"] {{
      --font-ui: "Segoe UI", Tahoma, Arial, sans-serif;
      --font-head: Georgia, "Times New Roman", serif;
      --bg: #f3f1ec;
      --bg-accent: #e5decc;
      --surface: #fffdf8;
      --text: #2e2518;
      --muted: #6f6658;
      --line: #e2d9c7;
      --accent: #7c5a21;
      --accent-soft: #f0e8d9;
      --table-head: #f7f2e9;
      --input-bg: #fffdf9;
      --input-text: #2e2518;
      --shadow: 0 14px 36px rgba(58, 42, 18, 0.1);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--font-ui);
      color: var(--text);
      background:
        radial-gradient(circle at 10% 0%, var(--bg-accent), transparent 30%),
        linear-gradient(180deg, #f9f8f5 0%, var(--bg) 100%);
    }}
    .page {{ width: min(1160px, calc(100% - 24px)); margin: 24px auto; }}
    .hero {{ background: var(--surface); border: 1px solid var(--line); border-radius: 18px; padding: 18px; box-shadow: var(--shadow); }}
    .top-row {{ display: flex; justify-content: flex-end; margin-bottom: 8px; }}
    .back-link {{
      display: inline-flex;
      align-items: center;
      text-decoration: none;
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--surface);
    }}
    .back-link:hover {{ background: var(--accent-soft); }}
    h1 {{ margin: 0 0 8px; font-size: 28px; line-height: 1.1; font-family: var(--font-head); }}
    .meta {{ color: var(--muted); font-size: 14px; line-height: 1.4; }}
    .meta-row {{ display: flex; gap: 12px; align-items: end; justify-content: space-between; flex-wrap: wrap; }}
    .date-picker-section {{ margin-top: 10px; padding: 10px 12px; border-radius: 12px; background: var(--accent-soft); border: 1px solid var(--line); }}
    .date-picker-title {{ margin: 0 0 8px; font-size: 13px; color: var(--muted); font-weight: 700; }}
    .date-radios {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 8px; }}
    .date-radio {{ display: inline-flex; align-items: center; gap: 7px; padding: 7px 10px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); cursor: pointer; }}
    .date-radio input[type="radio"] {{ width: 14px; height: 14px; accent-color: var(--accent); }}
    .date-label {{ font-size: 13px; color: var(--text); }}
    .filters {{ margin-top: 14px; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }}
    label {{ display: grid; gap: 6px; font-size: 13px; color: var(--muted); }}
    select {{ border: 1px solid var(--line); border-radius: 10px; padding: 10px; font-size: 14px; background: var(--input-bg); color: var(--input-text); }}
    .card {{ margin-top: 14px; background: var(--surface); border: 1px solid var(--line); border-radius: 18px; overflow: hidden; box-shadow: var(--shadow); }}
    .table-wrap {{ overflow: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 980px; table-layout: fixed; }}
    col.col-product {{ width: 20%; }}
    col.col-width {{ width: 20%; }}
    col.col-coating {{ width: 20%; }}
    col.col-thickness {{ width: 20%; }}
    col.col-price {{ width: 20%; }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 10px 12px; vertical-align: top; font-size: 14px; }}
    th {{ position: sticky; top: 0; background: var(--table-head); color: var(--text); text-transform: uppercase; letter-spacing: 0.03em; font-size: 12px; }}
    td:nth-child(2), td:nth-child(4), th:nth-child(2), th:nth-child(4) {{ text-align: center; }}
    td:nth-child(2), td:nth-child(4), td:nth-child(5) {{ white-space: nowrap; }}
    .price {{ font-weight: 700; color: var(--accent); white-space: nowrap; }}
    th:last-child, td:last-child {{ text-align: right; }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 680px) {{
      .date-radios {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="top-row"><a class="back-link" href="index.html">← К оглавлению</a></div>
      <h1>\u041f\u0420\u041e\u0424\u0418\u041b\u0418\u0420\u041e\u0412\u0410\u041d\u041d\u042b\u0419 \u0418 \u041f\u041b\u041e\u0421\u041a\u0418\u0419 \u041b\u0418\u0421\u0422 \u0421 \u041f\u041e\u041b\u0418\u041c\u0415\u0420\u041d\u042b\u041c \u041f\u041e\u041a\u0420\u042b\u0422\u0418\u0415\u041c</h1>
      <div class="meta-row">
        <div class="meta">
          \u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a: <strong id="source-file-text">{payload["source_file"]}</strong>
        </div>
        <label style="min-width: 260px;">
          \u0421\u0442\u0438\u043b\u044c \u043e\u0442\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u044f
          <select id="theme-switcher">
            <option value="steel">\u041a\u043e\u0440\u043f\u043e\u0440\u0430\u0442\u0438\u0432\u043d\u044b\u0439 \u0441\u0438\u043d\u0438\u0439</option>
            <option value="graphite">\u0413\u0440\u0430\u0444\u0438\u0442\u043e\u0432\u044b\u0439</option>
            <option value="premium">\u041f\u0440\u0435\u043c\u0438\u0443\u043c \u0431\u0435\u0436\u0435\u0432\u044b\u0439</option>
          </select>
        </label>
      </div>
      <div class="date-picker-section">
        <p class="date-picker-title">Выберите дату для просмотра цен:</p>
        <div class="date-radios" id="date-radios">{date_radios_html}</div>
      </div>
      <div class="filters">
        <label>\u041a\u043b\u0430\u0441\u0441 \u043f\u043e\u043a\u0440\u044b\u0442\u0438\u044f<select id="class-filter"></select></label>
        <label>\u0422\u0438\u043f \u043f\u043e\u043a\u0440\u044b\u0442\u0438\u044f<select id="coating-filter"></select></label>
        <label>\u0422\u043e\u043b\u0449\u0438\u043d\u0430<select id="thickness-filter"></select></label>
      </div>
      <div class="filters" style="margin-top: 10px;">
        <label style="display: inline-flex; align-items: center; gap: 8px; font-size: 14px; color: var(--text);">
          <input type="checkbox" id="show-special-rows">
          <span>\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0441\u043a\u043b\u0430\u0434\u0441\u043a\u0438\u0435 \u0438 \u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442\u043d\u044b\u0435 \u043f\u043e\u0437\u0438\u0446\u0438\u0438</span>
        </label>
      </div>
    </section>

    <section class="card">
      <div class="table-wrap">
        <table>
          <colgroup>
            <col class="col-product">
            <col class="col-width">
            <col class="col-coating">
            <col class="col-thickness">
            <col class="col-price">
          </colgroup>
          <thead>
            <tr>
              <th>\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u043f\u0440\u043e\u0434\u0443\u043a\u0446\u0438\u0438</th>
              <th>\u0428\u0438\u0440\u0438\u043d\u0430 \u043f\u0440\u043e\u0444\u0438\u043b\u044f \u043f\u043e\u043b\u043d\u0430\u044f, \u043c\u043c</th>
              <th>\u0422\u0438\u043f \u043f\u043e\u043a\u0440\u044b\u0442\u0438\u044f</th>
              <th>\u0422\u043e\u043b\u0449\u0438\u043d\u0430</th>
              <th>\u0426\u0435\u043d\u0430, \u0440\u0443\u0431./\u043c.\u043a\u0432.</th>
            </tr>
          </thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>
    </section>
  </main>

  <script>
    const snapshots = {snapshots_json};
    let data = snapshots[snapshots.length - 1].records;
    const themeSwitcher = document.getElementById("theme-switcher");
    const sourceFileText = document.getElementById("source-file-text");
    const dateRadios = document.querySelectorAll('input[name="price-date"]');
    const classFilter = document.getElementById("class-filter");
    const coatingFilter = document.getElementById("coating-filter");
    const thicknessFilter = document.getElementById("thickness-filter");
    const showSpecialRows = document.getElementById("show-special-rows");
    const tbody = document.getElementById("tbody");

    let classes = [];
    let allCoatings = [];
    let allThicknesses = [];
    let defaultCoating = "Polyester 25";

    const classLabels = {{
      STANDARD: "\u0421\u0422\u0410\u041d\u0414\u0410\u0420\u0422",
      ECONOM: "\u042d\u041a\u041e\u041d\u041e\u041c",
      RETAIL: "RETAIL",
    }};
    const coatingLabel = (value) => value
      .replace(/^Polyester\b/, "Полиэстер")
      .replace(/^Steelmatt Polyester\b/, "Steelmatt Полиэстер");

    function rebuildDomains() {{
      classes = Array.from(new Set(data.map(r => r.class_name)));
      allCoatings = Array.from(new Set(data.map(r => r.coating_type)));
      allThicknesses = Array.from(new Set(data.map(r => r.thickness_value)));
      defaultCoating = allCoatings.includes("Полиэстер 25")
        ? "Полиэстер 25"
        : "Polyester 25";
    }}

    function applySnapshot(index) {{
      const snap = snapshots[index];
      if (!snap) return;
      data = snap.records;
      if (sourceFileText) {{
        sourceFileText.textContent = snap.source_file;
      }}
      const prevClass = classFilter.value || "STANDARD";
      const prevCoating = coatingFilter.value || defaultCoating;
      const prevThickness = thicknessFilter.value || "all";
      rebuildDomains();
      setOptions(classFilter, classes, prevClass, (v) => classLabels[v] || v);
      setOptions(coatingFilter, allCoatings, prevCoating, coatingLabel);
      setOptions(thicknessFilter, allThicknesses, prevThickness);
      syncCoatingOptions();
      syncThicknessOptions();
      render();
    }}

    function applyTheme(theme) {{
      const allowed = ["steel", "graphite", "premium"];
      const normalized = allowed.includes(theme) ? theme : "steel";
      document.documentElement.setAttribute("data-theme", normalized);
      if (themeSwitcher) {{
        themeSwitcher.value = normalized;
      }}
      try {{
        localStorage.setItem("profiledSheetTheme", normalized);
      }} catch (error) {{
      }}
    }}

    function setOptions(select, items, selected, labelFn = null) {{
      const isAllowed = selected === "all" || items.includes(selected);
      const selectedValue = isAllowed ? selected : "all";
      const html = ['<option value="all">\u0412\u0441\u0435</option>']
        .concat(items.map(item => {{
          const label = labelFn ? labelFn(item) : item;
          return `<option value="${{item}}" ${{item === selectedValue ? "selected" : ""}}>${{label}}</option>`;
        }}))
        .join("");
      select.innerHTML = html;
    }}

    function syncCoatingOptions() {{
      const classValue = classFilter.value;
      const availableCoatings = Array.from(
        new Set(
          data
            .filter((row) => classValue === "all" || row.class_name === classValue)
            .map((row) => row.coating_type)
        )
      );
      setOptions(coatingFilter, availableCoatings, coatingFilter.value || defaultCoating, coatingLabel);
    }}

    function syncThicknessOptions() {{
      const classValue = classFilter.value;
      const coatingValue = coatingFilter.value;
      const availableThicknesses = Array.from(
        new Set(
          data
            .filter((row) => classValue === "all" || row.class_name === classValue)
            .filter((row) => coatingValue === "all" || row.coating_type === coatingValue)
            .map((row) => row.thickness_value)
        )
      );
      setOptions(thicknessFilter, availableThicknesses, thicknessFilter.value || "all");
    }}

    function formatPrice(value) {{
      if (value == null) return "-";
      return new Intl.NumberFormat("ru-RU").format(value);
    }}

    function render() {{
      const classValue = classFilter.value;
      const coatingValue = coatingFilter.value;
      const thicknessValue = thicknessFilter.value;
      const includeSpecial = showSpecialRows && showSpecialRows.checked;

      const filtered = data.filter((row) => {{
        const byClass = classValue === "all" || row.class_name === classValue;
        const byCoating = coatingValue === "all" || row.coating_type === coatingValue;
        const byThickness = thicknessValue === "all" || row.thickness_value === thicknessValue;
        const isStandardName = /стандартн/i.test(row.product_name);
        const isWarehouse = /\\*{{3,4}}/.test(row.product_name);
        const isSpecial = isStandardName || isWarehouse;
        const bySpecial = includeSpecial ? true : !isSpecial;
        return byClass && byCoating && byThickness && bySpecial && row.price !== null;
      }});

      const tailRowNos = new Set([1, 2, 3]);
      const sorted = [...filtered].sort((a, b) => {{
        const aTail = tailRowNos.has(a.product_row_no) ? 1 : 0;
        const bTail = tailRowNos.has(b.product_row_no) ? 1 : 0;
        if (aTail !== bTail) return aTail - bTail;
        if (a.product_row_no !== b.product_row_no) return a.product_row_no - b.product_row_no;
        if (a.class_name !== b.class_name) return a.class_name.localeCompare(b.class_name);
        if (a.thickness_value !== b.thickness_value) return a.thickness_value.localeCompare(b.thickness_value);
        return a.coating_type.localeCompare(b.coating_type);
      }});

      tbody.innerHTML = sorted.map((row) => `
        <tr>
          <td>${{row.product_name}}</td>
          <td>${{row.profile_width_full_mm || "-"}}</td>
          <td class="muted">${{row.coating_type}}</td>
          <td>${{row.thickness}}</td>
          <td class="price">${{formatPrice(row.price)}}</td>
        </tr>
      `).join("");

    }}

    rebuildDomains();
    setOptions(classFilter, classes, "STANDARD", (v) => classLabels[v] || v);
    setOptions(coatingFilter, allCoatings, defaultCoating, coatingLabel);
    setOptions(thicknessFilter, allThicknesses, "all");
    const savedTheme = (() => {{
      try {{
        return localStorage.getItem("profiledSheetTheme");
      }} catch (error) {{
        return null;
      }}
    }})();
    applyTheme(savedTheme || "steel");
    syncCoatingOptions();
    syncThicknessOptions();
    if (themeSwitcher) {{
      themeSwitcher.addEventListener("change", () => applyTheme(themeSwitcher.value));
    }}
    dateRadios.forEach((radio) => {{
      radio.addEventListener("change", (e) => {{
        applySnapshot(parseInt(e.target.value));
      }});
    }});
    classFilter.addEventListener("change", () => {{
      syncCoatingOptions();
      syncThicknessOptions();
      render();
    }});
    coatingFilter.addEventListener("change", () => {{
      syncThicknessOptions();
      render();
    }});
    thicknessFilter.addEventListener("change", render);
    if (showSpecialRows) {{
      showSpecialRows.addEventListener("change", render);
    }}
    render();
  </script>
</body>
</html>
"""


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(INPUT_DIR.glob("*.pdf"), key=parse_uploaded_datetime, reverse=True)
    if not pdf_files:
        raise SystemExit("No PDF files found in input/")

    parsed_by_file: dict[str, dict] = {}
    for pdf in sorted(pdf_files, key=parse_uploaded_datetime):
        doc = fitz.open(pdf)
        if len(doc) < TARGET_PAGE:
            continue
        page = doc[TARGET_PAGE - 1]
        rows, additions = parse_rows(page)
        records = build_records(rows)
        parsed_by_file[pdf.name] = {
            "uploaded_label": parse_uploaded_label(pdf),
            "source_file": pdf.name,
            "rows": rows,
            "additions": additions,
            "records": records,
        }

    # Единый список дат как в input/: даже если по разделу профнастила данных нет,
    # используем последнее доступное состояние цен, чтобы набор дат совпадал между разделами.
    snapshots: list[dict] = []
    last_known: dict | None = None
    for pdf in sorted(pdf_files, key=parse_uploaded_datetime):
        parsed = parsed_by_file.get(pdf.name)
        if parsed is not None:
            last_known = parsed
        if last_known is None:
            continue
        snapshots.append(
            {
                "uploaded_label": parse_uploaded_label(pdf),
                "source_file": pdf.name,
                "rows": last_known["rows"],
                "additions": last_known["additions"],
                "records": last_known["records"],
            }
        )

    # В истории оставляем уникальные даты: если за одну дату есть несколько PDF,
    # берем последнее доступное состояние для этой даты.
    snapshots_by_label: dict[str, dict] = {}
    for snap in snapshots:
        snapshots_by_label[snap["uploaded_label"]] = snap
    snapshots = list(snapshots_by_label.values())

    if not snapshots:
        raise SystemExit(f"No suitable PDF with page {TARGET_PAGE} found in input/")

    current = snapshots[-1]

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": current["source_file"],
        "source_page": TARGET_PAGE,
        "section_title": SECTION_TITLE,
        "latest_uploaded_label": current["uploaded_label"],
        "rows": current["rows"],
        "additions": current["additions"],
        "columns": [column.__dict__ for column in COLUMNS],
        "records": current["records"],
        "price_history": [
            {
                "uploaded_label": snap["uploaded_label"],
                "source_file": snap["source_file"],
                "records": snap["records"],
            }
            for snap in snapshots
        ],
    }

    json_path = DATA_DIR / "profiled-sheet-page4.json"
    html_path = SITE_DIR / "profiled-sheet-page4.html"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(build_html(payload), encoding="utf-8")

    print("Updated:")
    print(json_path)
    print(html_path)


if __name__ == "__main__":
    main()
