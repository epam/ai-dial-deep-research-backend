## 1. Reorder README sections

- [x] 1.1 Move **Configuration**, **Environment variables**, and **DIAL core configuration** up so they follow the intro, in that order (config block).
- [x] 1.2 Fold **Prerequisites** into **Local run** as its opening subsection; place **Local run** after the config block.
- [x] 1.3 Keep **Running the app in Docker (opt-in)**, **Driving the app from the CLI**, and **LLM tracing with Opik (optional)** last, in that order.
- [x] 1.4 Move section bodies verbatim — no rewording, no additions, no deletions.

## 2. Sync the table of contents

- [x] 2.1 Reorder the top-of-file TOC anchor list to match the new section order.
- [x] 2.2 Remove the standalone Prerequisites TOC entry (now a subsection of Local run).

## 3. Verify

- [x] 3.1 Check every in-page link still resolves (headings unchanged, only positions moved); confirm the DIAL-core-configuration section still restates the APP_PORT / macOS note so it is self-contained now that it precedes Local run.
- [x] 3.2 Read the README top-to-bottom to confirm the cold-start-contributor flow still reaches a working chat UI, and that configuration now appears before dev setup.
- [x] 3.3 Run `make lint` (README/markdown checks) and confirm no drift is reported.
