import csv
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from build_final_delivery import ROOT, FINAL, FILES, lines, answer_text


def main():
    report = json.loads((FINAL / '检查记录/全量检查结果.json').read_text(encoding='utf-8'))
    assert report['错误数'] == 0
    summary, active_sources = [], set()
    header = ['数据编号', '任务', '题目或原文', '答案', '解析（仅知识题）', '来源', '来源网址', '原始出处键', '检查状态']
    for name in FILES:
        with (FINAL / '数据' / (name+'.csv')).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f); writer.writerow(header)
            for i, r in lines(FINAL / '数据' / (name+'.jsonl')):
                active_sources.add(r['source_dataset'])
                row = [r['id'], name, r['text'], answer_text(r), r['annotations'].get('explanation','') if r['task']=='knowledge_rules' else '',
                       r['source_dataset'], r['source_url'], r['source_evidence_key'], '已完成程序检查；未认定为专业验收通过']
                writer.writerow(row)
                if i <= 3: summary.append(row)
        assert i == report['文件'][name]['目标条数']
    with (FINAL / '数据/先看样例.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w=csv.writer(f);w.writerow(header);w.writerows(summary)
    # Remove the unused evidence file created by the earlier build in this task.
    for p in (FINAL / '原始出处').glob('*.jsonl'):
        if p.stem not in active_sources:
            assert p.resolve().parent == (FINAL / '原始出处').resolve()
            p.unlink()
    for name in ['build_final_delivery.py','validate_final_delivery.py','prepare_text.py','prepare_knowledge.py',
                 'test_delivery_processing.py','finish_delivery.py','create_delivery_document.py']:
        shutil.copy2(ROOT/name, FINAL/'复现代码'/name)
    shutil.copy2(ROOT/'check_delivery_package.py', FINAL/'复现代码/检查交付包.py')
    samples = ROOT / 'quality_work/delivery_semantic_samples.jsonl'
    shutil.copy2(samples, FINAL/'检查记录/固定随机抽查样本.jsonl')
    limitations = {'实际发现和处理': [
        {'问题':'部分实体原标注漏掉了正文中的其他公司名称','处理':'保留发布者四类标注，公开写明漏标风险；没有宣称全部实体完整标注。'},
        {'问题':'公司名称的标题前空格导致证据位置偏移','处理':'按标题实际位置计算；全量字符核对通过。'},
        {'问题':'被合并方利润误归上市公司','处理':'剔除该类上下文；增加针对性测试。'},
        {'问题':'归母/扣非限定词遗漏','处理':'增加完整指标名，并拒收剩余不明确的简称匹配。'},
        {'问题':'观点对象带有持续关注等动作词','处理':'过滤该类对象匹配并重新选择样本。'},
        {'问题':'长句被截断、原因和结论边界不明确','处理':'只在完整句中提取；限制复杂前置效果描述。'},
        {'问题':'免责声明混入因果数据，以及业务收入、调整利润需要保留限定','处理':'过滤免责声明；保留业务范围、调整条件和完整指标上下文。'},
        {'问题':'答案冲突、解析仅图片、空白解析和不完整选项','处理':'从交付题池剔除，并以其他完整题替换。'}],
        '已运行针对性测试数':25,'全量原记录一致性检查条数':239673,'全量检查错误数':0,
        '专业准确率':None,'解释':'固定随机样本保留作复查依据，不能据此冒充双人标注或全部专业答案正确。'}
    (FINAL/'检查记录/检查发现与处理.json').write_text(json.dumps(limitations,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest_entries=[]
    for p in ROOT.glob('download_manifest*.json'):
        obj=json.loads(p.read_text(encoding='utf-8'))
        entries=obj if isinstance(obj,list) else obj.get('files',[])
        manifest_entries.extend(x for x in entries if x.get('status')=='downloaded')
    used=[]
    for item in json.loads((FINAL/'检查记录/原始文件与证据数量.json').read_text(encoding='utf-8')):
        hit=[x for x in manifest_entries if x.get('file','').replace('\\','/')==item['file'].replace('\\','/') and x.get('sha256')==item['full_download_sha256']]
        used.append({**item,'download_url':hit[-1]['url'] if hit else None,'capture_note':'证监会公开文本汇总文件，逐篇网址见包内原记录。' if 'CSRC' in item['file'] else '固定版本下载地址及原文件哈希。'})
    (FINAL/'来源说明/实际使用来源与版本.json').write_text(json.dumps(used,ensure_ascii=False,indent=2),encoding='utf-8')
    hashes=[]
    for p in sorted(FINAL.rglob('*')):
        if p.is_file() and p.name != '文件校验值.json':
            hashes.append({'file':p.relative_to(FINAL).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest()})
    (FINAL/'检查记录/文件校验值.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
    target=ROOT/'金融测评数据成品_李昊东_2026-10-02.zip'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for p in sorted(FINAL.rglob('*')):
            if p.is_file(): archive.write(p,p.relative_to(FINAL).as_posix())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert '金融测评数据交付说明_李昊东.docx' in archive.namelist()
    receipt={'file':target.name,'bytes':target.stat().st_size,'sha256':hashlib.file_digest(target.open('rb'),'sha256').hexdigest(),
             'zip_crc':'passed','records':239673,'knowledge':203870,'text':35803,'contains_original_evidence':True}
    (ROOT/'quality_work/最终交付回执.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
