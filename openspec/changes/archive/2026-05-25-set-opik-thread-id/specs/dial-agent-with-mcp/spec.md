## ADDED Requirements

### Requirement: Opik trace thread id sourced from incoming request

When Opik tracing is enabled, the app SHALL attempt to extract a thread identifier from the incoming chat completion request via a generically-named extraction helper (e.g. `extract_thread_id`) and construct the per-request `OpikTracer` with that identifier as its `thread_id`. The helper's body, today, SHALL only know how to read DIAL's conversation header (`X-CONVERSATION-ID`) from `request.headers`; the helper SHALL be named so a future second source can slot in without renaming. The helper SHALL be exception-safe: on any failure path — header absent, value empty after whitespace strip, request shape unexpected, or any other exception during extraction — the helper SHALL return `None`. When the helper returns `None`, the tracer SHALL be constructed without a `thread_id`, and the turn SHALL be traced exactly as before this change (one ungrouped trace per turn). Extraction failures SHALL NOT raise out of the helper and SHALL NOT cause the chat completion to fail.

#### Scenario: DIAL conversation id grouped into a single Opik thread
- **WHEN** Opik tracing is enabled and the chat completion request carries an `X-CONVERSATION-ID` header with a non-empty value, and the same conversation issues multiple turns
- **THEN** every turn's Opik trace SHALL be created with `thread_id` set to that conversation id, so all turns of the conversation appear under a single Opik thread in the Opik UI

#### Scenario: Conversation id missing falls back to ungrouped tracing
- **WHEN** Opik tracing is enabled and the chat completion request does not carry an `X-CONVERSATION-ID` header (e.g. a raw API client or eval harness call)
- **THEN** the tracer SHALL be constructed without a `thread_id`, the turn SHALL still be traced normally, and the trace SHALL appear as an individual record in Opik exactly as it did before this change

#### Scenario: Empty conversation id treated as missing
- **WHEN** Opik tracing is enabled and the request carries `X-CONVERSATION-ID` with an empty or whitespace-only value
- **THEN** the extraction helper SHALL return `None` and the tracer SHALL be constructed without a `thread_id`

#### Scenario: Extraction failure never breaks the turn
- **WHEN** Opik tracing is enabled and any exception is raised while attempting to read the conversation id (e.g. an unexpected `request.headers` shape on a future SDK version)
- **THEN** the helper SHALL return `None`, the tracer SHALL be constructed without a `thread_id`, the chat completion SHALL proceed normally, and no exception SHALL propagate out of the helper

#### Scenario: Thread id is not extracted when tracing is disabled
- **WHEN** Opik tracing is disabled (`OPIK_TRACING_ENABLED` unset or false) and a chat completion request is processed
- **THEN** no `OpikTracer` SHALL be constructed and no thread-id extraction SHALL run, preserving the "no Opik network calls and no Opik-dependent code paths" behaviour of the existing tracer-absent requirement
