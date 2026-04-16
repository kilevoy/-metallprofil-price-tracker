from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from datetime import datetime
from html import escape
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "input"
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"

SANDWICH_TITLE = 'ТРЕХСЛОЙНЫЕ СЭНДВИЧ-ПАНЕЛИ "МЕТАЛЛ ПРОФИЛЬ"'
COLORS_TITLE = "ПЕРЕЧЕНЬ СТАНДАРТНЫХ ЦВЕТОВ ДЛЯ ТРЕХСЛОЙНЫХ СЭНДВИЧ-ПАНЕЛЕЙ"
AIRPANEL_TITLE = 'ПЕРЕЧЕНЬ СТАНДАРТНЫХ ЦВЕТОВ ДЛЯ ТРЕХСЛОЙНЫХ СЭНДВИЧ-ПАНЕЛЕЙ "AIRPANEL"'


@dataclass
class ParsedPdf:
    pdf_path: Path
    uploaded_label: str
    sandwich: dict
    colors: dict


def unique(seq):
    seen = set()
    result = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def prettify_compound(text: str) -> str:
    text = text.replace("БелыйКамень", "Белый Камень")
    text = text.replace("ЗолотойДуб", "Золотой Дуб")
    text = text.replace("Античный дуб", "Античный дуб")
    text = text.replace("Золотой орех", "Золотой орех")
    text = text.replace("Беленый Дуб", "Беленый Дуб")
    text = text.replace("DarkBrown", "Dark Brown")
    text = text.replace("DarkGrey", "Dark Grey")
    text = text.replace("OxiBеige", "OxiBeige")
    return text


def find_page_index(doc: fitz.Document, marker: str) -> int:
    marker = marker.lower()
    for index in range(len(doc)):
        page_text = doc[index].get_text().lower()
        if marker in page_text:
            return index
    raise ValueError(f"Marker not found: {marker}")


def find_page_index_by_terms(doc: fitz.Document, required_terms: list[str]) -> int:
    required_terms = [term.lower() for term in required_terms]
    for index in range(len(doc)):
        page_text = doc[index].get_text().lower()
        if all(term in page_text for term in required_terms):
            return index
    raise ValueError(f"Page not found for terms: {required_terms}")


def parse_uploaded_label(path: Path) -> str:
    name = path.stem
    m_full = re.search(r"(\d{2})\.(\d{2})\.(\d{2,4})", name)
    if m_full:
        day, month, year = m_full.groups()
        if len(year) == 2:
            year = f"20{year}"
        return f"{day}.{month}.{year}"
    m_short = re.search(r"(\d{2})\.(\d{2})", name)
    if m_short:
        day, month = m_short.groups()
        year = str(datetime.fromtimestamp(path.stat().st_mtime).year)
        return f"{day}.{month}.{year}"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y")


def parse_uploaded_datetime(path: Path) -> datetime:
    label = parse_uploaded_label(path)
    return datetime.strptime(label, "%d.%m.%Y")


def format_number(value: float) -> str:
    if value is None:
        return "-"
    rounded = int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{rounded:,}".replace(",", " ")


def parse_currency_value(raw: str) -> float:
    return float(raw.replace(" ", "").replace(",", "."))


def parse_price_tokens(chunk: str) -> list[str]:
    return re.findall(r"-|\d{1,3}(?: \d{3})?(?:,\d+)?", chunk)


def find_page_block(doc: fitz.Document, page_terms: list[str], block_term: str) -> str:
    page_index = find_page_index_by_terms(doc, page_terms)
    page = doc[page_index]
    for block in page.get_text("blocks"):
        text = clean_text(block[4])
        if block_term in text:
            return text
    raise ValueError(f"Block not found: {block_term}")


