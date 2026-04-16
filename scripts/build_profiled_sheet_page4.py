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


def build_html(payload: dict) -> str:
    records_json = json.dumps(payload["records"], ensure_ascii=False)

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>\u041f\u0440\u043e\u0444\u043d\u0430\u0441\u0442\u0438\u043b \u0438 \u043f\u043b\u043e\u0441\u043a\u0438\u0439 \u043b\u0438\u0441\u0442 - \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0430 4</title>
  <style>
    :root {{
      --font-ui: "Segoe UI", "Arial", sans-serif;
      --font-head: "Segoe UI", "Arial", sans-serif;
      --bg: #edf1f6;
      --bg-accent: #dce5f2;
      --bg-noise: radial-gradient(circle at 2px 2px, rgba(27, 39, 52, 0.08) 1px, transparent 1px);
      --bg-pattern-size: 24px 24px;
      --surface: #ffffff;
      --text: #17212f;
      --muted: #576173;
      --line: #d8e0eb;
      --accent: #1f4e79;
      --accent-soft: #e6edf6;
      --table-head: #f3f7fc;
      --table-row-alt: #f8fbff;
      --input-bg: #ffffff;
      --input-text: #17212f;
      --shadow: 0 12px 34px rgba(10, 24, 40, 0.08);
      --radius-card: 18px;
      --radius-control: 12px;
      --radius-chip: 999px;
      --th-case: uppercase;
      --th-spacing: 0.03em;
      --field-border: solid;
      --field-border-width: 1px;
      --control-focus: 0 0 0 3px rgba(31, 78, 121, 0.16);
      --header-weight: 800;
      --hero-grid: linear-gradient(rgba(31, 78, 121, 0.07) 1px, transparent 1px),
        linear-gradient(90deg, rgba(31, 78, 121, 0.07) 1px, transparent 1px);
      --hero-grid-size: 24px 24px;
      --row-number-bg: #dde8f7;
      --row-number-text: #1f4e79;
    }}
    [data-theme="steel"] {{
      --font-ui: "Segoe UI", "Arial", sans-serif;
      --font-head: "Segoe UI", "Arial", sans-serif;
      --bg: #eef2f5;
      --bg-accent: #dde6ed;
      --bg-noise: radial-gradient(circle at 2px 2px, rgba(17, 45, 66, 0.09) 1px, transparent 1px);
      --bg-pattern-size: 20px 20px;
      --surface: #ffffff;
      --text: #1b2734;
      --muted: #5b6876;
      --line: #d2dbe4;
      --accent: #0b5f8a;
      --accent-soft: #e4f0f6;
      --table-head: #f1f7fb;
      --table-row-alt: #f5fbff;
      --input-bg: #f9fcff;
      --input-text: #1b2734;
      --shadow: 0 10px 30px rgba(15, 32, 48, 0.1);
      --radius-card: 12px;
      --radius-control: 8px;
      --radius-chip: 999px;
      --th-case: uppercase;
      --th-spacing: 0.05em;
      --field-border: solid;
      --field-border-width: 1px;
      --control-focus: 0 0 0 3px rgba(11, 95, 138, 0.2);
      --header-weight: 850;
      --hero-grid: linear-gradient(rgba(11, 95, 138, 0.08) 1px, transparent 1px),
        linear-gradient(90deg, rgba(11, 95, 138, 0.08) 1px, transparent 1px);
      --hero-grid-size: 18px 18px;
      --row-number-bg: #dbeef8;
      --row-number-text: #0b5f8a;
    }}
    [data-theme="graphite"] {{
      --font-ui: "Tahoma", "Arial", sans-serif;
      --font-head: "Trebuchet MS", "Tahoma", "Arial", sans-serif;
      --bg: #eceff2;
      --bg-accent: #d6dbe1;
      --bg-noise: linear-gradient(135deg, rgba(59, 79, 103, 0.08) 25%, transparent 25%),
        linear-gradient(225deg, rgba(59, 79, 103, 0.08) 25%, transparent 25%);
      --bg-pattern-size: 18px 18px;
      --surface: #ffffff;
      --text: #1d2026;
      --muted: #5d6470;
      --line: #d7dce3;
      --accent: #3b4f67;
      --accent-soft: #e8ecf2;
      --table-head: #f4f6f9;
      --table-row-alt: #f7f9fc;
      --input-bg: #ffffff;
      --input-text: #1d2026;
      --shadow: 0 12px 32px rgba(22, 28, 36, 0.09);
      --radius-card: 6px;
      --radius-control: 4px;
      --radius-chip: 5px;
      --th-case: none;
      --th-spacing: 0.01em;
      --field-border: dashed;
      --field-border-width: 1px;
      --control-focus: 0 0 0 2px rgba(59, 79, 103, 0.28);
      --header-weight: 700;
      --hero-grid: linear-gradient(rgba(59, 79, 103, 0.06) 1px, transparent 1px),
        linear-gradient(90deg, rgba(59, 79, 103, 0.06) 1px, transparent 1px);
      --hero-grid-size: 12px 12px;
      --row-number-bg: #e1e5eb;
      --row-number-text: #3b4f67;
    }}
    [data-theme="premium"] {{
      --font-ui: "Palatino Linotype", "Book Antiqua", "Georgia", serif;
      --font-head: "Georgia", "Times New Roman", serif;
      --bg: #f3f1ec;
      --bg-accent: #e5decc;
      --bg-noise: radial-gradient(circle at 30% 30%, rgba(124, 90, 33, 0.09) 1px, transparent 1px);
      --bg-pattern-size: 26px 26px;
      --surface: #fffdf8;
      --text: #2e2518;
      --muted: #6f6658;
      --line: #e2d9c7;
      --accent: #7c5a21;
      --accent-soft: #f0e8d9;
      --table-head: #f7f2e9;
      --table-row-alt: #fbf7ef;
      --input-bg: #fffdf9;
      --input-text: #2e2518;
      --shadow: 0 14px 36px rgba(58, 42, 18, 0.1);
      --radius-card: 22px;
      --radius-control: 14px;
      --radius-chip: 999px;
      --th-case: uppercase;
      --th-spacing: 0.08em;
      --field-border: solid;
      --field-border-width: 1px;
      --control-focus: 0 0 0 3px rgba(124, 90, 33, 0.2);
      --header-weight: 650;
      --hero-grid: linear-gradient(rgba(124, 90, 33, 0.06) 1px, transparent 1px),
        linear-gradient(90deg, rgba(124, 90, 33, 0.06) 1px, transparent 1px);
      --hero-grid-size: 32px 32px;
      --row-number-bg: #f0e4ce;
      --row-number-text: #7c5a21;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--font-ui);
      color: var(--text);
      background:
        var(--bg-noise),
        radial-gradient(circle at 10% 0%, var(--bg-accent), transparent 30%),
        linear-gradient(180deg, #f9f8f5 0%, var(--bg) 100%);
      background-size: var(--bg-pattern-size), auto, auto;
    }}
    .page {{ width: min(1160px, calc(100% - 24px)); margin: 24px auto; }}
    .hero {{
      background:
        var(--hero-grid),
        var(--surface);
      background-size: var(--hero-grid-size), auto;
      border: 1px solid var(--line);
      border-radius: var(--radius-card);
      padding: 18px;
      box-shadow: var(--shadow);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(26px, 4vw, 34px);
      line-height: 1.08;
      font-family: var(--font-head);
      font-weight: var(--header-weight);
      letter-spacing: 0.01em;
    }}
    [data-theme="premium"] h1 {{
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .meta {{ color: var(--muted); font-size: 14px; line-height: 1.4; }}
    [data-theme="premium"] .meta,
    [data-theme="premium"] label,
    [data-theme="premium"] th,
    [data-theme="premium"] td {{
      letter-spacing: 0.01em;
    }}
    .meta-row {{ display: flex; gap: 12px; align-items: end; justify-content: space-between; flex-wrap: wrap; }}
    .theme-control {{ min-width: 280px; max-width: 360px; }}
    .filters {{ margin-top: 14px; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }}
    label {{ display: grid; gap: 6px; font-size: 13px; color: var(--muted); font-weight: 600; }}
    select {{
      border: var(--field-border-width) var(--field-border) var(--line);
      border-radius: var(--radius-control);
      padding: 11px 12px;
      font-size: 14px;
      font-weight: 600;
      background: var(--input-bg);
      color: var(--input-text);
      transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.15s ease;
    }}
    select:focus {{
      outline: none;
      border-color: var(--accent);
      box-shadow: var(--control-focus);
    }}
    select:hover {{ transform: translateY(-1px); }}
    .toggle-wrap {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      font-size: 14px;
      color: var(--text);
      font-weight: 600;
      padding: 10px 12px;
      border: var(--field-border-width) var(--field-border) var(--line);
      border-radius: var(--radius-control);
      background: var(--input-bg);
    }}
    input[type="checkbox"] {{
      width: 16px;
      height: 16px;
      accent-color: var(--accent);
      cursor: pointer;
    }}
    .card {{
      margin-top: 14px;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius-card);
      overflow: hidden;
      box-shadow: var(--shadow);
    }}
    .summary {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
      background: var(--accent-soft);
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .summary-badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 10px;
      border-radius: var(--radius-chip);
      border: 1px solid color-mix(in oklab, var(--line) 78%, var(--accent) 22%);
      background: color-mix(in oklab, var(--surface) 85%, var(--accent-soft) 15%);
      font-size: 12px;
      font-weight: 700;
      color: var(--text);
    }}
    .summary-badge strong {{
      color: var(--accent);
      font-size: 13px;
    }}
    [data-theme="premium"] .summary-badge {{
      font-variant: small-caps;
      letter-spacing: 0.03em;
    }}
    .table-wrap {{ overflow: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 860px; }}
    tbody tr:nth-child(even) td {{ background: var(--table-row-alt); }}
    tbody tr:hover td {{ background: color-mix(in oklab, var(--accent-soft) 55%, var(--surface) 45%); }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 11px 12px; vertical-align: top; font-size: 14px; }}
    th {{
      position: sticky;
      top: 0;
      background: var(--table-head);
      color: var(--text);
      text-transform: var(--th-case);
      letter-spacing: var(--th-spacing);
      font-size: 12px;
      font-weight: 800;
      z-index: 2;
    }}
    .product-cell {{ font-weight: 700; }}
    .row-no {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 36px;
      height: 24px;
      margin-right: 8px;
      border-radius: var(--radius-chip);
      background: var(--row-number-bg);
      color: var(--row-number-text);
      font-size: 12px;
      font-weight: 800;
      vertical-align: middle;
    }}
    .coating-chip, .thickness-chip {{
      display: inline-flex;
      align-items: center;
      padding: 4px 9px;
      border-radius: var(--radius-chip);
      border: 1px solid var(--line);
      font-size: 12px;
      line-height: 1.2;
      background: var(--surface);
    }}
    .coating-chip {{ color: var(--muted); }}
    .thickness-chip {{ color: var(--accent); font-weight: 700; }}
    .price {{ font-weight: 700; color: var(--accent); white-space: nowrap; }}
    th:last-child, td:last-child {{ text-align: right; }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 760px) {{
      .theme-control {{ min-width: 100%; max-width: 100%; }}
      .filters {{ grid-template-columns: 1fr; }}
      .page {{ width: min(1160px, calc(100% - 16px)); margin: 16px auto; }}
      .hero, .card {{ border-radius: max(10px, calc(var(--radius-card) - 6px)); }}
      th, td {{ padding: 9px 10px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <h1>\u041f\u0420\u041e\u0424\u0418\u041b\u0418\u0420\u041e\u0412\u0410\u041d\u041d\u042b\u0419 \u0418 \u041f\u041b\u041e\u0421\u041a\u0418\u0419 \u041b\u0418\u0421\u0422 \u0421 \u041f\u041e\u041b\u0418\u041c\u0415\u0420\u041d\u042b\u041c \u041f\u041e\u041a\u0420\u042b\u0422\u0418\u0415\u041c</h1>
      <div class="meta-row">
        <div class="meta">
          \u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a: <strong>{payload["source_file"]}</strong>
        </div>
        <label class="theme-control">
          \u0421\u0442\u0438\u043b\u044c \u043e\u0442\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u044f
          <select id="theme-switcher">
            <option value="steel">\u041a\u043e\u0440\u043f\u043e\u0440\u0430\u0442\u0438\u0432\u043d\u044b\u0439 \u0441\u0438\u043d\u0438\u0439</option>
            <option value="graphite">\u0413\u0440\u0430\u0444\u0438\u0442\u043e\u0432\u044b\u0439</option>
            <option value="premium">\u041f\u0440\u0435\u043c\u0438\u0443\u043c \u0431\u0435\u0436\u0435\u0432\u044b\u0439</option>
          </select>
        </label>
      </div>
      <div class="filters">
        <label>\u041a\u043b\u0430\u0441\u0441 \u043f\u043e\u043a\u0440\u044b\u0442\u0438\u044f<select id="class-filter"></select></label>
        <label>\u0422\u0438\u043f \u043f\u043e\u043a\u0440\u044b\u0442\u0438\u044f<select id="coating-filter"></select></label>
        <label>\u0422\u043e\u043b\u0449\u0438\u043d\u0430<select id="thickness-filter"></select></label>
      </div>
      <div class="filters" style="margin-top: 10px;">
        <label class="toggle-wrap">
          <input type="checkbox" id="show-special-rows">
          <span>\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0441\u043a\u043b\u0430\u0434\u0441\u043a\u0438\u0435 \u0438 \u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442\u043d\u044b\u0435 \u043f\u043e\u0437\u0438\u0446\u0438\u0438</span>
        </label>
      </div>
    </section>

    <section class="card">
      <div id="summary" class="summary"></div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u043f\u0440\u043e\u0434\u0443\u043a\u0446\u0438\u0438</th>
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
    const data = {records_json};
    const themeSwitcher = document.getElementById("theme-switcher");
    const classFilter = document.getElementById("class-filter");
    const coatingFilter = document.getElementById("coating-filter");
    const thicknessFilter = document.getElementById("thickness-filter");
    const showSpecialRows = document.getElementById("show-special-rows");
    const tbody = document.getElementById("tbody");
    const summary = document.getElementById("summary");

    const classes = Array.from(new Set(data.map(r => r.class_name)));
    const allCoatings = Array.from(new Set(data.map(r => r.coating_type)));
    const allThicknesses = Array.from(new Set(data.map(r => r.thickness_value)));
    const defaultCoating = allCoatings.includes("Полиэстер 25")
      ? "Полиэстер 25"
      : "Polyester 25";

    const classLabels = {{
      STANDARD: "\u0421\u0422\u0410\u041d\u0414\u0410\u0420\u0422",
      ECONOM: "\u042d\u041a\u041e\u041d\u041e\u041c",
      RETAIL: "RETAIL",
    }};
    const coatingLabel = (value) => value
      .replace(/^Polyester\b/, "Полиэстер")
      .replace(/^Steelmatt Polyester\b/, "Steelmatt Полиэстер");

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

    function escapeHtml(value) {{
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
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
          <td class="product-cell"><span class="row-no">№${{row.product_row_no}}</span>${{escapeHtml(row.product_name)}}</td>
          <td><span class="coating-chip">${{escapeHtml(row.coating_type)}}</span></td>
          <td><span class="thickness-chip">${{escapeHtml(row.thickness)}}</span></td>
          <td class="price">${{formatPrice(row.price)}}</td>
        </tr>
      `).join("");

      const classLabel = classValue === "all" ? "Все" : (classLabels[classValue] || classValue);
      const coatingLabelText = coatingValue === "all" ? "Все" : coatingLabel(coatingValue);
      const thicknessLabel = thicknessValue === "all" ? "Все" : thicknessValue;
      summary.innerHTML = `
        <span class="summary-badge">\u041d\u0430\u0439\u0434\u0435\u043d\u043e: <strong>${{sorted.length}}</strong></span>
        <span class="summary-badge">\u041a\u043b\u0430\u0441\u0441: <strong>${{escapeHtml(classLabel)}}</strong></span>
        <span class="summary-badge">\u0422\u0438\u043f: <strong>${{escapeHtml(coatingLabelText)}}</strong></span>
        <span class="summary-badge">\u0422\u043e\u043b\u0449\u0438\u043d\u0430: <strong>${{escapeHtml(thicknessLabel)}}</strong></span>
      `;
    }}

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

    source_pdf = pdf_files[0]
    doc = fitz.open(source_pdf)
    if len(doc) < TARGET_PAGE:
        raise SystemExit(f"PDF has only {len(doc)} page(s), cannot read page {TARGET_PAGE}")

    page = doc[TARGET_PAGE - 1]
    rows, additions = parse_rows(page)
    records = build_records(rows)

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": source_pdf.name,
        "source_page": TARGET_PAGE,
        "section_title": SECTION_TITLE,
        "rows": rows,
        "additions": additions,
        "columns": [column.__dict__ for column in COLUMNS],
        "records": records,
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
