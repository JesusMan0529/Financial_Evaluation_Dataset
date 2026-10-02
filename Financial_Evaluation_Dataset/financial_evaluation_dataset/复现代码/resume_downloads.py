"""Restore successful pinned downloads only; do not silently adopt reserve failures."""
import json
from download_sources import ROOT, download


def main():
    seen = set()
    results = []
    for manifest in sorted(ROOT.glob('download_manifest*.json')):
        for item in json.loads(manifest.read_text(encoding='utf-8')):
            if not item.get('sha256') or item['file'] in seen:
                continue
            seen.add(item['file'])
            relative = item['file'].replace('\\', '/')
            result = download((item.get('source', 'CSRC'), item['url'], relative.removeprefix('raw/')))
            result['matches_original_hash'] = result.get('sha256') == item['sha256']
            results.append(result)
    (ROOT / 'restore_report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    if any(not row['matches_original_hash'] for row in results):
        raise SystemExit('Some files failed or differ from the original hashes; see restore_report.json.')


if __name__ == '__main__':
    main()
