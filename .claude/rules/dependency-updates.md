---
paths:
  - "pyproject.toml"
  - "poetry.lock"
---

# Updating dependency versions

The image installs from `poetry.lock`, so the lockfile decides what runs. `pyproject.toml` states
which versions the code supports.

- **Indirect dependency** (not listed in `pyproject.toml`): change only the lockfile, with
  `poetry update --lock <package>`. Do not add it to `pyproject.toml` just to set a minimum
  version. CI already guards against a vulnerable version: every pull request builds the image
  and Trivy fails the required `docker_build` check on any known vulnerability.
- **Direct dependency**: raise its floor in `pyproject.toml` to the version you lock, so the
  floor never claims support for a version nothing tests. When the bump fixes a vulnerability,
  name it in the comment above the line, as in `1.30.0 fixes CVE-2026-59951.` Then run
  `poetry lock`.
- Relock with plain `poetry lock`, which keeps every locked version that still fits. Use
  `poetry lock --regenerate` only when you mean to move every package to its newest version.
- Check the lockfile diff: only the packages you meant to change, and the dependencies they
  require, may change version. Then run `poetry check --lock`, `make lint` and `make test`.
