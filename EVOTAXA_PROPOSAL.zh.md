# EvoTaxa：截点感知的分类体系引导演化建模

## 1. 核心思想

EvoTaxa 是一个统一框架，用来建模研究领域、方法机制、政策工具、社会议题如何随时间演化。

核心主张是：

> 时间化分类体系解释一个领域在哪里发生结构性分化；演化图解释这种分化为什么发生，也就是通过瓶颈、机制、适配、替代和权衡去解释演化原因。

EvoTaxa 融合三条已有路线：

- TaxoAdapt：多维分类体系构建，以及横向扩展和纵向细化。
- ResearchForesight/ForeSci：截点感知语料构建、时间切片快照、基准任务和发布纪律、前瞻性评估。
- Methodological Evolution Graph：方法实体、类型化因果边、基于证据的瓶颈-机制-权衡记录，以及谱系搜索。

最终的系统不是单纯的分类体系构建器，也不是单纯的方法图谱。它是一个在时间截点约束下，发现、解释、审计领域演化的系统。

## 2. 动机

现有研究基础设施通常把论文组织成文档集合、引用网络、关键词索引或者静态主题簇。这些表示方式适合检索，但不擅长解释领域演化。

它们通常很难回答下面这些问题：

- 哪些子方向是真正新出现的，哪些只是改了名字？
- 一个宽泛主题什么时候开始分裂成多个机制层面的方向？
- 哪个反复出现的瓶颈推动了一个方法家族、评估协议或政策工具的演化？
- 哪个新方向是真正的后继机制，而不只是热度上升？
- 哪些证据支持一条演化关系边？这些证据能不能回到原文审计？

EvoTaxa 通过三类对象解决这些问题：

1. 用时间化分类体系捕捉领域结构和粒度变化。
2. 用局部演化图捕捉分类体系区域内部的方法/机制转移。
3. 用证据记录让每个重要演化判断可以追溯。

## 3. 总体流程

```text
原始语料
  -> 领域采集与元数据增强
  -> 相关性筛选与核心/支撑标注
  -> 截点感知的冻结语料
  -> 增强型时间化分类体系归纳
  -> 分类体系演化事件检测
  -> 分类体系约束的演化图构建
  -> 谱系、分支和瓶颈搜索
  -> 预测钩子 / 分析钩子 / 基准任务
```

核心设计原则是：

```text
分类体系决定去哪里看。
演化图解释结构为什么变化。
```

也就是说，分类体系负责限定观察区域和结构边界；演化图负责解释结构变化背后的机制原因。

## 4. 第一层：截点感知的语料构建

这一层借鉴 ResearchForesight 的截点感知思路，但 EvoTaxa 不应该绑定 ForeSci 的具体字段格式。

更合理的设计是：系统只要求一个最小内部数据契约，具体字段映射交给配置文件管理。这样同一套代码既能跑 AI 论文，也能跑社会科学文献、政策文本、访谈材料、新闻报道或机构报告。

### 输入

- 原始文档元数据。
- 可用的全文、摘要、报告正文或访谈文本。
- 发布时间、来源、机构、发表场所、引用量、arXiv id 等时间和来源信息。
- 领域配置、种子查询、字段映射配置。

### 处理

1. 合并和去重原始文档。
2. 根据领域配置生成启发式画像。
3. 运行相关性筛选。
4. 将文档标记为 `core`、`support`、`audit_only` 或 `exclude`。
5. 只用被接受的角色冻结截点感知语料。
6. 给每个文档分配时间切片。

### 推荐输出

这一层应该输出规范化文档、语料清单、筛选标签、核心/支撑语料和截点说明。具体文件名属于实现细节，可以在实现文档中定义。

截点边界是硬约束。任何截点之后的文档都不能进入分类体系归纳、演化关系边抽取、检索或答案生成。

## 5. 第二层：增强型时间化分类体系

当前分类体系系统已经支持多维度、时间切片式增长。EvoTaxa 要把它从一个标签树升级成更丰富的时间化结构图。

### 维度

对于 AI 研究，默认维度可以是：

- `tasks`（任务）
- `methodologies`（方法体系）
- `datasets`（数据集）
- `evaluation_methods`（评价方法）
- `real_world_domains`（真实应用领域）

对于社会科学，维度可以变成：

- `social_issues`（社会议题）
- `actors`（行动者）
- `mechanisms`（机制）
- `interventions`（干预）
- `measurement_strategies`（测量策略）
- `contexts`（情境）
- `outcomes`（结果）
- `public_frames`（公共话语框架）

这些维度不应该写死在代码里，而应该放在配置文件里管理。

### 分类体系节点是什么？

分类体系节点是 EvoTaxa 用来定位领域演化的基本语义单元。它不只是关键词、主题标签、聚类编号或文档标签。一个节点表示一个语义边界清楚的领域区域，包含：

- 名称和别名。
- 语义边界。
- 纳入标准和排除标准。
- 支撑文档。
- 代表性文档和反例文档。
- 时间状态。
- 与演化实体和关系的连接。

换句话说，一个节点要回答：

```text
这是什么类型的领域对象？
哪些文档应该属于这里？
哪些相邻概念不应该被放进来？
这个区域是如何出现、分裂、合并或衰退的？
有哪些实体和机制在这里面演化？
```

