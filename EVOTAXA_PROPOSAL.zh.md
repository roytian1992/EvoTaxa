# EvoTaxa：截点感知的 Taxonomy-Guided Evolution Modeling

## 1. 核心思想

EvoTaxa 是一个统一框架，用来建模研究领域、方法机制、政策工具、社会议题如何随时间演化。

核心主张是：

> 时间化 taxonomy 解释一个领域在哪里发生结构性分化；evolution graph 解释这种分化为什么发生，也就是通过 bottleneck、mechanism、adaptation、replacement 和 trade-off 去解释演化原因。

EvoTaxa 融合三条已有路线：

- TaxoAdapt：多维 taxonomy 构建，以及 width/depth expansion。
- ResearchForesight/ForeSci：cutoff-aware corpus 构建、时间切片快照、benchmark/release 纪律、foresight evaluation。
- Methodological Evolution Graph：方法实体、类型化因果边、基于证据的 bottleneck-mechanism-tradeoff 记录，以及 lineage search。

最终的系统不是单纯的 taxonomy builder，也不是单纯的方法图谱。它是一个在时间截点约束下，发现、解释、审计领域演化的系统。

## 2. 动机

现有研究基础设施通常把论文组织成文档集合、引用网络、关键词索引或者静态 topic cluster。这些表示方式适合检索，但不擅长解释领域演化。

它们通常很难回答下面这些问题：

- 哪些子方向是真正新出现的，哪些只是改了名字？
- 一个宽泛主题什么时候开始分裂成多个机制层面的方向？
- 哪个反复出现的 bottleneck 推动了一个方法家族、评估协议或政策工具的演化？
- 哪个新方向是真正的 successor mechanism，而不只是热度上升？
- 哪些证据支持一条 evolution edge？这些证据能不能回到原文审计？

EvoTaxa 通过三类对象解决这些问题：

1. 用 temporal taxonomy 捕捉领域结构和粒度变化。
2. 用局部 evolution graph 捕捉 taxonomy 区域内部的方法/机制转移。
3. 用 evidence records 让每个重要演化判断可以追溯。

## 3. 总体流程

```text
Raw corpus
  -> domain harvest and metadata enrichment
  -> relevance screening and core/support labeling
  -> cutoff-aware frozen corpus
  -> enriched temporal taxonomy induction
  -> taxonomy evolution event detection
  -> taxonomy-conditioned evolution graph construction
  -> lineage, branch, and bottleneck search
  -> forecast hooks / analysis hooks / benchmark tasks
```

核心设计原则是：

```text
Taxonomy controls where to look.
Evolution graph explains why the structure changes.
```

也就是说，taxonomy 负责限定观察区域和结构边界；evolution graph 负责解释结构变化背后的机制原因。

## 4. Layer 1：截点感知的语料构建

这一层借鉴 ResearchForesight 的 cutoff-aware 思路，但 EvoTaxa 不应该绑定 ForeSci 的具体字段格式。

更合理的设计是：系统只要求一个最小内部数据契约，具体字段映射交给配置文件管理。这样同一套代码既能跑 AI paper，也能跑 social science 文献、政策文本、访谈材料、新闻报道或机构报告。

### 输入

- 原始文档元数据。
- 可用的全文、摘要、报告正文或访谈文本。
- 发布时间、来源、机构、venue、citation count、arXiv id 等时间和来源信息。
- 领域配置、seed query、字段映射配置。

### 处理

1. 合并和去重原始文档。
2. 根据领域配置生成启发式 profile。
3. 运行 relevance screening。
4. 将文档标记为 `core`、`support`、`audit_only` 或 `exclude`。
5. 只用被接受的角色冻结 cutoff-aware corpus。
6. 给每个文档分配 chronology slice。

### 推荐输出

```text
documents.normalized.jsonl
corpus_manifest.json
screening_labels.jsonl
core_support_corpus.jsonl
core_support_manifest.json
```

cutoff 边界是硬约束。任何 post-cutoff 文档都不能进入 taxonomy induction、evolution-edge extraction、retrieval 或 answer generation。

## 5. Layer 2：增强型 Temporal Taxonomy

当前 taxonomy 系统已经支持多维度、时间切片式增长。EvoTaxa 要把它从一个 label tree 升级成更丰富的 temporal structure graph。

### 维度

对于 AI research，默认维度可以是：

