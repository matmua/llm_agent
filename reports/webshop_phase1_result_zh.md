# WebShop Phase 1 Shadow 检测结果

## 当前完成情况

- 已克隆官方 WebShop 到 `external/webshop`，该目录被 git 忽略。
- 已新建并配置 `webshop` conda 环境，用于官方 WebShop text env。
- 已下载 WebShop small 数据：
  - `external/webshop/data/items_shuffle_1000.json`
  - `external/webshop/data/items_ins_v2_1000.json`
  - `external/webshop/data/items_human_ins.json`
- 已构建 Lucene search index。
- 已实现 WebShop ReAct-style agent loop、结构化 entity-attribute state、pre-action shadow detector、post-action delta verifier、shadow policy、JSONL logger、分析脚本和单元测试。
- Phase 1 严格不干预动作，日志中 `executed_action == raw_action` 已检查通过。

## 运行结果

### 官方 WebShop small

- 日志目录：`logs/webshop_shadow_official_small/`
- 报告目录：`reports/webshop_official_small/`
- episode 数：20
- step 数：60
- 成功数：13/20
- success_rate：0.65
- shadow 等式：全部满足

关键检测指标：

- failed_episode_warning_recall：0.7143
- episodes_with_high_risk_rate：0.8000
- post_error_step_rate：0.2500
- potential_preventable_failure_count：5
- 最常见 pre-action 风险：`missing_attribute`、`premature_buy`
- 最常见 post-action 错误：`constraint_conflict`、`potential_preventable_failure`

注意：这里使用的是 deterministic `MockLLMClient`，不是 Qwen/DeepSeek 的真实模型能力结果。这个实验用于验证官方 WebShop 环境、完整轨迹记录和 shadow 检测分析链路。

### Mock smoke run

- 日志目录：`logs/webshop_shadow/`
- 报告文件：
  - `reports/webshop_shadow_summary.md`
  - `reports/webshop_shadow_metrics.json`
  - `reports/webshop_shadow_cases.jsonl`
- episode 数：20
- step 数：60
- 成功数：20/20
- success_rate：1.0

Mock run 用来保证没有官方依赖时仍能跑通最小流程和单元测试，不作为 WebShop benchmark 结果。

## 重点查看位置

- 官方摘要报告：`reports/webshop_official_small/webshop_shadow_summary.md`
- 官方指标 JSON：`reports/webshop_official_small/webshop_shadow_metrics.json`
- 官方失败案例 JSONL：`reports/webshop_official_small/webshop_shadow_cases.jsonl`
- 官方完整 step 日志：`logs/webshop_shadow_official_small/steps.jsonl`
- 官方 episode 汇总：`logs/webshop_shadow_official_small/episodes.jsonl`

## 流量说明

所有下载、安装、运行命令均通过 `./no_proxy_run.sh` 执行。该脚本会清除 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` 等代理变量，使项目流量走服务器网络，不走本地 SSH 代理。下载 GitHub/Hugging Face 内容时使用了服务器上的 `/etc/network_turbo` 学术加速。

## 当前局限

- 当前 agent 是 mock heuristic agent，因此不能代表 Qwen3-8B 或其他 LLM 的真实 WebShop 成绩。
- pre-action detector 仍有 false negative：有失败轨迹没有在失败前被预警。
- post-action constraint conflict 目前是规则式粗检，适合发现可疑点，但还不是最终判定器。
- Phase 2 的补全、阻断、修复、rollback 仍是接口/no-op，没有真实改变动作。

## 下一步建议

- 用本地 Qwen/OpenAI-compatible endpoint 替换 `--model mock`，跑同样的 20 条官方 WebShop small。
- 开启 `--use_llm_judge`，比较 rule-only 与 LLM judge 的 warning recall / false positive。
- Phase 2 再实现属性补全和一次 action revision，但必须保留与当前 shadow baseline 的并排比较。
