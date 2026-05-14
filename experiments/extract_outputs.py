import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open(r'd:/61.tool/Pic2PDF_Viewer/experiments/manga_ai_validation.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

for i, cell in enumerate(nb['cells']):
    for o in cell.get('outputs', []):
        t = o.get('text', '')
        if isinstance(t, list):
            t = ''.join(t)
        if not t.strip():
            continue
        src = ''.join(cell.get('source', []))[:60]
        print(f'=== CELL {i} | {src[:55]} ===')
        print(t[:800])
        print()
