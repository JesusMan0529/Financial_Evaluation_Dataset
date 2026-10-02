"""Read the same public listing API used by CSRC's official disclosure page."""
import hashlib
import json
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'raw/CSRC'
DEST.mkdir(parents=True, exist_ok=True)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ['script', 'style']:
            self.skip += 1
        if tag in ['p', 'br', 'tr'] and not self.skip:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ['script', 'style']:
            self.skip = max(0, self.skip - 1)
        if tag in ['p', 'tr'] and not self.skip:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain(html):
    parser = PlainText()
    parser.feed(html)
    return '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())


if __name__ == '__main__':
    records, receipts = {}, []
    page = 1
    actual_page_size = None
    while True:
        url = f'https://www.csrc.gov.cn/searchList/28de6b87eda140cb93de4dd10d11867d?_isAgg=true&_isJson=true&_pageSize=50&_template=index&_rangeTimeGte=&_channelName=&page={page}'
        path = DEST / f'page_{page:03d}.json'
        if path.exists():
            content = path.read_bytes()
        else:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.csrc.gov.cn/'})
            with urllib.request.urlopen(req, timeout=40) as response:
                content = response.read()
            path.write_bytes(content)
            time.sleep(0.2)
        data = json.loads(content)['data']
        if actual_page_size is None:
            actual_page_size = len(data['results'])
        receipts.append({'url': url, 'file': str(path.relative_to(ROOT)), 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
        for item in data['results']:
            date = item['publishedTimeStr'][:10]
            if date > '2026-10-01':
                continue
            text = plain(item.get('contentHtml', ''))
            if len(text) < 100:
                continue
            link = item['url']
            if link.startswith('//'):
                link = 'https:' + link
            records[item['manuscriptId']] = {'document_id': item['manuscriptId'], 'title': item['title'], 'published_at': date, 'source_url': link, 'text': text, 'source_file': str(path.relative_to(ROOT)), 'source_category': '监管处罚与问询文件', 'subtype': '行政处罚决定书'}
        if page % 5 == 0:
            print(f'pages={page}, documents={len(records)}, official_total={data["total"]}', flush=True)
        if page * actual_page_size >= data['total'] or not data['results']:
            break
        page += 1
    with (DEST / 'documents.jsonl').open('w', encoding='utf-8') as stream:
        for row in records.values():
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    (ROOT / 'download_manifest_csrc.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Completed: {len(records)} documents, {page} pages', flush=True)
