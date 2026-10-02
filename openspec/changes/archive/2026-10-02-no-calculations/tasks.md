## 1. Prompts

- [x] 1.1 Add the plan rule and its example plan item to Stage 2 of `PREP_AGENT_SYSTEM`
- [x] 1.2 Add the "nobody calculates" bullet to "Research strategy" in `RESEARCH_AGENT_SYSTEM_PROMPT`
- [x] 1.3 In `RESEARCH_REVIEW_SYSTEM_PROMPT`, drop the calculation from the work handed to the writer, say that nobody calculates, and add when a computed figure counts as covered
- [x] 1.4 Add the "## No calculations" section to `REPORT_SYSTEM_PROMPT`, name the rule in the "These rules outrank the request" paragraph, and say that stating a figure is not given is not a declined-request explanation
- [x] 1.5 Add check 7, "No calculations", to `REPORT_REVIEW_SYSTEM_PROMPT`, and renumber the glossary check to 8
- [x] 1.6 Build the writer's section and check 7 from one `CALCULATION_DEFINITION`, carrying the rounding exemption and the precedence over section descriptions and client rules
- [x] 1.7 Tell `QUERY_REVIEW_SYSTEM` never to ask how a figure should be computed
- [x] 1.8 Say in the preparation prompt that looking for what explains a difference between sources is not a calculation, and in the source-selection report-review part on disagreements that the "No calculations" check covers a figure computed from different facts
- [x] 1.9 State in the client-rules block, the research agent's bullet, research review's sentence and the shared definition that the rule that nobody calculates has the highest priority and no client rule overrides it

## 2. Tests

- [x] 2.1 Add prompt tests: the preparation prompt carries the plan rule; the research-agent, research-review, writer and report-review prompts carry their parts; research review no longer calls a calculation the writer's; the glossary check is numbered 8; the query check never asks how to compute; the writer and the reviewer carry the same definition

## 3. Docs and verification

- [x] 3.1 Add the preparation agent's part to rule 3 of the "Faithful relay of the sources" policy and to its row in `quality_policies.md`, in the internal documentation repository
- [x] 3.2 Run `make format`, `make lint` and `make test`
- [ ] 3.3 Run a query that asks for a computed figure against a local server, if one is running, and check the plan and the report; keep the conversation files outside the repository
- [x] 3.4 Check every channel's client rules on the main branch of the private configuration repository for a rule that asks for a calculation
