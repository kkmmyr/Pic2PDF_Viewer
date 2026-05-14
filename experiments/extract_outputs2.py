import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open(r'd:/61.tool/Pic2PDF_Viewer/experiments/manga_ai_validation.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

TARGET_CELLS = [16, 23, 24, 27]  # T3, T5-describe, T5-identify, free

for i, cell in enumerate(nb['cells']):
    if i not in TARGET_CELLS:
        continue
    src = ''.join(cell.get('source', []))[:80]
    print(f'\n=== CELL {i} ===')
    print(src)
    print('--- outputs ---')
    for o in cell.get('outputs', []):
        otype = o.get('output_type', '')
        # stream
        t = o.get('text', '')
        if isinstance(t, list): t = ''.join(t)
        # execute_result
        data = o.get('data', {})
        txt = data.get('text/plain', '')
        if isinstance(txt, list): txt = ''.join(txt)
        combined = t or txt
        if combined.strip():
            print(f'[{otype}]')
            print(combined[:2000])
