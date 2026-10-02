---
license: apache-2.0
language:
- zh
---

[Tigerbot](https://github.com/TigerResearch/TigerBot) 模型rethink时使用的外脑原始数据，财报类

- 共2500篇财报，抽取后按段落保存
- 发布时间区间为: 2022-02-28 至 2023-05-10

<p align="center" width="40%">


## Usage
```python
import datasets
ds_sft = datasets.load_dataset('TigerResearch/tigerbot-earning-plugin')
```