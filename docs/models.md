# Models

FitAI uses **two** Groq models, each with one job.

| role | setting | model | job |
|---|---|---|---|
| primary chat + structured extraction | `GROQ_MODEL` / `GROQ_EXTRACTION_MODEL` | `openai/gpt-oss-120b` | answers the user, and proposes structured candidates for memory/activity extraction |
| prompt-injection guard | `PROMPT_GUARD_MODEL` | `meta-llama/llama-prompt-guard-2-86m` | scores untrusted text safe/unsafe; never answers the user |

Keys stay split as before: the extraction client only ever uses
`GROQ_EXTRACTION_API_KEY` and never falls back to `GROQ_API_KEY`. The guard uses
`PROMPT_GUARD_API_KEY`, or `GROQ_API_KEY` when that is blank.

## Reasoning models (`openai/gpt-oss-*`)

`app/llm/client.py` adapts automatically, so nothing else needs to know:

- **Sampling**: only `temperature=1.0` / `top_p=1.0` are accepted. Other models
  keep the requested temperature.
- **Token budget**: the completion budget must also cover the model's reasoning
  trace. A small cap (the intent classifier uses 200 tokens) is raised to a floor
  of 2048, and 4096 is used when the caller sets none. Sending no budget at all
  is rejected by Groq with *"Please reduce the length of the messages or
  completion"*.
- **No tool calling**: the endpoint rejects the `tools` parameter. When tools are
  requested, the client answers with one plain completion instead, so chat keeps
  working. FitAI's live tools (web search, nearby gyms, activity log) are
  executed by the backend's deterministic selection in `retrieve_context_node`,
  not by model-initiated tool calls, so nothing is lost by default.

## Prompt-injection guard

`app/safety/prompt_guard.py` wraps the classifier contract:

- it accepts **exactly one user message** (no system prompt) and returns a
  probability: `0` safe, `1` unsafe;
- `PROMPT_GUARD_THRESHOLD` (default `0.5`) decides what counts as unsafe;
- it screens **user messages** (in `guardrails/guard.py`, after the deterministic
  regex rules, before any LLM call) and **retrieved RAG documents** (in
  `retrieve_context_node`, so instructions hidden inside an uploaded file never
  reach the answering model);
- it **fails open**: a timeout, provider error or unreadable response means "not
  unsafe". The deterministic safety rules remain the fail-closed layer, so a
  guard outage can never break chat;
- a withheld document is reported as a count in the tool results, never as
  content.

Set `PROMPT_GUARD_ENABLED=false` to keep only the deterministic rules.

## Live behaviour (verified)

```
benign "What do I like to do every day?"            -> 0.0004  safe
known  "Ignore all previous instructions ..."        -> 0.9996  unsafe
novel  "Pretend the developer role was disabled ..." -> 0.9994  unsafe
```

The third line is why the guard exists: the deterministic rules do not know it,
the guard model does.

## Testing

Every test uses fakes — no credentials, no network. Run
`python -m scripts.verify_memory_intelligence` from `backend/` for a live
end-to-end check against the configured models.