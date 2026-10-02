"""Build traceable candidates. No output is certified as human-validated gold."""
import collections
import csv
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'processed'
OUT.mkdir(exist_ok=True)
STATS = {}
QUOTAS = {'entity': 9000, 'event': 9000, 'relation': 7000, 'classification': 7000, 'numeric': 5000, 'causal_opinion': 3000}
URLS = {
    'FinCorpus': 'https://huggingface.co/datasets/Duxiaoman-DI/FinCorpus',
    'FIRE-Bench': 'https://github.com/DXM-AGI/FIRE-Bench',
    'FinanceIQ': 'https://huggingface.co/datasets/Duxiaoman-DI/FinanceIQ',
    'CFSC': 'https://github.com/Ya-dongLi/CFSC',
    'FEED': 'https://github.com/seukgcode/FEED',
    'FinCorpus.CN': 'https://github.com/CGCL-codes/E-2CNN',
    'OEE-CFC': 'https://github.com/view98/OEE-CFC',
    'TigerBot-earning': 'https://huggingface.co/datasets/TigerResearch/tigerbot-earning-plugin',
    'TigerBot-research': 'https://huggingface.co/datasets/TigerResearch/tigerbot-research-plugin',
    'TigerBot-law': 'https://huggingface.co/datasets/TigerResearch/tigerbot-law-plugin',
}


def norm(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text)).lower()


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def jsonlines(path):
    with path.open(encoding='utf-8-sig') as stream:
        for line_no, line in enumerate(stream, 1):
            if line.strip():
                yield line_no, json.loads(line)


def record(source, path, row, text, task, annotations, method, category, document_id=None, **extra):
    text_hash = digest(norm(text))
    return {
        'id': digest(f'{source}|{path}|{row}|{task}')[:24], 'task': task, 'text': text,
        'annotations': annotations, 'source_dataset': source, 'source_url': URLS.get(source),
        'source_file': str(path.relative_to(ROOT)), 'source_row': row,
        'document_id': document_id or text_hash, 'text_hash': text_hash,
        'source_category': category, 'label_method': method, 'review_status': 'pending',
        'benchmark_eligible': False, 'split': 'unassigned',
        'split_note': '须在人工审核后按原文档、公司和时间隔离；同文多任务必须同组。', **extra,
    }


FINANCE = re.compile(r'金融|银行|证券|会计|审计|税|债券|股票|期货|基金|保险|财务|货币|利率|贷款|利润|资产|负债|投资|财政|预算|汇率|通货膨胀|通货紧缩|国民收入|国际收支|资本市场|资本成本|市盈率|净现值|内部收益率|资本资产定价|经济周期|总供给|总需求|需求曲线|供给曲线|边际成本|边际收益|GDP|IS.LM|信用证|融资|盈亏平衡|资本金|现金流|股权')
MODULES = [
    ('时效与版本辨析题', r'施行日期|生效日期|废止|新旧|修订前|修订后|版本'),
    ('会计与审计准则题', r'会计|审计|借方|贷方|资产负债表|会计分录|折旧|摊销'),
    ('金融法律法规题', r'证券法|银行法|保险法|公司法|法规|条例|监管|法律|违法|税法|税率|增值税|所得税'),
    ('金融计算规则', r'计算|应缴纳|应支付|现值|终值|收益率为|利息为|等于多少'),
    ('规则应用案例题', r'某银行|某证券公司|某保险公司|某基金|某投资者|甲公司|乙公司'),
    ('金融产品与业务规则', r'期货|期权|债券|股票|基金|信托|理财|保险|存款|贷款'),
]


def module_for(text):
    for label, pattern in MODULES:
        if re.search(pattern, text):
            return label
    return '金融资格考试题'


def choice_letters(answer, options):
    value = answer.strip()
    if value.startswith('['):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, list) or not all(isinstance(x, str) for x in parsed):
            return None
        value = ''.join(parsed)
    exact = [key for key, text in options.items() if norm(text) == norm(value)]
    if len(exact) == 1:
        return exact[0]
    letters = re.sub(r'[\s,，、;；]', '', value).upper()
    if not re.fullmatch('[A-H]+', letters) or any(c not in options for c in letters):
        return None
    return ''.join(sorted(set(letters)))