节点可以很宽，也可以很细。宽节点用来组织领域结构，细节点用来捕捉新出现的子方向。EvoTaxa 预期在科研语料里节点会随着领域分化变得越来越具体；但在社会科学场景里，节点也可能发生跨维度连接、稳定化或重新语境化。

例子：

```text
错误信息治理 / interventions（干预）
  node_id: interventions__prebunking
  label: prebunking interventions（预防式干预）
  boundary: 在错误信息暴露前预先揭示操纵手法的干预
  excludes: 暴露后才进行的事实核查，且没有预先接种式干预

错误信息治理 / public_frames（公共话语框架）
  node_id: public_frames__free_speech_vs_safety
  label: free speech versus platform safety（言论自由与平台安全框架）
  boundary: 把内容治理争议表述为言论自由、平台安全、伤害预防之间张力的公共叙事
  excludes: 只讨论具体审核算法性能、且不涉及公共论辩框架的论文

政治极化 / measurement_strategies（测量策略）
  node_id: measurement__affective_polarization
  label: affective polarization measurement（情感极化测量）
  boundary: 测量党派或群体之间情感距离、厌恶、信任差异或社会距离的方法
  excludes: 只测量政策立场差异、但不测量群体情感或社会距离的研究

平台劳动 / mechanisms（机制）
  node_id: mechanisms__algorithmic_management
  label: algorithmic management（算法管理）
  boundary: 平台通过评分、派单、动态定价、可见性排序或自动惩罚来组织劳动过程的机制
  excludes: 只研究普通企业数字化管理、且不涉及平台中介或算法分配机制的研究

教育不平等 / interventions（干预）
  node_id: interventions__high_dosage_tutoring
  label: high-dosage tutoring（高频辅导干预）
  boundary: 通过高频、结构化、小组或一对一辅导来改善弱势学生学习结果的干预
  excludes: 一次性课后辅导、普通补课项目，或没有明确学习结果评估的资源投入

AI 治理 / policy_instruments（政策工具）
  node_id: policy_instruments__algorithmic_audits
  label: algorithmic audits（算法审计）
  boundary: 通过第三方审计、内部审计、合规评估或影响评估来识别和治理算法风险的政策工具
  excludes: 只提出抽象伦理原则、但没有审计流程、责任主体或评估对象的文本
```

同一个表面短语在不同维度里可以是不同节点。例如 `algorithmic audit` 在某次运行里可以是 `measurement_strategy`，在另一次运行里可以是 `policy_instrument`。所以 EvoTaxa 把节点视为带有维度约束的语义区域，而不是一个全局固定标签。

### 节点数据结构

每个分类体系节点不应该只有标签和描述，而应该携带更完整的边界、证据和状态信息：

```json
{
  "node_id": "",
  "dimension": "",
  "canonical_label": "",
  "aliases": [],
  "definition": "",
  "inclusion_criteria": "",
  "exclusion_criteria": "",
  "distinctive_phrases": [],
  "sibling_negative_phrases": [],
  "example_sentences": [],
  "created_time_slice": "",
  "node_status": "birth|emerging|growing|mature|fragmenting|declining",
  "support_documents": [],
  "representative_documents": [],
  "counterexample_documents": [],
  "assignment_uncertainty": 0.0,
  "semantic_coherence": 0.0,
  "temporal_novelty": 0.0,
  "linked_evolution_entities": [],
  "dominant_bottlenecks": [],
  "dominant_mechanisms": []
}
```

### 节点增强

借鉴 TaxoAdapt，每个节点都应该增强出：

- 区分性 key phrases。
- 该节点相关文档中可能出现的代表性句子。
- 用来区分相邻兄弟节点的反向短语。
- 纳入标准和排除标准。

这些增强信息会改善：

- 文档分类。
- 节点边界清晰度。
- 检索质量。
- 人工审计。
- 下游方法/机制实体抽取。

### 分类体系演化事件

EvoTaxa 应该显式记录分类体系层面的演化事件：

- `birth`：新节点出现。
- `split`：一个节点分化成多个更细方向。
- `merge`：两个节点在语义或经验上变得耦合。
- `rename`：术语变化，但概念连续性仍然存在。
- `decline`：支持度或增长趋势变弱。
- `fragmentation`：原本相对一致的节点内部出现多个不兼容机制。
- `cross_link`：两个不同维度的节点形成结构性连接。

这些事件应该作为一等产物写出，而不是只从最终快照里临时推断。

```json
{
  "event_id": "",
  "event_type": "split",
  "time_slice": "",
  "source_node_ids": [],
  "target_node_ids": [],
  "support_documents": [],
  "reason": "",
  "confidence": 0.0
}
```

## 6. 第三层：更好的扩展触发机制

当前分类体系扩展主要依赖“文档密度”和“未归属文档量”。EvoTaxa 应该使用更丰富的触发信号。

### 触发信号

```text
扩展触发分数 =
  文档密度
+ 未归属文档量
+ 语义异质性
+ 归属不确定性
+ 时间突增信号
+ 实体突增信号
+ 瓶颈集中度
+ 评价/测量方式变化信号
```

这个公式不是说这些项必须简单等权相加。真正实现时，每个信号应该先在同一个时间片内归一化，再由任务配置文件决定权重。核心意思是：分类体系扩展不应该只看“文档变多了”，还要看边界是否失效、内部是否分化、是否出现新实体、新瓶颈或新的评价/测量方式。

