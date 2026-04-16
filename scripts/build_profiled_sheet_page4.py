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

TARGET_PAGE = 4  # 1-based page number
SECTION_TITLE = "РџР РћР¤РР›РР РћР’РђРќРќР«Р™ Р РџР›РћРЎРљРР™ Р›РРЎРў РЎ РџРћР›РРњР•Р РќР«Рњ РџРћРљР Р«РўРР•Рњ"


@dataclass(frozen=True)
class PriceColumn:
    index: int
    class_name: str
    coating_type: str
    thickness: str


COLUMNS: list[PriceColumn] = [
    PriceColumn(1, "РЎРўРђРќР”РђР Рў", "VikingMP/COLOR 30 РјРєРј", "0.45"),
    PriceColumn(2, "РЎРўРђРќР”РђР Рў", "VikingMP 30 РјРєРј", "0.45"),
    PriceColumn(3, "РЎРўРђРќР”РђР Рў", "РџРѕР»РёСЌСЃС‚РµСЂ РґРІСѓСЃС‚РѕСЂ. 25/25 РјРєРј", "0.45"),
    PriceColumn(4, "РЎРўРђРќР”РђР Рў", "РџРѕР»РёСЌСЃС‚РµСЂ 25 РјРєРј", "0.45 (2)"),
    PriceColumn(5, "РЎРўРђРќР”РђР Рў", "РџРѕР»РёСЌСЃС‚РµСЂ 25 РјРєРј", "0.65"),
    PriceColumn(6, "РЎРўРђРќР”РђР Рў", "РџРѕР»РёСЌСЃС‚РµСЂ/COLOR 25 РјРєРј", "0.7 (2)"),
    PriceColumn(7, "РЎРўРђРќР”РђР Рў", "РџРѕР»РёСЌСЃС‚РµСЂ РјР°С‚РѕРІС‹Р№ РґРІСѓСЃС‚РѕСЂ.", "0.8"),
    PriceColumn(8, "РЎРўРђРќР”РђР Рў", "Steelmatt РџРѕР»РёСЌСЃС‚РµСЂ 25 РјРєРј", "0.9"),
    PriceColumn(9, "РЎРўРђРќР”РђР Рў", "Steelmatt РџРѕР»РёСЌСЃС‚РµСЂ 25 РјРєРј", "1.0"),
    PriceColumn(10, "Р­РљРћРќРћРњ", "РџРѕР»РёСЌСЃС‚РµСЂ 25 РјРєРј", "0.4"),
    PriceColumn(11, "Р­РљРћРќРћРњ", "РџРѕР»РёСЌСЃС‚РµСЂ/COLOR 25 РјРєРј", "0.4"),
    PriceColumn(12, "Р­РљРћРќРћРњ", "РџРѕР»РёСЌСЃС‚РµСЂ РјР°С‚РѕРІС‹Р№ РґРІСѓСЃС‚РѕСЂ.", "0.4"),
    PriceColumn(13, "Р­РљРћРќРћРњ", "Steelmatt РџРѕР»РёСЌСЃС‚РµСЂ 25 РјРєРј", "0.4"),
    PriceColumn(14, "RETAIL", "РЎРў**", "РЎРў**"),
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
    cleaned = raw.strip()
    if cleaned == "-" or not cleaned:
        return None
    return int(cleaned.replace(" ", ""))


def normalize_thickness(text: str) -> str:
    return text.replace(" (2)", "")


def parse_rows(page: fitz.Page) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    additions: list[dict] = []
    started = True
    in_additions = False

    for block in page.get_text("blocks"):
        text = str(block[4] or "").strip()
        if not text:
            continue

        compact = " ".join(text.split())
        if SECTION_TITLE in compact:
            started = True
            continue
        if compact == "Р”РћРџРћР›РќРРўР•Р›Р¬РќРћ":
            in_additions = True
            continue

        tokens = [line.strip() for line in text.splitlines() if line.strip()]
        if not tokens:
            continue

        if in_additions:
            if not tokens[0].isdigit():
                continue
            if len(tokens) < 5:
                continue
            additions.append(
                {
                    "row_no": int(tokens[0]),
                    "name": tokens[1],
                    "unit": tokens[3],
                    "price": parse_money(tokens[4]),
                }
            )
            continue

        if not tokens[0].isdigit():
            continue
        if len(tokens) < 6:
            continue

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
    default_class = "РЎРўРђРќР”РђР Рў"
    default_thickness = "all"

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>РџСЂРѕС„РЅР°СЃС‚РёР» Рё РїР»РѕСЃРєРёР№ Р»РёСЃС‚ - СЃС‚СЂР°РЅРёС†Р° 4</title>
  <style>
    :root {{
      --bg: #f4f3ef;
      --surface: #ffffff;
      --text: #1e1d1a;
      --muted: #666255;
      --line: #e1ddd3;
      --accent: #0f7c6d;
      --accent-soft: #e7f3f1;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 10% 0%, #e6f2ef, transparent 30%),
        linear-gradient(180deg, #f9f8f5 0%, var(--bg) 100%);
    }}
    .page {{
      width: min(1160px, calc(100% - 24px));
      margin: 24px auto;
    }}
    .hero {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.1;
    }}
    .meta {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.4;
    }}
    .filters {{
      margin-top: 14px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }}
    label {{
      display: grid;
      gap: 6px;
      font-size: 13px;
      color: var(--muted);
    }}
    select {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      font-size: 14px;
      background: #fff;
      color: var(--text);
    }}
    .card {{
      margin-top: 14px;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 18px;
      overflow: hidden;
    }}
    .summary {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
      background: var(--accent-soft);
    }}
    .table-wrap {{
      overflow: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 860px;
    }}
    th, td {{
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #f8faf9;
      color: #353229;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      font-size: 12px;
    }}
    .price {{
      font-weight: 700;
      color: var(--accent);
      white-space: nowrap;
    }}
    .muted {{
      color: var(--muted);
    }}
    @media (max-width: 720px) {{
      .page {{ width: calc(100% - 12px); margin: 12px auto; }}
      .hero {{ padding: 14px; }}
      h1 {{ font-size: 22px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <h1>РџСЂРѕС„РЅР°СЃС‚РёР» Рё РїР»РѕСЃРєРёР№ Р»РёСЃС‚ (СЃС‚СЂР°РЅРёС†Р° 4)</h1>
      <div class="meta">
        РСЃС‚РѕС‡РЅРёРє: <strong>{payload["source_file"]}</strong><br>
        Р Р°Р·РґРµР»: <strong>{payload["section_title"]}</strong><br>
        РџРѕР·РёС†РёРё: <strong>{len(payload["rows"])}</strong>, СЃС‚СЂРѕРє РІ Р±Р»РѕРєРµ "Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ": <strong>{len(payload["additions"])}</strong>
      </div>
      <div class="filters">
        <label>
          РљР»Р°СЃСЃ РїРѕРєСЂС‹С‚РёСЏ
          <select id="class-filter"></select>
        </label>
        <label>
          РўРѕР»С‰РёРЅР°
          <select id="thickness-filter"></select>
        </label>
      </div>
    </section>

    <section class="card">
      <div id="summary" class="summary"></div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>в„–</th>
              <th>РќР°РёРјРµРЅРѕРІР°РЅРёРµ РїСЂРѕРґСѓРєС†РёРё</th>
              <th>РўРёРї РїРѕРєСЂС‹С‚РёСЏ</th>
              <th>РўРѕР»С‰РёРЅР°</th>
              <th>Р¦РµРЅР°</th>
            </tr>
          </thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>
    </section>
  </main>

  <script>
    const data = {records_json};
    const classFilter = document.getElementById("class-filter");
    const thicknessFilter = document.getElementById("thickness-filter");
    const tbody = document.getElementById("tbody");
    const summary = document.getElementById("summary");

    const classes = Array.from(new Set(data.map(r => r.class_name)));
    const allThicknesses = Array.from(new Set(data.map(r => r.thickness_value)));

    function setOptions(select, items, selected) {{
      const isAllowed = selected === "all" || items.includes(selected);
      const selectedValue = isAllowed ? selected : "all";
      const html = ['<option value=\"all\">Р’СЃРµ</option>']
        .concat(items.map(item => `<option value=\"${{item}}\" ${{item === selectedValue ? "selected" : ""}}>${{item}}</option>`))
        .join("");
      select.innerHTML = html;
    }}

    function syncThicknessOptions() {{
      const classValue = classFilter.value;
      const availableThicknesses = Array.from(
        new Set(
          data
            .filter((row) => classValue === "all" || row.class_name === classValue)
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
      const thicknessValue = thicknessFilter.value;

      const filtered = data.filter((row) => {{
        const byClass = classValue === "all" || row.class_name === classValue;
        const byThickness = thicknessValue === "all" || row.thickness_value === thicknessValue;
        return byClass && byThickness && row.price !== null;
      }});

      tbody.innerHTML = filtered.map((row) => `
        <tr>
          <td>${{row.product_row_no}}</td>
          <td>${{row.product_name}}</td>
          <td class="muted">${{row.coating_type}}</td>
          <td>${{row.thickness}}</td>
          <td class="price">${{formatPrice(row.price)}} в‚Ѕ/${{row.unit}}</td>
        </tr>
      `).join("");

      summary.textContent = `РќР°Р№РґРµРЅРѕ СЃС‚СЂРѕРє: ${{filtered.length}}`;
    }}

    setOptions(classFilter, classes, "{default_class}");
    setOptions(thicknessFilter, allThicknesses, "{default_thickness}");
    syncThicknessOptions();
    classFilter.addEventListener("change", () => {{
      syncThicknessOptions();
      render();
    }});
    thicknessFilter.addEventListener("change", render);
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

