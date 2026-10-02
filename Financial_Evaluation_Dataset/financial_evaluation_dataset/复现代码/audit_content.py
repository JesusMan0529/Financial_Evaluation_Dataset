"""Profile substantive risks before changing or selecting any records."""
import collections
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'quality_work'
OUT.mkdir(exist_ok=True)


def rows(name):
    with (ROOT / 'processed' / name).open(encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def normalize(text):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', unicodedata.normalize('NFKC', text)).lower()


def option_norm(text):
    # Decimal points and minus signs distinguish legitimate numeric options.
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text)).lower()


def knowledge_flags(row):
    flags = []
    text, a = row['text'], row['annotations']
    stem = re.split(r'\n[A-H][、.．]', text, maxsplit=1)[0]
    opts = a['options']
    if (opts and len(opts) < 2) or (not opts and re.fullmatch(r'[A-H]+', a['answer'].strip())):
        flags.append('no_complete_choice_options')
    if len(set(option_norm(x) for x in opts.values())) != len(opts):
        flags.append('repeated_option_text')
    if opts and list(opts) != list('ABCDEFGH'[:len(opts)]):
        flags.append('nonconsecutive_options')
    if re.search(r'如图|见图|下图|上图|根据(?:下|上)表|(?:下表|上表|见表)[中所：:]|题图|附图|上述资料|前述资料', text):
        flags.append('possible_missing_context')
    if len(stem) < 120 and re.search(r'事项[（(]\d|编制相应|上述业务|上述事项|根据资料|根据材料', stem):
        flags.append('dependent_question_without_case')
    if re.search(r'《?民法通则|银监会|保监会|银保监会', text):
        flags.append('historical_law_or_institution_needs_date')
    if not a.get('explanation'):
        flags.append('no_publisher_explanation')
    if re.search(r'消防|道路施工|桥梁|钢筋|水泥|混凝土|公路工程|矿山|钻井|护理|手术|病人|畜牧|植物病|农药', stem) and not re.search(r'会计|审计|税|金融|银行|证券|债券|期货|基金|保险|财务|贷款|利润|融资|现金流|投资|资本|成本|储蓄|财富|房贷', text):
        flags.append('likely_out_of_finance_scope')
    if len(stem.strip()) < 5:
        flags.append('short_or_empty_stem')
    return flags


def main():
    report = {'knowledge': {}, 'text_tasks': {}, 'measurement_note': 'Counts identify risks; no semantic accuracy or F1 is inferred.'}
    counts, by_source, examples = collections.Counter(), collections.defaultdict(collections.Counter), collections.defaultdict(list)
    stem_groups = collections.Counter()
    for row in rows('knowledge_candidates.jsonl'):
        counts['rows'] += 1
        flags = knowledge_flags(row)
        if not flags:
            counts['none_of_listed_risks'] += 1
        for flag in flags:
            counts[flag] += 1
            by_source[row['source_dataset']][flag] += 1
            if len(examples[flag]) < 12:
                examples[flag].append({'id': row['id'], 'text': row['text'], 'annotations': row['annotations'], 'source': row['source_dataset']})
        stem = re.split(r'\n[A-H][、.．]', row['text'], maxsplit=1)[0]
        stem = re.sub(r'^\s*\d+[、.．]\s*', '', stem)
        if len(normalize(stem)) >= 30:
            stem_groups[normalize(stem)] += 1
    report['knowledge'] = {'counts': dict(counts), 'by_source': {k: dict(v) for k, v in by_source.items()},
                           'repeated_long_stem_groups': sum(n > 1 for n in stem_groups.values()),
                           'rows_in_repeated_long_stem_groups': sum(n for n in stem_groups.values() if n > 1)}
    for task in ['entity', 'event', 'relation', 'classification', 'numeric', 'causal_opinion']:
        c = collections.Counter()
        for row in rows(f'{task}_candidates.jsonl'):
            c['rows'] += 1
            c['characters'] += len(row['text'])
            if task == 'numeric':
                for a in row['annotations']:
                    c['fields'] += 1
                    for key in ['period', 'subject', 'consolidation_scope']:
                        c[f'missing_{key}'] += int(a.get(key) is None)
            if task == 'causal_opinion':
                for a in row['annotations']:
                    c[a['type']] += 1
                    if a['type'] == 'opinion_candidate':
                        for key in ['holder', 'target', 'polarity']:
                            c[f'missing_{key}'] += int(a.get(key) is None)
            if task == 'entity':
                c['possible_stock_codes_without_label'] += int(bool(re.search(r'(?:SH|SZ|NQ)\d{6}', row['text'])))
        report['text_tasks'][task] = dict(c)
    (OUT / 'content_profile.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'risk_examples.json').write_text(json.dumps(examples, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