### 触发信号定义

| 中文信号 | 配置字段 | 它衡量什么 | 直观含义 | 例子 |
|---|---|---|---|---|
| 文档密度 | `document_density` | 一个节点里被分配进来的文档数量，可以按时间片、兄弟节点或历史基线归一化。 | 这个节点可能太拥挤，需要更细的结构。 | `LLM-assisted methods` 在一年内突然聚集大量论文。 |
| 未归属文档量 | `unassigned_mass` | 不能被现有分类体系节点高置信度接住的文档比例或数量。 | 当前分类体系缺了一个语义区域，需要横向扩展。 | 很多关于 `synthetic survey respondents` 的论文既不像传统调查方法，也不像普通文本即数据研究。 |
| 语义异质性 | `semantic_heterogeneity` | 已经分配到同一个节点的文档内部是否语义差异很大，可由向量表示、抽取出的实体或 LLM 边界判断来估计。 | 一个节点里面混进了多个含义，可能需要拆分。 | `algorithmic auditing` 同时包含技术偏差测量、法律合规、平台问责三类论文。 |
| 归属不确定性 | `assignment_uncertainty` | 文档被分配到多个兄弟节点时，分数是否很接近。 | 节点边界不清楚，可能需要改边界、加别名，或者生成合并候选。 | 一篇论文同时像 `LLM annotation` 和 `survey automation`，且置信度接近。 |
| 时间突增信号 | `temporal_burst` | 某个节点、术语、实体或局部簇相比过去是否突然增长。 | 可能有新方向出生，或者旧方向发生快速转向。 | 新一代 LLM 系统出现后，`RAG evaluation` 相关论文突然增多。 |
| 实体突增信号 | `entity_burst` | 一个节点内部是否突然出现很多新的演化实体，例如方法、数据集、测量方法、干预设计、评价协议。 | 不只是文档数量增加，而是内部机制开始分化。 | 错误信息研究节点里突然出现预防式干预游戏、接种式信息、平台提示、实地实验等多种干预实体。 |
| 瓶颈集中度 | `bottleneck_concentration` | 多篇文档是否集中指向同一个限制、失败模式、数据缺口、效度问题或测量问题。 | 领域可能正在围绕一个共同瓶颈形成新分支。 | 很多 LLM 标注论文反复讨论可靠性、构念效度和提示词敏感性。 |
| 评价/测量方式变化信号 | `evaluation_or_measurement_shift_signal` | 领域的评价方式或测量方式是否发生变化。 | 一个方法区域可能正在围绕新的证据标准重新组织。 | 计算社会科学主题从词典计数转向基于向量表示的构念测量；AI 方法从基准准确率转向 LLM-as-a-judge 评价。 |

### 触发解释

- 高未归属文档量：触发横向扩展（width expansion）。
- 高文档密度的叶子节点且包含多个语义簇：触发纵向细化（depth expansion）。
- 兄弟节点重叠：生成合并候选或别名候选。
- 新术语突然爆发：生成新节点出生候选。
- 同一概念换了新术语：生成重命名候选。
- 成熟节点中反复出现同一瓶颈：交给演化图分析。
- 新评价协议或测量策略与某个机制簇绑定：生成跨维度连接。

这可以避免分类体系扩展只被文档数量驱动。

## 7. 第四层：分类体系约束的演化图

这是 EvoTaxa 最关键的升级，灵感来自方法演化图。

EvoTaxa 不构建一个覆盖全语料的巨大全局图，而是在分类体系区域内部构建局部演化图。

### 为什么需要局部图

全局方法图构建成本高、噪声大。分类体系约束的演化图更实际，因为分类体系节点可以：

- 限定候选文档池。
- 提供语义上下文。
- 减少候选对爆炸。
- 提高关系边类型判定精度。
- 让局部谱系搜索更有意义。

### 图节点

对于 AI 研究：

```json
{
  "method_id": "",
  "canonical_name": "",
  "aliases": [],
  "first_seen_date": "",
  "support_documents": [],
  "taxonomy_nodes": [],
  "entity_type": "architecture|training_recipe|agent_loop|retrieval_strategy|evaluation_protocol|dataset_construction|analysis_method"
}
```

对于社会科学：

```json
{
  "mechanism_id": "",
  "canonical_name": "",
  "aliases": [],
  "first_seen_date": "",
  "support_documents": [],
  "taxonomy_nodes": [],
  "entity_type": "intervention|policy_instrument|explanatory_mechanism|measurement_strategy|institutional_response|public_frame"
}
```

本质上，图节点不是只能表示“方法”。在社会科学场景里，它可以表示政策工具、干预设计、解释机制、测量策略、制度回应或公共话语框架。

### 关系边类型

核心关系词表是：

- `extends`：增加一个能力或组件。
- `improves`：沿某个维度优化已有机制。
- `replaces`：替换一个承重机制或关键工具。
- `adapts`：把方法/机制迁移到新的任务、模态、人群、地区或制度环境。
- `uses_component`：复用某个方法/机制作为组件。
- `compares`：引用、比较或评估另一个方法/机制。
- `background`：只有背景性提及，没有明确方法或机制关系。

强因果子集是：

```text
extends, improves, replaces, adapts
```

这些边用于谱系搜索。