def build_knowledge():
    path = ROOT / 'raw/FinCorpus/fin_exam.jsonl.gz'
    unique, conflicts = {}, set()
    counts = collections.Counter()
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for row, line in enumerate(stream, 1):
            counts['raw_rows'] += 1
            item = json.loads(line)
            text = item['text']
            parts = re.split(r'\n答案[：:]', text, maxsplit=1)
            if len(parts) != 2:
                counts['unparsed'] += 1
                continue
            question, remainder = parts
            answer_parts = re.split(r'\n(?:分析解释|解析|答案解析)[：:]', remainder, maxsplit=1)
            answer = answer_parts[0].strip()
            explanation = answer_parts[1].strip() if len(answer_parts) == 2 else ''
            if not answer or not question.strip():
                counts['empty_question_or_answer'] += 1
                continue
            options = dict(re.findall(r'^([A-H])[、.．]\s*(.+)$', question, re.M))
            stem = re.split(r'\n[A-H][、.．]', question, maxsplit=1)[0]
            stem = re.sub(r'^\s*\d+[、.．]\s*', '', stem)
            canonical = norm(stem) + '|' + '|'.join(sorted(norm(x) for x in options.values()))
            key = digest(canonical)
            letters = choice_letters(answer, options) if options else None
            if options and letters is None:
                counts['invalid_choice_answer'] += 1
                continue
            semantic_answer = '|'.join(sorted(norm(options[c]) for c in set(letters))) if options else norm(answer)
            if key in unique:
                counts['duplicate_question'] += 1
                if unique[key]['canonical_answer'] != semantic_answer:
                    conflicts.add(key)
                continue
            unique[key] = {'question': question, 'answer': answer, 'answer_letters': letters, 'explanation': explanation,
                           'source_row': row, 'canonical_answer': semantic_answer, 'options': options,
                           'text': text, 'stem': stem, 'source': 'FinCorpus', 'path': path}
    extra_counts = collections.Counter()
    extra_paths = [ROOT / 'raw/FIRE-Bench/dataset/FIRE/FIRE.json'] + sorted((ROOT / 'raw/FinanceIQ/data').rglob('*.csv'))
    for extra_path in extra_paths:
        if extra_path.suffix == '.json':
            source = 'FIRE-Bench'
            extras = json.loads(extra_path.read_text(encoding='utf-8'))
        else:
            source = 'FinanceIQ'
            with extra_path.open(encoding='utf-8-sig') as stream:
                extras = list(csv.DictReader(stream))
        for row, entry in enumerate(extras, 1):
            extra_counts[source + '_raw_rows'] += 1
            if source == 'FIRE-Bench':
                question = re.sub(r'\n\s*答[:：]\s*$', '', entry['question']).strip()
                question = re.sub(r'^问题[:：]', '', question)
                answer = entry['gold']
                options = dict(re.findall(r'^([A-H])[、.．]\s*(.+)$', question, re.M))
            else:
                options = {letter: entry[letter] for letter in 'ABCD' if entry.get(letter)}
                question = entry['Question'] + '\n' + '\n'.join(f'{k}. {v}' for k, v in options.items())
                answer = entry['Answer']
            # International English exams remain in raw reserves; this build prioritizes Chinese.
            if len(re.findall('[\u4e00-\u9fff]', question)) < 5:
                extra_counts['non_chinese_reserved'] += 1
                continue
            letters = choice_letters(answer, options)
            if not letters:
                extra_counts['invalid_choice_answer'] += 1
                continue
            stem = re.split(r'\n[A-H][、.．]', question, maxsplit=1)[0]
            stem = re.sub(r'^\s*\d+[、.．]\s*', '', stem)
            key = digest(norm(stem) + '|' + '|'.join(sorted(norm(x) for x in options.values())))
            semantic_answer = '|'.join(sorted(norm(options[c]) for c in set(letters)))
            if key in unique:
                extra_counts['duplicate_question'] += 1
                if unique[key]['canonical_answer'] != semantic_answer:
                    conflicts.add(key)
                continue
            unique[key] = {'question': question, 'answer': answer, 'answer_letters': letters, 'explanation': '',
                           'source_row': row, 'canonical_answer': semantic_answer, 'options': options,
                           'text': question, 'stem': stem, 'source': source, 'path': extra_path}
    module_counts = collections.Counter()
    source_counts = collections.Counter()
    with (OUT / 'knowledge_candidates.jsonl').open('w', encoding='utf-8') as stream, (OUT / 'knowledge_rejected.jsonl').open('w', encoding='utf-8') as rejected:
        for key, item in unique.items():
            reason = 'conflicting_answers' if key in conflicts else 'no_finance_keyword' if not FINANCE.search(item['question']) else None
            if reason is None and re.search(r'!\[|<img|如图所示|如下图|根据下图|如下表|根据下表|根据上述资料|根据以下资料', item['question']):
                reason = 'external_image_or_context_needs_recovery'
            if reason:
                counts[reason] += 1
                rejected.write(json.dumps({'question_key': key, 'source_row': item['source_row'], 'reason': reason}, ensure_ascii=False) + '\n')
                continue
            module = module_for(item['question'])
            obj = record(item['source'], item['path'], item['source_row'], item['question'], 'knowledge_rules',
                         {'answer': item['answer'], 'answer_letters': item['answer_letters'], 'explanation': item['explanation'], 'options': item['options']},
                         'publisher_answer_parsed_not_revalidated', '金融试题', module_candidate=module,
                         module_method='keyword_routing_requires_review', question_key=key,
                         original_question_source_url=None, applicable_law_version=None,
                         quality_flags=['仅通过结构筛选；答案、金融相关性和法规版本未人工核验', '只能追溯到发布数据文件，缺逐题原始网页'])
            stream.write(json.dumps(obj, ensure_ascii=False) + '\n')
            module_counts[module] += 1
            source_counts[item['source']] += 1
            counts['candidates'] += 1
    counts['conflicting_question_keys'] = len(conflicts)
    STATS['knowledge'] = {'counts': dict(counts), 'extra_source_counts': dict(extra_counts),
                          'source_candidates': dict(source_counts), 'module_candidates': dict(module_counts), 'gold_accepted': 0}