- `tasks`
- `methodologies`
- `datasets`
- `evaluation_methods`
- `real_world_domains`

对于 social science，维度可以变成：

- `social_issues`
- `actors`
- `mechanisms`
- `interventions`
- `measurement_strategies`
- `contexts`
- `outcomes`
- `public_frames`

这些维度不应该写死在代码里，而应该放在 config 里管理。

### 节点 Schema

每个 taxonomy node 不应该只有 label 和 description，而应该携带更完整的边界、证据和状态信息：

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
- 该节点相关文档中可能出现的 example sentences。
- 用来区分相邻兄弟节点的 sibling-negative phrases。
- inclusion criteria 和 exclusion criteria。

这些增强信息会改善：

- 文档分类。
- 节点边界清晰度。
- 检索质量。
- 人工审计。
- 下游 method/mechanism entity extraction。

### Taxonomy Evolution Events

EvoTaxa 应该显式记录 taxonomy 层面的演化事件：

- `birth`：新节点出现。
- `split`：一个节点分化成多个更细方向。
- `merge`：两个节点在语义或经验上变得耦合。
- `rename`：术语变化，但概念连续性仍然存在。
- `decline`：支持度或增长趋势变弱。
- `fragmentation`：原本相对一致的节点内部出现多个不兼容机制。
- `cross_link`：两个不同维度的节点形成结构性连接。

这些事件应该作为一等 artifact 写出，而不是只从最终 snapshot 里临时推断。

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

## 6. Layer 3：更好的 Expansion Trigger

当前 taxonomy 扩展主要依赖 density 和 unlabeled mass。EvoTaxa 应该使用更丰富的触发信号。

### Trigger Signals

```text
expansion_score =
  document_density
+ unassigned_mass
+ semantic_heterogeneity
+ assignment_uncertainty
+ temporal_burst
+ entity_burst
+ bottleneck_concentration
+ evaluation_or_measurement_shift_signal
```

### Trigger Interpretation

- 高 unlabeled mass：触发 width expansion。
- dense leaf 且包含多个语义 cluster：触发 depth expansion。
- 兄弟节点重叠：生成 merge 或 alias candidate。
- 新术语突然爆发：生成 birth candidate。
- 同一概念换了新术语：生成 rename candidate。
- 成熟节点中反复出现同一 bottleneck：交给 evolution graph 分析。
- 新 evaluation protocol 或 measurement strategy 与某个 mechanism cluster 绑定：生成 cross-dimension link。

这可以避免 taxonomy growth 只被文档数量驱动。

## 7. Layer 4：Taxonomy-Conditioned Evolution Graph

这是 EvoTaxa 最关键的升级，灵感来自 methodological evolution graph。

EvoTaxa 不构建一个覆盖全语料的巨大 global graph，而是在 taxonomy 区域内部构建 local evolution graph。

### 为什么需要 Local Graph

全局 method graph 构建成本高、噪声大。taxonomy-conditioned graph 更实际，因为 taxonomy node 可以：

- 限定候选文档池。
- 提供语义上下文。
- 减少 pair explosion。
- 提高 edge typing 精度。
- 让局部 lineage search 更有意义。

### 图节点

对于 AI research：

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

对于 social science：

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

本质上，图节点不是只能表示“方法”。在 social science 场景里，它可以表示政策工具、干预设计、解释机制、测量策略、制度回应或公共话语框架。

### Edge Types

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

这些边用于 lineage search。

### Evidence Records

每条非 background 边都应该携带 evidence record：

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

substring verification 非常重要：

> 如果 bottleneck、mechanism 或 trade-off 的引用片段无法在原文中找到，这条边不能进入 trusted graph。

未验证的边可以保留在 candidate 文件里，但不能作为 gold evidence 或高置信 forecast hook 使用。

## 8. Layer 5：Taxonomy-Graph Feedback Loop

taxonomy 和 evolution graph 不应该是两个独立模块。

### Taxonomy to Graph

taxonomy 提供：

- 局部文档池。
- 节点路径和语义边界。
- 维度上下文。
- 候选 pair 约束。
- 跨节点 neighborhood。

### Graph to Taxonomy

evolution graph 提供：

- 节点 split 的证据。
- 节点 merge 的证据。
- 节点内部的 method/mechanism lineage。
- bottleneck concentration signal。
- 跨维度依赖。
- node status update。

