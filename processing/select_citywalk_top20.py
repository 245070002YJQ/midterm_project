
from pathlib import Path
from collections import OrderedDict, defaultdict
from openpyxl import load_workbook, Workbook
import unicodedata
import math
import re

# ==========================================
# 1. FILE PATHS
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR / "country_citywalk_cleaned4.xlsx"
OUTPUT_FILE = BASE_DIR / "citywalk_top20.xlsx"

TOP_N = 20

SHEET1 = "CityWalk核心景点名录"
SHEET2 = "周边地铁出入口与公交配套表"

if not INPUT_FILE.exists():
    raise FileNotFoundError(
        f"Input file not found: {INPUT_FILE}"
    )

print("Reading Excel...")

wb_in = load_workbook(
    INPUT_FILE,
    read_only=True,
    data_only=True
)

ws1 = wb_in[SHEET1]
ws2 = wb_in[SHEET2]


# ==========================================
# 2. FIND COLUMN BY NAME
# ==========================================

def find_col(headers, name):

    cleaned = [
        str(x).strip() if x is not None else ""
        for x in headers
    ]

    if name not in cleaned:
        raise ValueError(
            f"Column not found: {name}"
        )

    return cleaned.index(name)


# ==========================================
# 3. EXTRACT CORE PLACE NAME
# ==========================================

# Remove these suffixes from the END
# of the place name, not from the middle.

NAME_SUFFIXES = sorted(
    [
        "历史文化街区",
        "特色商业步行街",
        "特色商业街区",
        "商业文化街区",
        "文化商业街区",
        "商业步行街",
        "传统风貌区",
        "商业街区",
        "历史街区",
        "文化街区",
        "文旅街区",
        "特色街区",
        "旅游景区",
        "商业街",
        "步行街",
        "风景区",
        "景区",
        "街区",
        "商圈"
    ],
    key=len,
    reverse=True
)

# Generic names should not be
# incorrectly combined.
GENERIC_NAMES = {
    "商业",
    "文化",
    "特色",
    "历史",
    "旅游",
    "文旅",
    "传统",
    "商业文化"
}


def normalize_name(name):

    text = unicodedata.normalize(
        "NFKC", str(name)
    ).strip()

    # Remove whitespace
    text = re.sub(r"\s+", "", text)

    original_text = text

    # Example:
    # 春熙路-太古里商圈 -> 春熙路
    text = re.split(
        r"[-—–－]",
        text,
        maxsplit=1
    )[0]

    # Remove trailing bracket information
    # Example:
    # 春熙路步行街(南门) -> 春熙路步行街
    while True:

        new_text = re.sub(
            r"\([^()]*\)$",
            "",
            text
        )

        if new_text == text:
            break

        text = new_text

    # Remove suffixes repeatedly
    # Example:
    # 宽窄巷子步行街 -> 宽窄巷子
    # 宽窄巷子景区   -> 宽窄巷子

    changed = True

    while changed:

        changed = False

        for suffix in NAME_SUFFIXES:

            if text.endswith(suffix):

                new_text = text[:-len(suffix)]

                # Avoid an empty or generic name
                if (
                    len(new_text) >= 2
                    and new_text not in GENERIC_NAMES
                ):

                    text = new_text
                    changed = True
                    break

    # Fallback for overly generic results
    if (
        len(text) < 2
        or text in GENERIC_NAMES
    ):
        text = original_text

    return text.casefold()


# ==========================================
# 4. READ SHEET 1
# ==========================================

rows1 = ws1.iter_rows(values_only=True)

headers1 = list(next(rows1))

CITY_COL = find_col(headers1, "城市")
ID_COL = find_col(headers1, "景点统一编码")
NAME_COL = find_col(headers1, "CityWalk景点名称")
SCORE_COL = find_col(headers1, "score_numeric")

POSITION_COL = (
    find_col(headers1, "city_position")
    if "city_position" in headers1
    else None
)

city_groups = OrderedDict()

for row_number, row in enumerate(
    rows1,
    start=2
):

    if all(v is None for v in row):
        continue

    city = str(row[CITY_COL] or "").strip()
    place_id = str(row[ID_COL] or "").strip()
    name = str(row[NAME_COL] or "").strip()

    if not city or not place_id or not name:
        continue

    try:
        score = float(row[SCORE_COL])

    except (ValueError, TypeError):
        continue

    if not math.isfinite(score):
        continue

    core_name = normalize_name(name)

    if city not in city_groups:
        city_groups[city] = []

    city_groups[city].append({
        "row": list(row),
        "city": city,
        "id": place_id,
        "name": name,
        "core_name": core_name,
        "score": score,
        "original_row": row_number
    })