class TaskWriter:
    def __init__(self):
        self.streams = {task: (OUT / f'{task}_candidates.jsonl').open('w', encoding='utf-8') for task in QUOTAS}
        self.counts = collections.Counter()
        self.subtypes = collections.defaultdict(collections.Counter)
        self.seen = collections.defaultdict(set)
        self.documents = collections.defaultdict(set)
        self.samples = collections.defaultdict(list)

    def add(self, obj):
        task = obj['task']
        if self.counts[task] >= QUOTAS[task] or obj['text_hash'] in self.seen[task]:
            return False
        self.seen[task].add(obj['text_hash'])
        self.documents[task].add(obj['document_id'])
        self.streams[task].write(json.dumps(obj, ensure_ascii=False) + '\n')
        self.counts[task] += 1
        self.subtypes[task][obj.get('subtype', obj['source_dataset'])] += 1
        if len(self.samples[task]) < 30:
            self.samples[task].append(obj)
        return True

    def close(self):
        for stream in self.streams.values():
            stream.close()
        with (OUT / 'review_examples.jsonl').open('w', encoding='utf-8') as stream:
            for examples in self.samples.values():
                for obj in examples:
                    stream.write(json.dumps(obj, ensure_ascii=False) + '\n')
        STATS['text_tasks'] = {task: {'candidate_rows': self.counts[task], 'unique_texts': len(self.seen[task]),
                                     'document_groups': len(self.documents[task]), 'candidate_target': QUOTAS[task],
                                     'subtypes': dict(self.subtypes[task]), 'gold_accepted': 0} for task in QUOTAS}


