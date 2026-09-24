## 1. Demo pills

- [x] 1.1 Pass `pill_title_max_chars=None` to `convert_citations` in the demo, and drop the
  default-budget constant it replaces (`app/annotations_demo/completion.py`)

## 2. Tests and docs

- [x] 2.1 Assert that the demo's pill titles equal its popup-card titles, each the whole attachment
  title followed by the cited page (`tests/test_annotations_demo.py`)
- [x] 2.2 Say in the demo's "What to look for" list in `README.md` that the title is whole on the
  pill as on the popup card
- [x] 2.3 Run `make format`, `make lint` and the test suite
