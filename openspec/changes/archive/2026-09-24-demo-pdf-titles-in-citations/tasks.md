## 1. Demo labels

- [x] 1.1 Return each attachment's title, stripped and `None` when blank, alongside its URL from
  the demo's attachment resolution (`app/annotations_demo/attachments.py`)
- [x] 1.2 Pass the titles and the default `max_pill_title_chars` to `convert_citations`, and log
  the titled count on the `citations resolved` event (`app/annotations_demo/completion.py`)

## 2. Tests and docs

- [x] 2.1 Test that the popup entries carry the whole attachment title and the pills the shortened
  one, and that an attachment without a title is labelled from its marker
  (`tests/test_annotations_demo.py`)
- [x] 2.2 Describe the labels in the demo's "What to look for" list in `README.md`
- [x] 2.3 Run `make format`, `make lint` and the test suite
