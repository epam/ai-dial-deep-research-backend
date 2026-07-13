## MODIFIED Requirements

### Requirement: Minimal developer README
The repository SHALL include a `README.md` at its root that describes, at minimum: prerequisites (Docker, uv install one-liner), how to install dependencies, how to start the stack, how to open the chat UI on `http://localhost:3000`, how to select the `Deep Research` deployment (deployment id `deep-research`), and how to tear the stack down.

The README SHALL order its top-level sections by audience, widening from general to specialized: a general-audience introduction first, then a configuration-and-deployment block (what to configure, the environment-variables reference, and DIAL Core registration) aimed at operators, then the contributor sections (local run with its prerequisites, followed by optional developer tooling). Contributor-only content SHALL NOT precede the configuration-and-deployment block.

#### Scenario: Cold-start contributor
- **WHEN** a new contributor follows the README top-to-bottom
- **THEN** they SHALL reach a working chat UI conversing with the `Deep Research` application without consulting other repositories or internal documentation

#### Scenario: Operator finds configuration before dev setup
- **WHEN** a reader opens the README to configure or deploy the app
- **THEN** the configuration and environment-variables sections SHALL appear before the local-development and contributor sections, so the reader reaches configuration without scrolling past dev setup
