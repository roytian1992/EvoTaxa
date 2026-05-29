# EvoTaxa 交接文档：下一步推进与可用资源

## Scope

这份交接文档用于让新的会话窗口快速接手 EvoTaxa 项目，重点覆盖：

- 当前仓库状态。
- 已经稳定的方案和代码能力。
- 哪些结果可信、哪些不能直接当研究结论。
- 可用的数据源和优先级。
- 下一步应该怎么推进。
- 关键路径、命令和风险点。

当前最重要的目标是：从 fixture 级 proof-of-concept 推进到真实的 computational social science methods 数据实验。

## Current State

仓库根目录：

```text
/vepfs-mlp2/c20250513/241404044/users/roytian/EvoTaxa
```

交接前的稳定基线：

```text
branch: main
remote: origin/main
proposal/doc baseline commit: 8223c33 Polish Chinese proposal narrative
```

仓库现在包含两类内容：

- 方案文档：算法定位、中文/英文 proposal、数据源调研、输入契约。
- 可运行代码：`src/evotaxa/` 下已经有 lite/full pipeline、schema、自适应修订、演化图、trajectory、hook、evaluation、ablation 等模块。

关键文档：

- `README.md`：算法流程、运行命令、输出布局、LLM 配置。
- `EVOTAXA_PROPOSAL.md`：英文 proposal。
- `EVOTAXA_PROPOSAL.zh.md`：中文版 proposal，已改成更偏方案叙述，删除了不适合 proposal 的工程细节，并换成 social science 节点例子。
- `docs/input_contract.md`：输入数据契约，说明 EvoTaxa 不依赖 ForeSci 固定字段。
- `docs/computational_social_science_data_sources.md`：computational social science methods 数据源可用性调研。

## Trusted Results

下面这些可以作为当前可信基线：

- 核心方案已经稳定：EvoTaxa = taxonomy induction + schema-adaptive quote-grounded evolution graph + state/trajectory modeling。
- 中文 proposal 已经更适合对导师/合作者展示：解释了 node 是什么、expansion trigger 是什么、social science 例子是什么。
- README 中的算法流程和架构图已经可用。
- 代码层面已经有 `run-lite` 和 `run-full` 两条 pipeline。
- fixture 级测试覆盖了 scientific/social 两类样例、schema 命令、adaptive social case study、ablation 入口、LLM task shape。
- 数据源调研结论明确：OpenAlex 应该作为第一个真实 corpus 来源，ACL Anthology 作为 NLP/text-as-data 分支补充。

数据源可用性结论来自 `docs/computational_social_science_data_sources.md`：

| Source | 当前可用性 | 推荐用途 |
|---|---|---|
| OpenAlex | API 可访问，不需要 key | 主语料来源 |
| ACL Anthology | 静态 metadata 可下载 | NLP/text-as-data 分支补充 |
| Semantic Scholar | 当前环境遇到 HTTP 429 | 不作为第一来源 |
| arXiv | 当前环境遇到 429/timeout | 不作为第一来源 |
| Crossref | 搜索可用，但 abstract 弱 | DOI/metadata fallback |

OpenAlex 已测试的 title/abstract query 统计：

| Query | 观察到的时间范围 | 1990-2026 数量 |
|---|---:|---:|
| `computational social science` | 1990-2026 | 13,917 |
| `text as data social science` | 1990-2026 | 14,224 |
| `digital trace data social science` | 1999-2026 | 785 |
| `LLM social science annotation` | 2023-2026 | 126 |

## Untrusted Or Failed Results

这些内容不能直接当作研究结论：

- 目前还没有真实 OpenAlex 数据集下载进仓库。
- 如果本地存在 `examples/` 输出，它们主要是 fixture smoke run 产物，不是研究结果。
- 当前 `configs/social_science.example.toml` 和 `configs/social_misinformation_governance.adaptive.toml` 仍然指向 `tests/fixtures/social/` 小样例。
- Semantic Scholar 和 arXiv 在当前环境下访问不稳定，暂时不适合做第一批数据。
- Crossref 缺少足够 abstract，不适合作为 quote-grounded evolution modeling 的主语料。
- local LLM config 是开发示例。不要把明文 token 提交进仓库。