### 证据记录

每条非背景边都应该携带证据记录：

```json
{
  "edge_id": "",
  "source_entity": "",
  "target_entity": "",
  "edge_type": "improves",
  "source_document": "",
  "target_document": "",
  "time_delta": "",
  "bottleneck": {
    "description": "",
    "quote": "",
    "dimension": ""
  },
  "mechanism": {
    "description": "",
    "quote": ""
  },
  "tradeoff": {
    "description": "",
    "quote": ""
  },
  "confidence": 0.0,
  "substring_verified": true
}
```

字符串匹配验证非常重要：

> 如果瓶颈、机制或权衡的引用片段无法在原文中找到，这条边不能进入可信图。

未验证的边可以保留在候选文件里，但不能作为金标准证据或高置信预测钩子使用。

### 自适应 schema（数据契约）演化

为了让 EvoTaxa 真正迁移到社会科学，schema（数据契约）不能只是提示词里写死的一段标签说明。我们应该把 schema 本身也当作可演化对象。

这里重点有两类 schema：

- `relation_schema`：定义有哪些关系类型、每种关系是什么意思、允许哪些实体对、需要哪些证据槽位。
- `entity_evidence_schema`：定义一个领域里可以抽取哪些实体类型，以及这些实体和关系必须由哪些证据槽位支撑。

每类 schema 都应该支持三种模式：

- `fixed`（固定模式）：使用配置文件里人工写好的 schema。这是基准任务和消融实验的比较锚点。
- `inferred`（推断模式）：在正式抽取前，让 LLM/智能体根据语料样本、分类体系节点和少量种子样例推断领域 schema。
- `adaptive`：先从 fixed 或 inferred schema 启动，再根据抽取失败、引用验证失败、低置信边、重复实体类型、分类体系-图反馈生成 schema 修订。

推荐配置项包括：实体 schema 模式、关系 schema 模式、证据 schema 模式、种子 schema 来源、schema 推断样本量、schema 修订最小支持数和最大修订轮数。

关键约束是：schema 可以进化，但不能静默漂移。每次变化都要写出版本、差异、支持样例和是否晋升的决策。

#### 关系 schema 演化

关系 schema 是对当前 MEG 风格关系边词表的增强。关系类型不能只是 `improves` 这种字符串，而应该是一个结构化契约：

```json
{
  "edge_type": "improves",
  "label": "Improves",
  "definition": "",
  "source_role": "newer mechanism",
  "target_role": "older mechanism",
  "allowed_source_entity_types": [],
  "allowed_target_entity_types": [],
  "directionality": "directed",
  "temporal_constraint": "source_after_target",
  "evidence_slots": ["bottleneck", "mechanism", "tradeoff"],
  "positive_cues": [],
  "negative_cues": [],
  "counterexamples": [],
  "strong_edge": true,
  "confidence": 0.0,
  "schema_source": "fixed|inferred|adaptive"
}
```

AI 研究场景下，默认关系类型可以保持：

```text
extends, improves, replaces, adapts, uses_component, compares, background
```

但社会科学场景下，系统可以推断或晋升更贴近领域的关系类型，例如：

```text
diffuses_to, institutionalizes, reframes, operationalizes, mediates, moderates, evaluates, contests
```

演化流程如下：

1. 从配置文件读取固定关系 schema。
2. 采样文档、分类体系节点、实体提及和候选实体对。
3. 如果 `relation_schema_mode = inferred`，先推断候选关系类型、定义和证据要求。
4. 对候选 schema 做规范化：不能有重复标签，必须有清晰方向性，必须定义源/目标角色，必须声明证据槽位。
5. 把 schema 注入批量关系抽取和关系边证据判断提示词。
6. 审计输出：可信边、候选边、被拒绝的关系对、关系混淆、未验证证据。
7. 给每条边打分：关系置信度、引用落地性、时间顺序、分类体系局部性、schema 匹配度、证据槽完整度。
8. 把被拒绝的关系对作为负向先验和关系反例反馈回 schema。
9. 如果是 adaptive 模式，提出 schema 修订：新增关系、合并关系、拆分含混关系、重命名关系、收紧证据要求。
10. 对 schema 修订候选运行 schema 修订裁判。裁判可以晋升、拒绝，或者标记为需要人工审查。
11. 只有达到支持阈值并通过裁判决策的修订才能晋升，并写成新的 schema 版本。

这样我们会同时拥有两种实验设置：固定 schema 的图用于公平比较，自适应 schema 的图用于跨领域迁移。

关系抽取应该支持两种运行模式：

- `fixed_schema`：模型拿到封闭关系 schema，只能在这个 schema 下接受或拒绝候选对。
- `adaptive_schema`：模型仍然基于当前 schema 抽取，但被拒绝的候选对、缺失的证据槽位、重复出现的 schema 不匹配会反过来成为 schema 修订的候选信号。

被拒绝的关系对不是垃圾数据，而是负向证据。它们需要写出明确原因，例如 `weak_co_mention`、`comparison_only`、`temporal_violation`、`no_mechanism_evidence`、`schema_mismatch`、`unsupported_by_quotes`。这点在社会科学里尤其重要，因为共现不等于存在因果、制度或机制层面的关系。

#### 实体和证据 schema 演化

