# LLM Constraint And Finetune Workflow

## Decision Training Prep Log Contract

- `decision_id`
- `persona`
- `curr_step`
- `event`
- `ts`
- `prompt_kind`
- `final_prompt`
- `prompt_hash`
- `decision`
- `constraint_hit`
- `retry_reason`
- `execution_outcome`
- `minimal_filter_enabled`
- `minimal_filter_applied`
- `minimal_filter_summary`
- `schema_version`

## Log Formatting Rules

- All training-prep events write to `logs/training_dataset/decision_training_prep.jsonl`
- Each line is one event and must be joinable by `decision_id`
- Every event must include `decision_id`, `persona`, `curr_step`, `event`, and `ts`
- Complex values like `decision` stay as JSON objects instead of free-form strings
- `minimal_filter_enabled` 表示本轮是否经过最小化决策过滤链路
- `minimal_filter_applied` 表示本轮是否真的命中过滤条件
- `minimal_filter_summary` 说明过滤依据，例如 `invalid_targets`、资源剔除数量、是否触发单次重试
- `schema_version` 用于后续字段扩展和历史数据迁移

## Historical Backfill

- 历史日志回填脚本：`test/check_backfill_training_prep_logs.py`
- 默认行为是 dry-run，只输出将要变更的记录数
- 使用 `--write` 时会先创建时间戳备份，再原地回填 JSONL 文件