def cfsc_entities(writer):
    path = ROOT / 'raw/CFSC/CFSC-NER/CFSC-NER-Alldata.json'
    rows = json.loads(path.read_text(encoding='utf-8'))
    bad = 0
    for index, row in enumerate(rows, 1):
        text = row['text']
        spans = [{'start': v['from'], 'end': v['to'], 'text': v['text'], 'type': v['Level 1 Aspect']} for v in row['labels']]
        if not all(text[s['start']:s['end']] == s['text'] for s in spans):
            bad += 1
            continue
        writer.add(record('CFSC', path, index, text, 'entity', spans, 'publisher_annotation', '金融新闻与研报',
                          quality_flags=['标签为Corporate/Stock/Market/Economy；缺原新闻文档ID，待原文级隔离核验']))
    STATS['cfsc'] = {'raw_rows': len(rows), 'rows_with_invalid_spans_excluded': bad}


def feed_tasks(writer):
    count = collections.Counter()
    doc_seen = set()
    for split in ['train', 'dev', 'test']:
        path = ROOT / f'raw/FEED/{split}.json.zip'
        with zipfile.ZipFile(path) as archive:
            rows = json.loads(archive.read(f'{split}.json'))
        for index, (document_id, row) in enumerate(rows, 1):
            count['raw_documents'] += 1
            if document_id in doc_seen:
                count['duplicate_document_id'] += 1
                continue
            doc_seen.add(document_id)
            text = '\n'.join(row['sentences'])
            events = []
            for event_id, name, arguments in row['recguid_eventname_eventdict_list']:
                roles = []
                for role, value in arguments.items():
                    if value is None:
                        continue
                    starts = [m.start() for m in re.finditer(re.escape(value), text)]
                    if not starts:
                        count['argument_not_in_text'] += 1
                    roles.append({'role': role, 'text': value, 'mentions': [{'start': x, 'end': x + len(value)} for x in starts]})
                events.append({'event_id': event_id, 'event_type': name, 'arguments': roles})
            if not events or any(not arg['mentions'] for e in events for arg in e['arguments']):
                count['excluded_incomplete_evidence'] += 1
                continue
            if writer.counts['event'] < QUOTAS['event']:
                task, labels = 'event', events
            else:
                task, labels = 'classification', sorted({event['event_type'] for event in events})
            writer.add(record('FEED', path, index, text, task, labels, 'publisher_distant_supervision', '上市公司公告',
                              document_id=document_id, original_split=split, stock_code=document_id.split('_')[0],
                              published_at=document_id.split('_')[1] if '_' in document_id else None,
                              subtype='金融公告事件类型多标签分类' if task == 'classification' else '金融事件抽取',
                              quality_flags=['远程监督标签未达到本项目人工验收状态']))
    STATS['feed'] = dict(count)


def relations(writer):
    counts = collections.Counter()
    for split in ['train', 'dev', 'test']:
        path = ROOT / f'raw/FinCorpus.CN/relation_data/FinCorpus.CN/{split}.json'
        for line, row in jsonlines(path):
            counts['raw_rows'] += 1
            text, labels = row['text'], []
            triples_seen = set()
            for spo in row['spo_list']:
                subject, obj = spo['subject'], spo['object']
                if not subject or not obj or subject not in text or obj not in text:
                    counts['invalid_triples'] += 1
                    continue
                key = (subject, spo['predicate'], obj)
                if key in triples_seen:
                    counts['duplicate_triples'] += 1
                    continue
                triples_seen.add(key)
                labels.append({**spo,
                    'subject_mentions': [{'start': m.start(), 'end': m.end()} for m in re.finditer(re.escape(subject), text)],
                    'object_mentions': [{'start': m.start(), 'end': m.end()} for m in re.finditer(re.escape(obj), text)]})
            if len(triples_seen) == 0 or any(not x['subject'] or x['subject'] not in text or x['object'] not in text for x in row['spo_list']):
                counts['excluded_rows'] += 1
                continue
            writer.add(record('FinCorpus.CN', path, line, text, 'relation', labels, 'publisher_spo_annotations', '年报与财务报告',
                              original_split=split, quality_flags=['未采用predict_entity模型预测字段', '原数据缺公司年报ID；人工检查关系方向及漏标']))
    STATS['relations'] = dict(counts)


