# 金融大模型测评数据集

这份数据是为金融大模型测评项目整理的，主要补充“知识与规则”和“文本理解与抽取”两个方向。知识与规则有 **203,870 条**，文本任务有 **35,803 条**，合计 **239,673 条**。

使用公开数据集已有的题目和标注，再补充财报、研报和监管处罚文本，用 Python 完成筛选、去重、字段统一和规则抽取。没有使用大模型批量生成答案。

## 下载与打开

直接到 [Releases](https://github.com/JesusMan0529/Financial_Evaluation_Dataset/releases/latest) 下载 `Financial_Evaluation_Dataset_v1.0.0.zip`，解压后即可使用。压缩包包含本说明和完整数据目录。

第一次看数据，先打开 `数据/先看样例.csv`；想了解处理方法，可以看 `brief_explanation.pdf`。各任务同时提供 CSV 和 JSONL：CSV 方便查看，JSONL 方便写程序读取，两种格式存的是同一批数据。

仓库中超过 50 MiB 的数据文件通过 Git LFS 保存。如果使用 Git 克隆，需要先安装 [Git LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)，再执行：

```bash
git lfs install
git clone https://github.com/JesusMan0529/Financial_Evaluation_Dataset.git
```

需要完整数据时，请下载 Releases 中的压缩包。GitHub 的 `Code → Download ZIP` 不一定包含 LFS 文件正文。

## 数据数量

| 方向 | 任务 | 条数 |
| --- | --- | ---: |
| 知识与规则 | 金融选择题及答案、解析 | 203,870 |
| 文本理解与抽取 | 实体抽取 | 8,100 |
| 文本理解与抽取 | 事件抽取 | 8,100 |
| 文本理解与抽取 | 关系抽取 | 6,303 |
| 文本理解与抽取 | 文本分类 | 6,700 |
| 文本理解与抽取 | 数值与财务字段抽取 | 4,000 |
| 文本理解与抽取 | 因果与观点抽取 | 2,600 |
| **合计** | | **239,673** |

文本六类任务共 35,803 条。其中，因果与观点包含因果 1,300 条、观点 1,300 条。每道知识题计一条；每条文本与对应任务计一条，不按其中的实体、事件或财务字段个数重复计数，CSV 和 JSONL 也不重复计数。

## 文件放在哪里

```text
README.md
Financial_Evaluation_Dataset/
├── brief_explanation.pdf
└── financial_evaluation_dataset/
    ├── 数据/          七类任务的 CSV、JSONL、样例和标签表
    ├── 原始出处/      入选数据对应的原始记录及出处
    ├── 检查记录/      数量、筛选统计、检查结果和文件校验值
    ├── 来源说明/      来源网址、下载版本、原项目说明和许可文件
    └── 复现代码/      采集、筛选、抽取、导出及检查脚本
```

后文中的 `数据/`、`原始出处/` 等路径，均相对于 `Financial_Evaluation_Dataset/financial_evaluation_dataset/`。

## 来源与处理方法

| 成品任务 | 实际使用来源 | 处理方法 |
| --- | --- | --- |
| 知识与规则 | [FinCorpus](https://huggingface.co/datasets/Duxiaoman-DI/FinCorpus) 176,504 条；[CFLUE](https://github.com/aliyun/cflue) 27,366 条 | 解析题干、选项、答案和解析，剔除缺项、答案冲突、缺少上下文等记录，按规范化题干去重 |
| 实体抽取 | [CFSC](https://github.com/Ya-dongLi/CFSC) 8,100 条 | 保留原发布者标注，统一字段并检查字符位置，筛去部分明显不合适的记录 |
| 事件抽取 | [FEED](https://github.com/seukgcode/FEED) 8,100 条 | 保留事件及角色标注，补充角色文本在输入中的出现位置 |
| 关系抽取 | [E-2CNN 中的 FinCorpus.CN](https://github.com/CGCL-codes/E-2CNN) 6,303 条 | 保留主语、关系、宾语，检查主语和宾语是否出现在原文中 |
| 文本分类 | FEED 6,500 条；[中国证监会公开处罚文本](https://www.csrc.gov.cn/csrc/c101928/zfxxgk_zdgk.shtml) 200 条 | 公告按原事件类型分类；处罚文本按明确的违法认定提取主题，保留原文证据 |
| 数值与财务字段 | [TigerBot 财报语料](https://huggingface.co/datasets/TigerResearch/tigerbot-earning-plugin) 4,000 条 | 按字段名称、数字和单位抽取，补充公司、期间、口径及单位换算结果 |
| 因果与观点 | [TigerBot 研报语料](https://huggingface.co/datasets/TigerResearch/tigerbot-research-plugin) 2,600 条 | 从明确表达因果或观点的句子中提取字段，保留原句和字符位置 |

文本来源覆盖上市公司公告、财报、财经新闻与研报、监管处罚四类。监管材料使用处罚文本，本版没有问询函数据。CSMAR 没有实际下载入选数据，因此未计入来源和数量。

`FinCorpus` 和 `FinCorpus.CN` 是两个不同来源，前者用于知识题，后者用于关系抽取。`来源说明/` 还保留了部分未入选项目的说明文件，例如 FIRE-Bench、FinanceIQ、CFQA、FinCausal；这些项目没有计入成品数量。具体下载地址、版本和校验值见 `来源说明/实际使用来源与版本.json`。

本次排除了项目此前收集的 ConvFinQA、DocFinQA、FinanceBench、TAT-DQA、MME-Finance、InvestorBench、FinMTEB、FinBen/PIXIU 八个项目及其子数据集。排除清单见 `来源说明/旧项目排除清单.json`。此处按数据来源排除，没有拿全部旧数据正文逐条比对。

## 标签和字段

完整标签表见 `数据/标签表.json`。

- **实体**：公司、股票、市场对象、经济概念，分别对应 `Corporate`、`Stock`、`Market`、`Economy`，沿用原来源的定义。
- **事件**：股权冻结、股份回购、股东减持、股东增持、股权质押；角色包含公司、持有人、股数、日期等。
- **关系**：开展、拥有、位于、合作、投资、属于、应用于。
- **分类**：公告使用五类事件主题；处罚文本使用内幕交易、操纵市场、信息披露违法、虚假记载、未勤勉尽责、传播虚假信息。可以同时有多个标签。
- **财务字段**：字段名称、原始数值和单位、统一后的数值和单位、公司、期间、会计口径及原文证据。
- **因果与观点**：因果记录原因、结果和原句；观点记录表达者、对象、观点内容、倾向及原文证据。

JSONL 中常用字段如下：

| 字段 | 含义 |
| --- | --- |
| `id` | 样本编号 |
| `task` | 任务名称 |
| `text` | 需要处理的输入文本；知识题包含题干和选项 |
| `annotations` | 答案或抽取结果 |
| `source_dataset`、`source_url` | 数据来源名称和网址 |
| `source_evidence_file`、`source_evidence_key` | 包内原始记录的位置和索引 |
| `label_method` | 标注或处理方法 |
| `review_status`、`benchmark_eligible` | 当前检查状态；本版未标为独立验收后的金标数据 |

字符位置从 0 开始，使用 Python 的 `[start, end)` 规则，即 `text[start:end]` 对应标注文本。原文没有明确给出的信息写为“未说明”，不会为了填满字段而猜测。因果标签记录的是原文的因果表述。

## 用 Python 读取

不需要安装模型。安装 Python 后，在仓库根目录运行下面的代码即可读取第一条知识题：

```python
import json
from pathlib import Path

folder = Path("Financial_Evaluation_Dataset/financial_evaluation_dataset/数据")
with (folder / "知识与规则.jsonl").open(encoding="utf-8") as f:
    sample = json.loads(next(f))

print(sample["text"])
print(sample["annotations"])
```

读取其他任务时，将文件名换成对应的 JSONL 名称。大文件建议逐行读取，避免一次性全部装入内存。

## 文件检查与处理代码

使用 Python 3.11 或更高版本，在仓库根目录执行：

```bash
python "Financial_Evaluation_Dataset/financial_evaluation_dataset/复现代码/检查交付包.py"
```

脚本检查文件是否齐全、大小和 SHA-256 是否一致，并核对包内的数量报告，不需要第三方库。

`检查记录/全量检查结果.json` 保存了 239,673 条数据的原始记录比对、字符位置、单位换算和 CSV 条数等检查结果。文件完整性检查与模型效果评测是两件事。

`复现代码/` 保留了整理过程中使用的脚本。重新采集和生成数据时，需要按脚本中的目录设置补齐原始下载文件与中间文件；成品包没有包含全部下载缓存。只读取数据、运行文件完整性检查和已有处理测试，不需要这些缓存。

处理测试可在 `复现代码/` 目录中运行：

```bash
python -m unittest test_processing test_delivery_processing
```

## 质量指标

请开发者自行根据需求进行特化质量指标检测。

## 使用说明

使用时请保留原数据来源和许可说明。CFLUE 数据集采用 CC BY-NC-SA 4.0，其他来源按各自许可使用；CFSC、FEED 的随包说明未给出明确的独立数据许可。本仓库的整理和发布不替代原数据权利人的授权。

数据集开源且非商用，供个人或组织自行研究使用。
