"""Produce six complete-schema text task files with evidence and explicit unknowns."""
import collections
from decimal import Decimal
import json
from pathlib import Path
import re

from build_candidates import digest, jsonlines, norm, record

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'delivery_v2'
DEST.mkdir(exist_ok=True)
TARGETS = {'entity': 8100, 'event': 8100, 'relation': 6303, 'classification': 6700, 'numeric': 4000, 'causal_opinion': 2600}
STATS = {}
USED = set()


def finish(row, check_method):
    row['review_status'] = 'automated_content_checks_passed'
    row['benchmark_eligible'] = False
    row['split'] = 'evaluation_pool'
    row['split_note'] = '统一测评题池；未建立隐藏测试集，不声明公司或时间隔离完成。'
    row['checks'] = {'version': 'text_checks_v2', 'method': check_method, 'independent_human_review': False}
    return row


def select(task, rows):
    result = []
    for row in rows:
        if row['text_hash'] in USED:
            continue
        USED.add(row['text_hash'])
        result.append(row)
        if len(result) == TARGETS[task]:
            break
    return result


def write(task, rows):
    names = {'entity': '实体抽取', 'event': '事件抽取', 'relation': '关系抽取', 'classification': '文本分类',
             'numeric': '数值与财务字段', 'causal_opinion': '因果与观点'}
    path = DEST / f'{names[task]}.jsonl'
    with path.open('w', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    STATS.setdefault(task, {}).update(requested=TARGETS[task], exported=len(rows), shortfall=max(0, TARGETS[task] - len(rows)),
                                     source_counts=dict(collections.Counter(x['source_dataset'] for x in rows)))
    print(task, len(rows), flush=True)


def original_rows(task):
    return [row for _, row in jsonlines(ROOT / f'processed/{task}_candidates.jsonl')]


def entities():
    path = ROOT / 'raw/CFSC/CFSC-NER/CFSC-NER-Alldata.json'
    raw = json.loads(path.read_text(encoding='utf-8'))
    country_only = {'中国', '美国', '英国', '日本', '德国', '法国', '印度', '俄罗斯', '欧盟'}
    pool, excluded = [], collections.Counter()
    for index, row in enumerate(raw, 1):
        labels, seen = [], set()
        bad = False
        for a in row['labels']:
            span = {'start': a['from'], 'end': a['to'], 'text': a['text'], 'type': a['Level 1 Aspect']}
            if row['text'][span['start']:span['end']] != span['text']:
                bad = True
                break
            key = (span['start'], span['end'], span['type'])
            if key not in seen:
                seen.add(key)
                labels.append(span)
        if bad or not labels:
            excluded['invalid_or_empty_annotation'] += 1
            continue
        if all(a['type'] == 'Economy' and a['text'] in country_only for a in labels):
            excluded['country_only_as_economic_concept'] += 1
            continue
        if any(len(a['text'].strip()) < 2 for a in labels):
            excluded['one_character_entity'] += 1
            continue
        obj = record('CFSC', path, index, row['text'], 'entity', labels, 'publisher_annotation', '金融新闻与研报',
                     quality_flags=['原发布者四类标签；完整性和类别正确性未独立人工验收', '缺原始新闻文档ID'])
        pool.append(finish(obj, 'source_span_check_and_obvious_annotation_risk_filter'))
    STATS['entity'] = {'pool_rows': len(pool), 'excluded': dict(excluded)}
    write('entity', select('entity', sorted(pool, key=lambda x: x['id'])))


def events():
    rows = original_rows('event')
    pool = []
    for row in rows:
        annotations = []
        for e in row['annotations']:
            seen, args = set(), []
            for a in e['arguments']:
                key = (a['role'], a['text'])
                if key not in seen:
                    seen.add(key)
                    args.append(a)
            annotations.append({**e, 'arguments': args})
        row['annotations'] = annotations
        row['quality_flags'] = ['沿用 FEED 远程监督标签，字符位置通过检查；不声明为人工金标']
        pool.append(finish(row, 'role_text_evidence_and_duplicate_role_check'))
    write('event', select('event', sorted(pool, key=lambda x: x['id'])))


def relations():
    pool, excluded = [], collections.Counter()
    for split in ['train', 'dev', 'test']:
        path = ROOT / f'raw/FinCorpus.CN/relation_data/FinCorpus.CN/{split}.json'
        for line, row in jsonlines(path):
            text, labels, seen = row['text'], [], set()
            if any(not a['subject'] or not a['object'] or a['subject'] not in text or a['object'] not in text for a in row['spo_list']):
                excluded['missing_subject_or_object_evidence'] += 1
                continue
            if any(a['predicate'] == '位于' for a in row['spo_list']) and re.search(r'在.{0,12}(?:建立|设立|建设|投资|开发)', text) and not re.search(r'总部|注册|坐落|所在地|地处', text):
                excluded['branch_activity_not_company_location'] += 1
                continue
            for a in row['spo_list']:
                key = (a['subject'], a['predicate'], a['object'])
                if key in seen:
                    continue
                seen.add(key)
                labels.append({**a, 'subject_mentions': [{'start': m.start(), 'end': m.end()} for m in re.finditer(re.escape(a['subject']), text)],
                               'object_mentions': [{'start': m.start(), 'end': m.end()} for m in re.finditer(re.escape(a['object']), text)]})
            if not labels:
                continue
            obj = record('FinCorpus.CN', path, line, text, 'relation', labels, 'publisher_spo_annotations', '年报与财务报告',
                         original_split=split, quality_flags=['保留原三元组；不使用 predict_entity；缺原始年报ID，语义及漏标未独立人工验收'])
            pool.append(finish(obj, 'triple_evidence_check_and_obvious_location_scope_filter'))
    frequencies = collections.Counter(a['predicate'] for x in pool for a in x['annotations'])
    # Include rare relation types before a stable shuffled remainder.
    pool.sort(key=lambda x: (min(frequencies[a['predicate']] for a in x['annotations']), x['id']))
    STATS['relation'] = {'pool_rows': len(pool), 'excluded': dict(excluded)}
    write('relation', select('relation', pool))


REGULATORY = {'内幕交易': r'内幕交易', '操纵市场': r'操纵(?:证券)?市场', '信息披露违法': r'信息披露违法',
              '虚假记载': r'虚假记载', '未勤勉尽责': r'未勤勉尽责', '传播虚假信息': r'传播虚假信息'}


def regulatory_labels(text):
    evidence = []
    # Restrict to legal-characterization sentences, avoiding the party's defense section.
    for match in re.finditer(r'[^。\n]*构成[^。\n]*[。]?', text):
        sentence = match.group()
        if re.search(r'不构成|未构成|不应|申辩|辩称|提出|主张|认为不', sentence):
            continue
        if not re.search(r'构成.{0,110}(?:所述|规定|违法|行为)', sentence):
            continue
        for label, pattern in REGULATORY.items():
            if re.search(pattern, sentence):
                evidence.append({'label': label, 'start': match.start(), 'end': match.end(), 'text': sentence})
    return sorted({x['label'] for x in evidence}), evidence


def classifications():
    path = ROOT / 'raw/CSRC/documents.jsonl'
    regulatory = []
    for line, row in jsonlines(path):
        labels, evidence = regulatory_labels(row['text'])
        if not labels:
            continue
        obj = record('CSRC', path, line, row['text'], 'classification', labels, 'regulator_characterization_evidence',
                     '监管处罚与问询文件', document_id='CSRC:' + row['document_id'], title=row['title'], published_at=row['published_at'],
                     classification_evidence=evidence, subtype='监管认定主题',
                     quality_flags=['只取明确构成违法的认定句；不是完整法定案由体系；未独立人工验收'])
        obj['source_url'] = row['source_url']
        regulatory.append(finish(obj, 'regulatory_characterization_and_negated_defense_filter'))
    used_regulatory = []
    for row in sorted(regulatory, key=lambda x: x['id']):
        if row['text_hash'] in USED:
            continue
        USED.add(row['text_hash'])
        used_regulatory.append(row)
        if len(used_regulatory) == 200:
            break
    feed = [finish(x, 'source_event_labels') for x in original_rows('classification') if x['source_dataset'] == 'FEED']
    selected = list(used_regulatory)
    for row in sorted(feed, key=lambda x: x['id']):
        if len(selected) == TARGETS['classification']:
            break
        if row['text_hash'] not in USED:
            USED.add(row['text_hash'])
            row['quality_flags'] = ['由 FEED 事件标签转换；远程监督，未独立人工验收']
            selected.append(row)
    STATS['classification'] = {'regulatory_evidence_pool': len(regulatory), 'regulatory_selected': len(used_regulatory)}
    write('classification', selected)


METRICS = ['归属于上市公司股东的扣除非经常性损益的净利润', '扣除非经常性损益后的净利润',
           '归属于上市公司股东扣除非经常性损益后的净利润', '归属于母公司股东扣除非经常性损益后的净利润',
           '归属于上市公司股东净利润', '归属于母公司股东净利润', '归属于上市公司股东净资产',
           '扣非后归属于上市公司股东的净利润', '扣除非经常性损益后归属于上市公司股东的净利润',
           '归属于上市公司股东的净利润', '归属于母公司股东的净利润', '归属于上市公司股东的净资产',
           '经营活动产生的现金流量净额', '营业总收入', '主营业务收入', '其他业务收入', '营业收入', '营业总成本',
           '主营业务成本', '营业成本', '营业利润', '利润总额', '净利润', '总资产', '资产总额', '负债总额',
           '净资产', '所有者权益', '基本每股收益', '稀释每股收益', '货币资金', '投资收益',
           '归母净利润', '销售收入', '销售费用', '管理费用', '财务费用', '研发费用',
           '总负债', '资本公积', '盈余公积', '应收账款', '应付账款', '流动资产', '非流动资产',
           '流动负债', '非流动负债', '经营活动现金流量净额', '存货', '实收资本', '股本', '应收票据',
           '长期股权投资', '固定资产', '无形资产', '短期借款', '长期借款', '营业外收入', '营业外支出',
           '所得税费用', '预收款项', '预付款项', '税金及附加', '其他应收款', '其他应付款',
           '应付职工薪酬', '应交税费', '未分配利润', '存货跌价准备', '交易性金融资产',
           '应收账款余额', '应收票据余额', '存货余额', '利息收入', '利息支出', '净利息收入',
           '手续费及佣金净收入', '手续费及佣金收入', '手续费及佣金支出', '公允价值变动收益',
           '信用减值损失', '资产减值损失', '递延所得税资产', '递延所得税负债']
NUMERIC = re.compile(r'(?P<field>' + '|'.join(map(re.escape, sorted(METRICS, key=len, reverse=True))) +
                     r')[\s为达约：:是到计金额]*[（(]?(?:人民币)?[）)]?\s*(?P<number>[-−－]?\d[\d,，]*(?:\.\d+)?)\s*(?P<unit>亿元|万元|千元|元/股|元)')
RATIO = re.compile(r'(?P<field>加权平均净资产收益率|净资产收益率|资产负债率|营业利润率|销售毛利率|毛利率|净利率)'
                   r'[\s为达约：:是到计]*(?P<number>[-−－]?\d+(?:\.\d+)?)\s*(?P<unit>%|％)')


def report_subject(title):
    if not re.search(r'(?:20\d{2})\s*年?(?:年度|半年度|年报)', title):
        return None
    company = re.split(r'[:：]|20\d{2}\s*年?', title, maxsplit=1)[0].strip(' -：:')
    if not company or len(company) > 45 or re.search(r'公告|摘要|报告|修订|更正|关于', company):
        return None
    return company


def numeric_annotations(text, title, raw_text):
    labels = []
    company = report_subject(title)
    year_match = re.search(r'(20\d{2})\s*年?(?:年度|半年度|年报)', title)
    report_year = int(year_match[1]) if year_match else None
    explicit_years = set(int(x) for x in re.findall(r'(20\d{2})\s*年', raw_text))
    if len(explicit_years) > 1 or not company or not report_year:
        return []
    # A paragraph about subsidiaries or sensitivity scenarios needs broader context; select another.
    if re.search(r'如果|假设|假定|敏感性|预算|预计|计划|目标|预测|增加或减少|子公司|联营|合营|被合并方|被购买方|收购标的', raw_text):
        return []
    explicit_year = next(iter(explicit_years)) if explicit_years else None
    if explicit_year is not None and explicit_year != report_year:
        return []
    period = explicit_year or report_year
    if explicit_year is None and not re.search(r'报告期|本期|本年|当期|全年|年度|期末', raw_text):
        return []
    if re.search(r'半年度|半年报', title):
        period_label = f'{period}年上半年'
    else:
        period_label = f'{period}年'
    period_from = 'paragraph_explicit_year' if explicit_year is not None else 'report_title_and_current_period_phrase'
    scope = '母公司' if '母公司财务' in raw_text or '母公司报表' in raw_text else '合并' if re.search(r'合并报表|合并财务|合并口径', raw_text) and '母公司' not in raw_text else '未说明'
    prefix = len(text) - len(raw_text)
    for m in sorted([*NUMERIC.finditer(text, prefix), *RATIO.finditer(text, prefix)], key=lambda x: x.start()):
        value = m['number'].replace(',', '').replace('，', '').replace('−', '-').replace('－', '-')
        factor = {'亿元': Decimal(100000000), '万元': Decimal(10000), '千元': Decimal(1000), '元': Decimal(1), '元/股': Decimal(1), '%': Decimal('0.01'), '％': Decimal('0.01')}[m['unit']]
        field = m['field']
        before = re.split(r'[，,；;。\n]', text[prefix:m.start()])[-1][-18:]
        if field in {'净利润', '净资产', '扣除非经常性损益后的净利润'} and re.search(r'归属|扣除|扣非|每股', before):
            continue
        # In "比上年增加营业收入...", this is a change amount, not the metric itself.
        if re.search(r'增加|减少|增长|下降|提升|降低', before[-5:]):
            continue
        if '每股' not in field and m['unit'] == '元/股':
            continue
        field_period = period_label
        if re.search(r'(?:上年|去年|上一年)(?:度|同期|期末)?(?:实现|的|公司|为|\s)*$', before):
            field_period = f'{period - 1}年' + ('上半年' if '上半年' in period_label else '')
        elif re.search(r'(?:上期|前期)\s*$', before):
            # The preceding fiscal period is not always the preceding year.
            continue
        local_context = re.split(r'[；;。\n]', text[prefix:m.start()])[-1]
        business = re.search(r'(?:^|[，,；;])(?:其中)?(?P<scope>[^，,；;。\n]{2,100}(?:业务|产品|板块|渠道|分部|地区|服务))(?:的)?\s*$', local_context)
        adjustments = list(re.finditer(r'剔除[^，,；;。\n]{2,30}后|调整后|扣除[^，,；;。\n]{2,30}影响后', local_context))
        metric_context_start = m.start() - len(local_context)
        labels.append({'field': field, 'value': value, 'unit': m['unit'], 'normalized_value': str(Decimal(value) * factor),
                       'normalized_unit': 'ratio' if m['unit'] in {'%', '％'} else '元/股' if '每股' in field else '元', 'start': m.start(), 'end': m.end(), 'text': m.group(),
                       'subject': company, 'subject_evidence': {'start': len('报告：') + title.index(company), 'end': len('报告：') + title.index(company) + len(company), 'text': company},
                       'period': field_period, 'period_basis': period_from, 'period_granularity': 'half_year' if '上半年' in field_period else 'year', 'consolidation_scope': scope,
                       'business_scope': business['scope'] if business else '未说明',
                       'measurement_basis': adjustments[-1].group() if adjustments else '未说明调整',
                       'metric_context': {'start': metric_context_start, 'end': m.end(), 'text': text[metric_context_start:m.end()]},
                       'scope_note': '未说明表示输入没有给出合并/母公司口径，不猜测。', 'observation_kind': 'reported_metric'})
    return labels


def numerics():
    path = ROOT / 'raw/TigerBot-earning/tigerbot-earning-plugin.json'
    selected, docs, rejected = [], collections.Counter(), collections.Counter()
    for line, row in jsonlines(path):
        raw_text, title = row['content'], row.get('title', '')
        if len(raw_text) > 3500 or len(raw_text) < 20 or not re.search(r'营业|利润|资产|每股|成本|权益|现金流|货币资金|投资收益|利息|手续费|毛利率|净利率', raw_text):
            continue
        doc = digest(f'{title}|{row.get("publishTime")}')
        if docs[doc] >= 50:
            continue
        text = '报告：' + title + '\n正文：' + raw_text
        labels = numeric_annotations(text, title, raw_text)
        if not labels:
            rejected['context_or_pattern_not_sufficient'] += 1
            continue
        h = digest(norm(text))
        if h in USED:
            continue
        obj = record('TigerBot-earning', path, line, text, 'numeric', labels, 'explicit_metric_with_report_context', '年报与财务报告',
                     document_id=doc, title=title, published_at=row.get('publishTime'),
                     original_paragraph=raw_text, quality_flags=['公司来自报告标题，年份来自原文或报告标题及当期措辞', '未说明的会计口径保留未说明；未独立人工验收'])
        selected.append(finish(obj, 'numeric_context_and_decimal_unit_checks'))
        docs[doc] += 1
        USED.add(h)
        if len(selected) == TARGETS['numeric']:
            break
    STATS['numeric'] = {'document_groups': len(docs), 'not_selected': dict(rejected),
                        'field_count': sum(len(x['annotations']) for x in selected),
                        'scope_unspecified': sum(a['consolidation_scope'] == '未说明' for x in selected for a in x['annotations'])}
    write('numeric', selected)


def span(text, start, end):
    while start < end and text[start] in ' \t\n，,：:；;':
        start += 1
    while end > start and text[end - 1] in ' \t\n，,。.;；':
        end -= 1
    return {'start': start, 'end': end, 'text': text[start:end]}


def clear_causal(sentence):
    # Keep an entire grammatical sentence; multi-sentence enumerations are rejected.
    m = re.fullmatch(r'(.{5,140}?)(?:主要原因是|主要系|主要由于)(.{5,160})[。！？]?', sentence)
    if m:
        effect, cause = m.span(1), m.span(2)
    else:
        m = re.fullmatch(r'\s*(?:由于|因为)(.{5,140}?)[，,](?:因此|所以|从而|导致|使得)(.{5,160})[。！？]?', sentence)
        if not m:
            return None
        cause, effect = m.span(1), m.span(2)
    c, e = span(sentence, *cause), span(sentence, *effect)
    if len(e['text']) > 80 or re.search('[，,；;]', e['text']):
        return None
    if not c['text'] or not e['text'] or re.match(r'[①②③123一二三][、.．\s子]', c['text']):
        return None
    if re.match(r'\d{4}年(?:增长|下降)|[)）]|比如|例如', e['text']) or e['text'].count('(') != e['text'].count(')'):
        return None
    if re.search(r'一是|二是|三是|如下|以下|包括[:：]', c['text']):
        return None
    if re.search(r'[；;]|但|相较|此外|与此同时|关注|预计|近期|后续|未来|将|有望', c['text']):
        return None
    if re.match(r'以及|叠加|加之|并且|同时', e['text']):
        return None
    return {'type': 'causal', 'cause': c, 'effect': e, 'assertion': '预测或推测' if re.search(r'可能|预计|有望|或将|将会', sentence) else '原文陈述',
            'evidence': sentence, 'note': '标注原文表达的因果，不声称已验证经济因果。'}


OPINION = re.compile(r'(?P<holder>我们|本报告)(?P<cue>认为|预计|建议|看好|判断)[，,：:\s]*(?P<claim>[^。！？\n]{10,220})')
TARGET = re.compile(r'(?:20\d{2}\s*年(?:上半年|下半年)?[,，\s]*)?(?P<target>公司|行业|板块|市场|需求|供给|价格|估值|业绩|(?:[\u4e00-\u9fffA-Za-z]{2,14})(?:行业|板块|市场|业务|产品|产业|公司))')


def clear_opinion(sentence):
    matches = list(OPINION.finditer(sentence))
    if len(matches) != 1:
        return None
    m = matches[0]
    if sentence[m.end('claim'):].strip('。！？ \t'):
        return None
    target = TARGET.match(m['claim'])
    if not target:
        return None
    if re.search(r'一种|可能|是|认为|将|存在|带动|出现|保持|提升|改善|随着|对于|预计|建议|实现|有望|增长|关注|持续|把握|受益|看好|重视|重视|布局|继续|积极', target['target']):
        return None
    target_start = m.start('claim') + target.start('target')
    target_end = m.start('claim') + target.end('target')
    claim = span(sentence, m.start('claim'), m.end('claim'))
    polarity = '正向' if m['cue'] == '看好' else '未说明'
    time = re.search(r'20\d{2}\s*[-—–至]\s*20\d{2}\s*年|20\d{2}\s*年(?:上半年|下半年|[一二三四1-4]季度)?|未来\s*[一二三四五六七八九十\d]+\s*年|明年|今年|下半年|上半年', claim['text'])
    return {'type': 'opinion', 'holder': '报告作者', 'holder_evidence': span(sentence, *m.span('holder')),
            'target': sentence[target_start:target_end], 'target_evidence': span(sentence, target_start, target_end),
            'claim': claim, 'polarity': polarity, 'forecast_time': time.group() if time else '未说明',
            'note': '本任务抽取观点持有人、对象和命题；情感极性和预测时间只在原文明确时填写。'}


def causal_opinions():
    path = ROOT / 'raw/TigerBot-research/tigerbot-research-plugin.json'
    selected, counts, docs = [], collections.Counter(), collections.Counter()
    desired = {'causal': 1300, 'opinion': 1300}
    for line, row in jsonlines(path):
        if len(row['content']) > 3500:
            continue
        title, date = row.get('title', ''), row.get('publishTime')
        doc = digest(f'{title}|{date}')
        if docs[doc] >= 10:
            continue
        for sm in re.finditer(r'[^。！？\n]+[。！？]?', row['content']):
            sentence = sm.group().strip()
            if not 15 <= len(sentence) <= 300:
                continue
            if re.search(r'免责声明|风险揭示|版权|本报告所载|请谨慎参考|不代表.{0,30}立场|报告在编写|分析师声明|法律责任|不构成.{0,20}投资|仅供.{0,20}参考', sentence):
                continue
            annotation = clear_causal(sentence) if counts['causal'] < desired['causal'] else None
            if annotation is None and counts['opinion'] < desired['opinion']:
                annotation = clear_opinion(sentence)
            if annotation is None:
                continue
            if digest(norm(sentence)) in USED:
                continue
            obj = record('TigerBot-research', path, line, sentence, 'causal_opinion', [annotation], 'explicit_single_sentence_evidence',
                         '金融新闻与研报', document_id=doc, title=title, published_at=date,
                         parent_paragraph_hash=digest(norm(row['content'])),
                         parent_sentence_start=sm.start() + len(sm.group()) - len(sm.group().lstrip()),
                         quality_flags=['保留明确因果或明确报告作者观点；未独立人工验收'])
            selected.append(finish(obj, 'complete_evidence_fields_and_restricted_linguistic_cues'))
            counts[annotation['type']] += 1
            docs[doc] += 1
            USED.add(obj['text_hash'])
            # One natural sentence per original paragraph, rather than multiplying annotation records.
            break
        if all(counts[k] >= v for k, v in desired.items()):
            break
    STATS['causal_opinion'] = {'subtypes': dict(counts), 'document_groups': len(docs)}
    write('causal_opinion', selected)


def main():
    entities()
    events()
    relations()
    classifications()
    numerics()
    causal_opinions()
    report = {'requested_total': 35803, 'exported_total': sum(x['exported'] for x in STATS.values()), 'tasks': STATS,
              'quality_status': 'automated_content_checks_not_independent_gold', 'semantic_accuracy_or_f1': None}
    (DEST / '文本处理统计.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if report['exported_total'] != report['requested_total']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
