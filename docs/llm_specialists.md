# Specialized LLM agents

Five specialists can now invoke an LLM independently after the deterministic financial engine completes. Their configurable role prompts live in `backend/app/agents/prompts/{financial,credit,market,liquidity,operational}.md`. Administrator overrides use `AGENT_PROMPTS_DIR`; fixed guardrails are appended and prompt hashes are stored with each interpretation.

## Enable

Keep offline mode with `SPECIALIST_PROVIDER=deterministic` (the default). To enable provider-backed interpretation in backend `.env`:

```dotenv
SPECIALIST_PROVIDER=openai-compatible
OPENAI_API_KEY=<your-provider-key>
SPECIALIST_MODEL=<model-supporting-strict-json-schema-and-function-calling>
# Optional compatible endpoint:
# OPENAI_BASE_URL=https://your-compatible-provider.example/v1
# Optional per-dimension overrides, as JSON:
# SPECIALIST_MODELS={"credit":"credit-model-id","market":"market-model-id"}
```

If `SPECIALIST_MODEL` is unset, it falls back to `OPENAI_MODEL`; `SPECIALIST_MODELS` overrides individual dimensions. Provider compatibility and account model access must be tested before enabling. Narrative generation is independent: `MODEL_PROVIDER` may remain deterministic when specialist models are enabled. No credentials were used for live provider calls in this implementation session.

## Contracts and permissions

`SpecialistProvider` is a Python protocol. The supplied adapter uses the OpenAI-compatible Chat Completions interface, strict JSON schema responses and strict function arguments. This follows the distinction between [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat) and [function calling](https://developers.openai.com/api/docs/guides/function-calling?api-mode=chat) in the official documentation. Other adapters can implement the protocol; non-OpenAI compatible endpoints must support these specific contracts or fail explicitly.

An evidence packet includes only the specialist's canonical metrics, deterministic findings, source records referenced by that dimension and provenance. Market price evidence is summarized with its period/count; its deterministic metrics contain the calculations. Uploaded source text remains in the user-data message, never in role instructions.

The sole available tool, `get_metric`, returns a server-computed metric from that packet. The schema enumerates permitted metric keys. Runtime dispatch rejects unknown tools, keys and extra arguments. There is no assessment selector, database query tool, shell, browser, file write or order-execution capability. A maximum of three tool rounds (configurable 1–5), four calls per round and a per-specialist wall-clock timeout bound execution. Each model response has a configured completion-token limit. Models without tools can directly return the structured interpretation.

`SpecialistAnalysis` contains dimension, insights and limitations. An insight has a kind, interpretation text, canonical finding IDs, metric IDs and evidence IDs. Every insight must reference a known finding or metric and actual corresponding evidence within that dimension. Extra schema fields, including generated scores, are rejected. Model output has no authority to mutate metrics, categories, scores, source records or workflow control.

## Presentation and failure behavior

Accepted output is attached as `AgentOutput.llm_interpretation`, stored in checkpoints/execution artifacts and exposed in the Agent Activity view. The view separately discloses provider/model, status, references, prompt hash, usage and limitations. Its validation label explicitly states that semantic financial claims remain unverified: valid schema and source IDs do not prove entailment or truth.

Provider refusal, invalid JSON/schema, unauthorized calls, invented references, missing credentials or timeout produce a sanitized failed interpretation, a critic warning and `completed_with_warnings`; deterministic metrics and findings remain available. The workflow does not repeatedly call an unavailable provider as a supposed evidence correction. A dimension with no source evidence does not call a model. Cancellation is propagated for job recovery.

Recorded usage sums all saved specialist execution attempts, including targeted reanalysis, plus narrative usage. Missing usage is null rather than fabricated zero; cost is null for paid providers until an explicit pricing policy is implemented. No hidden SDK retries are used for specialist calls. Crash-lost/in-flight provider requests may not appear in saved token counts and can be billed again on replay.

Tests use both injected protocol implementations and the real OpenAI SDK against `httpx.MockTransport`: all five roles, strict output/request contracts, read-only tool loops, tool budgets, unauthorized names/keys/arguments, refusal, unsupported references, timeout, prompt/data separation, unchanged numerical outputs and token accounting are verified without paid API access. They do not establish live model quality, semantic prompt-injection resistance or provider availability.