例如：

- 如果一个 taxonomy node 内部包含多条互不连接的 strong-causal lineage，它可能需要 split。
- 如果两个兄弟节点共享大量 method/mechanism entities 和 edges，它们可能需要 merge 或 cross-link。
- 如果一个成熟节点反复引用同一 bottleneck，同时出现多个新机制，它可能进入 `fragmenting` 状态。
- 如果一个新 entity 在多个时间切片中出现，并开始获得 adaptation edges，它可能应该成为一个新分支。

## 9. Layer 6：Lineage and Branch Search

EvoTaxa 应该支持在 strong-causal graph 上做 lineage reconstruction。

### Minimal Version

先实现：

- confidence-weighted DFS。
- temporal beam search。
- branch-point extraction。

### Full Version

进一步加入 self-guided temporal tree search。

Candidate prior：

```text
edge_prior =
  edge_confidence
* temporal_coherence
* taxonomy_locality
* evidence_strength
```

Chain score：

```text
chain_score =
  normalized_length
+ mean_edge_confidence
+ search_visit_score
+ bottleneck_resolution_score
+ taxonomy_trajectory_score
```

搜索结果应该返回：

- ancestor chains。
- successor chains。
- branch points。
- unresolved bottleneck paths。
- replacement paths。
- cross-domain adaptation paths。

## 10. Forecast and Analysis Hooks

主要下游 artifact 是 `forecast_hooks.jsonl`。

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

这些 hooks 可以用于：

- benchmark task construction。
- research planning。
- idea evaluation。
- social-science mechanism analysis。
- policy/intervention evolution analysis。

## 11. Output Artifacts

推荐 artifact layout 是：

```text
data/evotaxa/<run_id>/
  corpus/
    documents.normalized.jsonl
    manifest.json
  taxonomy/
    taxonomy_nodes.enriched.json
    taxonomy_snapshot.enriched.json
    taxonomy_events.jsonl
    document_assignments.enriched.jsonl
    node_quality_scores.jsonl
  graph/
    method_registry.jsonl
    method_aliases.jsonl
    paper_method_mentions.jsonl
    method_edges.paper_level.jsonl
    method_edges.aggregated.jsonl
    method_evidence_records.jsonl
  search/
    evolution_chains.jsonl
    branch_points.jsonl
  hooks/
    forecast_hooks.jsonl
    social_analysis_hooks.jsonl
  audit/
    unverified_edges.jsonl
    low_confidence_nodes.jsonl
    taxonomy_judge_report.json
```

在代码实现里，`method_*` 文件名可以保留，用来兼容 AI research；但内部实体 schema 应该叫 evolution entity，避免 social science 场景下只有“method”这个窄含义。

## 12. Taxonomy 质量评估

借鉴 TaxoAdapt judge 的思想，但要把它变成生产级 artifact。

### Metrics

- Dimension alignment：节点是否属于它声明的维度。
- Parent-child granularity：child node 是否真的比 parent 更具体。
- Sibling coherence：兄弟节点是否处于相近粒度。
- Node uniqueness：两个节点是否重复表达同一概念。
- Document relevance：分配到节点的文档是否真的属于该节点。
- Coverage：children 是否覆盖了 parent 足够多的文档质量。
- Temporal stability：节点跨时间切片是否保持语义一致。
- Boundary clarity：inclusion/exclusion criteria 是否能区分相邻节点。

### Output

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

低质量节点不应该直接作为高置信 graph extraction 或 benchmark task 的种子，除非经过人工审计。

## 13. EvoTaxa 如何改进 ForeSci

### Direction Forecasting

旧形式：

> 哪个 taxonomy direction 会增长？

新形式：

> 哪条 mechanism-level successor path 最可能从 cutoff-visible bottleneck 和 lineage 中出现？

### Bottleneck-Opportunity Discovery

旧形式：

> 找出一个 bottleneck 和一个 opportunity。

新形式：

> 找出由 typed causal edges 和 evidence quotes 支撑的 bottleneck-to-mechanism transition。

### Strategic Research Planning

旧形式：

> 对候选方向排序。

新形式：

> 用 lineage centrality、bottleneck openness、evidence strength、branch maturity 和 trade-off risk 给候选方向排序。

### Venue Positioning

旧形式：

> 判断 venue fit 和 evidence upgrades。

