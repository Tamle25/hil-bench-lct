# HiL-Bench

Repo to run on the public dataset of **[HiL-Bench](https://static.scale.com/uploads/67a153343e046988406ef320/HiL_Bench.pdf)**, a benchmark designed to measure agents' ability to identify when they need to ask for help in coding tasks. Every task has blockers, ambiguities that **must** be clarified in order for the task to be solved correctly.

Task types:

- SQL
- SWE

Modes:

- Baseline: the agent is presented with the task with blockers as is
- Full info: the agent is given the task AND the blocker resolutions upfront
- Ask human: the agent is presented with the task with blockers as is and has access to an `ask_human` tool to get clarifications

## Setup

1. Create a `uv` project venv.
2. Copy `.env_template` to `.env` and set your provider keys.
3. The public dataset is hosted externally on Hugging Face at [ScaleAI/hil-bench](https://huggingface.co/datasets/ScaleAI/hil-bench), not committed into this repo; download or materialize the task inputs locally and pass their path to the CLI.
4. In each agent config YAML, set explicit hosting mode in top-level `hosting.type`:
   - `litellm_proxy` (requires `LITELLM_BASE_URL`)
   - `provider_direct` (requires `LITELLM_BASE_URL` to be unset)
   - `self_hosted` (requires `agent.model.api_base` or `hosting.api_base_env`)
5. Create configs and a `config_mappings.yaml` (see `config_mappings.example.yaml`). The configs can be for specific task type, mode, and/or model system and user prompts. **Only modify the prompts and LLM configs from the provided example config YAMLs; all other configuration fields should remain untouched.** If you do modify the prompts, make sure you keep the same set of placeholder variables.
6. Create `judge_config.yaml` (see `judge_config.example.yaml`). This is the model hosting configuration for the `ask_human` tool and must include explicit `hosting.type` (`litellm_proxy`, `provider_direct`, or `self_hosted`).
   - Agent self-hosted URLs can be env-driven via `hosting.api_base_env` (or set directly with `agent.model.api_base`).
   - ask_human self-hosted URL can be env-driven via `hosting.self_hosted_base_url_env` (or set directly with `hosting.self_hosted_base_url`).

## Examples of How to Run

SQL only:

```bash
uv run hil sql /path/to/sql_task_dir \
  --model openai/gpt-5.3-codex \
  --num-workers 4 \
  --passes 3 \
  --all-modes \
  --config-mapping config_mappings.yaml \
  --judge-config judge_config.yaml \
  --output-dir results
```

SWE only:

```bash
uv run hil swe /path/to/swe_tasks_dir \
  --model openai/gpt-5.3-codex \
  --num-tasks 10 \
  --passes 3 \
  --all-modes \
  --config-mapping config_mappings.yaml \
  --judge-config judge_config.yaml \
  --output-dir results
```

SQL + SWE:

```bash
uv run hil sql /path/to/sql_task_dir \
  --model openai/gpt-5.3-codex anthropic/claude-sonnet-4 \
  --passes 2 \
  --all-modes \
  --config-mapping config_mappings.yaml \
  --judge-config judge_config.yaml \
  --output-dir results

uv run hil swe /path/to/swe_tasks_dir \
  --model openai/gpt-5.3-codex anthropic/claude-sonnet-4 \
  --passes 2 \
  --all-modes \
  --config-mapping config_mappings.yaml \
  --judge-config judge_config.yaml \
  --output-dir results
```

## Scoring

- **Question Precision** divides the number of accepted blocker matches by all tool questions. Each accepted question counts, including an accepted repeat.
- **Blocker Recall** divides the number of distinct blockers resolved per attempt by all registered blockers. A completed attempt with zero questions contributes all its blockers to the denominator.
- **ASK-F1** is the harmonic mean of Precision and Recall. The benchmark-level score uses the summed counts across included attempts in `ask_human` mode.
- **Pass@k** measures whether at least one of the first `k` attempts passed. In `ask_human`, an attempt must satisfy the SWE or SQL verifier and resolve every registered blocker. In `baseline` and `full_info`, the verifier result determines pass. Use `artifact_pass_at_k` for output correctness across all three modes and `pass_at_k` for the benchmark's pass rule.

`uv run hil` saves per-pass metrics and `consolidated_metrics.json`. Use `run_hil_bench.py --passes 3` for the CSV/JSON summary and Pass@3. The stricter `ask_human` pass rule can produce different numbers from the paper. Use a fresh run name to collect complete clarification logs for runs saved before this change.

## Benchmark tiếng Việt từ Jira

Bộ [Jira mẫu](examples/jira_vi/) có một ticket SQL giả lập, cơ sở dữ liệu SQLite, truy vấn chuẩn và câu hỏi kiểm định judge. Có thể kiểm tra bộ mẫu bằng Python chuẩn, không cần model hay Docker.

```bash
python -m hil_bench.jira_dataset examples/jira_vi/jira_export.json examples/jira_vi/annotations.json
```

Với dữ liệu nội bộ, xuất issue sang JSON, rồi tạo `annotations.json` theo schema mẫu. Người duyệt viết đề tiếng Việt đã làm sạch, xác nhận 3–5 blocker độc lập và cung cấp câu hỏi mẫu cùng câu trả lời cho từng blocker. Trường `problem` nhận text hoặc Atlassian Document Format. Chọn `problem_source: jira_description` khi đã duyệt nội dung mô tả trong bản xuất. Đường dẫn artifact tính từ thư mục chứa file chú thích.

- **SQL** cung cấp SQLite, `table_descriptions.csv`, mô tả cột và truy vấn chuẩn chỉ đọc.
- **SWE** dùng `swe.repository_name`, `swe.image_archive`, `swe.test_patch` và `swe.tests_to_pass`. Đóng gói image Docker có repo tại `/app` và hai chương trình grader `/root/run_script.sh` và `/root/parser.py` tương thích với runner SWE. Có thể khai báo thêm `swe.test_files` và `swe.ground_truth_patch`.

Đưa đề bài vào `problem` và lưu câu trả lời cho từng blocker trong `resolution`. Người duyệt chạy `baseline` để phát hiện blocker có thể suy ra, rồi chạy `full_info` để xác nhận đề có thể giải khi đủ thông tin. Giữ bản xuất Jira, artifact và kết quả chạy nội bộ trong môi trường được phép xử lý dữ liệu đó.

`judge_config.vi.example.yaml` cấu hình endpoint OpenAI-compatible tự host với Qwen2.5-32B-Instruct. Đặt `ASK_HUMAN_SELF_HOSTED_BASE_URL` theo endpoint thực tế và kiểm định chính model đó bằng câu hỏi khớp và không khớp đã được người duyệt gán nhãn. [Model card](https://huggingface.co/Qwen/Qwen2.5-32B-Instruct)

DeepSeek cũng chạy trực tiếp qua mapping `deepseek/deepseek-flash`. DeepSeek công bố endpoint OpenAI-compatible tại `https://api.deepseek.com` và model hiện hành `deepseek-flash`, có tool calling và JSON output. [DeepSeek models and pricing](https://api-docs.deepseek.com/quick_start/pricing/) · [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)

```powershell
Copy-Item .env_template .env
$env:LITELLM_BASE_URL = "https://api.deepseek.com"
$env:LITELLM_API_KEY = Read-Host "Paste DeepSeek API key"
$env:LITELLM_USER = "hil-bench-local"

uv run python run_hil_bench.py `
  --task-type sql `
  --num-datapoints 1 `
  --models deepseek/deepseek-flash `
  --passes 1 `
  --modes baseline ask_human full_info `
  --agent-config-mapping config_mappings.yaml `
  --judge-config judge_config.deepseek.yaml `
  --output-dir results
```

Nếu bạn có ChatGPT Plus, có thể dùng Codex CLI đã đăng nhập bằng ChatGPT làm judge mà không tạo API key. Chạy `codex login`, chọn đăng nhập bằng ChatGPT, rồi dùng `judge_config.vi.codex.yaml`. Backend này gọi `codex exec` trong sandbox chỉ đọc cho từng câu hỏi. Gói Plus áp dụng allowance của Codex, không biến thành API key. Model Codex phải là model đang hiển thị trong tài khoản của bạn.

```powershell
codex login
codex login status

uv run python -m hil_bench.judge_calibration `
  --jira-export examples/jira_vi/jira_export.json `
  --jira-annotations examples/jira_vi/annotations.json `
  --cases examples/jira_vi/calibration.json `
  --judge-config judge_config.vi.codex.yaml
```

```bash
uv run python -m hil_bench.judge_calibration \
  --jira-export examples/jira_vi/jira_export.json \
  --jira-annotations examples/jira_vi/annotations.json \
  --cases examples/jira_vi/calibration.json \
  --judge-config judge_config.vi.example.yaml
```

Sau khi cấu hình model agent trong `config_mappings.yaml`, chạy cả ba chế độ trên cùng bộ Jira. Số lượt chạy mặc định là 3. Ví dụ dưới dùng một lượt để chạy thử.

```bash
uv run python run_hil_bench.py --task-type sql \
  --jira-export examples/jira_vi/jira_export.json \
  --jira-annotations examples/jira_vi/annotations.json \
  --models openai/gpt-5.4 --passes 1 \
  --modes baseline ask_human full_info \
  --agent-config-mapping config_mappings.yaml \
  --judge-config judge_config.vi.example.yaml
```

Với Windows PowerShell, chạy bản dùng ChatGPT plan cho judge như sau:

```powershell
uv run python run_hil_bench.py `
  --task-type sql `
  --num-datapoints 1 `
  --jira-export examples/jira_vi/jira_export.json `
  --jira-annotations examples/jira_vi/annotations.json `
  --models gpt-5.6-luna `
  --passes 1 `
  --modes baseline ask_human full_info `
  --agent-config-mapping config_mappings.yaml `
  --judge-config judge_config.vi.codex.yaml `
  --output-dir results
```


## Harbor

Harbor supports three modes for every task: `baseline`, `ask_human`, `full_info`.

- Runnable standalone tasks (this repo): `harbor_sql/hil-bench-sql_<i>-<mode>` and `harbor_swe/hil-bench-swe_<j>-<mode>`
- Registry layout (published): one dataset `scale-ai/hil-bench` containing all SQL+SWE mode tasks

```bash
# One-time setup
uv tool install harbor
harbor auth login


harbor run -p harbor_sql/hil-bench-sql_3-baseline \
  -a claude-code -m anthropic/claude-opus-4-1
harbor run -p harbor_swe/hil-bench-swe_5-ask_human \
  -a claude-code -m anthropic/claude-opus-4-1
```

For `ask_human` mode, select the judge backend with `ASK_HUMAN_BACKEND`
(`litellm_proxy`, `provider_native`, or `vllm`) and set that backend's model,
URL, and credential variables. `litellm_proxy` is the default. Proxy mode
requires a caller-supplied `LITELLM_USER` and fails closed before an
API request when it is missing. Provider-native and direct vLLM modes do not
require proxy attribution.

The local Harbor verifiers record the strict result as `reward` and the SWE/SQL
verifier result as `output_correct` in `reward.json`. The same file reports
question counts, blocker counts, Precision, Recall and F1. The `oracle` agent
submits the reference output directly, so `baseline` and `full_info` are suitable
for an oracle smoke test. Use an agent with `ask_human` access to validate strict
passing in that mode. Registry runs use the verifiers from the published dataset version.

Registry examples:

```bash
# Run the full published dataset (all tasks)
harbor run -d scale-ai/hil-bench@v1 -a claude-code -m anthropic/claude-opus-4-1

# Run one specific published task
harbor run -t scale-ai/hil-bench-sql_3-baseline@v1 \
  -a claude-code -m anthropic/claude-opus-4-1
```

## Output Structure

The `run_hil_bench.py` wrapper writes under `<output_dir>/<run_name>/public_metrics/`:

- `pass_level_metrics.csv`
- `summary_metrics.json` (top levels: `SQL`, `SWE`, `BOTH`)
- `trajectories/<mode>/<model>/<task>/pass_<i>_trajectory.json`