实体 schema 和证据 schema 也应该演化。AI 论文和社会科学文本暴露出来的对象并不一样。AI 研究中重要实体可能是架构、训练配方、检索策略、数据集、评价协议；社会科学中重要实体可能是政策工具、机构、干预、群体、公共话语框架、机制、结果、测量策略。

一个实体 schema 条目可以是：

```json
{
  "entity_type": "policy_instrument",
  "definition": "",
  "inclusion_criteria": "",
  "exclusion_criteria": "",
  "aliases": [],
  "allowed_dimensions": [],
  "example_mentions": [],
  "negative_examples": [],
  "quality_rules": []
}
```

一个证据 schema 条目可以是：

```json
{
  "slot": "intervention_mechanism",
  "definition": "",
  "required": true,
  "quote_required": true,
  "allowed_source": "source|target|either",
  "validation": "substring|semantic_overlap|human_audit"
}
```

这一层的反馈来自抽取行为本身：

- 如果大量高质量提及被反复归为 `unknown`，提出新增实体类型。
- 如果两个实体类型经常规范化到同一组名称，提出合并。
- 如果某个实体类型边界不清，增加排除标准和负例。
- 如果某类关系边的必要引用经常找不到，收紧证据槽位或降低该关系类型的置信等级。
- 如果社会科学文本反复表达行动者、语境、干预、结果，而当前证据 schema 只要求瓶颈和机制，就提出领域证据槽位。

例如 AI 治理试点可能推断出：

```text
entity types: model_risk_frame, audit_mechanism, regulatory_instrument, accountability_actor, compliance_metric
evidence slots: problem_definition, governance_mechanism, institutional_context, observed_outcome, tradeoff
```

这个设计比完全自由的智能体更稳：LLM 可以推断和修订 schema，但每次修订都必须被约束、落盘、评估，并且能和固定基线做对比。

## 8. 第五层：分类体系-图反馈循环

分类体系和演化图不应该是两个独立模块。

### 从分类体系到图

分类体系提供：

- 局部文档池。
- 节点路径和语义边界。
- 维度上下文。
- 候选对约束。
- 跨节点邻域。

### 从图到分类体系

演化图提供：

- 节点拆分的证据。
- 节点合并的证据。
- 节点内部的方法/机制谱系。
- 瓶颈集中信号。
- 跨维度依赖。
- 节点状态更新。

例如：

- 如果一个分类体系节点内部包含多条互不连接的强因果谱系，它可能需要拆分。
- 如果两个兄弟节点共享大量方法/机制实体和关系边，它们可能需要合并或跨维度连接。
- 如果一个成熟节点反复引用同一瓶颈，同时出现多个新机制，它可能进入 `fragmenting` 状态。
- 如果一个新实体在多个时间切片中出现，并开始获得适配关系边，它可能应该成为一个新分支。

## 9. 第六层：谱系和分支搜索

EvoTaxa 应该支持在强因果图上做谱系重建。

### 最小版本

先实现：

- 置信度加权 DFS。
- 时间约束 beam search。
- 分支点提取。

### 完整版本

进一步加入自引导时间树搜索。

候选先验：

```text
edge_prior =
  edge_confidence
* temporal_coherence
* taxonomy_locality
* evidence_strength
```

链路得分：

```text
chain_score =
  normalized_length
+ mean_edge_confidence
+ search_visit_score
+ bottleneck_resolution_score
+ taxonomy_trajectory_score
```

搜索结果应该返回：

- 祖先链路。
- 后继链路。
- 分支点。
- 未解决瓶颈路径。
- 替代路径。
- 跨领域适配路径。

## 10. 预测和分析钩子

主要下游产物是 `forecast_hooks.jsonl`。

```json
{
  "hook_id": "",
  "hook_type": "unresolved_bottleneck|successor_mechanism|replacement_path|evaluation_shift|cross_domain_adaptation|fragmenting_node",
  "taxonomy_node": "",
  "evolution_chain": [],
  "root_bottleneck": "",
  "candidate_successor": "",
  "support_edges": [],
  "support_documents": [],
  "risk_or_tradeoff": "",
  "cutoff_valid": true,
  "confidence": 0.0
}
```

这些钩子可以用于：

- 基准任务构建。
- 研究规划。
- 想法评估。
- 社会科学机制分析。
- 政策/干预演化分析。

## 11. 输出产物

proposal 层面不规定具体目录结构，但每次运行都应该产出下面几类可复现、可审计的结果：

| 产物类别 | 内容 | 作用 |
|---|---|---|
| 语料产物 | 规范化文档、语料清单、筛选标签、核心/支撑语料 | 保证截点、来源和文档角色可复现 |
| 分类体系产物 | 增强节点、时间快照、文档分配、节点质量分数、演化事件 | 记录领域结构如何出现、扩展、拆分、合并或衰退 |
| schema 产物 | 固定 schema、推断 schema、自适应修订、最终 schema、修订报告 | 防止关系和实体定义静默漂移 |
| 演化图产物 | 演化实体、别名合并、实体提及、可信关系边、候选关系边、未验证关系边、证据记录 | 解释分类体系变化背后的机制链路 |
| 搜索和轨迹产物 | 谱系链、分支点、演化轨迹、状态转移 | 支持后继机制、替代路径和未解决瓶颈分析 |
| 钩子产物 | 预测钩子、社会科学分析钩子、钩子评分报告 | 支持基准任务构建、研究规划和社会机制分析 |
| 审计产物 | LLM 裁判记录、未验证证据、低置信节点、质量报告 | 支持人工复核和错误定位 |

