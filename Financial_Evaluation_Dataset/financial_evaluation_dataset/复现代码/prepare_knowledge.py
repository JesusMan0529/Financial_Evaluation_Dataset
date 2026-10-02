"""Select the requested knowledge count with substantive exclusions and lineage."""
import ast
import collections
import copy
import json
from pathlib import Path
import re
import unicodedata

from audit_content import knowledge_flags
from build_candidates import choice_letters, digest, module_for, norm, record, URLS

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'delivery_v2'
DEST.mkdir(exist_ok=True)
TARGET = 203870
URLS['CFLUE'] = 'https://huggingface.co/datasets/DianJin/CFLUE'


def items():
    path = ROOT / 'processed/knowledge_candidates.jsonl'
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)
    for split in ['train', 'val', 'test']:
        path = ROOT / f'raw/CFLUE/{split}.json'
        if not path.exists():
            continue
        for index, item in enumerate(json.loads(path.read_text(encoding='utf-8')), 1):
            options = ast.literal_eval(item['choices']) if isinstance(item['choices'], str) else item['choices']
            if not isinstance(options, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in options.items()):
                continue
            letters = choice_letters(item['answer'], options)
            if not letters:
                continue
            text = item['question'] + '\n' + '\n'.join(f'{k}. {v}' for k, v in options.items())
            yield record('CFLUE', path, index, text, 'knowledge_rules',
                         {'answer': item['answer'], 'answer_letters': letters, 'explanation': item.get('analysis') or '', 'options': options},
                         'publisher_answer_and_analysis', '金融试题', module_candidate=module_for(text),
                         original_split=split, exam_name=item.get('名称'), exam_subject=item.get('科目'), exam_chapter=item.get('章节'))


def stem(row):
    value = re.split(r'\n[A-H][、.．]', row['text'], maxsplit=1)[0]
    value = re.sub(r'^问题[:：]', '', value)
    return re.sub(r'^\s*\d+[、.．]\s*', '', value)


def key_for(row):
    # Preserve numeric and negation content, while normalizing presentation punctuation.
    value = unicodedata.normalize('NFKC', stem(row))
    value = re.sub(r'[\s。，,；;：:？?！!、]', '', value)
    value = re.sub(r'(?<!\d)\.|\.(?!\d)', '', value)
    value = value.replace('()', '').replace('( )', '').lower()
    return digest(value + '|' + '|'.join(sorted(norm(x) for x in row['annotations']['options'].values())))


def semantic_answer(row):
    a = row['annotations']
    if a['options']:
        return '|'.join(sorted(norm(a['options'][x]) for x in a['answer_letters']))
    return norm(a['answer'])


def explicit_explanation_conflict(row):
    a = row['annotations']
    explanation = a.get('explanation', '')
    answer = a.get('answer_letters')
    if not answer:
        return False
    matches = re.findall(r'(?:正确答案(?:为|是)?|答案(?:为|是))\s*[:：]?\s*([A-H](?:[、,，\s]*[A-H])*)', explanation)
    tail = re.search(r'(?:综上(?:所述|分析)?|故|因此)[^。]{0,15}?([A-H]+)(?:选项)?正确[。.]?\s*$', explanation)
    if tail:
        matches.append(tail[1])
    return any(''.join(sorted(set(re.findall('[A-H]', value)))) != answer for value in matches)


def rejection_reasons(row):
    flags = knowledge_flags(row)
    # Missing explanations are allowed for published exam answers, but ranked below explained records.
    reasons = [x for x in flags if x != 'no_publisher_explanation']
    if not row['annotations']['options'] and 'no_complete_choice_options' not in reasons:
        reasons.append('no_complete_choice_options')
    if explicit_explanation_conflict(row):
        reasons.append('explicit_answer_explanation_disagreement')
    if re.search(r'\d[OoＯ]\d', row['text']):
        reasons.append('ambiguous_ocr_digit')
    if '\ufffd' in row['text'] or '\ufffd' in row['annotations'].get('explanation', ''):
        reasons.append('replacement_character_in_content')
    if re.search(r'!\[[^]]*\]\(|<img', row['annotations'].get('explanation', ''), re.I):
        reasons.append('explanation_depends_on_external_image')
    if not row['annotations'].get('explanation', '').strip():
        reasons.append('no_readable_explanation')
    return reasons