def parse_accessories_prices(doc: fitz.Document) -> dict:
    # Базовые цены для Полиэстер 25 мкм берем из строки "1 Плоский лист ТУ"
    poly_block = find_page_block(
        doc,
        ["ОСНОВНЫЕ ВИДЫ ПРОДУКЦИИ С ПОЛИМЕРНЫМ ПОКРЫТИЕМ И ОЦИНКОВАННОЙ СТАЛИ", "Плоский лист ТУ"],
        "1 Плоский лист ТУ",
    )
    if "м.кв." not in poly_block:
        raise ValueError("Unexpected format for polyester flat sheet row")
    # Для этой строки цены идут как отдельные колонки, поэтому разбираем
    # только "целые" и "десятичные с запятой", без склейки через пробел.
    poly_tokens = re.findall(r"\d+,\d+|\d+", poly_block.split("м.кв.", 1)[1])
    if len(poly_tokens) < 2:
        raise ValueError("Not enough polyester prices in flat sheet row")
    polyester_05_base = parse_currency_value(poly_tokens[0])
    polyester_07_base = parse_currency_value(poly_tokens[1])

    # Базовые цены для оцинковки берем из строки "1 Плоский лист **" (прайс №2)
    zinc_block = find_page_block(
        doc,
        ["ОСНОВНЫЕ ВИДЫ ПРОДУКЦИИ ОЦИНКОВАННЫЕ", "Плоский лист **"],
        "1 Плоский лист **",
    )
    zinc_tokens = parse_price_tokens(zinc_block)
    # Токены строки: [1, 1250, 0,9600, 347,88, 353,76, ...]
    # База для фасонных изделий ТСП:
    # 0,45 -> 405,72 ; 0,5 -> 432,00 ; 0,7 -> 579,60
    if len(zinc_tokens) < 11:
        raise ValueError("Not enough galvanized prices in flat sheet row")
    zinc_045_base = parse_currency_value(zinc_tokens[6])
    zinc_05_base = parse_currency_value(zinc_tokens[8])
    zinc_07_base = parse_currency_value(zinc_tokens[10])

    return {
        "Оцинковка": {
            "0,45": round(zinc_045_base * 1.9, 2),
            "0,5": round(zinc_05_base * 1.9, 2),
            "0,7": round(zinc_07_base * 1.9, 2),
        },
        "Полиэстер 25 мкм": {
            "0,45": None,
            "0,5": round(polyester_05_base * 1.9, 2),
            "0,7": round(polyester_07_base * 1.9, 2),
        },
    }


