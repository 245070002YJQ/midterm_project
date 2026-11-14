
from pathlib import Path
from collections import Counter
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
import math

# ==========================================
# 1. Input and output paths
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR / "country_citywalk_data.xlsx"
OUTPUT_FILE = BASE_DIR / "country_citywalk_cleaned4.xlsx"

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"File not found: {INPUT_FILE}"
    )

print("Reading original Excel...")

# ==========================================
# 2. Open workbook
# ==========================================

wb = load_workbook(INPUT_FILE)

SHEET_NAME = "CityWalk核心景点名录"
ws = wb[SHEET_NAME]

# Sheet 2 remains unchanged

headers = {
    str(cell.value).strip(): cell.column
    for cell in ws[1]
    if cell.value is not None
}

required_columns = [
    "景点统一编码",
    "城市",
    "CityWalk景点名称",
    "检索分类标签",
    "详细业态类型",
    "综合热度/评分"
]

for column in required_columns:
    if column not in headers:
        raise ValueError(
            f"Missing column: {column}"
        )

ID_COL = headers["景点统一编码"]
CITY_COL = headers["城市"]
NAME_COL = headers["CityWalk景点名称"]
CATEGORY_COL = headers["检索分类标签"]
TYPE_COL = headers["详细业态类型"]
SCORE_COL = headers["综合热度/评分"]

ORIGINAL_COLS = ws.max_column

# ==========================================
# 3. EXCLUDE keywords
# These words have FIRST priority.
# Check name, category and business type.
# ==========================================

EXCLUDE_KEYWORDS = (
    "风景名胜",
    "体育",
    "企业",
    "公司",
    "公园",
    "博物馆",
    "寺庙",
    "寺院",
    "道观",
    "馆",
    "宫",
    "商场",
    "购物中心",
    "商城",
    "百货",
    "超市",
    "桥",
    "室内",
    "游乐场",
    "游乐园",
    "动物园",
    "植物园",
    "水族馆",
    "写字楼",
    "办公楼",
    "酒店",
    "宾馆"
)

# ==========================================
# 4. KEEP keywords
# At least one keyword must exist in
# name, category or business type.
# ==========================================

KEEP_KEYWORDS = (
    "历史文化街区",
    "商业文化街区",
    "商业步行街",
    "商业街区",
    "历史街区",
    "特色街区",
    "文化街区",
    "文旅街区",
    "步行街",
    "商业街",
    "老街",
    "古街",
    "街区",
    "文创",
    "文化创意",
    "创意街区",
    "创意园",
    "传统风貌区"
)

# ==========================================
# 5. Clean scores
# ==========================================

def clean_score(value):

    if value is None or isinstance(value, bool):
        return None

    text = str(value).strip()

    missing_values = {
        "",
        "[]",
        "-",
        "none",
        "null",
        "nan",
        "n/a",
        "未知",
        "暂无",
        "无"
    }

    if text.lower() in missing_values:
        return None

    try:
        score = float(text)

    except (ValueError, TypeError):
        return None

    if not math.isfinite(score):
        return None

    # Only accept rating numbers from 0 to 5
    if not (0 < score <= 5):
        return None

    return score


# ==========================================
# 6. Check all THREE text columns
# ==========================================

def check_place(name, category, business_type):

    fields = [
        str(name or "").strip(),
        str(category or "").strip(),
        str(business_type or "").strip()
    ]

    # STEP 1:
    # Any excluded word -> remove whole row
    for field in fields:
        for word in EXCLUDE_KEYWORDS:
            if word in field:
                return False, "Excluded"

    # STEP 2:
    # Must contain at least one KEEP word
    for field in fields:
        for word in KEEP_KEYWORDS:
            if word in field:
                return True, "Kept"

    # STEP 3:
    # No KEEP keyword -> remove whole row
    return False, "No_Keep_Keyword"


# ==========================================
# 7. Read and clean Sheet 1
# ==========================================

city_groups = {}
statistics = Counter()
city_statistics = {}