新形式：

> 用 taxonomy 和 evolution graph 判断一个贡献到底是 method innovation、evaluation innovation、adaptation、component reuse 还是 application contribution。

## 14. Social Science Extension

EvoTaxa 可以通过替换 entity vocabulary 迁移到 social science。

### Taxonomy Dimensions

- `social_issues`
- `actors`
- `mechanisms`
- `interventions`
- `measurement_strategies`
- `contexts`
- `outcomes`
- `public_frames`

### Evolution Graph Entities

- Policy instruments。
- Intervention designs。
- Explanatory mechanisms。
- Measurement strategies。
- Institutional responses。
- Public frames。
- Behavioral mechanisms。

### Edge Interpretation

- `extends`：给已有政策或机制增加新组件。
- `improves`：在成本、采用率、targeting 或 outcome 等维度上改进 intervention。
- `replaces`：用一种机制或政策工具替换另一种。
- `adapts`：把 intervention 迁移到新群体、地区或机构环境。
- `uses_component`：借用一个 submechanism。
- `compares`：经验上比较多个 intervention 或 mechanism。
- `background`：背景性提及。

### Example Analyses

- misinformation research 如何从 content moderation 转向 platform governance 和 inoculation interventions。
- polarization research 如何从 survey-based attitude measurement 转向 social-network 和 platform-mediated mechanisms。
- AI governance 如何从 model-risk framing 演化到 institutional accountability、auditing 和 regulatory design。
- education inequality interventions 如何从 resource access 转向 learning analytics、tutoring 和 family/community mechanisms。

## 15. Implementation Roadmap

### Phase 1：Taxonomy Upgrade

目标：在加入 graph layer 之前，先提高 taxonomy 质量。

任务：

- 加入 node enrichment。
- 加入 inclusion/exclusion criteria。
- 加入 node-level quality judge。
- 加入显式 taxonomy event artifacts。
- 加入 low-confidence 和 overlap reports。

Deliverables：

```text
taxonomy_nodes.enriched.json
taxonomy_events.jsonl
node_quality_scores.jsonl
taxonomy_judge_report.json
```

### Phase 2：MEG-Lite

目标：先为一个领域构建局部 method/mechanism evolution graph。

推荐 pilot domain：

```text
llm_agent
```

范围：

- 先只处理 `methodologies` 和 `evaluation_methods`。
- 只使用 cutoff-visible documents。
- 使用 title、abstract 和可用 full text。
- 先从 node-local candidate pairs 开始，而不是一上来做 global citation resolution。

Deliverables：

```text
method_registry.jsonl
paper_method_mentions.jsonl
method_edges.paper_level.jsonl
method_evidence_records.jsonl
```

### Phase 3：Evolution Hooks

目标：把 graph structure 转成 forecast/task candidates。

任务：

- 提取 branch points。
- 提取 unresolved bottlenecks。
- 提取 successor mechanisms。
- 提取 replacement/adaptation paths。
- 构建 `forecast_hooks.jsonl`。

Deliverables：

```text
evolution_chains.jsonl
branch_points.jsonl
forecast_hooks.jsonl
```

### Phase 4：Search Upgrade

目标：用 self-guided temporal search 替代简单 lineage search。

任务：

- 实现 temporal coherence scoring。
- 加入 graph-aware priors。
- 加入 masked visited edges 的 branch re-search。
- 与 beam search 和 greedy DFS 比较。

Deliverables：

```text
lineage_search_results.jsonl
lineage_search_eval.json
```

### Phase 5：ForeSci Integration

目标：改进 benchmark construction。

任务：

- 从 `forecast_hooks.jsonl` 生成 task candidates。
- 比较旧 task candidates 和 EvoTaxa candidates。
- 评估 expert preference、traceability 和 hidden-target alignment。

Deliverables：

```text
evotaxa_task_candidates/
evotaxa_vs_old_task_quality_report.md
```

### Phase 6：Social Science Pilot

目标：证明跨领域分析价值。

候选领域：

- AI governance。
- Misinformation。
- Political polarization。
- Education inequality。
- Platform labor。

Deliverables：

```text
social_taxonomy_nodes.enriched.json
social_mechanism_edges.jsonl
social_analysis_hooks.jsonl
case_study_report.md
```

## 16. Engineering Plan

推荐模块：