# ==========================================
# 5. SORT AND REMOVE DUPLICATE PLACES
# ==========================================

selected_places = []
removed_duplicates = []

for city, records in city_groups.items():

    # Sort by:
    # 1. Higher score first
    # 2. Same score: earlier Excel row first

    records.sort(
        key=lambda item: (
            -item["score"],
            item["original_row"]
        )
    )

    seen_names = {}
    unique_records = []

    for item in records:

        key = item["core_name"]

        # Same CORE name within one city
        if key in seen_names:

            winner = seen_names[key]

            removed_duplicates.append({
                "city": city,
                "core_name": key,
                "kept_name": winner["name"],
                "kept_score": winner["score"],
                "removed_name": item["name"],
                "removed_score": item["score"]
            })

            continue

        seen_names[key] = item
        unique_records.append(item)

    # Select first 20 unique places
    top_records = unique_records[:TOP_N]

    for position, item in enumerate(
        top_records,
        start=1
    ):

        output_row = list(item["row"])

        # Reset city ranking to 1-20
        if POSITION_COL is not None:
            output_row[POSITION_COL] = position

        # Add core name for checking
        output_row.append(item["core_name"])

        item["output_row"] = output_row

        selected_places.append(item)

    print(
        f"{city}: "
        f"{len(records)} original, "
        f"{len(unique_records)} unique, "
        f"{len(top_records)} selected"
    )


# ==========================================
# 6. GET SELECTED PLACE IDs
# ==========================================

selected_ids = set()

for item in selected_places:

    if item["id"] in selected_ids:
        raise ValueError(
            f"Duplicate place ID: {item['id']}"
        )

    selected_ids.add(item["id"])


# ==========================================
# 7. MATCH SHEET 2
# ==========================================

rows2 = ws2.iter_rows(values_only=True)

headers2 = list(next(rows2))

LINK_COL = find_col(
    headers2,
    "关联景点编码"
)

transport_groups = defaultdict(list)

for row in rows2:

    if all(v is None for v in row):
        continue

    linked_id = str(
        row[LINK_COL] or ""
    ).strip()

    # Keep ALL transport rows for
    # the winning place IDs
    if linked_id in selected_ids:

        transport_groups[linked_id].append(row)


# ==========================================
# 8. CREATE OUTPUT EXCEL
# ==========================================

wb_out = Workbook(write_only=True)

out1 = wb_out.create_sheet(SHEET1)
out2 = wb_out.create_sheet(SHEET2)

# Add the core-name checking column
out1.append(
    headers1 + ["name_match_key"]
)

out2.append(headers2)

# Sheet 1:
# TOP 20 unique places per city
for item in selected_places:

    out1.append(item["output_row"])

# Sheet 2:
# ALL transport records linked to
# the selected original place IDs

matched_count = 0

for item in selected_places:

    place_id = item["id"]

    for transport_row in transport_groups[place_id]:

        out2.append(transport_row)
        matched_count += 1


# ==========================================
# 9. SAVE OUTPUT
# ==========================================

wb_out.save(OUTPUT_FILE)
wb_in.close()


# ==========================================
# 10. SUMMARY
# ==========================================

no_transport = [
    item
    for item in selected_places
    if not transport_groups[item["id"]]
]

print()
print("========== TOP 20 SUMMARY ==========")

print("Cities:", len(city_groups))
print("Selected places:", len(selected_places))
print("Duplicate names removed:", len(removed_duplicates))
print("Matched transport rows:", matched_count)
print("Places without transport:", len(no_transport))

print()
print("========== DUPLICATE EXAMPLES ==========")

for item in removed_duplicates[:20]:

    print(
        item["city"],
        "| Core:", item["core_name"],
        "| Kept:", item["kept_name"],
        "| Removed:", item["removed_name"]
    )

print()
print("Sheet 1: TOP 20 unique core names")
print("Sheet 2: All corresponding metro/bus rows")
print("Output:", OUTPUT_FILE)
print("Completed successfully!")
