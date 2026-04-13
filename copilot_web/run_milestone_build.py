import os, json, openpyxl

XLSX_PATH = r'C:\Users\KennethManjo\Downloads\SixTerminal-main\SixTerminal-main\Milestone Map.xlsx'
PROJECTS_DIR = r'C:\Users\KennethManjo\Downloads\SixTerminal-main\SixTerminal-main\copilot_web\projects'

SLUG_MAP = {
    'Anaheim, CA': 'anaheim_ca', 'Anna, TX': 'anna_tx', 'Aventura, FL': 'aventura_fl',
    'Colorado Springs, CO': 'colorado_springs_co', 'Davenport, FL': 'davenport_fl',
    'Delray, FL': 'delray_fl', 'Fairfax, VA': 'fairfax_va', 'Frisco, TX': 'frisco_tx',
    'Meridian, ID': 'meridian_id', 'Mesa, AZ': 'mesa_az', 'Mt Juliet, TN': 'mt_juliet_tn',
    'San Diego, CA': 'san_diego_ca', 'Selma, NC': 'selma_nc', 'Willis, TX': 'willis_tx',
}

def is_na(v):
    return v is None or str(v).strip().upper() == 'N/A'

wb = openpyxl.load_workbook(XLSX_PATH, read_only=True)
ws = wb.active
by_project = {}

for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i == 0:
        continue
    proj_type = str(row[0]).strip() if row[0] else ''
    proj_name = str(row[1]).strip() if row[1] else ''
    std_name  = str(row[2]).strip() if row[2] else ''
    act_id    = row[3]
    sort_ord  = row[4]
    act_name  = str(row[5]).strip() if row[5] else ''

    if not proj_name or not std_name:
        continue
    if is_na(act_id) and is_na(act_name):
        continue

    if proj_name not in by_project:
        by_project[proj_name] = {'type': proj_type, 'milestones': []}

    by_project[proj_name]['milestones'].append({
        'standardized_name': std_name,
        'activity_id': None if is_na(act_id) else act_id,
        'activity_name': None if is_na(act_name) else act_name,
        'sort': sort_ord,
    })

written = 0
for proj_name, data in by_project.items():
    slug = SLUG_MAP.get(proj_name)
    if not slug:
        print(f'SKIPPED (no bucket): {proj_name}')
        continue
    out = os.path.join(PROJECTS_DIR, slug, 'milestone_map.json')
    payload = {
        'project': proj_name,
        'type': data['type'],
        'milestones': sorted(data['milestones'], key=lambda x: x['sort'] or 99)
    }
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    count = len(data['milestones'])
    print(f'OK  {slug}: {count} milestones')
    written += 1

print(f'\nDone. {written} project files written.')