具体文件名可以在实现文档中定义。proposal 只要求这些产物类别存在，并且每个关键判断都能追溯到输入文档、时间切片、schema 版本和原文证据。

## 12. 分类体系质量评估

借鉴 TaxoAdapt 裁判的思想，但要把它变成生产级产物。

### 评估指标

- 维度一致性：节点是否属于它声明的维度。
- 父子粒度：子节点是否真的比父节点更具体。
- 兄弟一致性：兄弟节点是否处于相近粒度。
- 节点唯一性：两个节点是否重复表达同一概念。
- 文档相关性：分配到节点的文档是否真的属于该节点。
- 覆盖度：子节点是否覆盖了父节点中足够多的高质量文档。
- 时间稳定性：节点跨时间切片是否保持语义一致。
- 边界清晰度：纳入/排除标准是否能区分相邻节点。

### 输出

```json
{
  "node_id": "",
  "dimension_alignment": 0.0,
  "granularity": 0.0,
  "sibling_coherence": 0.0,
  "uniqueness": 0.0,
  "document_relevance": 0.0,
  "coverage": 0.0,
  "temporal_stability": 0.0,
  "boundary_clarity": 0.0,
  "judge_notes": ""
}
```

低质量节点不应该直接作为高置信图抽取或基准任务的种子，除非经过人工审计。

## 13. EvoTaxa 如何改进 ForeSci

### 方向预测

旧形式：

> 哪个分类方向会增长？

新形式：

> 哪条机制级后继路径最可能从截点可见的瓶颈和谱系中出现？

### 瓶颈-机会发现

旧形式：

> 找出一个瓶颈和一个机会。

新形式：

> 找出由类型化因果边和证据引用支撑的“瓶颈到机制”转移。

### 战略性研究规划

旧形式：

> 对候选方向排序。

新形式：

> 用谱系中心性、瓶颈开放度、证据强度、分支成熟度和权衡风险给候选方向排序。

### 投稿定位

旧形式：

> 判断发表场所匹配度和证据升级需求。

新形式：

> 用分类体系和演化图判断一个贡献到底是方法创新、评价创新、适配、组件复用还是应用贡献。

## 14. 社会科学扩展

EvoTaxa 可以通过替换实体词表迁移到社会科学。

### 分类体系维度

- `social_issues`（社会议题）
- `actors`（行动者）
- `mechanisms`（机制）
- `interventions`（干预）
- `measurement_strategies`（测量策略）
- `contexts`（情境）
- `outcomes`（结果）
- `public_frames`（公共话语框架）

### 演化图实体

- 政策工具。
- 干预设计。
- 解释机制。
- 测量策略。
- 制度回应。
- 公共话语框架。
- 行为机制。

### 关系边解释

- `extends`：给已有政策或机制增加新组件。
- `improves`：在成本、采用率、目标人群定位或结果等维度上改进干预。
- `replaces`：用一种机制或政策工具替换另一种。
- `adapts`：把干预迁移到新群体、地区或机构环境。
- `uses_component`：借用一个子机制。
- `compares`：经验上比较多个干预或机制。
- `background`：背景性提及。

### 示例分析

- 错误信息研究如何从内容审核转向平台治理和接种式干预。
- 极化研究如何从基于调查的态度测量转向社会网络和平台中介机制。
- AI 治理如何从模型风险框架演化到制度问责、审计和监管设计。
- 教育不平等干预如何从资源获取转向学习分析、辅导和家庭/社区机制。

### 双层演化视图

社会科学的演化不应该被强行压成一种图或一种叙事。有些领域像科研方法演化，核心是概念不断分化、分类体系粒度越来越细；另一些领域会出现旧主题回归、问题被重新语境化、制度周期、公共框架迁移等现象。EvoTaxa 应该同时支持这些情况，但不能把循环回归写死成默认解释。

推荐设计是双层视图：

```text
微观视图：证据支撑的局部机制
宏观视图：自适应模式综合
```

#### 微观视图

微观视图解释局部演化：

- 哪些实体、概念、方法、干预或测量工具发生了变化？
- 它们之间由哪种类型化关系连接？
- 哪条原文引用支撑这条边？
- 这条边影响了哪个分类体系节点或状态转移？
- 这条边属于哪条演化轨迹？

这个视图应该贴近当前 EvoTaxa 产物：

```text
分类体系节点
实体
类型化关系边
关系边得分
证据引用
状态转移
演化轨迹
```

它是证据层，应该局部、可检查，并能解释某条关系边或演化轨迹为什么成立。

#### 宏观视图

宏观视图从微观证据里总结领域层面的规律。它不应该预设所有领域都是周期性的，而是应该在多个候选宏观模式上估计模式画像：

```text
分化           # 分类体系变得更细
汇聚           # 多个分支汇合成共同框架
混合           # 不同分支的方法或机制组合
重新语境化     # 旧机制迁移到新媒介、制度或技术环境
循环回归       # 旧主题在新条件下回归
制度化         # 临时实践变成正式工具、标准或治理流程
替代           # 新机制替代旧机制
碎片化         # 领域分裂成多个弱连接方向
稳定化         # 术语和关系随时间稳定下来
```

