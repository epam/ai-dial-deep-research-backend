# multimodal-tool-output

## Purpose

Tools loaded by the agent may return content other than plain text — notably images. MCP delivers these as standardized LangChain v1 content blocks (e.g. `{type: "image", base64, mime_type}`), and the agent forwards them unchanged inside `ToolMessage.content`. For the model to actually perceive that content, the deployment's LLM endpoint must accept multimodal content inside tool-result messages. OpenAI's `/chat/completions` endpoint does not (tool-message content is typed text-only and image blocks are silently dropped); OpenAI's `/responses` API does, as do Anthropic Claude's native API and similar provider-side endpoints. This capability captures the contract the agent imposes on whatever LLM path its deployment provides.

## Requirements

### Requirement: LLM endpoint accepts multimodal content in tool-result messages

The agent SHALL forward MCP tool outputs as `ToolMessage.content` blocks in the LangChain v1 standard form (e.g. `{type: "image", base64, mime_type}` for image content), without provider-specific flattening. Any deployment of the app SHALL route the agent's LLM calls — directly or indirectly — to an upstream model whose API accepts those blocks as part of tool-result messages. Indirect routing (e.g. a DIAL adapter that translates `/chat/completions` into the upstream provider's `/responses` API) SHALL satisfy this requirement provided the upstream endpoint accepts the content. Deployments whose LLM path terminates at OpenAI `/chat/completions` without `/responses` translation SHALL be considered non-conforming, because that endpoint silently drops image blocks from tool-result messages.

#### Scenario: Image-returning MCP tool reaches the model
- **WHEN** an MCP tool returns image content and the agent emits a `ToolMessage` whose `content` is a list containing a `{type: "image", base64, mime_type}` block
- **THEN** the configured LLM endpoint SHALL deliver that block to a model that can perceive it, and the next assistant turn SHALL be able to reason over the image
