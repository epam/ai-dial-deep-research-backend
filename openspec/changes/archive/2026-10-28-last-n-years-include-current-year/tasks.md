# Tasks

## 1. Prompts

- [x] 1.1 In `PREP_AGENT_SYSTEM`, state the rule where the agent is told to resolve a mechanical time normalization itself, and count the default-span example the same way; verify by reading the rendered prompt in a test
- [x] 1.2 In `QUERY_REVIEW_SYSTEM`, add the rule next to the line on relative spans; verify by reading the rendered prompt in a test
- [x] 1.3 Add prompt tests that both prompts carry the rule and that the default-span example ends with the current year; verify with `make test`
- [x] 1.4 Run `make format` and `make lint`; verify both pass

## 2. Preparation eval (private repository)

- [x] 2.1 Add preparation cases: a two-turn conversation that asks for "the last 2 years" and a single-turn "last 10 years"; add the current-year red flag to the existing relative-span case and to the decline-to-choose case, and update the comments that show the old default span; verify the files parse as YAML
- [x] 2.2 Run the time-period cases twice each on a local app with the new prompt, and once on the old prompt as a baseline; verify the new cases pass and the existing ones do not regress, and record the outcomes in the case comments. Done on 2026-10-28 for the time-period cases and the decline-to-choose case; three cases could not be run because the key hit its cost limit
- [x] 2.3 Re-run the time-period cases, the decline-to-choose case (three times) and the three unrun cases after the 2026-10-29 prompt edits (the resolved years go into the query; the default opens the reply); verify the recorded query carries the years and the default is announced. Done on 2026-10-29: all pass, the years were in the query every time, the default was announced in both runs that reached it

## Workflow follow-up

- Archive the change in the same pull request, as this repository does.
