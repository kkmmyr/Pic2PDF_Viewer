import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open(r'd:/61.tool/Pic2PDF_Viewer/experiments/manga_ai_validation.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

for i, cell in enumerate(nb['cells']):
    if i not in [16, 23, 24, 27]:
        continue
    print(f'\n=== CELL {i} raw outputs ===')
    for j, o in enumerate(cell.get('outputs', [])):
        otype = o.get('output_type')
        t = o.get('text', '')
        if isinstance(t, list): t = ''.join(t)
        data = o.get('data', {})
        keys = list(data.keys())
        print(f'  [{j}] type={otype} text_len={len(t)} data_keys={keys}')
        if t.strip() and 'Image' not in t:
            print(f'    TEXT: {repr(t[:300])}')
