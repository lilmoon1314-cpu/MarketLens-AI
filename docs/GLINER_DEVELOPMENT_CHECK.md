# GLiNER2 开发验证

日期：2026-10-03。包版本2.0.0；模型`fastino/gliner2-multi-v1`，revision
`ce747d79a8e362d3dee0b0b26d1201f7f1a8615a`；Windows、Python3.12、CPU、batch4。
权重约1.23GB，位于忽略的`.local/huggingface/`。正式配置初值为char与中文value描述。

## 方法

四条人工编写的开发样例（不是冻结验收集）：

| 正文 | 预期sentiment | 预期value |
|---|---|---|
| 电池续航只有两小时，希望改进。 | negative | actionable |
| 包装完整，物流很快，操作也很方便。 | positive | actionable |
| 不错。 | positive | non_actionable |
| 加微信领优惠券，代理加盟。 | neutral | spam |

同一组合Schema、实际模型，对比两种切分与两种feedback_value描述；sentiment/topic标签仍为固定英文枚举。使用适配器阈值后的结果比较，单次推理耗时不含加载，不代表1000条吞吐。

| splitter | value描述 | sentiment匹配 | value匹配 | 推理秒 |
|---|---|---|---|---|
| whitespace | English | 3/4 | 1/4 | 0.505 |
| whitespace | 中文 | 3/4 | 1/4 | 0.423 |
| char | English | 2/4 | 3/4 | 0.449 |
| char | 中文 | 1/4 | 3/4 | 0.491 |

## 结论与限制

采用char/中文作为中文高价值路由的开发初值：电池样例actionable分数0.6497，超过既定0.60路由阈值；char/English同例0.5630会漏选。这个小样本不足以证明配置最优。两种char配置都把广告识别为actionable；char/中文把电池投诉识别为neutral。登记为质量风险，F14/F15需扩展独立标注集评估spam召回和负面情绪，不能宣称中文质量达标或据此降低阈值。

另一个显式model_smoke以两条短中文及一条300次重复长评论验证真实分数、顺序、模型复用和截断，1 passed，11.13秒含加载。它只验证接口可运行。上游CPU使用eager attention fallback和torch.jit弃用警告，未导致失败。

## 发行版兼容性

原锁1.3.2没有`set_word_splitter`，因此升级至正式2.0.0，仍使用span架构；其依赖要求使transformers锁为4.57.6、tokenizers0.22.2、huggingface-hub0.36.2。按完整Schema实际编码长度检查512位置上限，保留原文，截断推理视图。依据[官方接口说明](https://github.com/fastino-ai/GLiNER2)核对已安装源码与真实推理，不把main接口视为旧发行版接口。
