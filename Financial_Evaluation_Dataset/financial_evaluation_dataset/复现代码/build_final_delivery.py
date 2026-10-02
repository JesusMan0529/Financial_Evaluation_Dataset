"""Export readable CSV, portable original evidence and a local audit index."""
import collections
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import zipfile

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / 'delivery_v2'
FINAL = ROOT / '交付成品'
FILES = ['知识与规则', '实体抽取', '事件抽取', '关系抽取', '文本分类', '数值与财务字段', '因果与观点']
SOURCES = {'FinCorpus', 'CFLUE', 'FIRE-Bench', 'CFSC', 'FEED', 'FinCorpus.CN', 'CSRC', 'TigerBot-earning', 'TigerBot-research'}
LABELS = {'Corporate': '公司', 'Stock': '股票', 'Market': '市场对象', 'Economy': '经济概念',
          'EquityFreeze': '股权冻结', 'EquityRepurchase': '股份回购', 'EquityUnderweight': '股东减持',
          'EquityOverweight': '股东增持', 'EquityPledge': '股权质押', 'CompanyName': '公司名称',
          'HighestTradingPrice': '最高交易价', 'LowestTradingPrice': '最低交易价', 'RepurchasedShares': '回购股数',
          'RepurchaseAmount': '回购金额', 'EquityHolder': '持有人', 'TradedShares': '交易股数', 'StartDate': '开始日期',
          'EndDate': '结束日期', 'LaterHoldingShares': '事后持股数', 'PledgedShares': '本次质押股数',
          'Pledgee': '质权人', 'TotalHoldingShares': '总持股数', 'TotalHoldingRatio': '总持股比例',
          'TotalPledgedShares': '累计质押股数', 'ReleasedDate': '解除质押日期', 'AveragePrice': '均价',
          'FrozeShares': '冻结股数', 'LegalInstitution': '司法机构', 'UnfrozeDate': '解冻日期', 'ClosingDate': '完成日期'}


def lines(path):
    with path.open(encoding='utf-8-sig') as f:
        for index, line in enumerate(f, 1):
            if line.strip():
                yield index, json.loads(line)


def key(path, row):
    return path.replace('\\', '/') + '#' + str(row)


def answer_text(row):
    a, task = row['annotations'], row['task']
    if task == 'knowledge_rules':
        return a['answer_letters'] + '：' + '；'.join(a['options'][x] for x in a['answer_letters'])
    if task == 'entity':
        return '；'.join(x['text'] + '（' + LABELS[x['type']] + '）' for x in a)
    if task == 'relation':
        return '；'.join(x['subject'] + ' → ' + x['predicate'] + ' → ' + x['object'] for x in a)
    if task == 'event':
        return '\n'.join(LABELS[x['event_type']] + '：' + '；'.join(LABELS[v['role']] + '=' + v['text'] for v in x['arguments']) for x in a)
    if task == 'classification':
        return '；'.join(LABELS.get(x, x) for x in a)
    if task == 'numeric':
        return '\n'.join(f"{x['subject']}｜{x['period']}｜{x['field']}={x['value']}{x['unit']}｜会计口径：{x['consolidation_scope']}｜业务范围：{x['business_scope']}｜调整条件：{x['measurement_basis']}" for x in a)
    return '\n'.join('原因：' + x['cause']['text'] + '；结果：' + x['effect']['text'] if x['type'] == 'causal'
                     else '观点持有人：' + x['holder'] + '；对象：' + x['target'] + '；观点：' + x['claim']['text'] for x in a)


