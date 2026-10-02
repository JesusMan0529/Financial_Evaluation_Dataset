"""Create one plain Chinese explanation; numerical claims come from checked files."""
import json
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from build_final_delivery import LABELS

ROOT = Path(__file__).resolve().parent
FINAL = ROOT / '交付成品'
DOC = FINAL / '金融测评数据交付说明_李昊东.docx'


def main():
    report = json.loads((FINAL / '检查记录/全量检查结果.json').read_text(encoding='utf-8'))
    assert report['错误数'] == 0
    knowledge = json.loads((FINAL / '检查记录/知识题处理统计.json').read_text(encoding='utf-8'))
    textstats = json.loads((FINAL / '检查记录/文本处理统计.json').read_text(encoding='utf-8'))
    d = Document()
    for part in [d._element, d.styles._element]:
        for border in list(part.iter(qn('w:pBdr'))):
            border.getparent().remove(border)
    section = d.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(.65)
    section.left_margin = section.right_margin = Inches(.7)
    normal = d.styles['Normal']
    normal.font.name = '宋体'; normal.font.size = Pt(10.5)
    normal._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15
    for stylename, size in [('Title', 22), ('Heading 1', 15), ('Heading 2', 12)]:
        s = d.styles[stylename]
        s.font.name = '黑体'; s.font.size = Pt(size); s.font.color.rgb = RGBColor(0,0,0)
        s._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
    footer = section.footer.paragraphs[0]
    footer.alignment = 2
    footer.add_run('金融测评数据交付说明  ·  ')
    field = OxmlElement('w:fldSimple'); field.set(qn('w:instr'), 'PAGE'); footer._p.append(field)

    def p(s):
        d.add_paragraph(s)
    def h(s):
        d.add_heading(s, level=1)
    def table(headers, rows, widths=None):
        t = d.add_table(rows=1, cols=len(headers)); t.autofit = False
        for c, s in zip(t.rows[0].cells, headers):
            c.text = s
            for run in c.paragraphs[0].runs: run.bold = True
            sh = OxmlElement('w:shd'); sh.set(qn('w:fill'), 'E9EEF2'); c._tc.get_or_add_tcPr().append(sh)
        repeat = OxmlElement('w:tblHeader'); t.rows[0]._tr.get_or_add_trPr().append(repeat)
        for values in rows:
            cells = t.add_row().cells
            for c, s in zip(cells, values): c.text = str(s)
        borders = OxmlElement('w:tblBorders')
        for side in ['top','left','bottom','right','insideH','insideV']:
            b = OxmlElement('w:'+side); b.set(qn('w:val'),'single'); b.set(qn('w:sz'),'4'); b.set(qn('w:color'),'C5CDD3'); borders.append(b)
        t._tbl.tblPr.append(borders)
        for row in t.rows:
            nosplit = OxmlElement('w:cantSplit'); row._tr.get_or_add_trPr().append(nosplit)
            for i, c in enumerate(row.cells):
                if widths: c.width = Inches(widths[i])
                margins = OxmlElement('w:tcMar')
                for side in ['top','bottom','left','right']:
                    m = OxmlElement('w:'+side); m.set(qn('w:w'),'75'); m.set(qn('w:type'),'dxa'); margins.append(m)
                c._tc.get_or_add_tcPr().append(margins)
                for paragraph in c.paragraphs:
                    paragraph.paragraph_format.space_after = Pt(3)
                    paragraph.paragraph_format.space_before = Pt(1)
                    for run in paragraph.runs: run.font.size = Pt(9.5)
        d.add_paragraph().paragraph_format.space_after = Pt(0)
        return t
    def page(): d.add_page_break()
    def link(label, url):
        paragraph = d.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(4)
        paragraph.add_run(label + '：')
        hyperlink = OxmlElement('w:hyperlink')
        rid = paragraph.part.relate_to(url, 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink', is_external=True)
        hyperlink.set(qn('r:id'), rid)
        r = OxmlElement('w:r'); pr = OxmlElement('w:rPr')
        color = OxmlElement('w:color'); color.set(qn('w:val'),'005A9C'); pr.append(color)
        r.append(pr); tx = OxmlElement('w:t'); tx.text = url; r.append(tx); hyperlink.append(r); paragraph._p.append(hyperlink)

    d.add_heading('金融测评数据交付说明', 0)
    p('整理：李昊东　　日期：2026年10月2日')
    p('本次交付新增知识题203,870条、文本任务35,803条，共239,673条。已完成下载、清洗、任务处理和全量程序检查。压缩包包含数据、对应的原始记录、检查结果和处理代码。你不需要配置环境，也不需要自己运行模型。')
    h('1. 交了多少数据')
    table(['文件 / 任务','实际条数'], [
        ['知识与规则','203,870'],['实体抽取','8,100'],['事件抽取','8,100'],['关系抽取','6,303'],
        ['文本分类','6,700'],['数值与财务字段','4,000'],['因果与观点','2,600'],['合计','239,673']], [5.1,2.0])
    p('知识题均含题目、完整选项、答案和文字解析。文本的六类任务都有原文和按统一字段整理的答案；因果与观点各1,300条。CSV和JSONL是同一批数据的两种格式，不重复计数。')
    p('本次按你确认的203,870和35,803补齐总量，不要求七个知识模块分别达到旧表中的参考分配。数值任务剔除了主体、期间不清的记录，最终保留4,000条；分类调整为6,700条。')
    p('之前表里的两个“0”表示那两个模块没有数量差额，因为候选数量已超过参考分配；并不表示没有找到数据。')
    h('2. 怎么直接交给师姐')
    p('把“金融测评数据交付说明_李昊东.docx”和成品ZIP一起发过去即可；ZIP里也放了同一份说明。解压后，先看“数据/先看样例.csv”，再看对应任务的CSV。用Excel或WPS即可查看。程序读取时用JSONL，每行是一条数据。')

    page(); h('3. 六类任务到底做了什么')
    table(['任务','用直白的话解释','本次怎么做'], [
        ['实体抽取','找出公司、股票、市场对象和经济概念。','采用CFSC现成标签，核对文字位置，去掉重复标注及明显异常记录。'],
        ['事件抽取','找出发生了什么、涉及谁、多少股、什么日期。','采用FEED原有事件与角色，核对每个角色能否在公告中找到。'],
        ['关系抽取','写清“谁—什么关系—谁/什么”。','采用FinCorpus.CN原三元组，不采用其模型预测字段，剔除缺原文证据等记录。'],
        ['文本分类','给一篇文字归类；同一篇可以有多个类别。','公告沿用事件类别；处罚文件只从监管认定句提取主题，过滤否定和申辩句。'],
        ['数值抽取','找出哪个公司的什么指标，是多少，单位是什么，属于哪一年。','从财报标题和正文提取公司、期间、指标、值与单位，用精确小数换算。'],
        ['因果与观点','因果：为什么、产生什么结果。观点：谁认为、对什么对象、说了什么。','研报中只选明确因果句或明确“我们/本报告”观点句，保留文字证据。']], [1.0,2.6,3.5])
    p('方案采用“现成标注数据＋针对原文的处理规则”。前三类已有足量数据，无须从零训练模型；数值、处罚分类、因果和观点没有合适的现成完整答案，已自行处理。')
    h('4. 标签表（第一版）')
    table(['任务','允许使用的标签 / 答案字段'], [
        ['实体','Corporate=公司；Stock=股票；Market=市场对象；Economy=经济概念。'],
        ['事件','股权冻结、股份回购、股东减持、股东增持、股权质押；保留每个事件对应的角色。'],
        ['关系','开展、拥有、位于、合作、投资、属于、应用于。本次未出现“任职于”，不计入实际覆盖。'],
        ['分类','公告使用上述五个事件相关主题；处罚使用内幕交易、操纵市场、信息披露违法、虚假记载、未勤勉尽责、传播虚假信息。'],
        ['数值','指标、原数值、原单位、换算值、公司、期间、合并/母公司口径、业务范围、调整条件和原文位置。'],
        ['因果 / 观点','因果：原因、结果、原文语气、证据。观点：持有人、对象、完整观点、极性、预测时间及证据。']], [1.0,6.1])
    p('完整字段及事件角色中英对照保存在“数据/标签表.json”。原文未说明的口径、极性和时间填写“未说明”，不凭空补答案。分类是主题标签；例如质押相关公告也可能讲解除质押。')

    page(); h('5. 实际验证了什么')
    table(['检查','实测结果'], [
        ['最终数量','知识203,870；文本35,803；每个CSV与对应JSONL条数一致。'],
        ['逐条原记录核对','全部239,673条均能在包内找到下载原始记录；题目、发布者答案、源标签与转换结果已核对。'],
        ['重复检查','知识按题干和选项归一化去重；六类文本去掉空白和字形差异后跨任务去重。'],
        ['标注位置','实体、事件角色、关系主客体、金额及因果观点的证据位置逐条检查。'],
        ['数值换算','万元、亿元、负号、每股单位和百分比按精确小数复算；公司位置和期间字段检查通过。'],
        ['处理程序','25项针对易错情况的测试通过。全量检查报告错误数为0。'],
        ['数据文件与压缩包','保存文件SHA-256；最终ZIP进行CRC校验，检查文件是否损坏。']], [1.6,5.5])
    p('检查过程中已处理：缺完整选项、重复选项、冲突答案、文字与答案明显不一致、解析依赖外部图片、只有空白解析、乱码、因果长句截断、观点对象混入动词、被合并方利润错归主体、归母/扣非限定词遗漏及标题空格造成的位置偏移。')
    h('6. 使用时必须知道的几件事')
    p('数量缺口已补齐。PPT要求的95%、98%等专业准确率还没有实测；格式正确、原文对得上，不代表专业答案一定正确。文件已明确记录：完成程序检查，但没有通过专业金标验收。“金标”就是经独立确认的标准答案。')
    p('实际抽查发现CFSC可能漏掉正文中的其他公司名称。因此本包保留原发布者的四类标注，不保证找全每个实体。FEED采用远程监督，即通过已有信息自动生成标注，并非逐条人工标注；事件角色对应关系、历史与计划状态仍可能有误。关系源标签也未逐条检查专业含义。')
    p('数值期间只做到年份或上半年层级；没有恢复原PDF页码、完整表格和全部财务字段。业务范围及剔除费用等调整条件另存字段和原文，不能把分业务收入或调整后利润当作公司总收入或原利润。未明确口径的字段写“未说明”。因果记录原文的说法；观点未明确好坏方向时写“未说明”。')
    p('知识题保留题库公布答案，不统一视作2026年的现行法规答案。七个知识模块由关键词初步分流，版本辨析等类别的覆盖较少。公开数据可能已被模型训练使用；本包尚未划分隐藏测试集，也未完成公司/时间隔离或全面语义去重。')
    p('这份成品用于团队审阅数据、确认标签和运行试验。若要宣布达到PPT验收线，仍需独立确认的标准答案与正式测量；本次没有编造这一结果。')

    page(); h('7. 数据来自哪里')
    sources = [
        ['FinCorpus',str(knowledge['source_counts'].get('FinCorpus',0))+'道知识题','发布卡Apache-2.0'],
        ['CFLUE（仅知识部分）',str(knowledge['source_counts'].get('CFLUE',0))+'道知识题','CC-BY-NC-SA-4.0'],
        ['CFSC','8,100条实体任务','未找到独立许可文件'],
        ['FEED','8,100条事件＋6,500条公告分类','未找到独立许可文件；远程监督'],
        ['E-2CNN / FinCorpus.CN','6,303条关系任务','仓库MIT'],
        ['TigerBot财报','4,000条数值任务','发布卡Apache-2.0'],
        ['TigerBot研报','2,600条因果观点任务','发布卡Apache-2.0'],
        ['证监会行政处罚','200条监管分类','官方公开文本；采集截至2026-10-01']]
    table(['来源','实际进入交付的数量','来源说明'], sources, [1.65,2.8,2.65])
    p('已排除原八大项目及其全部已识别子数据集、镜像和改名版本：ConvFinQA、DocFinQA、FinanceBench、TAT-DQA、MME-Finance、InvestorBench、FinMTEB、FinBen/PIXIU。完整排除清单随包提供。CFLUE应用部分未使用。')
    p('排除按项目及子数据集执行，没有使用已有项目凑数量。不同公开来源仍可能收录相同题目或公告；按你确认的要求，本次不与原46,130条知识题和9,197条文本任务逐条比较。')
    p('四类来源均有：上市公司公告、年报与财报、金融新闻/研报、监管处罚。监管来源本次只有处罚决定书，没有交易所问询函。CSMAR公开入口已查看，但没有取得可用数据文件，不计入下载量。')
    p('包内数据保留各来源署名和原许可信息，没有把所有来源改成同一许可证。CFLUE限非商业使用并要求署名、同方式共享。CFSC和FEED许可范围尚不明确，本包用于本地科研和团队审阅，尚未公开上传。')
    h('官方入口（点击可打开）')
    for label, url in [
        ('FinCorpus','https://huggingface.co/datasets/Duxiaoman-DI/FinCorpus'),
        ('CFLUE','https://github.com/aliyun/cflue'),('CFSC','https://github.com/Ya-dongLi/CFSC'),
        ('FEED','https://github.com/seukgcode/FEED'),('FinCorpus.CN','https://github.com/CGCL-codes/E-2CNN'),
        ('财报','https://huggingface.co/datasets/TigerResearch/tigerbot-earning-plugin'),
        ('研报','https://huggingface.co/datasets/TigerResearch/tigerbot-research-plugin'),
        ('处罚','https://www.csrc.gov.cn/csrc/c101928/zfxxgk_zdgk.shtml')]: link(label,url)

    page(); h('8. 文件怎么读：看这三个例子就够了')
    p('例1：原文“报告期内，公司实现营业收入2.40亿元”。标题为鸿泉物联2022年年度报告。答案是：公司=鸿泉物联；期间=2022年；指标=营业收入；原值=2.40亿元；换算后=240,000,000元；原文没有明确合并口径，因此口径=未说明。')
    p('例2：原文“1月份重卡销量大幅度下滑，主要系去年同期销量高位，今年1月春节销售淡季，终端需求走弱。”原因是后半句三项；结果是“1月份重卡销量大幅度下滑”。不能把原因和结果倒过来。')
    p('例3：观点写成“我们认为……”，持有人是报告作者；对象和完整观点从后文提取。没有作者姓名就不编姓名；没有明确看涨看跌就不编正负向。')
    table(['包内目录','你需要知道的用途'], [
        ['数据','7类任务的CSV和JSONL、21条展示样例、标签表。'],
        ['原始出处','入选数据及解释支持记录对应的下载原记录。不是重新生成的摘要。'],
        ['检查记录','数量、逐条检查结果、文件哈希和检查中发现的问题。'],
        ['来源说明','下载地址、版本、原文件哈希、旧项目排除清单及来源README/许可文件。'],
        ['复现代码','采集与处理脚本。阅读和交付数据不需要运行这些代码。']], [1.2,5.9])
    p('CSV中的“原始出处键”，对应原始出处文件里的evidence_key。每条JSONL也写明source_evidence_file。原下载文件中的行号或数组序号保留在source_row；包内只收录需要的原记录，因此使用出处键查找，不直接拿原行号定位包内行。')
    p('“来源可追溯”在本包指可以找到公开数据文件和其中的原记录。它不代表每一道题都已经找到最初题库网页、权威法规条文或原PDF页码。出处文件中的原记录哈希和下载清单中的整文件哈希是两个不同层级。')
    p('字符位置从0开始，终点取后一位。比如“甲公司”的起点是0、终点是3。位置检查只是确认文字对得上，专业答案是否正确要另看原文含义和适用规则。')
    d.core_properties.author = '李昊东'
    d.core_properties.title = '金融测评数据交付说明'
    d.core_properties.subject = '新增知识与规则及六类文本任务的数据、出处和检查说明'
    d.save(DOC)
    labeltable = {'版本': '2026-10-02', '英文代码中文对照': LABELS, '实体范围': ['Corporate','Stock','Market','Economy'],
                  '事件类型': ['EquityFreeze','EquityRepurchase','EquityUnderweight','EquityOverweight','EquityPledge'],
                  '关系': ['开展','拥有','位于','合作','投资','属于','应用于'],
                  '监管主题': ['内幕交易','操纵市场','信息披露违法','虚假记载','未勤勉尽责','传播虚假信息'],
                  '数值字段': ['field','value','unit','normalized_value','normalized_unit','subject','subject_evidence','period','period_basis','period_granularity','consolidation_scope','business_scope','measurement_basis','metric_context','start','end','text'],
                  '因果字段': ['cause','effect','assertion','evidence'], '观点字段': ['holder','holder_evidence','target','target_evidence','claim','polarity','forecast_time'],
                  '缺失约定': '原文不明确时写未说明；不凭空补字段。', '位置约定': 'Python字符位置[start,end)，从0开始。',
                  '计数约定': '知识一题一条；文本一个输入和一个任务算一条，不按实体/事件/字段数拆计。',
                  '验收状态': '已完成程序检查；未完成独立专业金标验收。'}
    (FINAL / '数据/标签表.json').write_text(json.dumps(labeltable, ensure_ascii=False, indent=2), encoding='utf-8')
    print(DOC)


if __name__ == '__main__':
    main()
