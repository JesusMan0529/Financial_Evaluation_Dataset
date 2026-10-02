"""Check the unzipped delivery using standard Python; no models or packages required."""
import hashlib
import json
from pathlib import Path


def main():
    folder = Path(__file__).resolve().parent
    root = folder.parent if folder.name == '复现代码' else folder / '交付成品'
    manifest = json.loads((root / '检查记录/文件校验值.json').read_text(encoding='utf-8'))
    for entry in manifest:
        path = (root / entry['file']).resolve()
        assert path.is_relative_to(root.resolve()), '非法路径'
        assert path.is_file(), '缺文件：' + entry['file']
        assert path.stat().st_size == entry['bytes'], '大小变化：' + entry['file']
        with path.open('rb') as f:
            assert hashlib.file_digest(f, 'sha256').hexdigest() == entry['sha256'], '内容变化：' + entry['file']
    report = json.loads((root / '检查记录/全量检查结果.json').read_text(encoding='utf-8'))
    assert report['错误数'] == 0
    assert report['知识题唯一问题数'] == 203870
    assert report['文本任务去重后条数'] == 35803
    print('检查通过：所有文件齐全，校验值一致；知识203870条，文本35803条。')
    print('这检查的是交付包完整性；不代表专业准确率已验收。')


if __name__ == '__main__':
    main()