宏观层应该先结构、后解释。规则或统计检测器先从 EvoTaxa 产物里估计模式得分；LLM 可以负责总结解释，但不应该从零决定模式。

示例输出：

```json
{
  "domain": "computational social science methods",
  "period": "2015-2026",
  "dominant_patterns": [
    {"pattern": "differentiation", "score": 0.86},
    {"pattern": "hybridization", "score": 0.73},
    {"pattern": "recontextualization", "score": 0.58},
    {"pattern": "recurrence", "score": 0.22}
  ],
  "interpretation": "该领域主要表现为分化，同时文本即数据、因果推断和 LLM 辅助标注之间的混合趋势增强；循环回归信号较弱。"
}
```

#### 模式证据

模式得分应该来自已有产物：

```text
分化（differentiation）：
  分类体系拆分率
  新子节点出现率
  分类体系深度增加
  演化轨迹分支因子

混合（hybridization）：
  跨维度连接率
  跨分类体系轨迹数量
  同一实体跨多个维度出现的频率

汇聚（convergence）：
  多个前序分支指向同一节点或实体
  演化轨迹合并
  原本分离节点之间共享词表上升

重新语境化（recontextualization）：
  旧关系模式在新行动者、媒介、技术或制度环境中复用
  证据角色结构相似，但语境词发生变化

循环回归（recurrence）：
  旧主题和新主题之间的语义相似度
  较大的时间间隔
  共享角色或证据槽位
  语境变化而不是完全重复

制度化（institutionalization）：
  支撑文档随时间增加
  可信关系边反复出现
  schema 趋于稳定
  出现政策、标准、协议、审计或治理类实体

碎片化（fragmentation）：
  兄弟节点增长较快
  轨迹汇聚度较低
  分支点很多，但共享后继较弱

稳定化（stabilization）：
  schema 修订减少
  关系类型组合趋于稳定
  同一分类体系区域内反复出现高置信关系边
```

#### 可视化

可视化也应该是双层的：

```text
微观视图：
  局部分类体系子树 + 选中的演化轨迹 + 证据引用

宏观视图：
  自适应模式画像 + 时间轴带 + 代表性演化轨迹
```

这样避免画成一张不可读的全局大图。微观视图是证据显微镜；宏观视图是理论层面的规律综合。

## 15. 实施路线图

### 阶段 1：分类体系升级

目标：在加入图层之前，先提高分类体系质量。

任务：

- 加入节点增强。
- 加入纳入/排除标准。
- 加入节点级质量判断。
- 加入显式分类体系演化事件。
- 加入低置信节点和重叠节点报告。

预期产物：增强后的分类体系节点、显式演化事件、节点质量分数和分类体系审计报告。

### 阶段 2：轻量方法演化图

目标：先为一个领域构建局部方法/机制演化图。

推荐试点领域：

```text
llm_agent（LLM 智能体）
```

范围：

- 先只处理 `methodologies` 和 `evaluation_methods`。
- 只使用截点可见文档。
- 使用标题、摘要和可用全文。
- 先从节点内部的候选实体对开始，而不是一上来做全局引用解析。
- 加入关系 schema 的固定、推断、自适应三种模式。
- 加入可配置的实体 schema 和证据 schema，支持跨领域抽取。
- 保存 schema 版本、差异和晋升决策。
- 加入批量 LLM 关系抽取，要求引用支撑证据，并保存被拒绝实体对的审计记录。
- 加入关系边打分，显式评估时间因果性、schema 匹配、引用落地性和分类体系局部性。

预期产物：最终关系 schema、最终实体 schema、最终证据 schema、schema 修订记录、演化实体清单、实体提及、关系抽取报告、被拒绝关系对、关系边得分和证据记录。

### 阶段 3：演化钩子

目标：把图结构转成预测候选和任务候选。

任务：

- 提取分支点。
- 提取未解决瓶颈。
- 提取后继机制。
- 提取替代路径和适配路径。
- 构建 `forecast_hooks.jsonl`。

预期产物：演化链、分支点和预测钩子。

### 阶段 4：演化轨迹建模升级

目标：用演化轨迹推断替代简单谱系串联。

任务：

- 实现时间一致性打分。
- 加入图感知先验。
- 加入避免重复访问关系边的分支感知轨迹构造。
- 与 beam search 和 greedy DFS 比较。

预期产物：演化轨迹、轨迹评估、领域状态和状态转移。

### 阶段 5：ForeSci 集成

目标：改进基准任务构建。

任务：

- 从 `forecast_hooks.jsonl` 生成任务候选。
- 比较旧任务候选和 EvoTaxa 任务候选。
- 评估专家偏好、可追溯性和隐藏目标对齐度。

预期产物：EvoTaxa 任务候选，以及与旧任务候选的质量对比报告。

### 阶段 6：社会科学试点

目标：证明跨领域分析价值。

候选领域：

- AI 治理。
- 错误信息。
- 政治极化。
- 教育不平等。
- 平台劳动。

预期产物：社会科学分类体系节点、社会机制关系边、社会科学分析钩子、关系拒绝记录、关系边评分和案例研究报告。

## 16. 实现原则

本文档只约束算法层面的对象、流程和证据标准，不绑定具体代码组织或执行方式。实现时需要遵守下面几个原则：

