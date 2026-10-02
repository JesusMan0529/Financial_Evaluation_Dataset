"""Download separately released financial exams at fixed revisions."""
import concurrent.futures
import json
import urllib.parse
from download_sources import ROOT, download


def main():
    fire = json.loads((ROOT / 'evidence/FIRE_tree.json').read_text(encoding='utf-8'))['sha']
    iq = json.loads((ROOT / 'evidence/FinanceIQ_meta.json').read_text(encoding='utf-8'))
    items = [('FIRE-Bench', f'https://raw.githubusercontent.com/DXM-AGI/FIRE-Bench/{fire}/{name}', f'FIRE-Bench/{name}')
             for name in ['dataset/FIRE/FIRE.json', 'README.md', 'LICENSE']]
    for item in iq['siblings']:
        name = item['rfilename']
        if name.endswith('.csv') or name == 'README.md':
            items.append(('FinanceIQ', f'https://huggingface.co/datasets/Duxiaoman-DI/FinanceIQ/resolve/{iq["sha"]}/{urllib.parse.quote(name)}', f'FinanceIQ/{name}'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(download, items))
    (ROOT / 'download_manifest_knowledge_extra.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
