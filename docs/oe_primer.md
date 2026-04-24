# OpenEvolve: a technical primer

## 1. Conceptual foundations

### Background and Origins

OpenEvolve is an open-source implementation of **AlphaEvolve**, a system Google DeepMind announced in **May 2025**. AlphaEvolve paired Gemini models with an automated evaluator and an evolutionary database, and produced several headline results: a procedure for multiplying 4×4 complex matrices using **48 scalar multiplications** (first improvement over Strassen's 1969 algorithm in that setting), a ~0.7% recovery of worldwide Google compute via a Borg scheduling heuristic, a 23% speedup on a matrix-multiplication kernel used in Gemini training, and improvements on ~20% of more than 50 open mathematical problems. DeepMind published a blog post and whitepaper; the arXiv version ([Novikov et. al., 2025](https://arxiv.org/abs/2506.13131)) followed in June 2025. Asankhaya Sharma (GitHub `codelion`, CTO at patched.codes) released **OpenEvolve roughly one week after** the AlphaEvolve whitepaper.

OpenEvolve has already replicated core AlphaEvolve results at reduced scale. In the GitHub repository `examples/circle_packing` case (n=26 circles in a unit square), OpenEvolve reaches a sum of radii of **2.634** versus AlphaEvolve's reported 2.635 — about 99.97% of the DeepMind result in ~800 iterations. In GitHub repository `examples/function_minimization`, a trivial random-search seed evolves into a simulated-annealing algorithm with cooling schedule. Extensions beyond the paper include first-class MAP-Elites/island configuration, an artifacts side-channel (stderr/tracebacks fed back into prompts), cascade evaluation, LLM-based code-quality feedback, and multi-language support (Python, Rust, R, Metal shaders).

### The core idea: LLMs as mutation operators

Classical evolutionary algorithms evolve a population through three mechanisms: **mutation** (random local changes), **crossover** (recombining two parents), and **selection** (keeping fitter variants). OpenEvolve keeps the scaffolding but replaces mutation with an LLM. Each iteration samples a parent program, builds a rich prompt containing the parent's code, its metrics, and "inspiration" programs drawn from elsewhere in the population, and asks an LLM to produce either a search/replace diff or a full rewrite. The resulting candidate is executed by a user-supplied `evaluate()` function that returns a set of metrics; the program database decides whether to keep it. **There is no explicit crossover operator** — recombination emerges implicitly because the LLM sees multiple inspiration programs in its prompt context.

### MAP-Elites and quality-diversity search

Vanilla genetic algorithms keep a single fitness-ranked population and tend to converge on one local optimum. OpenEvolve instead uses **MAP-Elites** (Multi-dimensional Archive of Phenotypic Elites), a quality-diversity algorithm that discretizes a *behavior* space into a grid of cells along user-chosen feature axes and retains only the best program per cell. The archive is therefore a portfolio of diverse high performers rather than a ranked list.

OpenEvolve's default feature dimensions are **complexity** (LOC inside the `EVOLVE-BLOCK`) and **diversity** (a structural similarity metric). Users can declare any metric returned by their evaluator as a feature dimension via `database.feature_dimensions` in the config, and control grid resolution with `feature_bins` (default 10 bins per axis). A new candidate replaces the incumbent of its cell if its fitness — `combined_score` when present, else an average of numeric non-feature metrics — is higher. OpenEvolve does the binning itself, so evaluators should return raw continuous values rather than pre-binned indices.

### Island models and migration

OpenEvolve further partitions the population into **islands** (default 5) that evolve independently in parallel, each with its own MAP-Elites grid. Periodically — every `migration_interval` generations (not wall-clock seconds, not total iterations) — the top `migration_rate` fraction (default 10%) of each island's programs migrates to the next island in a **ring topology**. Islands guard against premature convergence by keeping different search threads isolated long enough to develop distinct solutions; migration then cross-pollinates those lineages. Worker processes are pinned deterministically: `island_id = worker_id % num_islands`.

### Key vocabulary

**Inspirations** are programs surfaced into the LLM prompt to provide in-context examples; they are sampled from a mix of top performers, diverse feature-grid extremes, lineage ancestors, and random draws, and are deliberately distinct from the "top programs" shown in the prompt's metrics section. **Elites** are the current occupants of MAP-Elites cells. **Archive** typically refers to the cross-island collection of elites. **Artifacts** are side-channel output (stderr, profiler data, build warnings, LLM feedback) that evaluators may return alongside metrics; OpenEvolve injects these into subsequent prompts, creating a feedback loop that helps the LLM correct failures. **Cascade evaluation** runs cheap tests first (`evaluate_stage1`) and gates progression to expensive tests (`evaluate_stage2`, `evaluate_stage3`) by score thresholds.

---

## 2. Practical usage

### Installation

OpenEvolve requires **Python 3.10 or newer**. The standard install is `pip install openevolve`; runtime dependencies are `openai`, `pyyaml`, `numpy`, `tqdm`, and `flask` (the Flask dep powers the visualizer). To install from source for development, clone the repo and run `pip install -e ".[dev]"`. A Docker image is published at `ghcr.io/algorithmicsuperintelligence/openevolve:latest`.

All LLM calls go through the **OpenAI Python SDK**, so every provider is configured with the same two environment variables:

```bash
export OPENAI_API_KEY="sk-..."            # your provider's key
export OPENAI_API_BASE="https://..."      # optional; overrides config.yaml api_base
```

Gemini keys work with `api_base: "https://generativelanguage.googleapis.com/v1beta/openai/"`; Ollama uses `http://localhost:11434/v1` and a dummy key; OptiLLM can front any backend with test-time compute wrappers. An additional env var, `ENABLE_ARTIFACTS=false`, disables the artifact side-channel globally.

### Project layout

A typical project is three files in one directory. OpenEvolve creates its outputs alongside them:

```
my_project/
├── initial_program.py       # seed program with EVOLVE-BLOCK markers
├── evaluator.py             # defines evaluate(program_path) -> dict
├── config.yaml              # LLM, database, evaluator, prompt settings
└── openevolve_output/       # auto-created on first run
    ├── best/
    │   ├── best_program.py
    │   └── best_program_info.json
    ├── checkpoints/
    │   ├── checkpoint_10/
    │   │   ├── best_program.py
    │   │   ├── best_program_info.json
    │   │   ├── programs/
    │   │   └── metadata.json
    │   └── checkpoint_20/ ...
    └── evolution_trace.jsonl
```

### Writing an initial program

Mark the mutable region (if diff-based mutations) of the seed with comment sentinels. Everything outside the markers is **preserved verbatim** across generations — use that for imports, helpers, test harnesses, and `__main__` blocks.

```python
# initial_program.py
# EVOLVE-BLOCK-START
"""Function minimization example for OpenEvolve"""
import numpy as np

def search_algorithm(iterations=1000, bounds=(-5, 5)):
    """A random search that often gets stuck in local minima."""
    best_x = np.random.uniform(bounds[0], bounds[1])
    best_y = np.random.uniform(bounds[0], bounds[1])
    best_value = evaluate_function(best_x, best_y)
    for _ in range(iterations):
        x = np.random.uniform(bounds[0], bounds[1])
        y = np.random.uniform(bounds[0], bounds[1])
        value = evaluate_function(x, y)
        if value < best_value:
            best_value = value
            best_x, best_y = x, y
    return best_x, best_y, best_value
# EVOLVE-BLOCK-END


# Fixed context below — not evolved.
def evaluate_function(x, y):
    return np.sin(x) * np.cos(y) + np.sin(x * y) + (x**2 + y**2) / 20

def run_search():
    return search_algorithm()

if __name__ == "__main__":
    x, y, v = run_search()
    print(f"min at ({x}, {y}) with value {v}")
```

Multiple `EVOLVE-BLOCK` pairs are legal but the documented convention is exactly one per file. For non-Python artifacts use the target language's comment leader (e.g., `// EVOLVE-BLOCK-START` for Rust or Metal).

### Writing an evaluator

The evaluator is an importable Python module with a top-level `evaluate(program_path: str) -> dict` function. `program_path` is the absolute path to the candidate file; the evaluator imports it, runs it, and returns a dict of `str -> float` metrics where higher is better. A key named `combined_score`, when present, is used for ranking; otherwise OpenEvolve averages the numeric metrics that are not being used as feature dimensions.

```python
# evaluator.py
import importlib.util, time

def _load(program_path):
    spec = importlib.util.spec_from_file_location("candidate", program_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def evaluate(program_path):
    try:
        t0 = time.time()
        mod = _load(program_path)
        x, y, value = mod.run_search()
        elapsed = time.time() - t0
        return {
            "runs_successfully": 1.0,
            "value_score": max(0.0, 1.0 - abs(value)),   # higher is better
            "speed_score":  1.0 / (elapsed + 0.01),
            "combined_score": max(0.0, 1.0 - abs(value)),
        }
    except Exception:
        # Never raise — return a zero-score instead.
        return {"runs_successfully": 0.0, "combined_score": 0.0}
```

Evaluators should **catch their own exceptions** rather than raising; unhandled exceptions and timeouts are captured by OpenEvolve as artifacts (stderr, traceback) and surfaced into the next generation's prompt. A per-run timeout is enforced via `evaluator.timeout` (default 60 s in examples; up to 1800 s for heavy benchmarks). Timed-out evaluations return an `error:0.0` score without retry; other failures retry up to `evaluator.max_retries` (default 3).

To return artifacts alongside metrics, import `EvaluationResult`:

```python
from openevolve.evaluation_result import EvaluationResult

def evaluate(program_path):
    ...
    return EvaluationResult(
        metrics={"performance": 0.85, "correctness": 1.0, "combined_score": 0.92},
        artifacts={"stderr": "warning: suboptimal memory access",
                   "profiling_data": {...},
                   "llm_feedback": "could use better variable names"},
    )
```

For cascade evaluation, define `evaluate_stage1`, `evaluate_stage2`, and optionally `evaluate_stage3` (still with a plain `evaluate()` as a fallback), then set `evaluator.cascade_evaluation: true` and `evaluator.cascade_thresholds: [0.5, 0.8]` in the config. A known gotcha (issue #137): `cascade_evaluation: true` with no `evaluate_stage1` defined silently falls back to single-stage `evaluate()` with no warning.

### A minimal config.yaml

OpenEvolve's config has four nested sections — `llm`, `prompt`, `database`, `evaluator` — plus several top-level scalars. **Evolution-strategy flags (`diff_based_evolution`, `allow_full_rewrites`, `max_iterations`, `random_seed`, `checkpoint_interval`, `max_code_length`, `language`) live at the top level, not under a section**; this trips up newcomers.

```yaml
# config.yaml — minimal
max_iterations: 100            # overridden by CLI --iterations
checkpoint_interval: 10
random_seed: 42                # enables deterministic reruns
diff_based_evolution: true     # LLM emits SEARCH/REPLACE blocks
allow_full_rewrites: false
language: "python"             # Other options: "rust | "text" | etc

llm:
  api_base: "https://generativelanguage.googleapis.com/v1beta/openai/"
  models:
    - name: "gemini-2.5-flash"
      weight: 1.0
  temperature: 0.7
  max_tokens: 8000

prompt:
  system_message: |
    You are an expert programmer. Improve the function for correctness and speed.
  num_top_programs: 3          # top performers shown as in-context exemplars
  num_diverse_programs: 2      # diverse exemplars for exploration
  include_artifacts: true      # inject prior stderr/feedback into prompts

database:
  population_size: 100
  num_islands: 3
  migration_interval: 20       # generations, not iterations
  migration_rate: 0.1
  feature_dimensions: ["complexity", "diversity"]
  feature_bins: 10

evaluator:
  timeout: 60
  max_retries: 3
  parallel_evaluations: 4      # ProcessPoolExecutor worker count
  cascade_evaluation: false
  enable_artifacts: true
```

Important knobs worth flagging: **`llm.models`** is a list of `{name, weight}` pairs — weights are *sampling* probabilities, so one model is chosen per generation (not all queried in parallel). A separate `evaluator_models` list is used only when `evaluator.use_llm_feedback: true`; those models *are* all queried and their scores averaged by weight. **`database.feature_dimensions`** must reference either built-in features (`complexity`, `diversity`) or keys that your evaluator actually returns — otherwise OpenEvolve raises. **`prompt.template_dir`** points to a folder of override templates (see §4). The authoritative defaults live in `configs/default_config.yaml` in the repo; the values above are the ones that appear consistently across example configs.

### Running an evolution

The CLI entry point is a script at the repo root:

```bash
python openevolve-run.py \
  examples/function_minimization/initial_program.py \
  examples/function_minimization/evaluator.py \
  --config examples/function_minimization/config.yaml \
  --iterations 50
```

Only three flags are documented: `--config <path>`, `--iterations N` (overrides `max_iterations`), and `--checkpoint <dir>` to resume. Iterations are parallelized across `evaluator.parallel_evaluations` worker processes. Checkpoints are written every `checkpoint_interval` iterations to `openevolve_output/checkpoints/checkpoint_<N>/` and contain the current best program, all evaluated candidates (in `programs/`), and the full database state (`metadata.json`). Resuming preserves islands, MAP-Elites feature maps, archives, and random seeds; iteration numbering continues, so resuming from checkpoint 50 writes checkpoint 60 next.

### Inspecting results

After a run, the final best program lands at `openevolve_output/best/best_program.py` with a `best_program_info.json` sidecar containing metrics, program id, and the iteration at which it was found. Every checkpoint directory mirrors this structure, so you can `diff` across checkpoints to watch the algorithm evolve. A typical end-of-run log looks like:

```
Evolution complete! Best program metrics:
  runs_successfully: 1.0000
  value_score:       0.9766
  distance_score:    0.8626
  combined_score:    1.4206
  reliability_score: 1.0000
```

### The web visualizer

OpenEvolve ships a Flask-based visualizer at `scripts/visualizer.py`. Install its separate requirements first (`pip install -r scripts/requirements.txt`), then run `python scripts/visualizer.py` (auto-picks the newest checkpoint under `examples/`) or `python scripts/visualizer.py --path openevolve_output/checkpoints/checkpoint_100/`. The UI renders the evolution tree as a network graph (node radius = fitness on the selected metric), lets you click any node to see its code and the exact prompt/LLM response that produced it, charts metric-versus-generation, and live-reloads as new checkpoints are written.

---

## 3. Architecture and internals

### Five components and one iteration

The codebase decomposes cleanly into five subsystems that correspond to the AlphaEvolve architecture: a **Controller** (`openevolve/controller.py`) that owns the evolution loop; a **Program Database** (`openevolve/database.py`) with MAP-Elites grids and islands; an **LLM Ensemble** (`openevolve/llm/ensemble.py`); a **Prompt Sampler** (under `openevolve/prompt/`) that builds context-rich prompts; and an **Evaluator** (`openevolve/evaluator.py`) that runs candidate programs with cascade support, timeouts, and artifact capture. A single iteration proceeds as follows:

1. The controller takes a snapshot of the database and submits a task to a `ProcessPoolExecutor` worker pinned to an island.
2. The worker asks the database to sample a parent from its island plus a set of inspirations.
3. The prompt sampler assembles a system message, the parent code, its metrics and feature coordinates, evolution history, inspiration programs, and artifacts from prior runs.
4. The LLM ensemble picks one model by weight and calls it via the OpenAI SDK.
5. The response is parsed — either as SEARCH/REPLACE diff blocks or as a full rewrite — and applied to produce the candidate file.
6. The evaluator runs the candidate with a timeout, optionally cascading through stages, and returns an `EvaluationResult`.
7. The worker ships a `SerializableResult` back to the main process, which reconstructs a `Program` and inserts it into the database, updating MAP-Elites cells and triggering migration if the per-island generation counter has reached `migration_interval`.

<img src="./assets/openevolve_architecture.png" width="500" height="400">

### Program database

Each stored `Program` carries a UUID, parent id (for lineage), generation/iteration number, island id, the full source string, a metrics dict, feature-grid coordinates derived from raw metric values, and a pending-artifacts dict. Artifacts below ~10 KB are stored inline; larger ones spill to disk. Parent selection within an island uses an exploitation/exploration split (roughly 70/30 by default), biased toward high-fitness programs for parents. Inspirations are selected **separately and deliberately differently** — drawn from top performers, lineage ancestors, diverse MAP-Elites extremes, and random samples — so that the LLM's creative context doesn't collapse onto the same handful of programs it's being told are the best.

### Prompt construction

Default prompt templates live in `openevolve/prompt/templates.py`. A custom set can be supplied by pointing `prompt.template_dir` at a folder containing files like `system_message.txt`, `diff_user.txt`, `full_rewrite.txt`, `evolution_history.txt`, `top_programs.txt`, and — for LLM-feedback evaluation — `evaluator_system_message.txt` and `evaluation.txt`. Placeholders include `{metrics}`, `{improvement_areas}`, `{artifacts}`, `{evolution_history}`, `{current_program}`, `{previous_attempts}`, `{top_programs}`, and `{program_number}`. Setting `prompt.use_template_stochasticity: true` with a `template_variations` dict lets OpenEvolve randomly swap in different phrasings each generation to diversify outputs. A rendered diff-mode prompt ends with an exact instruction block:

### Diff mode vs full rewrite

**Diff mode is the default and preferred strategy.** The LLM emits one or more SEARCH/REPLACE blocks; the parser locates the exact SEARCH text inside the parent's `EVOLVE-BLOCK` region and substitutes. The diff delimiter pattern is itself configurable. **Full-rewrite mode** has the LLM emit a complete replacement program; it is less demanding for smaller models but lower-quality on longer files. `allow_full_rewrites: true` with `diff_based_evolution: true` lets OpenEvolve occasionally request full rewrites as an escape hatch.

### Parallelism, async, and checkpointing

Parallelism is **process-based** via `concurrent.futures.ProcessPoolExecutor` in `ProcessParallelController`, deliberately bypassing the GIL for CPU-bound evaluators. Workers initialize once, lazily create their LLM clients and evaluators, and then loop on sample→prompt→LLM→evaluate. The database snapshot model means workers never contend on locks. Running in serial mode is catastrophically slow (~14× slower and ~50% lower solution quality per the authors' benchmarks) — **parallelism is effectively mandatory for acceptable results**, not optional. LLM calls inside workers are synchronous OpenAI SDK calls; `OpenEvolve.run()` itself is awaited in examples and appears to be an `asyncio` coroutine at the top level (uncertain from external docs alone, but consistent with `await` usage). Checkpoints are fully resumable: the database state (programs, islands, archives, feature maps), best program, and random seeds all persist, so continuation from `checkpoint_50` is byte-identical to an uninterrupted run through iteration 60.

### LLM backends

OpenEvolve is **OpenAI-API-compatible only** — there is no native Anthropic or Gemini SDK integration. Anthropic and Gemini are used through their OpenAI-compatible endpoints; local models via Ollama, vLLM, LM Studio, or OptiLLM. The `LLMEnsemble` normalizes the weights in the `models:` list and samples exactly one model per generation using a seeded `random.Random`, making model selection deterministic given `random_seed`. A distinct `evaluator_models` list is used only when `use_llm_feedback: true`, in which case every listed model is queried and their scores are averaged weighted by each model's weight. The project also supports "model-based islands" where each island is pinned to a specific model instead of weighted sampling. Recent releases fix provider-specific quirks (e.g., PR #385 fixed Anthropic models erroring when both `temperature` and `top_p` are passed).

---

## 4. Integration and customization

### The Python API

Two API surfaces coexist, both exported from `openevolve.__init__`. The **class-based API** is the original:

```python
import asyncio, os
from openevolve import OpenEvolve

os.environ["OPENAI_API_KEY"] = "..."

evolve = OpenEvolve(
    initial_program_path="initial_program.py",
    evaluation_file="evaluator.py",
    config_path="config.yaml",
)
best_program = asyncio.run(evolve.run(iterations=1000))

for name, value in best_program.metrics.items():
    print(f"  {name}: {value:.4f}")
print(best_program.code)
```

The **functional API** (`openevolve/api.py`) added in the 0.2.x line removes the filesystem boilerplate:

```python
from openevolve import run_evolution, evolve_function

# Inline code + callable evaluator — no files needed.
result = run_evolution(
    initial_program="def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)",
    evaluator=lambda path: {"score": benchmark_fib(path)},
    iterations=100,
)
print(result.best_code)

# Or wrap a Python function with test cases.
result = evolve_function(
    bubble_sort,
    test_cases=[([3,1,2], [1,2,3]), ([5,2,8], [2,5,8])],
    iterations=50,
)
```

Additional helpers `evolve_code` and `evolve_algorithm` exist with similar shapes. Exact kwargs lists for these helpers were not verified from source in this research — **confirm signatures against `openevolve/api.py` before relying on them in production**.

### Customization hooks

OpenEvolve has no formal plugin registry; customization is expressed through **configuration, prompt templates, and the evaluator module**. The supported surfaces are:

- **Custom evaluators**: any Python module exposing `evaluate(program_path)`, optionally with `evaluate_stage1/2/3` for cascade.
- **Custom metrics**: just return them from the evaluator; reference them by key in `database.feature_dimensions` to use them as MAP-Elites axes.
- **Custom prompt templates**: drop override files in `prompt.template_dir` to replace the code-oriented defaults. Inline a custom `prompt.system_message` directly in YAML for simpler cases. Use `prompt.use_template_stochasticity` for wording variety.
- **LLM-judge feedback**: set `evaluator.use_llm_feedback: true`, list `evaluator_models`, and supply `evaluator_system_message.txt` / `evaluation.txt`. Results blend with algorithmic scores via `llm_feedback_weight`.
- **Artifact side-channel**: `evaluator.enable_artifacts` + `prompt.include_artifacts` wires stderr, tracebacks, and custom debug data back into prompts.
- **Inference-time compute**: route the generator LLM through OptiLLM to get MoA, `executecode`, `readurls`, or `z3_solver` plugins by simply setting the model name (e.g., `"moa&readurls-o3"`).

### What can be evolved beyond code

The framework operates on text plus an evaluator — **it will evolve anything you can score**. Demonstrated non-code use cases include LLM system prompts (`examples/llm_prompt_optimization` [link](https://github.com/algorithmicsuperintelligence/openevolve/tree/main/examples/llm_prompt_optimization) reports +23% accuracy on HotpotQA), natural-language content (a Towards Data Science walkthrough evolves poetry using LLM-only evaluators), and configuration artifacts. Non-code use cases generally require custom prompt templates because the built-in templates assume the artifact is code, and usually pair best with `language: "text"` plus `diff_based_evolution: false`. OpenEvolve is explicit that it evolves **entire files**, not just single functions — a key differentiator from the earlier FunSearch system.

### Integration patterns

The natural ways to embed OpenEvolve in a larger pipeline are:

- **CLI mode with checkpoint hand-off**: drive `openevolve-run.py` from a job scheduler, and treat the `openevolve_output/checkpoints/` directory (plus `best/best_program.py`) as the pipeline artifact. `evolution_trace.jsonl` is easy to ingest into downstream analysis.
- **Library mode (inline)**: use `run_evolution(...)` with an in-process callable evaluator, avoiding the filesystem entirely — ideal when OpenEvolve is one stage of a Python pipeline.
- **Library mode (files)**: use `OpenEvolve(initial_program_path, evaluation_file, config_path).run(...)` when the evaluator has to be a separate file (e.g., because it imports heavyweight dependencies you don't want in the host process).
- **Evaluator-as-gateway**: any external system integration (web API calls, containerized sandboxes, distributed benchmarks) goes in the `evaluate()` function. OpenEvolve does not itself know how to sandbox untrusted code — you must supply that isolation.
- **Docker image**: `ghcr.io/algorithmicsuperintelligence/openevolve:latest` for reproducible deployment; mount a workspace, pass CLI args.
- **MCP tool wrapper**: the AMD ROCm blog demonstrates exposing OpenEvolve as an MCP tool inside a Cline coding agent; this pattern works for any agent framework that can call a subprocess or Python function.

For reproducibility in a pipeline, rely on `random_seed` (default 42), which is propagated to the LLM ensemble, database, and evaluator.

### Known limitations and gotchas

Cost is the dominant real-world constraint. The README's rough per-iteration estimates are **o3 ≈ $0.15–0.60, o3-mini ≈ $0.03–0.12, Gemini-2.5-Pro ≈ $0.08–0.30, Gemini-2.5-Flash ≈ $0.01–0.05**; with 1000 iterations across multiple islands, paid runs can quickly reach hundreds of dollars. Recommended mitigations are cascade evaluation to filter failing candidates early, smaller populations, cheaper models for early iterations, and Gemini free-tier or Ollama for development. Gemini's free tier has tightened since late 2025, producing 429s during long runs.

Specific known issues worth flagging:

- **Cascade silent fallback**: `cascade_evaluation: true` without `evaluate_stage1` falls through to `evaluate()` with no warning.
- **Default templates are code-oriented**: non-code evolutions require a full custom template set.
- **Top-level vs nested fields**: forgetting that `diff_based_evolution`, `allow_full_rewrites`, `max_iterations`, and `random_seed` are top-level is a frequent config error.
- **No built-in sandboxing**: the evaluator executes arbitrary LLM-generated code in-process. For untrusted domains, wrap evaluation in a container or subprocess yourself.
- **Active churn**: the codebase is explicitly a research project; expect breaking changes across minor releases. Pin a version in production.

---

## 5. Glossary

| Term | Meaning |
|---|---|
| **AlphaEvolve** | Google DeepMind's Gemini-powered evolutionary coding agent (May 2025), which OpenEvolve reimplements. |
| **Archive** | The collection of elite programs across all MAP-Elites cells (and across islands). |
| **Artifacts** | Side-channel data (stderr, tracebacks, LLM feedback, profiler output) returned by the evaluator and injected into later prompts. |
| **Cascade evaluation** | Multi-stage evaluation (`evaluate_stage1/2/3`) gated by thresholds so expensive tests only run on promising candidates. |
| **Combined score** | Reserved metrics-dict key used preferentially for ranking; when absent, OpenEvolve averages numeric non-feature metrics. |
| **Controller** | The `OpenEvolve` / `ProcessParallelController` class that orchestrates the evolution loop. |
| **Diff mode** | LLM emits SEARCH/REPLACE blocks that patch specific fragments of the parent program. Default mode. |
| **EVOLVE-BLOCK markers** | `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` comment sentinels delimiting the mutable region of the initial program. |
| **Elite** | The best program occupying a given MAP-Elites cell. |
| **Ensemble** | Weighted list of LLMs under `llm.models`; one is sampled per generation by weight. |
| **Evaluator** | User-supplied Python module whose `evaluate(program_path)` returns a metrics dict (or `EvaluationResult`). |
| **Feature dimensions** | The axes of the MAP-Elites grid; configured in `database.feature_dimensions` and binned automatically by OpenEvolve. |
| **Full-rewrite mode** | LLM emits a complete replacement program instead of a diff. Better for weaker models or short files. |
| **Generation** | Per-island iteration counter used to trigger migration. |
| **Inspiration programs** | Programs from elsewhere in the database included in the prompt for context; deliberately chosen to differ from the "top programs" shown in metrics. |
| **Island** | An isolated sub-population with its own MAP-Elites grid; evolves in parallel with others and exchanges programs via ring migration. |
| **Iteration** | One sample→prompt→LLM→evaluate→insert cycle executed by a worker. |
| **LLM feedback** | Optional secondary LLM-as-judge step that scores code quality; merged into metrics via `llm_feedback_weight`. |
| **MAP-Elites** | Multi-dimensional Archive of Phenotypic Elites — quality-diversity algorithm that keeps the best program in each cell of a discretized feature space. |
| **Migration** | Periodic transfer of top programs from one island to the next in ring topology, triggered by generations (not wall-clock). |
| **OptiLLM** | Same author's inference-time-compute proxy; exposes test-time plugins (MoA, executecode, z3_solver) via model-name strings. |
| **Prompt Sampler** | Component that builds prompts using parent, inspirations, metrics, artifacts, and templates. |
| **Program Database** | Central store of all programs, metadata, island assignments, and MAP-Elites cells (`openevolve/database.py`). |
| **Quality-diversity search** | Family of algorithms (including MAP-Elites) that optimize for a portfolio of diverse high performers rather than a single optimum. |

---

## 6. Further reading

The canonical sources to consult next are the **OpenEvolve GitHub repository** (`https://github.com/algorithmicsuperintelligence/openevolve`, formerly `codelion/openevolve`) — particularly its README, `CLAUDE.md` developer-orientation doc, `configs/default_config.yaml`, and the `examples/` directory (start with `function_minimization`, then `circle_packing` and `llm_prompt_optimization`). The **PyPI page** (`https://pypi.org/project/openevolve/`) tracks release metadata. The **release notes** and recent PRs are worth scanning for breaking changes before pinning a version.

For conceptual background, read **DeepMind's AlphaEvolve blog post** (14 May 2025, `https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/`), the accompanying **whitepaper PDF**, and the **arXiv version** at `https://arxiv.org/abs/2506.13131`. DeepMind's `google-deepmind/alphaevolve_results` repo documents the reported results. For community context, see the **author's Hugging Face launch blog** (`https://huggingface.co/blog/codelion/openevolve`, 20 May 2025), the **Show HN thread** (`https://news.ycombinator.com/item?id=44043625`), Michael Lones's critical commentary "The boring truth about AlphaEvolve", the **Towards Data Science walkthrough** "Beyond Code Generation: Continuously Evolve Text with LLMs" which demonstrates non-code usage, and the **DeepWiki indexed source tour** at `https://deepwiki.com/codelion/openevolve` which cross-references file and line numbers. Recent academic follow-ups that benchmark against OpenEvolve include **CodeEvolve** (arXiv 2510.14150), **GigaEvo** (arXiv 2511.17592), and **"Barbarians at the Gate: How AI is Upending Systems Research"** (arXiv 2510.06189).

---

## Conclusion: what to take away

OpenEvolve is best understood as a small, legible scaffolding around one central idea — **use an LLM as a mutation operator, and let MAP-Elites plus islands maintain a diverse portfolio of candidate programs** — plus a growing list of practical ergonomics: artifacts, cascades, LLM-judge feedback, checkpoints, and a visualizer. For an integrator, the three files you write (initial program, evaluator, config) are the entire contract with the framework, and your evaluator is the only place you truly need to exercise engineering judgment: it defines fitness, gates cost, enforces safety, and bridges to the external world. The framework itself is still a moving target — expect config fields to drift, expect provider-specific bugs, expect to read the source when docs disagree — but the conceptual model is stable and matches AlphaEvolve's architecture closely enough that the DeepMind paper is a useful ongoing reference. Pin a version, write a good evaluator, start with cheap models and short runs, and treat `best/best_program.py` plus the checkpoint directory as your integration artifacts.