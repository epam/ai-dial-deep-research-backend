# Tasks

## 1. Prompts

- [x] 1.1 In `PREP_AGENT_SYSTEM`, state the rule where the agent is told to resolve a mechanical time normalization itself, and count the default-span example the same way; verify by reading the rendered prompt in a test
- [x] 1.2 In `QUERY_REVIEW_SYSTEM`, add the rule next to the line on relative spans; verify by reading the rendered prompt in a test
- [x] 1.3 Add prompt tests that both prompts carry the rule and that the default-span example ends with the current year; verify with `make test`
- [x] 1.4 Run `make format` and `make lint`; verify both pass


## Workflow follow-up

- Archive the change in the same pull request, as this repository does.