def main():
    counts, pool, conflicts = collections.Counter(), {}, set()
    rejected = []
    for row in items():
        counts['input_records'] += 1
        reasons = rejection_reasons(row)
        if reasons:
            counts.update(reasons)
            rejected.append({'id': row['id'], 'source_dataset': row['source_dataset'], 'source_file': row['source_file'],
                             'source_row': row['source_row'], 'reasons': reasons})
            continue
        key = key_for(row)
        row['question_key'] = key
        if key in pool:
            counts['normalized_duplicate'] += 1
            previous = pool[key]
            if semantic_answer(previous) != semantic_answer(row):
                conflicts.add(key)
            else:
                counts['consistent_duplicate_answer'] += 1
                previous.setdefault('corroborating_release_records', []).append({'source_dataset': row['source_dataset'],
                    'source_file': row['source_file'], 'source_row': row['source_row'], 'answer_letters': row['annotations']['answer_letters']})
                if (not previous['annotations'].get('explanation') and row['annotations'].get('explanation')
                        and {k: norm(v) for k, v in previous['annotations']['options'].items()} == {k: norm(v) for k, v in row['annotations']['options'].items()}):
                    previous['annotations']['explanation'] = row['annotations']['explanation']
                    previous['explanation_source'] = {'source_dataset': row['source_dataset'], 'source_file': row['source_file'], 'source_row': row['source_row']}
            continue
        pool[key] = row
    for key in conflicts:
        row = pool.pop(key)
        rejected.append({'id': row['id'], 'source_dataset': row['source_dataset'], 'source_file': row['source_file'],
                         'source_row': row['source_row'], 'reasons': ['conflicting_released_answers']})
    counts['conflicting_released_answers'] = len(conflicts)
    # Published analyses improve inspectability; they are not assumed independently verified.
    ranked = sorted(pool.values(), key=lambda row: (not bool(row['annotations'].get('explanation')),
                                                  -len(row.get('corroborating_release_records', [])), row['id']))
    counts['usable_after_listed_checks'] = len(ranked)
    chosen = ranked[:TARGET]
    sources, modules = collections.Counter(), collections.Counter()
    with (DEST / '知识与规则.jsonl').open('w', encoding='utf-8') as stream:
        for original in chosen:
            row = copy.deepcopy(original)
            row['review_status'] = 'automated_content_checks_passed'
            row['benchmark_eligible'] = False
            row['split'] = 'evaluation_pool'
            row['split_note'] = '交付统一测评题池；未建立训练/验证/隐藏测试分片，不声明公司或时间隔离完成。'
            row['applicable_law_version'] = {'status': 'not_established', 'note': '保留原题库答案；不声明为现行法规答案。'}
            row['quality_flags'] = ['保留发布者答案；未逐题完成独立专业复核', '公开数据可能已进入被测模型训练集']
            row['checks'] = {'version': 'knowledge_checks_v2', 'invalid_options': False, 'duplicate_options': False,
                             'referenced_missing_context_detected': False, 'explicit_explanation_disagreement': False,
                             'normalization_duplicates_removed': True, 'independent_human_review': False}
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            sources[row['source_dataset']] += 1
            modules[row['module_candidate']] += 1
    with (ROOT / 'quality_work/knowledge_exclusions_v2.jsonl').open('w', encoding='utf-8') as stream:
        for row in rejected:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    report = {'requested': TARGET, 'exported': len(chosen), 'shortfall': max(0, TARGET - len(chosen)),
              'counts': dict(counts), 'source_counts': dict(sources), 'module_counts': dict(modules),
              'missing_explanation': sum(not row['annotations'].get('explanation') for row in chosen),
              'quality_status': 'automated_checks_not_independent_gold', 'measured_semantic_accuracy': None}
    (DEST / '知识题处理统计.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if len(chosen) != TARGET:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