## Important Paths

核心文档：

```text
README.md
EVOTAXA_PROPOSAL.md
EVOTAXA_PROPOSAL.zh.md
docs/input_contract.md
docs/computational_social_science_data_sources.md
docs/HANDOFF_20260529_evotaxa_next_steps.md
```

配置文件：

```text
configs/scientific_research.example.toml
configs/social_science.example.toml
configs/social_misinformation_governance.adaptive.toml
configs/induction_only.example.toml
configs/local_llm.example.toml
```

测试 fixture：

```text
tests/fixtures/science/corpus.jsonl
tests/fixtures/science/taxonomy_nodes.json
tests/fixtures/science/assignments.jsonl
tests/fixtures/social/corpus.jsonl
tests/fixtures/social/taxonomy_nodes.json
tests/fixtures/social/assignments.jsonl
```

关键实现入口：

```text
src/evotaxa/cli.py
src/evotaxa/pipeline.py
src/evotaxa/induction.py
src/evotaxa/taxonomy.py
src/evotaxa/schema.py
src/evotaxa/relation_schema.py
src/evotaxa/graph.py
src/evotaxa/edge_evidence.py
src/evotaxa/edge_scoring.py
src/evotaxa/coevolution.py
src/evotaxa/state.py
src/evotaxa/trajectory.py
src/evotaxa/hooks.py
src/evotaxa/evaluation.py
src/evotaxa/ablation.py
```

## Important Scripts

CLI 入口：

```text
src/evotaxa/cli.py
```

主 pipeline：

```text
src/evotaxa/pipeline.py
```

当前支持的命令：

```text
python -m evotaxa.cli validate-config --config <config>
python -m evotaxa.cli run-lite --config <config> --print-manifest
python -m evotaxa.cli run-full --config <config> --print-manifest
python -m evotaxa.cli infer-schema --config <config> --print-summary
python -m evotaxa.cli adapt-schema --config <config> --print-summary
python -m evotaxa.cli run-ablation --config <config> --variants default no_coevolution no_expansion no_edge_judge no_llm --print-summary
```

editable install 之后也可以使用：

```text
evotaxa run-full --config <config> --print-manifest
```

## What Was Tried

已经做过的主要工作：

- 把算法定位为 taxonomy induction + method/mechanism evolution。
- 对比并融合了当前方案、TaxoAdapt、methodological evolution graph。
- 写了英文 proposal 和中文 proposal。
- 确定系统名为 EvoTaxa。
- 在 README 中加入算法流程和总体架构图。
- 实现 config-driven Python package。
- 加入 lite/full pipeline。
- 加入 fixed / inferred / adaptive schema 模式。
- 加入 quote-grounded relation/evidence audit。
- 加入 negative relation evidence。
- 加入 taxonomy expansion、taxonomy-graph feedback、co-evolution、state transition、trajectory inference、hook generation、quality report、ablation。
- 整理中文 proposal，避免它变成工程设计文档。
- 调研 social science 数据源，结论是 OpenAlex 先做主数据源。

## What Was Learned

当前比较明确的判断：

- Social science 不应该被强行套成“科研分类越来越细”的单一路径。
- 有些领域确实是 differentiation，有些领域会出现 recurrence、recontextualization、institutionalization、stabilization。
- 所以 proposal 中保留了 two-level view：
  - micro view：局部、quote-grounded 的机制和 trajectory。
  - macro view：adaptive pattern synthesis，先作为 TODO，不要第一阶段实现。
- relation schema 演化不够，entity schema 和 evidence schema 也应该支持 fixed/inferred/adaptive。
- 被拒绝的 relation pair 很重要，它们是 negative evidence，尤其在 social science 中可以防止把 co-mention 错当成因果或机制关系。
- 第一批真实实验不建议从公共舆论周期开始，建议从 computational social science methods 开始，因为更接近“方法演化”和“分类粒度变细”的主线。

## Recommended Next Steps

1. 实现 OpenAlex downloader。
   - 用 `title_and_abstract.search`，不要用 broad `search`。
   - 保存 query bucket。
   - reconstruct `abstract_inverted_index`。
   - 导出符合 `docs/input_contract.md` 的 JSONL。