for row_number, row in enumerate(
    ws.iter_rows(min_row=2, values_only=True),
    start=2
):

    if all(value is None for value in row):
        continue

    statistics["original"] += 1

    city = str(
        row[CITY_COL - 1] or ""
    ).strip()

    place_id = str(
        row[ID_COL - 1] or ""
    ).strip()

    name = str(
        row[NAME_COL - 1] or ""
    ).strip()

    category = str(
        row[CATEGORY_COL - 1] or ""
    ).strip()

    business_type = str(
        row[TYPE_COL - 1] or ""
    ).strip()

    # Register the city
    if city and city not in city_statistics:
        city_statistics[city] = Counter()

    if city:
        city_statistics[city]["original"] += 1

    # STEP A: Remove missing essential fields
    if not city or not place_id or not name:
        statistics["missing_identity"] += 1
        continue

    # STEP B: Remove invalid or missing scores
    score = clean_score(
        row[SCORE_COL - 1]
    )

    if score is None:
        statistics["invalid_score"] += 1
        city_statistics[city]["invalid_score"] += 1
        continue

    # STEP C: Check 3 fields for keywords
    keep, reason = check_place(
        name,
        category,
        business_type
    )

    if not keep:

        statistics[reason] += 1
        city_statistics[city][reason] += 1

        continue

    # STEP D: Keep qualified record
    record = {
        "values": list(row[:ORIGINAL_COLS]),
        "city": city,
        "place_id": place_id,
        "score": score,
        "original_row": row_number
    }

    if city not in city_groups:
        city_groups[city] = []

    city_groups[city].append(record)

    statistics["kept"] += 1
    city_statistics[city]["kept"] += 1


# ==========================================
# 8. Sort each city independently
# ==========================================

cleaned_records = []

for city, records in city_groups.items():

    records.sort(
        key=lambda item: (
            -item["score"],
            item["place_id"],
            item["original_row"]
        )
    )

    # Continuous position from 1 to N
    for position, item in enumerate(
        records,
        start=1
    ):

        item["city_position"] = position

        cleaned_records.append(item)


# ==========================================
# 9. Write cleaned Sheet 1
# ==========================================

# Delete Sheet 1 old data rows
# Original source file is not modified
if ws.max_row > 1:
    ws.delete_rows(2, ws.max_row - 1)

SCORE_NEW_COL = ORIGINAL_COLS + 1
POSITION_COL = ORIGINAL_COLS + 2

ws.cell(
    row=1,
    column=SCORE_NEW_COL,
    value="score_numeric"
)

ws.cell(
    row=1,
    column=POSITION_COL,
    value="city_position"
)

for item in cleaned_records:

    ws.append(
        item["values"] + [
            item["score"],
            item["city_position"]
        ]
    )

# ==========================================
# 10. Format Excel
# ==========================================

ws.freeze_panes = "A2"

last_col = get_column_letter(
    POSITION_COL
)

ws.auto_filter.ref = (
    f"A1:{last_col}{ws.max_row}"
)

for row_number in range(2, ws.max_row + 1):
    ws.cell(
        row_number,
        SCORE_NEW_COL
    ).number_format = "0.0"

ws.column_dimensions[
    get_column_letter(SCORE_NEW_COL)
].width = 18

ws.column_dimensions[
    get_column_letter(POSITION_COL)
].width = 18

# ==========================================
# 11. Save workbook
# ==========================================

wb.save(OUTPUT_FILE)

# ==========================================
# 12. Print cleaning report
# ==========================================

print()
print("========== Cleaning Summary ==========")

print("Original:", statistics["original"])
print("Removed missing identity:", statistics["missing_identity"])
print("Removed invalid scores:", statistics["invalid_score"])
print("Removed excluded keywords:", statistics["Excluded"])
print("Removed no keep keyword:", statistics["No_Keep_Keyword"])
print("Final kept:", statistics["kept"])

print()
print("========== 15 Cities ==========")

for city, city_stat in city_statistics.items():

    print(
        f"{city}: "
        f"original={city_stat['original']}, "
        f"removed_score={city_stat['invalid_score']}, "
        f"removed_keywords={city_stat['Excluded']}, "
        f"final={city_stat['kept']}"
    )

print()
print("Sheet 1: Cleaned")
print("Sheet 2: Unchanged")
print("Saved:", OUTPUT_FILE)
print("Cleaning completed!")
