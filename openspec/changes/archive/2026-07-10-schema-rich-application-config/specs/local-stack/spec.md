# local-stack (delta)

## MODIFIED Requirements

### Requirement: Deep Research app registered as a DIAL application
The DIAL core configuration SHALL register Deep Research as a schema-rich application **type** plus at least one application **instance**, and SHALL ship a single API key (name: `dial_api_key`, role: `default`) under which the chat UI can invoke it:

- An `applicationTypeSchemas` entry SHALL declare the type: display name `Deep Research`, `dial:applicationTypeCompletionEndpoint` pointing at `http://host.docker.internal:5000/openai/deployments/deep-research/chat/completions`, `dial:applicationTypeSchemaEndpoint` pointing at `http://host.docker.internal:5000/v1/configuration-support/application-schema`, and `dial:appendApplicationPropertiesHeader: false`. Core's settings (`dial_conf/settings/settings.json`) SHALL keep `applications.includeCustomApps` enabled.
- At least one application instance SHALL reference the type via `applicationTypeSchemaId` and carry an `applicationProperties` object valid against the schema (the committed example properties).

Because `dial_conf/core/config.json` is untracked, the README SHALL document generic example snippets for both the `applicationTypeSchemas` entry and an instance, kept in sync with the schema.

#### Scenario: Application visible in chat UI
- **WHEN** a contributor opens the chat UI after the stack is up
- **THEN** the application instance of type `Deep Research` SHALL appear as a selectable application/agent in the UI

#### Scenario: Routing to the host-running app with instance properties
- **WHEN** a user sends a message to a Deep Research instance from the chat UI
- **THEN** DIAL core SHALL proxy the request to the host-running app over `host.docker.internal:5000` at the `deep-research` deployment path with the application identity attached, and the turn SHALL run with that instance's `applicationProperties`

#### Scenario: Core loads the schema from the app
- **WHEN** DIAL core (>= 0.41.0) starts with the `applicationTypeSchemas` entry configured and the host app running
- **THEN** core SHALL fetch the property schema from the app's schema endpoint and accept instances whose `applicationProperties` validate against it
