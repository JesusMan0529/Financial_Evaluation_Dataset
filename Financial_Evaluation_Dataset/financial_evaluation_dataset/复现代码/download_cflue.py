"""Download only CFLUE knowledge splits; application mixtures are excluded."""
import concurrent.futures
import json
from download_sources import ROOT, download


def main():
    meta = json.loads((ROOT / 'evidence/cflue_hf.json').read_text(encoding='utf-8'))
    items = [('CFLUE-knowledge', f'https://huggingface.co/datasets/DianJin/CFLUE/resolve/{meta["sha"]}/{name}', f'CFLUE/{name}')
             for name in ['train.json', 'val.json', 'test.json']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(download, items))
    (ROOT / 'download_manifest_cflue_knowledge.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