```text
src/evotaxa/
  config.py
  io.py
  loaders.py
  models.py
  taxonomy.py
  graph.py
  search.py
  hooks.py
  pipeline.py
  cli.py
```

更细粒度拆分时，可以演化成：

```text
src/evotaxa/
  taxonomy_enrichment.py
  taxonomy_judge.py
  taxonomy_events.py
  graph_entities.py
  graph_edges.py
  evidence_validation.py
  lineage_search.py
  hook_generation.py
```

推荐脚本或 CLI 命令：

```text
evotaxa validate-config --config configs/<domain>.toml
evotaxa run-lite --config configs/<domain>.toml
evotaxa enrich-taxonomy --config configs/<domain>.toml
evotaxa build-graph --config configs/<domain>.toml
evotaxa search-lineage --config configs/<domain>.toml
evotaxa build-hooks --config configs/<domain>.toml
```

## 17. Evaluation Plan

### Taxonomy Evaluation

比较：

- 当前 ResearchForesight taxonomy。
- ResearchForesight + node enrichment。
- ResearchForesight + node enrichment + taxonomy judge pruning。
- Config-driven EvoTaxa taxonomy，用于非 ForeSci schema 的 social science corpus。

指标：

- Alignment。
- Granularity。
- Sibling coherence。
- Uniqueness。
- Document relevance。
- Coverage。
- Human audit pass rate。

### Graph Evaluation

比较：

- Cue-based method evolution assets。
- Taxonomy-conditioned MEG-lite。
- MEG-lite with evidence verification。
- MEG-lite plus temporal lineage search。

指标：

- Edge type accuracy。
- Evidence verification rate。
- Bottleneck quote validity。
- Human-rated lineage coherence。
- Forecast hook usefulness。

### Downstream Evaluation

比较：

- Existing ForeSci task candidates。
- EvoTaxa-generated task candidates。
- Social-science analysis hooks。

指标：

- Expert preference。
- Traceability。
- Hidden future-target alignment。
- Reduction in evidence-decision drift。
- Improved bottleneck/opportunity specificity。
- 对社会机制、政策工具或干预路径的解释有效性。

## 18. Paper Positioning

可能的标题：

> EvoTaxa: Cutoff-Aware Taxonomy-Guided Evolution Modeling for Scientific and Social Foresight

核心定位：

> TaxoAdapt adapts taxonomies to evolving corpora. Methodological evolution graphs expose typed method lineages. EvoTaxa unifies these ideas under temporal cutoff constraints: taxonomy snapshots localize the evolving structure, and evidence-grounded evolution graphs explain the mechanism-level transitions inside that structure.

中文表述：

> TaxoAdapt 解决 evolving corpus 上的 taxonomy adaptation 问题；methodological evolution graph 揭示类型化的方法 lineage；EvoTaxa 把两者统一到 cutoff-aware setting 中：taxonomy snapshots 定位领域结构如何演化，evidence-grounded evolution graphs 解释这种结构内部的机制级转移。

核心贡献：

1. 一个 cutoff-aware enriched temporal taxonomy framework。
2. 一个 taxonomy-conditioned evolution graph construction method。
3. 用于 evolution edges 的 evidence-grounded bottleneck-mechanism-tradeoff records。
4. 一个 taxonomy-graph feedback loop，用来建模 split、merge、birth、rename 和 fragmentation events。
5. 在 foresight task construction 和 social science mechanism/intervention analysis 中的下游应用。

## 19. Immediate Next Steps

推荐第一个实现目标：

```text
Domain: llm_agent
Cutoff: existing ResearchForesight cutoff
Dimensions: methodologies, evaluation_methods
Goal: build MEG-lite and forecast_hooks.jsonl
```

最小 deliverable：

1. 用配置文件定义 corpus field mapping、taxonomy dimensions、entity types 和 edge cues。
2. 增强现有 taxonomy nodes。
3. 评估 node quality。
4. 从 node-local documents 中抽取 method/mechanism entities。
5. 为高置信 candidate pairs 构建 typed edges。
6. 验证 bottleneck/mechanism/tradeoff quotes。
7. 产出 20-50 个 forecast hooks。
8. 人工审计这些 hooks 是否优于当前 cue-based method evolution assets。

这是证明 EvoTaxa 是真实算法升级，而不是简单 rebranding 的最短路径。