def original_records(path):
    if path.name.endswith('.jsonl.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                yield i, json.loads(line)
    elif path.suffix == '.zip':
        with zipfile.ZipFile(path) as z:
            rows = json.loads(z.read(path.name.removesuffix('.zip')))
        for i, (docid, obj) in enumerate(rows, 1):
            yield i, {'document_id': docid, 'record': obj}
    elif 'CFLUE' in path.parts or 'CFSC' in path.parts or 'FIRE-Bench' in path.parts:
        for i, row in enumerate(json.loads(path.read_text(encoding='utf-8')), 1):
            yield i, row
    else:
        yield from lines(path)


def main():
    for folder in ['数据', '原始出处', '检查记录', '复现代码', '来源说明']:
        (FINAL / folder).mkdir(parents=True, exist_ok=True)
    requests, source_for, counts = collections.defaultdict(set), {}, {}
    summary = []
    for name in FILES:
        total = 0
        dst = FINAL / '数据' / (name + '.jsonl')
        with dst.open('w', encoding='utf-8') as out, (dst.with_suffix('.csv')).open('w', encoding='utf-8-sig', newline='') as c:
            writer = csv.writer(c)
            writer.writerow(['数据编号', '任务', '题目或原文', '答案', '解析（仅知识题）', '来源', '来源网址', '原始出处键', '检查状态'])
            for _, row in lines(INPUT / (name + '.jsonl')):
                source = row['source_dataset']
                assert source in SOURCES
                refs = [row] + row.get('corroborating_release_records', [])
                if row.get('explanation_source'):
                    refs.append(row['explanation_source'])
                for ref in refs:
                    requests[ref['source_file']].add(ref['source_row'])
                    source_for[ref['source_file']] = ref['source_dataset']
                row['source_evidence_file'] = '原始出处/' + source + '.jsonl'
                row['source_evidence_key'] = key(row['source_file'], row['source_row'])
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
                readable = [row['id'], name, row['text'], answer_text(row),
                            row['annotations'].get('explanation', '') if row['task'] == 'knowledge_rules' else '',
                            source, row['source_url'], row['source_evidence_key'], '已完成程序检查；未认定为专业验收通过']
                writer.writerow(readable)
                if total < 3:
                    summary.append(readable)
                total += 1
        counts[name] = total
        print('export', name, total, flush=True)
    with (FINAL / '数据' / '先看样例.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['数据编号', '任务', '题目或原文', '答案', '解析（仅知识题）', '来源', '来源网址', '原始出处键', '检查状态'])
        w.writerows(summary)
    db = sqlite3.connect(ROOT / 'quality_work' / 'source_reference.sqlite')
    db.execute('DROP TABLE IF EXISTS evidence')
    db.execute('CREATE TABLE evidence (key TEXT PRIMARY KEY, raw TEXT NOT NULL)')
    streams, provenance = {}, []
    try:
        for file, wanted in requests.items():
            path, source = ROOT / file, source_for[file]
            if source not in streams:
                streams[source] = (FINAL / '原始出处' / (source + '.jsonl')).open('w', encoding='utf-8')
            found = set()
            for index, original in original_records(path):
                if index not in wanted:
                    continue
                found.add(index)
                raw = json.dumps(original, ensure_ascii=False, sort_keys=True)
                obj = {'evidence_key': key(file, index), 'source_file': file, 'source_row': index,
                       'source_record_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'source_record': original}
                streams[source].write(json.dumps(obj, ensure_ascii=False) + '\n')
                db.execute('INSERT INTO evidence VALUES (?,?)', (obj['evidence_key'], raw))
                if len(found) == len(wanted):
                    break
            assert found == wanted, (file, len(wanted - found))
            provenance.append({'file': file, 'selected_original_records': len(found), 'full_download_bytes': path.stat().st_size,
                               'full_download_sha256': hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()})
            db.commit()
            print('evidence', file, len(found), flush=True)
    finally:
        for f in streams.values():
            f.close()
        db.close()
    (FINAL / '检查记录' / '原始文件与证据数量.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
    (FINAL / '检查记录' / '交付数量.json').write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding='utf-8')
    for name in ['知识题处理统计.json', '文本处理统计.json']:
        shutil.copy2(INPUT / name, FINAL / '检查记录' / name)
    for path in ROOT.glob('download_manifest*.json'):
        shutil.copy2(path, FINAL / '来源说明' / path.name)
    shutil.copy2(ROOT / 'exclusion_registry.json', FINAL / '来源说明' / '旧项目排除清单.json')
    for name in ['build_candidates.py', 'audit_content.py', 'prepare_knowledge.py', 'prepare_text.py', 'build_final_delivery.py',
                 'validate_final_delivery.py', 'test_processing.py', 'test_delivery_processing.py', 'download_sources.py',
                 'download_more.py', 'download_knowledge_extra.py', 'download_cflue.py', 'resume_downloads.py', 'collect_csrc.py']:
        path = ROOT / name
        if path.exists():
            shutil.copy2(path, FINAL / '复现代码' / name)
    for path in (ROOT / 'raw').rglob('*'):
        if path.is_file() and path.name.lower() in {'license', 'license.txt', 'license.md', 'readme.md'}:
            dest = FINAL / '来源说明' / path.relative_to(ROOT / 'raw')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)


if __name__ == '__main__':
    main()
