import concurrent.futures
import json
import urllib.parse
from download_sources import download, ROOT

items = []
tree = json.loads((ROOT / 'evidence/e2cnn_tree.json').read_text(encoding='utf-8'))
for entry in tree['tree']:
    path = entry['path']
    if entry['type'] == 'blob' and (path.startswith(('entity_data/FinCorpus.CN/', 'relation_data/FinCorpus.CN/')) or path in ['readme.md', 'LICENSE']):
        items.append(('FinCorpus.CN', f"https://raw.githubusercontent.com/CGCL-codes/E-2CNN/{tree['sha']}/{path}", 'FinCorpus.CN/' + path))
for name in ['earning', 'research', 'law']:
    meta = json.loads((ROOT / f'evidence/tiger_{name}.json').read_text(encoding='utf-8'))
    repo = f'TigerResearch/tigerbot-{name}-plugin'
    for file in meta['siblings']:
        path = file['rfilename']
        if path.endswith(('.json', '.md')):
            items.append((repo, f"https://huggingface.co/datasets/{repo}/resolve/{meta['sha']}/{path}", f'TigerBot-{name}/' + path))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(download, items))
(ROOT / 'download_manifest_more.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