def normalize_price_tokens(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value == "-":
            result.append("-")
        else:
            result.append(format_number(parse_currency_value(value)))
    return result


def parse_sandwich_page(doc: fitz.Document) -> dict:
    page_index = find_page_index_by_terms(
        doc,
        [SANDWICH_TITLE, "МП ТСП-Z", "ДОПОЛНИТЕЛЬНЫЕ ОПЦИИ"],
    )
    page = doc[page_index]
    blocks = [clean_text(block[4]) for block in page.get_text("blocks") if clean_text(block[4])]
    full_text = page.get_text()
    date_match = re.search(r"Цены действительны с (\d{2} [а-яА-Я]+ \d{4}г\.)", full_text)
    effective_date = date_match.group(1) if date_match else ""

    section = "class_1"
    products = {"class_1": [], "class_2": []}
    accessories = []

    for block in blocks:
        if "КЛАСС 2" in block:
            section = "class_2"
            continue

        for mark in ("МП ТСП-Z", "МП ТСП-S", "МП ТСП-К"):
            if mark in block and "м.кв." in block and re.match(r"^\d+\s", block):
                left, right = block.split(mark, 1)
                width_part, prices_part = right.split("м.кв.", 1)
                name = re.sub(r"^\d+\s+", "", left).strip()
                prices = parse_price_tokens(prices_part)
                if len(prices) >= 9:
                    products[section].append(
                        {
                            "name": name,
                            "mark": mark,
                            "width": width_part.strip(),
                            "prices": normalize_price_tokens(prices[:9]),
                        }
                    )
                break

        if "Фасонное изделие для ТСП -" in block and "Цена плоского листа" in block:
            thickness = block.split("Фасонное изделие для ТСП -", 1)[1].split("(", 1)[0].strip()
            accessories.append({"thickness": thickness, "formula": "Цена плоского листа × 1,9"})

    return {
        "page_index": page_index + 1,
        "effective_date": effective_date,
        "class_1_meta": "Минвата 105 кг/м3, ГОСТ 32603-2021, сталь 0.5/0.5.",
        "class_2_meta": "Стеновые панели: ГОСТ 32603-2021 класс 2. Кровельные панели: ТУ 5284-001-37144780-2012. Минвата 95 кг/м3, сталь 0.5/0.5.",
        "thickness_headers": ["50", "60", "80", "100", "120", "150", "170", "200", "250"],
        "products": products,
        "accessories": accessories,
        "accessories_prices": parse_accessories_prices(doc),
        "minimum_order_panels": "200 м.кв.",
    }


def parse_colors_page(doc: fitz.Document) -> dict:
    page_index = find_page_index_by_terms(
        doc,
        [COLORS_TITLE, "VALORI-20-Brown", "PURMAN-20-3005"],
    )
    full_text = doc[page_index].get_text()
    date_match = re.search(r"Цены действительны с (\d{2} [а-яА-Я]+ \d{4}г\.)", full_text)
    text = full_text.split(AIRPANEL_TITLE)[0]

    polyester = unique(re.findall(r"Полиэстер ПЭ-01-([A-Za-zА-Яа-я0-9]+)", text))
    purman = unique(re.findall(r"PURMAN-20-([A-Za-zА-Яа-я0-9]+)", text))
    valori = unique(re.findall(r"VALORI-20-([A-Za-zА-Яа-я0-9]+)", text))
    ecosteel_raw = unique(
        re.findall(r"ECOSTEEL(?:_[A-ZА-Я]+)?-\d{2}-([A-Za-zА-Яа-яЁё ]+?)(?: \(|\n|$)", text)
    )
    ecosteel = unique(prettify_compound(item.strip()) for item in ecosteel_raw if item.strip())

    polyester = [prettify_compound(item) for item in polyester]
    purman = [prettify_compound(item) for item in purman]
    valori = [prettify_compound(item) for item in valori]

    return {
        "page_index": page_index + 1,
        "effective_date": date_match.group(1) if date_match else "",
        "polyester": polyester,
        "purman": purman,
        "ais_related": "См. PURMAN",
        "ecosteel": ecosteel,
        "valori": valori,
        "minimum_order_raw_material": "Минимальный объем заказа сырья отсутствует",
    }


def parse_pdf(path: Path) -> ParsedPdf:
    doc = fitz.open(path)
    return ParsedPdf(
        pdf_path=path,
        uploaded_label=parse_uploaded_label(path),
        sandwich=parse_sandwich_page(doc),
        colors=parse_colors_page(doc),
    )


def compare_prices(current: ParsedPdf, previous: ParsedPdf | None) -> dict:
    if previous is None:
        return {
            "has_previous": False,
            "status": "Первый загруженный прайс для сравнения",
            "price_changes": [],
            "summary": "Нет предыдущего файла для сравнения",
        }

    changes = []
    for section_key in ("class_1", "class_2"):
        current_rows = current.sandwich["products"][section_key]
        previous_rows = previous.sandwich["products"][section_key]
        for current_row, previous_row in zip(current_rows, previous_rows):
            for idx, (cur, prev) in enumerate(zip(current_row["prices"], previous_row["prices"])):
                if cur == "-" or prev == "-" or cur == prev:
                    continue
                current_value = parse_currency_value(cur)
                previous_value = parse_currency_value(prev)
                percent = round((current_value - previous_value) / previous_value * 100, 2)
                changes.append(
                    {
                        "product": current_row["mark"],
                        "section": section_key,
                        "thickness": current.sandwich["thickness_headers"][idx],
                        "previous": prev,
                        "current": cur,
                        "percent": percent,
                    }
                )

    if not changes:
        summary = "Изменений по ценам на сэндвич-панели относительно предыдущего загруженного прайса не найдено"
    else:
        percents = [item["percent"] for item in changes]
        min_percent = min(percents)
        max_percent = max(percents)
        summary = (
            f"Обнаружено {len(changes)} изменений. "
            f"Диапазон изменения: от {str(min_percent).replace('.', ',')}% до {str(max_percent).replace('.', ',')}%."
        )

    return {
        "has_previous": True,
        "status": summary,
        "price_changes": changes,
        "summary": summary,
        "previous_file": previous.pdf_path.name,
        "current_file": current.pdf_path.name,
    }


def build_price_history(snapshots: list[dict]) -> list[dict]:
    history = []
    for snap in snapshots:
        history.append(
            {
                "date": snap["uploaded_label"],
                "effective_date": snap["sandwich"]["effective_date"],
                "label": snap["uploaded_label"],
                "sandwich": snap["sandwich"],
                "source_file": snap["source_file"],
            }
        )
    return history


def build_price_rows(rows: list[dict], hidden_fix: bool) -> str:
    rendered = []
    for row in rows:
        is_hidden_fix = row["mark"] == "МП ТСП-S"
        attrs = ' class="hidden-fix-row" hidden' if is_hidden_fix and hidden_fix else ""
        prices = "".join(f"<td>{escape(value)}</td>" for value in row["prices"])
        label = (
            "Стеновая ТСП-Z" if row["mark"] == "МП ТСП-Z"
            else "Стеновая ТСП-S" if row["mark"] == "МП ТСП-S"
            else "Кровельная ТСП-К"
        )
        rendered.append(f"<tr{attrs}><td class=\"product\">{escape(label)}</td>{prices}</tr>")
    return "\n".join(rendered)


def build_chip_list(items: list[str]) -> str:
    return "".join(f'<span class="chip">{escape(item)}</span>' for item in items)


def generate_html(current: ParsedPdf, comparison: dict, price_history: list[dict]) -> str:
    latest_file_label = current.uploaded_label
    effective_date = current.sandwich["effective_date"]
    colors = current.colors
    acc = current.sandwich["accessories_prices"]

    # Подготавливаем таблицы для каждого снапшота
    snapshots_data = []
    for snap in price_history:
        s = snap["sandwich"]
        snapshots_data.append({
            "date": snap["date"],
            "effective_date": snap["effective_date"],
            "label": snap["label"],
            "class_1_rows": build_price_rows(s["products"]["class_1"], hidden_fix=True),
            "class_2_rows": build_price_rows(s["products"]["class_2"], hidden_fix=True),
        })

    # Текущие цены (последний снапшот)
    current_snap = snapshots_data[-1]
    class_1_rows = current_snap["class_1_rows"]
    class_2_rows = current_snap["class_2_rows"]

    # Radio-кнопки дат
    date_radios_html = ""
    for i, snap in enumerate(snapshots_data):
        checked = "checked" if i == len(snapshots_data) - 1 else ""
        date_radios_html += f"""
          <label class="date-radio">
            <input type="radio" name="price-date" value="{i}" {checked}>
            <span class="date-label">{escape(snap["label"])}</span>
          </label>"""

    # Данные для JS — все снапшоты
    import json as _json
    snapshots_json = _json.dumps(snapshots_data, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Прайс на сэндвич-панели</title>
  <style>
    :root {{
      --bg: #f3eee7;
      --surface: rgba(255, 252, 247, 0.94);
      --surface-strong: #fffdfa;
      --text: #181511;
      --muted: #6e665c;
      --accent: #b24e2d;
      --accent-deep: #8f381f;
      --line: rgba(70, 53, 39, 0.1);
      --line-strong: rgba(70, 53, 39, 0.18);
      --shadow: 0 22px 60px rgba(58, 38, 22, 0.1);
      --radius: 24px;
      --font-head: Georgia, "Times New Roman", serif;
      --font-body: "Segoe UI", Tahoma, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--font-body);
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(178, 78, 45, 0.14), transparent 28%),
        radial-gradient(circle at 85% 8%, rgba(200, 171, 118, 0.18), transparent 24%),
        linear-gradient(180deg, #f9f4ed 0%, var(--bg) 100%);
      min-height: 100vh;
    }}
    .page {{ width: min(1180px, calc(100% - 32px)); margin: 28px auto 48px; }}
    .hero {{
      padding: 34px 34px 28px;
      border-radius: 30px;
      background:
        linear-gradient(135deg, rgba(255, 252, 247, 0.98), rgba(245, 233, 224, 0.92)),
        linear-gradient(180deg, rgba(255,255,255,0.6), rgba(255,255,255,0));
      border: 1px solid rgba(178, 78, 45, 0.14);
      box-shadow: var(--shadow);
      position: relative;
      overflow: hidden;
    }}
    .top-row {{
      display: flex;
      justify-content: flex-end;
      margin-bottom: 10px;
      position: relative;
      z-index: 2;
    }}
    .back-link {{
      display: inline-flex;
      align-items: center;
      text-decoration: none;
      color: var(--accent-deep);
      font-size: 13px;
      font-weight: 700;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid rgba(70, 53, 39, 0.15);
      background: rgba(255, 255, 255, 0.86);
    }}
    .back-link:hover {{
      background: rgba(178, 78, 45, 0.08);
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -90px -115px auto;
      width: 290px;
      height: 290px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(178, 78, 45, 0.16), transparent 70%);
    }}
    .hero::before {{
      content: "";
      position: absolute;
      inset: -1px auto auto -1px;
      width: 180px;
      height: 6px;
      background: linear-gradient(90deg, var(--accent), rgba(178, 78, 45, 0));
    }}
    .eyebrow {{
      margin: 0 0 12px;
      color: var(--accent);
      font-size: 14px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }}
    h1 {{
      margin: 0;
      font-family: var(--font-head);
      font-size: clamp(28px, 4vw, 42px);
      line-height: 1;
      letter-spacing: -0.03em;
      max-width: 820px;
      font-weight: 700;
      text-wrap: balance;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 22px;
    }}
    .pill {{
      padding: 10px 15px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.78);
      border: 1px solid rgba(70, 53, 39, 0.07);
      font-size: 14px;
      color: var(--text);
    }}
    .pill strong {{ color: var(--accent); }}
    .pill a {{
      color: var(--accent-deep);
      text-decoration: none;
      border-bottom: 1px solid rgba(143, 56, 31, 0.35);
    }}
    .pill a:hover {{
      border-bottom-color: rgba(143, 56, 31, 0.75);
    }}
    .date-picker-section {{
      margin-top: 24px;
      padding: 18px 20px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.7);
      border: 1px solid rgba(70, 53, 39, 0.08);
    }}
    .date-picker-title {{
      margin: 0 0 14px;
      font-size: 15px;
      font-weight: 600;
      color: var(--text);
    }}
    .date-radios {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 10px;
      align-items: stretch;
    }}
    .date-radio {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 10px 16px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.8);
      border: 1px solid rgba(70, 53, 39, 0.1);
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .date-radio:hover {{
      border-color: var(--accent);
      background: rgba(178, 78, 45, 0.06);
    }}
    .date-radio input[type="radio"] {{
      width: 16px;
      height: 16px;
      accent-color: var(--accent);
      cursor: pointer;
    }}
    .date-radio input[type="radio"]:checked + .date-label {{
      color: var(--accent);
      font-weight: 600;
    }}
    .date-label {{
      font-size: 14px;
      color: var(--text);
      white-space: normal;
    }}
    .section {{
      margin-top: 24px;
      padding: 26px 26px 24px;
      border-radius: var(--radius);
      background: var(--surface);
      border: 1px solid rgba(70, 53, 39, 0.08);
      box-shadow: var(--shadow);
    }}
    .section-head {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }}
    .section h2 {{
      margin: 0 0 6px;
      font-family: var(--font-head);
      font-size: clamp(26px, 3vw, 34px);
      letter-spacing: -0.02em;
      line-height: 1;
    }}
    .section p {{ margin: 0; color: var(--muted); line-height: 1.45; }}
    .toolbar {{ display: flex; justify-content: flex-end; }}
    .toggle {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 999px;
      background: linear-gradient(180deg, #fffefc, #f7f0e8);
      border: 1px solid var(--line-strong);
      color: var(--text);
      font-size: 14px;
      cursor: pointer;
      user-select: none;
    }}
    .toggle input {{
      width: 16px;
      height: 16px;
      accent-color: var(--accent);
    }}
    .table-wrap {{
      overflow-x: auto;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: var(--surface-strong);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.8);
    }}
    table {{ width: 100%; border-collapse: collapse; min-width: 760px; }}
    th, td {{
      padding: 15px 16px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: middle;
      font-size: 14px;
    }}
    thead th {{
      position: sticky;
      top: 0;
      background: linear-gradient(180deg, #fff8f2, #fcf3eb);
      z-index: 1;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      border-bottom: 1px solid var(--line-strong);
    }}
    tbody td:first-child, thead th:first-child {{
      position: sticky;
      left: 0;
      z-index: 2;
      background: inherit;
    }}
    thead th:first-child {{ z-index: 3; }}
    tbody tr:last-child td {{ border-bottom: 0; }}
    tbody tr:hover {{ background: rgba(178, 78, 45, 0.045); }}
    .product {{ min-width: 250px; font-weight: 600; color: var(--accent-deep); }}
    .info-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }}
    .info-card {{
      padding: 18px;
      border-radius: 18px;
      background: var(--surface-strong);
      border: 1px solid var(--line);
    }}
    .info-card h3 {{
      margin: 0 0 10px;
      font-family: var(--font-head);
      font-size: 22px;
      line-height: 1;
    }}
    .info-card p {{
      margin: 0;
      font-size: 14px;
      line-height: 1.5;
      color: var(--muted);
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .chip {{
      padding: 8px 10px;
      border-radius: 999px;
      background: #faf2ec;
      border: 1px solid rgba(178, 78, 45, 0.1);
      font-size: 13px;
      line-height: 1;
    }}
    .list-blocks {{ display: grid; gap: 6px; margin-top: 10px; }}
    .list-line {{
      padding: 8px 12px;
      border-radius: 14px;
      background: #faf6f1;
      border: 1px solid rgba(70, 53, 39, 0.08);
      font-size: 14px;
      line-height: 1.3;
      color: var(--text);
    }}
    .list-line strong {{ color: var(--accent-deep); }}
    footer {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
      text-align: center;
    }}
    footer a {{
      color: var(--accent-deep);
      text-decoration: none;
      border-bottom: 1px solid rgba(143, 56, 31, 0.35);
    }}
    footer a:hover {{
      border-bottom-color: rgba(143, 56, 31, 0.75);
    }}
    @media (max-width: 720px) {{
      .page {{ width: min(100% - 20px, 1180px); margin-top: 12px; }}
      .hero, .section {{ padding: 20px; }}
      .hero {{ padding-top: 24px; }}
      .section-head {{ display: block; }}
      .toolbar {{ margin-top: 12px; justify-content: flex-start; }}
      tbody td:first-child, thead th:first-child {{ position: static; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="top-row"><a class="back-link" href="index.html">← К оглавлению</a></div>
      <p class="eyebrow">Сэндвич-панели</p>
      <h1>Прайс на сэндвич-панели</h1>
      <div class="meta">
        <span class="pill"><strong>Действует с:</strong> <span id="effective-date-text">{escape(effective_date)}</span></span>
        <span class="pill"><strong>Последний загруженный прайс-лист:</strong> {escape(latest_file_label)}</span>
        <span class="pill"><strong>Документация:</strong> <a href="https://github.com/kilevoy/-metallprofil-price-tracker#readme" target="_blank" rel="noopener noreferrer">README</a></span>
      </div>
      <div class="date-picker-section">
        <p class="date-picker-title">Выберите дату для просмотра цен:</p>
        <div class="date-radios" id="date-radios">
          {date_radios_html}
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <div>
          <h2>Класс 1</h2>
          <p>{escape(current.sandwich["class_1_meta"])}</p>
        </div>
        <div class="toolbar">
          <label class="toggle">
            <input type="checkbox" id="toggle-hidden-fix">
            Показать со скрытым креплением
          </label>
        </div>
      </div>
      <div class="table-wrap" style="margin-top: 14px;">        <table id="class1-table">
          <thead>
            <tr>
              <th>Позиция</th>
              <th>50 мм</th><th>60 мм</th><th>80 мм</th><th>100 мм</th><th>120 мм</th><th>150 мм</th><th>170 мм</th><th>200 мм</th><th>250 мм</th>
            </tr>
          </thead>
          <tbody>
            {class_1_rows}
          </tbody>
        </table>
      </div>
    </section>

    <section class="section">      <h2>Класс 2</h2>      <p style="margin-bottom: 14px;">{escape(current.sandwich["class_2_meta"])}</p>      <div class="table-wrap">        <table id="class2-table">
          <thead>
            <tr>
              <th>Позиция</th>
              <th>50 мм</th><th>60 мм</th><th>80 мм</th><th>100 мм</th><th>120 мм</th><th>150 мм</th><th>170 мм</th><th>200 мм</th><th>250 мм</th>
            </tr>
          </thead>
          <tbody>
            {class_2_rows}
          </tbody>
        </table>
      </div>
    </section>

    <section class="section">
      <h2>Фасонные изделия для ТСП</h2>
      <p style="margin-bottom: 14px;">Показаны расчетные цены за <strong>м.кв.</strong> по формуле страницы 28: <strong>цена плоского листа × 1,9</strong>.</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Материал</th>
              <th>0,45 мм</th>
              <th>0,5 мм</th>
              <th>0,7 мм</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="product">Оцинковка</td>
              <td>{format_number(acc["Оцинковка"]["0,45"])}</td>
              <td>{format_number(acc["Оцинковка"]["0,5"])}</td>
              <td>{format_number(acc["Оцинковка"]["0,7"])}</td>
            </tr>
            <tr>
              <td class="product">Полиэстер 25 мкм</td>
              <td>-</td>
              <td>{format_number(acc["Полиэстер 25 мкм"]["0,5"])}</td>
              <td>{format_number(acc["Полиэстер 25 мкм"]["0,7"])}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="section">
      <div class="info-grid">
        <article class="info-card">
          <h3>Стандартные цвета</h3>
          <p>По листу стандартных цветов для трехслойных сэндвич-панелей (Екатеринбург).</p>
          <div class="list-blocks">
            <div class="list-line"><strong>Полиэстер:</strong> {escape(", ".join(colors["polyester"]))}</div>
            <div class="list-line"><strong>PURMAN:</strong> {escape(", ".join(colors["purman"]))}</div>
            <div class="list-line"><strong>AIS / AGRARIUM / INDUSTRIUM / STERILIUM:</strong> {escape(colors["ais_related"])}</div>
            <div class="list-line"><strong>ECOSTEEL:</strong> {escape(", ".join(colors["ecosteel"]))}</div>
            <div class="list-line"><strong>VALORI:</strong> {escape(", ".join(colors["valori"]))}</div>
          </div>
        </article>
        <article class="info-card">
          <h3>Минимальный заказ</h3>
          <p>Минимальный заказ одного наименования из стандартного сырья, то есть одинаковые тип, толщина, цвет и вид профилирования, составляет <strong>{escape(current.sandwich["minimum_order_panels"])}</strong>.</p>
          <div class="chips">
            <span class="chip">Минимум: {escape(current.sandwich["minimum_order_panels"])}</span>
            <span class="chip">{escape(colors["minimum_order_raw_material"])}</span>
          </div>
        </article>
      </div>
    </section>

    <footer>
      Сгенерировано автоматически из PDF в папке input.
      <a href="https://github.com/kilevoy/-metallprofil-price-tracker#readme" target="_blank" rel="noopener noreferrer">README</a>
    </footer>
  </main>
  <script>
    const snapshots = {snapshots_json};
    const toggle = document.getElementById("toggle-hidden-fix");
    const dateRadios = document.querySelectorAll('input[name="price-date"]');
    const class1Body = document.querySelector("#class1-table tbody");
    const class2Body = document.querySelector("#class2-table tbody");

    function applySnapshot(index) {{
      const snap = snapshots[index];
      class1Body.innerHTML = snap.class_1_rows;
      class2Body.innerHTML = snap.class_2_rows;
      document.getElementById("effective-date-text").textContent = snap.effective_date;
      syncHiddenFixRows();
    }}

    function syncHiddenFixRows() {{
      const hiddenFixRows = document.querySelectorAll(".hidden-fix-row");
      hiddenFixRows.forEach((row) => {{
        row.hidden = !toggle.checked;
      }});
    }}

    dateRadios.forEach((radio) => {{
      radio.addEventListener("change", (e) => {{
        applySnapshot(parseInt(e.target.value));
      }});
    }});

    toggle.addEventListener("change", syncHiddenFixRows);
    syncHiddenFixRows();
  </script>
</body>
</html>
"""


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(INPUT_DIR.glob("*.pdf"), key=parse_uploaded_datetime)
    if not pdf_files:
      raise SystemExit("No PDF files found in input/")

    parsed_by_file: dict[str, ParsedPdf] = {}
    for path in pdf_files:
        try:
            parsed_by_file[path.name] = parse_pdf(path)
        except Exception as exc:
            print(f"[WARN] Failed to fully parse {path.name}: {exc}")

    # Единый список дат как в input/: если PDF не распарсился, используем
    # последнее доступное состояние цен, чтобы дата не выпадала из истории.
    snapshots: list[dict] = []
    last_known: ParsedPdf | None = None
    for path in pdf_files:
        parsed = parsed_by_file.get(path.name)
        if parsed is not None:
            last_known = parsed
        if last_known is None:
            continue
        snapshots.append(
            {
                "uploaded_label": parse_uploaded_label(path),
                "source_file": path.name,
                "sandwich": last_known.sandwich,
                "colors": last_known.colors,
            }
        )

    # В истории оставляем уникальные даты: если за одну дату есть несколько PDF,
    # берем последнее доступное состояние для этой даты.
    snapshots_by_label: dict[str, dict] = {}
    for snap in snapshots:
        snapshots_by_label[snap["uploaded_label"]] = snap
    snapshots = list(snapshots_by_label.values())

    if not snapshots:
        raise SystemExit("No suitable PDF data found for sandwich panels in input/")

    current_snapshot = snapshots[-1]
    previous_snapshot = snapshots[-2] if len(snapshots) > 1 else None
    current = ParsedPdf(
        pdf_path=Path(current_snapshot["source_file"]),
        uploaded_label=current_snapshot["uploaded_label"],
        sandwich=current_snapshot["sandwich"],
        colors=current_snapshot["colors"],
    )
    previous = (
        ParsedPdf(
            pdf_path=Path(previous_snapshot["source_file"]),
            uploaded_label=previous_snapshot["uploaded_label"],
            sandwich=previous_snapshot["sandwich"],
            colors=previous_snapshot["colors"],
        )
        if previous_snapshot
        else None
    )
    comparison = compare_prices(current, previous)
    price_history = build_price_history(snapshots)

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "current_file": current_snapshot["source_file"],
        "previous_file": previous_snapshot["source_file"] if previous_snapshot else None,
        "latest_uploaded_label": current_snapshot["uploaded_label"],
        "sandwich": current_snapshot["sandwich"],
        "colors": current_snapshot["colors"],
        "comparison": comparison,
        "price_history": price_history,
    }

    (DATA_DIR / "sandwich-panels.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (SITE_DIR / "sandwich-panels.html").write_text(
        generate_html(current, comparison, payload["price_history"]), encoding="utf-8",
    )
    print("Updated:")
    print(DATA_DIR / "sandwich-panels.json")
    print(SITE_DIR / "sandwich-panels.html")


if __name__ == "__main__":
    main()