METRIC = re.compile(r'(?P<field>营业总收入|营业收入|营业利润|利润总额|净利润|总资产|资产总额|负债总额|所有者权益|经营活动产生的现金流量净额|基本每股收益|货币资金|营业成本|投资收益)[\s为达约：:是]*[（(]?(?:人民币)?[）)]?\s*(?P<number>[-−－]?\d[\d,，]*(?:\.\d+)?)\s*(?P<unit>亿元|万元|千元|元|%)')


def numeric_labels(text):
    labels = []
    for match in METRIC.finditer(text):
        number = match['number'].replace(',', '').replace('，', '').replace('−', '-').replace('－', '-')
        factor = {'亿元': Decimal(100000000), '万元': Decimal(10000), '千元': Decimal(1000), '元': Decimal(1), '%': Decimal('0.01')}[match['unit']]
        labels.append({'field': match['field'], 'value': number, 'unit': match['unit'],
                       'normalized_value': str(Decimal(number) * factor),
                       'normalized_unit': 'ratio' if match['unit'] == '%' else '元/股' if match['field'] == '基本每股收益' else '元',
                       'start': match.start(), 'end': match.end(), 'text': match.group(),
                       'period': None, 'subject': None, 'consolidation_scope': None})
    return labels


def causal_labels(text):
    # Explicit linguistic cues propose spans only; they do not establish economic causation.
    labels = []
    for match in re.finditer(r'(?:^|(?<=[。！？\n]))[^。！？\n]{10,350}(?:[。！？]|$)', text):
        sentence = match.group()
        cause = effect = None
        a = re.search(r'(.{4,150}?)(?:主要原因是|主要系|主要由于)(.{4,170})', sentence)
        if a:
            effect, cause = a.span(1), a.span(2)
        else:
            a = re.search(r'^\s*(?:由于|因为)(.{4,150}?)[，,](?:因此|所以|从而)?(.{4,170})', sentence)
            if a:
                cause, effect = a.span(1), a.span(2)
        if cause and effect:
            labels.append({'type': 'causal_candidate', 'cause': {'start': match.start() + cause[0], 'end': match.start() + cause[1], 'text': sentence[slice(*cause)]},
                           'effect': {'start': match.start() + effect[0], 'end': match.start() + effect[1], 'text': sentence[slice(*effect)]},
                           'status': 'needs_semantic_review'})
    return labels


def opinion_labels(text):
    labels = []
    for match in re.finditer(r'(?:我们认为|我们预计|我们建议|我们看好|本报告认为|预计|建议关注|看好)[^。！？\n]{8,240}', text):
        labels.append({'type': 'opinion_candidate', 'start': match.start(), 'end': match.end(), 'text': match.group(),
                       'holder': None, 'target': None, 'polarity': None, 'status': 'needs_role_annotation'})
    return labels