2. 构建第一个真实 config。
   - Domain: `computational_social_science_methods`。
   - Years: `1990-2026`。
   - Text: title + abstract。
   - Source: OpenAlex only。
   - Schema mode: 先 fixed baseline，再 adaptive。

3. 先跑 deterministic baseline。
   - `run-full`。
   - 先禁用 LLM。
   - 确认 taxonomy expansion、state transitions、trajectory、hook report 都能产出。

4. baseline 稳定后再加本地 LLM。
   - 使用 OpenAI-compatible endpoint。
   - 先只开 `entity_extraction` 和 `edge_evidence_judge`。
   - 再开 `relation_extraction_batch` 和 `schema_revision_judge`。

5. 做第一版 case study 检查。
   - 是否能恢复 network/simulation -> digital trace/social media data。
   - 是否能看到 text-as-data 分化到 supervised classification、embedding、frame/stance detection、LLM annotation。
   - 是否能看到 LLM-assisted methods 只在 2023 后明显出现。
   - rejected relation pairs 是否有效阻止弱共现变成假 evolution edge。

6. OpenAlex 跑通后再加 ACL Anthology。
   - ACL 只补 NLP-heavy branches。
   - 重点是 text-as-data、stance/frame/ideology detection、LLM annotation。

7. macro pattern synthesis 暂缓。
   - 先不要实现 recurrence/cycle detector。
   - 等真实 corpus 上 state 和 trajectory artifacts 稳定后再做。

## Command Template

安装并运行测试：

```bash
cd /vepfs-mlp2/c20250513/241404044/users/roytian/EvoTaxa
pip install -e .
pytest -q
```

运行 social fixture baseline：

```bash
python -m evotaxa.cli run-full \
  --config configs/social_science.example.toml \
  --print-manifest
```

运行 adaptive misinformation fixture：

```bash
python -m evotaxa.cli run-full \
  --config configs/social_misinformation_governance.adaptive.toml \
  --print-manifest
```

运行 ablation：

```bash
python -m evotaxa.cli run-ablation \
  --config configs/social_science.example.toml \
  --variants default no_coevolution no_expansion no_edge_judge no_llm \
  --print-summary
```

本地 LLM 开发配置形状：

```toml
[llm]
provider = "openai_compat"
model_name = "GLM-4.6-FP8"
api_key_env = "EVOTAXA_LLM_API_KEY"
base_url = "http://localhost:8001/v1"
enabled_tasks = ["entity_extraction", "edge_evidence_judge"]
```

本地设置 key：

```bash
export EVOTAXA_LLM_API_KEY='<your-local-token>'
```

## Data Resource Plan

第一批 OpenAlex query buckets：

```text
computational social science
computational social science methods
social science computational methods
text as data social science
computational text analysis social science
digital trace data social science
network analysis computational social science
agent-based modeling computational social science
LLM social science annotation
synthetic respondents large language models
computational social science reproducibility
platform data access social science
```

初始 seed taxonomy：

```text
Digital Trace Data
Text-as-Data / Computational Text Analysis
Network Analysis
Causal Inference & Experiments
Agent-Based Modeling / Social Simulation
LLM-Assisted Social Science Methods
Reproducibility / Ethics / Data Governance
```

建议时间切片：

```text
1990-2008: early computational social science, network analysis, simulation
2009-2014: social media and digital trace data rise
2015-2019: text-as-data, embeddings, platform measurement, causal designs
2020-2022: reproducibility, data access, computational ethics
2023-2026: LLM annotation, synthetic respondents, LLM-assisted social science
```

## Risks And Constraints

- 真实 OpenAlex downloader 尚未实现。
- abstract-only evidence 可能不足以支撑强 quote-grounded relation extraction，后续可能需要全文或更长文本。
- OpenAlex broad search 会引入噪声，优先使用 `title_and_abstract.search`。
- LLM extraction 会引入噪声，必须保留 schema validation、quote verification 和 rejected-pair audit。
- adaptive schema 有漂移风险，所以必须保留 fixed-schema baseline。
- macro pattern synthesis 有价值，但不应该早于真实 corpus 上 state/trajectory 稳定性验证。
