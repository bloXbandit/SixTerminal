"""
build_milestone_map.py
Run once locally to parse Milestone Map.xlsx and write milestone_map.json
into each project's bucket folder.

Usage:
    python copilot_web/build_milestone_map.py
"""
import os
import json
import openpyxl

XLSX_PATH = os.path.join(os.path.dirname(__file__), "..", "Milestone Map.xlsx")
PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")

SLUG_MAP = {
    "Anaheim, CA":        "anaheim_ca",
    "Anna, TX":           "anna_tx",
    "Aventura, FL":       "aventura_fl",
    "Boggy Creek, FL":    "boggy_creek_fl",
    "Canoga Park, CA":    "canoga_park_ca",
    "Cocoa, FL":          "cocoa_fl",
    "Colorado Springs, CO": "colorado_springs_co",
    "Dallas, TX":         "dallas_tx",
    "Davenport, FL":      "davenport_fl",
    "Delray, FL":         "delray_fl",
    "Fairfax, VA":        "fairfax_va",
    "Four Corners, FL":   "four_corners_fl",
    "Frisco, TX":         "frisco_tx",
    "Glendale, CA":       "glendale_ca",
    "Meridian, ID":       "meridian_id",
    "Mesa, AZ":           "mesa_az",
    "Mountain View, CA":  "mountain_view_ca",
    "Mt Juliet, TN":      "mt_juliet_tn",
    "Ocala, FL":          "ocala_fl",
    "Ontario, CA":        "ontario_ca",
    "Playa Vista, CA":    "playa_vista_ca",
    "Riverview, FL":      "riverview_fl",
    "San Diego, CA":      "san_diego_ca",
    "Selma, NC":          "selma_nc",
    "Willis, TX":         "willis_tx",
}


def is_na(val):
    if val is None:
        return True
    return str(val).strip().upper() == "N/A"


def build():
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
    ws = wb.active

    by_project = {}

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # skip header

        proj_type  = str(row[0]).strip() if row[0] else ""
        proj_name  = str(row[1]).strip() if row[1] else ""
        std_name   = str(row[2]).strip() if row[2] else ""
        activity_id = row[3]
        sort_order  = row[4]
        activity_name = str(row[5]).strip() if row[5] else ""

        if not proj_name or not std_name:
            continue

        # Skip rows where both activity_id AND activity_name are N/A
        if is_na(activity_id) and is_na(activity_name):
            continue

        if proj_name not in by_project:
            by_project[proj_name] = {"type": proj_type, "milestones": []}

        by_project[proj_name]["milestones"].append({
            "standardized_name": std_name,
            "activity_id": None if is_na(activity_id) else activity_id,
            "activity_name": None if is_na(activity_name) else activity_name,
            "sort": sort_order,
        })

    written = []
    skipped = []

    for proj_name, data in by_project.items():
        slug = SLUG_MAP.get(proj_name)
        if not slug:
            skipped.append(proj_name)
            continue

        project_dir = os.path.join(PROJECTS_DIR, slug)
        os.makedirs(project_dir, exist_ok=True)

        out_path = os.path.join(project_dir, "milestone_map.json")
        payload = {
            "project": proj_name,
            "type": data["type"],
            "milestones": sorted(data["milestones"], key=lambda x: x["sort"] or 99),
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        written.append(f"  {slug}: {len(data['milestones'])} milestones → {out_path}")

    print("=== Milestone Map Build Complete ===")
    print(f"Written ({len(written)}):")
    for w in written:
        print(w)
    if skipped:
        print(f"\nSkipped - no bucket folder mapped ({len(skipped)}):")
        for s in skipped:
            print(f"  {s}")


if __name__ == "__main__":
    build()