def raw_reports(writer):
    for kind in ['earning', 'research']:
        path = ROOT / f'raw/TigerBot-{kind}/tigerbot-{kind}-plugin.json'
        total, unique_documents = 0, set()
        ca = op = 0
        numeric_reserve = []
        for line, row in jsonlines(path):
            total += 1
            text = row['content']
            date, title = row.get('publishTime'), row.get('title', '')
            doc_id = digest(f'{title}|{date}')
            unique_documents.add(doc_id)
            if kind == 'earning':
                labels = numeric_labels(text)
                if labels and len(text) <= 6000:
                    writer.add(record('TigerBot-earning', path, line, text, 'numeric', labels, 'regex_metric_value_unit', '年报与财务报告',
                                      document_id=doc_id, title=title, published_at=date,
                                      quality_flags=['仅显式指标与单位；时期、主体及合并口径需核验', '未解析跨行表格和隐含单位']))
            elif len(text) <= 3500 and len(text) >= 30:
                labels, subtype = [], None
                if ca < 1500:
                    labels = causal_labels(text)
                    subtype = '因果预标注'
                if not labels and op < 1500:
                    labels = opinion_labels(text)
                    subtype = '观点预标注'
                if labels:
                    added = writer.add(record('TigerBot-research', path, line, text, 'causal_opinion', labels, 'explicit_cue_regex', '金融新闻与研报',
                                             document_id=doc_id, title=title, published_at=date, subtype=subtype,
                                             quality_flags=['规则预标注；须补齐观点持有人、对象及因果语义审核']))
                    if added:
                        if subtype == '因果预标注':
                            ca += 1
                        else:
                            op += 1
        STATS[f'TigerBot-{kind}'] = {'raw_paragraph_rows': total, 'distinct_title_date_groups': len(unique_documents)}


def law_material():
    path = ROOT / 'raw/TigerBot-law/tigerbot-laws-plugin.json'
    n = 0
    seen = set()
    with (OUT / 'financial_law_material.jsonl').open('w', encoding='utf-8') as stream:
        for line, row in jsonlines(path):
            if not re.search(r'银行|证券|保险|期货|基金|会计|审计|税|金融|信托|公司法|票据|外汇|支付', row['title']):
                continue
            key = digest(norm(row['title'] + row['content']))
            if key in seen:
                continue
            seen.add(key)
            obj = {'id': key, **row, 'source_dataset': 'TigerBot-law', 'source_url': URLS['TigerBot-law'],
                   'source_file': str(path.relative_to(ROOT)), 'source_row': line,
                   'material_only': True, 'benchmark_eligible': False, 'law_version_verified': False,
                   'note': '历史法规材料，未核验现行有效性；不是现成问题答案。'}
            stream.write(json.dumps(obj, ensure_ascii=False) + '\n')
            n += 1
    STATS['financial_law_material'] = n


def csrc_classification(writer):
    path = ROOT / 'raw/CSRC/documents.jsonl'
    types = ['内幕交易', '操纵市场', '操纵证券市场', '信息披露违法', '虚假记载', '未勤勉尽责', '传播虚假信息']
    count = 0
    total = 0
    for line, row in jsonlines(path):
        total += 1
        if count >= 300:
            continue
        text = row['text']
        labels = sorted({'操纵市场' if label == '操纵证券市场' else label for label in types if label in text})
        if not labels:
            continue
        obj = record('CSRC', path, line, text, 'classification', labels, 'regulatory_text_keyword_candidates', '监管处罚与问询文件',
                     document_id='CSRC:' + row['document_id'], subtype='监管处罚主题多标签预分类',
                     published_at=row['published_at'], title=row['title'],
                     quality_flags=['关键词可能出现在引用法条或申辩中，须按最终认定事实复核'])
        obj['source_url'] = row['source_url']
        if writer.add(obj):
            count += 1
    STATS['CSRC'] = {'downloaded_documents': total, 'subtype': '行政处罚决定书', 'inquiry_letters': 0}


def main():
    build_knowledge()
    print('knowledge', STATS['knowledge'], flush=True)
    writer = TaskWriter()
    cfsc_entities(writer)
    csrc_classification(writer)
    feed_tasks(writer)
    relations(writer)
    raw_reports(writer)
    writer.close()
    law_material()
    STATS['acceptance'] = {'knowledge_target_gap': 203870, 'text_target_gap': 35803,
                           'human_validated_gold': 0, 'status': 'candidate_package_not_accepted_benchmark',
                           'old_dataset_row_level_dedup': 'not_required_per_user_use_dataset_family_exclusion',
                           'company_time_split': 'not_done', 'semantic_dedup': 'not_done'}
    write_json(OUT / 'build_stats.json', STATS)
    print(json.dumps(STATS, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