- 配置驱动：领域维度、字段映射、实体类型、关系类型、证据槽位和触发信号都应该由配置管理。
- 产物可追溯：分类体系节点、演化事件、关系边、证据记录、schema 修订和预测钩子都要落盘，便于复现实验和人工审计。
- 截点隔离：任何截点之后的文档不能进入训练、归纳、抽取、检索或判断过程。
- 双轨 schema：固定 schema 用于公平比较，自适应 schema 用于跨领域迁移。
- 证据优先：高置信演化关系必须有可验证引用；没有通过原文验证的关系只能作为候选或审计材料。
- 跨领域适配：代码可以复用研究论文场景的文件命名，但算法内部应使用“演化实体”这一更通用的概念，避免把社会科学对象强行压成“方法”。

## 17. 评估方案

### 分类体系评估

比较：

- 当前 ResearchForesight 分类体系。
- ResearchForesight + 节点增强。
- ResearchForesight + 节点增强 + 分类体系裁判剪枝。
- 配置驱动的 EvoTaxa 分类体系，用于非 ForeSci schema 的社会科学语料。

指标：

- 维度对齐。
- 粒度合理性。
- 兄弟节点一致性。
- 唯一性。
- 文档相关性。
- 覆盖度。
- 人工审计通过率。

### 图评估

比较：

- 基于线索词的方法演化资产。
- 分类体系约束的轻量方法演化图。
- 加入证据验证的轻量方法演化图。
- 加入时间谱系搜索的轻量方法演化图。

指标：

- 关系边类型准确率。
- 证据验证通过率。
- 瓶颈引用有效性。
- 人工评分的谱系一致性。
- 预测钩子有用性。

### 下游评估

比较：

- 现有 ForeSci 任务候选。
- EvoTaxa 生成的任务候选。
- 社会科学分析钩子。

指标：

- 专家偏好。
- 可追溯性。
- 隐藏未来目标对齐度。
- 证据到决策漂移的降低幅度。
- 瓶颈/机会表述的具体性提升。
- 对社会机制、政策工具或干预路径的解释有效性。

## 18. 论文定位

可能的标题：

> EvoTaxa: Cutoff-Aware Taxonomy-Guided Evolution Modeling for Scientific and Social Foresight

核心定位：

> TaxoAdapt adapts taxonomies to evolving corpora. Methodological evolution graphs expose typed method lineages. EvoTaxa unifies these ideas under temporal cutoff constraints: taxonomy snapshots localize the evolving structure, and evidence-grounded evolution graphs explain the mechanism-level transitions inside that structure.

中文表述：

> TaxoAdapt 解决演化语料上的分类体系适配问题；方法演化图揭示类型化的方法谱系；EvoTaxa 把两者统一到截点感知设置中：分类体系快照定位领域结构如何演化，证据支撑的演化图解释这种结构内部的机制级转移。

核心贡献：

1. 一个截点感知、增强型、时间化的分类体系框架。
2. 一个分类体系约束的演化图构建方法。
3. 用于演化关系边的证据支撑瓶颈-机制-权衡记录。
4. 一个分类体系-图反馈循环，用来建模拆分、合并、新生、重命名和碎片化事件。
5. 在前瞻性任务构建和社会科学机制/干预分析中的下游应用。

## 19. 近期下一步

推荐第一个实现目标：

```text
领域：llm_agent（LLM 智能体）
截点：沿用现有 ResearchForesight 截点
维度：methodologies（方法体系）, evaluation_methods（评价方法）
目标：构建轻量方法演化图，并产出 forecast_hooks.jsonl
```

最小产物：

1. 用配置文件定义语料字段映射、分类体系维度、实体类型和关系线索。
2. 增强现有分类体系节点。
3. 评估节点质量。
4. 从节点局部文档中抽取方法/机制实体。
5. 为高置信候选实体对构建类型化关系边。
6. 验证瓶颈/机制/权衡引用。
7. 产出 20-50 个预测钩子。
8. 人工审计这些钩子是否优于当前基于线索词的方法演化资产。

这是证明 EvoTaxa 是真实算法升级，而不是简单重新包装的最短路径。

## 20. 暂缓 TODO：自适应模式综合层

当前 proposal 已经加入双层演化视图，但宏观模式综合层暂时不实现。它应该等核心状态和轨迹产物在至少一个真实社会科学语料上稳定后再做。

计划产物包括模式画像、模式证据记录和模式时间线。具体文件名留到实现文档中定义。

计划实现：

1. 加入分化、汇聚、混合、重新语境化、循环回归、制度化、替代、碎片化、稳定化等模式检测器。
2. 从已有 EvoTaxa 产物计算模式得分：分类体系事件、状态转移、演化轨迹、关系边得分、schema 修订、关系拒绝记录。
3. 为每个宏观模式绑定代表性的微观层证据。
4. 可选使用 LLM 总结检测器支撑的证据，但不能让 LLM 从零生成模式画像。
5. 加入可视化友好的字段：时间跨度、代表性节点、代表性轨迹、模式得分、证据 id、解释文本。
6. 加入测试和消融，对比有无分类体系协同演化、schema 适配、负向证据时模式画像的变化。

这一层应该保持可选。不同领域可能主要表现为分化，也可能表现为循环回归或重新语境化。算法应该估计这种差异，而不是把单一演化理论强加给所有语料。
