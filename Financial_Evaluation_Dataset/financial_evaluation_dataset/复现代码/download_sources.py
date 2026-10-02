"""Download public, separately identified new sources; retain hashes and provenance."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parent


def download(item):
    name, url, relative = item
    path = ROOT / 'raw' / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    result = {'source': name, 'url': url, 'file': str(path.relative_to(ROOT))}
    try:
        if not path.exists():
            part = path.with_suffix(path.suffix + '.part')
            headers = {'User-Agent': 'AcademicDataCollection/1.0'}
            if url.startswith('https://www.csrc.gov.cn/'):
                headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.csrc.gov.cn/'}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as response, part.open('wb') as stream:
                while block := response.read(1024 * 1024):
                    stream.write(block)
            part.replace(path)
        result.update(bytes=path.stat().st_size, sha256=hashlib.file_digest(path.open('rb'), 'sha256').hexdigest(), status='downloaded')
    except Exception as exc:
        result.update(status='failed', error=str(exc))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


if __name__ == '__main__':
    feed_sha = json.loads((ROOT / 'evidence/feed.json').read_text(encoding='utf-8'))['sha']
    oee_sha = json.loads((ROOT / 'evidence/oee_tree.txt').read_text(encoding='utf-8'))['sha']
    fin_sha = json.loads((ROOT / 'evidence/fincorpus.json').read_text(encoding='utf-8'))['sha']
    items = [('FinCorpus-exam', f'https://huggingface.co/datasets/Duxiaoman-DI/FinCorpus/resolve/{fin_sha}/data/fin_exam.jsonl.gz', 'FinCorpus/fin_exam.jsonl.gz')]
    for split in ['train', 'dev', 'test']:
        items.append(('FEED', f'https://raw.githubusercontent.com/seukgcode/FEED/{feed_sha}/{split}.json.zip', f'FEED/{split}.json.zip'))
        items.append(('OEE-CFC', f'https://raw.githubusercontent.com/view98/OEE-CFC/{oee_sha}/data/OEE_CFC/{split}.jsonlines', f'OEE-CFC/{split}.jsonlines'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(download, items))
    (ROOT / 'download_manifest.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
