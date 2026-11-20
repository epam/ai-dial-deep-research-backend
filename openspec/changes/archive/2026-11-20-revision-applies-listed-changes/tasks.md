## 1. Revision request

- [x] 1.1 Change `REPORT_REVISION_REQUEST` in `src/dial_deep_research/app/research/prompts.py`: apply each listed change and change nothing else; an item that adds a value adds it with its citation where the item says; an item that corrects or removes a passage changes only that passage; keep every other sentence, table row and citation; output the whole revised report, and only the report
- [x] 1.2 Add a test that the rendered revision request carries the instruction to keep the unlisted parts of the draft, the review items inside `<revision_instruction>` and the draft inside `<draft>`

## 2. Checks

- [x] 2.1 Run `make format`, `make lint` and the tests
- [x] 2.2 Confirm that `docs/architecture.md` needs no update: the loop's nodes, edges and routing do not change
