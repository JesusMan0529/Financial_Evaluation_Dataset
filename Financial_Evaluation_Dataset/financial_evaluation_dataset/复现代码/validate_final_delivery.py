"""Check every delivered row against its original publisher record."""
import ast
import collections
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
import re
import sqlite3
import unicodedata
import traceback

ROOT = Path(__file__).resolve().parent
FINAL = ROOT / '交付成品'
EXPECTED = {'知识与规则': 203870, '实体抽取': 8100, '事件抽取': 8100, '关系抽取': 6303,
            '文本分类': 6700, '数值与财务字段': 4000, '因果与观点': 2600}
ALLOWED = {'FinCorpus', 'CFLUE', 'FIRE-Bench', 'CFSC', 'FEED', 'FinCorpus.CN', 'CSRC', 'TigerBot-earning', 'TigerBot-research'}


def norm(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', s)).lower()


def sha(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def span(text, obj, expected=None):
    assert isinstance(obj['start'], int) and isinstance(obj['end'], int)
    assert 0 <= obj['start'] < obj['end'] <= len(text)
    assert text[obj['start']:obj['end']] == (expected if expected is not None else obj['text'])


def knowledge_original(src, raw):
    if src == 'FinCorpus':
        text, rest = re.split(r'\n答案[：:]', raw['text'], maxsplit=1)
        parts = re.split(r'\n(?:分析解释|解析|答案解析)[：:]', rest, maxsplit=1)
        return text, parts[0].strip(), parts[1].strip() if len(parts) > 1 else ''
    if src == 'CFLUE':
        options = ast.literal_eval(raw['choices']) if isinstance(raw['choices'], str) else raw['choices']
        text = raw['question'] + '\n' + '\n'.join(f'{k}. {v}' for k, v in options.items())
        return text, raw['answer'], raw.get('analysis') or ''
    # FIRE-Bench source uses nested item fields; preserve exact original answer.
    if 'gold' in raw:
        text = re.sub(r'\n\s*答[:：]\s*$', '', raw['question']).strip()
        return re.sub(r'^问题[:：]', '', text), raw['gold'], ''
    entry = raw.get('item', raw)
    options = {x: entry[x] for x in 'ABCDEFGH' if entry.get(x)}
    question = entry.get('question', entry.get('Question'))
    if options:
        question += '\n' + '\n'.join(f'{k}. {v}' for k, v in options.items())
    return question, entry.get('answer', entry.get('Answer')), ''


def main():
    db = sqlite3.connect(ROOT / 'quality_work/source_reference.sqlite')
    errors, results, ids, hashes, qkeys = [], {}, set(), set(), set()
    rng = random.Random(20261002)
    samples = []
    evidence_count = 0
    for path in sorted((FINAL / '原始出处').glob('*.jsonl')):
        if path.stem not in ALLOWED:
            continue
        for line in path.open(encoding='utf-8'):
            e = json.loads(line)
            canonical = json.dumps(e['source_record'], ensure_ascii=False, sort_keys=True)
            assert sha(canonical) == e['source_record_sha256'], 'portable evidence record hash differs'
            hit = db.execute('SELECT raw FROM evidence WHERE key=?', (e['evidence_key'],)).fetchone()
            if hit is None and path.stem == 'FIRE-Bench':
                continue  # Earlier export's unused file is removed when packaging.
            assert hit and hit[0] == canonical, 'portable evidence does not match original download'
            evidence_count += 1
        print('checked evidence', path.stem, evidence_count, flush=True)
    def original(ref):
        k = ref.get('source_evidence_key') or ref['source_file'].replace('\\', '/') + '#' + str(ref['source_row'])
        hit = db.execute('SELECT raw FROM evidence WHERE key=?', (k,)).fetchone()
        assert hit, 'original evidence missing: ' + k
        return json.loads(hit[0])
    for name, target in EXPECTED.items():
        path = FINAL / '数据' / (name + '.jsonl')
        counters, sources, labels, picked = collections.Counter(), collections.Counter(), collections.Counter(), []
        for index, line in enumerate(path.open(encoding='utf-8'), 1):
            r = json.loads(line)
            try:
                t, a, task = r['text'], r['annotations'], r['task']
                assert r['id'] not in ids, 'repeated ID'
                ids.add(r['id'])
                assert r['source_dataset'] in ALLOWED, 'unapproved source'
                assert r['source_url'] and r['source_url'].startswith('https://'), 'missing source URL'
                assert (FINAL / r['source_evidence_file']).is_file(), 'missing portable evidence'
                assert r['text_hash'] == sha(norm(t)), 'input hash mismatch'
                assert t.strip() and a and '\ufffd' not in t, 'empty or corrupt content'
                assert r['benchmark_eligible'] is False and r['review_status'] == 'automated_content_checks_passed'
                raw = original(r)
                if task == 'knowledge_rules':
                    assert r['question_key'] not in qkeys, 'duplicate normalized question'
                    qkeys.add(r['question_key'])
                    assert a['options'] and a['answer_letters'] and all(x in a['options'] for x in a['answer_letters'])
                    assert len(set(norm(x) for x in a['options'].values())) == len(a['options']), 'duplicate option'
                    assert a['explanation'].strip() and not re.search(r'!\[[^]]*\]\(|<img', a['explanation'], re.I)
                    oldtext, oldanswer, oldexplanation = knowledge_original(r['source_dataset'], raw)
                    assert t == oldtext, 'source question differs'
                    assert norm(a['answer']) == norm(oldanswer), 'publisher answer changed'
                    if r.get('explanation_source'):
                        ref = r['explanation_source']
                        _, _, oldexplanation = knowledge_original(ref['source_dataset'], original(ref))
                    assert a['explanation'] == oldexplanation, 'explanation trace differs'
                    labels[r['module_candidate']] += 1
                else:
                    assert r['text_hash'] not in hashes, 'duplicate text across six tasks'
                    hashes.add(r['text_hash'])
                if task == 'entity':
                    assert t == raw['text']
                    assert {(x['start'],x['end'],x['text'],x['type']) for x in a} == {(x['from'],x['to'],x['text'],x['Level 1 Aspect']) for x in raw['labels']}
                    for x in a:
                        span(t, x)
                        labels[x['type']] += 1
                elif task in {'event', 'classification'} and r['source_dataset'] == 'FEED':
                    assert r['document_id'] == raw['document_id']
                    assert t == '\n'.join(raw['record']['sentences'])
                    source_events = raw['record']['recguid_eventname_eventdict_list']
                    if task == 'classification':
                        assert set(a) == {e[1] for e in source_events}
                        labels.update(a)
                    else:
                        assert len(a) == len(source_events)
                        for event in a:
                            src = next(e for e in source_events if e[0] == event['event_id'])
                            assert event['event_type'] == src[1]
                            assert {(x['role'], x['text']) for x in event['arguments']} == {(k,v) for k,v in src[2].items() if v is not None}
                            for x in event['arguments']:
                                assert x['mentions']
                                for m in x['mentions']:
                                    span(t, m, x['text'])
                            labels[event['event_type']] += 1
                elif task == 'relation':
                    assert t == raw['text']
                    assert {(x['subject'], x['predicate'], x['object']) for x in a} == {(x['subject'], x['predicate'], x['object']) for x in raw['spo_list']}
                    for x in a:
                        for v in ['subject', 'object']:
                            assert x[v + '_mentions']
                            for m in x[v + '_mentions']:
                                span(t, m, x[v])
                        labels[x['predicate']] += 1
                elif task == 'classification':
                    assert t == raw['text'] and r['source_url'] == raw['source_url']
                    assert set(a) == {x['label'] for x in r['classification_evidence']}
                    for x in r['classification_evidence']:
                        span(t, x)
                        assert '构成' in x['text'] and not re.search('不构成|未构成|申辩|主张', x['text'])
                    labels.update(a)
                elif task == 'numeric':
                    assert t == '报告：' + raw['title'] + '\n正文：' + raw['content']
                    for x in a:
                        span(t, x)
                        span(t, x['subject_evidence'], x['subject'])
                        span(t, x['metric_context'])
                        if x['business_scope'] != '未说明':
                            assert x['business_scope'] in x['metric_context']['text']
                        if x['measurement_basis'] != '未说明调整':
                            assert x['measurement_basis'] in x['metric_context']['text']
                        factor = {'元': '1', '元/股': '1', '千元': '1000', '万元': '10000', '亿元': '100000000', '%': '0.01', '％': '0.01'}[x['unit']]
                        assert Decimal(x['normalized_value']) == Decimal(x['value']) * Decimal(factor)
                        assert x['normalized_unit'] == ('ratio' if x['unit'] in {'%', '％'} else '元/股' if '每股' in x['field'] else '元')
                        assert x['period'] and x['period_basis'] and x['consolidation_scope'] in {'未说明', '合并', '母公司'}
                        assert re.match(r'20\d{2}年', x['period'])
                        labels[x['field']] += 1
                        counters['财务字段数'] += 1
                        counters['口径未说明字段数'] += x['consolidation_scope'] == '未说明'
                elif task == 'causal_opinion':
                    start = r['parent_sentence_start']
                    assert raw['content'][start:start+len(t)] == t, 'original sentence offset mismatch'
                    assert start == 0 or raw['content'][start - 1] in '。！？\n \t', 'sentence was chopped'
                    assert r['parent_paragraph_hash'] == sha(norm(raw['content']))
                    for x in a:
                        if x['type'] == 'causal':
                            span(t, x['cause']); span(t, x['effect'])
                            assert x['evidence'] == t
                        else:
                            assert x['holder'] == '报告作者'
                            span(t, x['holder_evidence']); span(t, x['target_evidence'], x['target']); span(t, x['claim'])
                            assert x['holder_evidence']['text'] in {'我们', '本报告'}
                        labels[x['type']] += 1
                sources[r['source_dataset']] += 1
                counters['条数'] += 1
                if len(picked) < 8:
                    picked.append(r)
                else:
                    j = rng.randrange(index)
                    if j < 8:
                        picked[j] = r
            except (AssertionError, KeyError, ValueError, TypeError, StopIteration) as err:
                errors.append({'file': name, 'line': index, 'id': r.get('id'), 'error': str(err), 'check_line': traceback.extract_tb(err.__traceback__)[-1].lineno})
        assert counters['条数'] == target or errors, (name, counters['条数'], target)
        with path.with_suffix('.csv').open(encoding='utf-8-sig', newline='') as f:
            assert sum(1 for _ in csv.DictReader(f)) == target
        results[name] = {**counters, '目标条数': target, '来源': dict(sources), '标签或字段频次': dict(labels),
                         'sha256': hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()}
        samples += picked
        print('checked', name, counters['条数'], 'errors', len(errors), flush=True)
    db.close()
    report = {'日期': '2026-10-02', '检查范围': '全部239673条；CSV条数与JSONL一致；逐条核对下载原始记录',
              '错误数': len(errors), '错误记录': errors[:100], '文件': results, '文本任务去重后条数': len(hashes), '包内原记录核对数': evidence_count,
              '知识题唯一问题数': len(qkeys), '已测专业标签准确率': None,
              '说明': '位置、来源一致和单位换算检查已实测；没有把检查通过率当作语义准确率。'}
    (FINAL / '检查记录' / '全量检查结果.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (ROOT / 'quality_work' / 'delivery_semantic_samples.jsonl').open('w', encoding='utf-8') as f:
        for r in samples:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    if errors:
        print(json.dumps(errors[:10], ensure_ascii=False))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
