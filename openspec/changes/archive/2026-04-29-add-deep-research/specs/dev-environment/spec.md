## MODIFIED Requirements

### Requirement: Minimal developer README
The repository SHALL include a `README.md` at its root that describes, at minimum: prerequisites (Docker, uv install one-liner), how to install dependencies, how to start the stack, how to open the chat UI on `http://localhost:3000`, how to select the `Deep Research` deployment (deployment id `deep-research`), and how to tear the stack down.

#### Scenario: Cold-start contributor
- **WHEN** a new contributor follows the README top-to-bottom
- **THEN** they SHALL reach a working chat UI conversing with the `Deep Research` application without consulting other repositories or internal documentation
