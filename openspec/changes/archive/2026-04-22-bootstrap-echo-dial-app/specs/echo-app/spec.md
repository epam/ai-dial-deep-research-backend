## ADDED Requirements

### Requirement: DIAL-protocol application server
The repository SHALL implement an application server that conforms to the DIAL application protocol, using the official DIAL Python SDK, exposing a chat completion endpoint consumable by DIAL core.

#### Scenario: Request accepted from DIAL core
- **WHEN** DIAL core forwards a chat completion request to the app with a well-formed DIAL envelope
- **THEN** the app SHALL accept the request and respond with a well-formed DIAL chat completion response

#### Scenario: Rejects malformed requests
- **WHEN** the app receives a request that does not conform to the DIAL application protocol
- **THEN** it SHALL respond with an appropriate HTTP 4xx error surfaced via the SDK, without crashing the server process

### Requirement: Echo behavior for the last user message
The app SHALL treat each incoming chat completion request as an echo: the assistant response content SHALL be the textual content of the last message in the request whose role is `user`, prefixed with a stable, short marker that identifies the response as an echo (e.g. `echo: `).

#### Scenario: Single user turn
- **WHEN** the request contains exactly one user message with content `"hello"`
- **THEN** the assistant response content SHALL equal `"echo: hello"`

#### Scenario: Multi-turn history
- **WHEN** the request contains multiple messages and the last one has role `user` with content `"ping"`
- **THEN** the assistant response content SHALL equal `"echo: ping"` regardless of the contents of earlier messages

#### Scenario: Empty last user message
- **WHEN** the request's last user message has empty string content
- **THEN** the assistant response content SHALL equal `"echo: "` (the marker with no trailing text)

#### Scenario: Non-text attachments on the user message
- **WHEN** the last user message carries non-text attachments alongside text content
- **THEN** the app SHALL echo only the text content and SHALL NOT fail due to the presence of attachments

### Requirement: Streaming response path
The app SHALL produce its echo response through the SDK's streaming API so that the streaming code path is exercised end-to-end, even though the content is trivial.

#### Scenario: Streamed delivery
- **WHEN** DIAL core requests a streaming chat completion
- **THEN** the app SHALL emit the echo content via one or more streaming chunks terminated by an end-of-stream signal, conforming to the SDK's streaming contract

### Requirement: Health endpoint
The app SHALL expose a lightweight health check endpoint that returns success when the process is able to serve requests.

#### Scenario: Health probe
- **WHEN** a client (or Docker healthcheck) issues a GET to the health endpoint
- **THEN** the app SHALL respond with HTTP 200 and a minimal body indicating healthy status

### Requirement: Local run without Docker
The app SHALL be runnable directly on a developer machine (outside Docker) against a configurable host and port, suitable for iterating on the handler with only Python tooling installed.

#### Scenario: Local run target
- **WHEN** a contributor runs `make run`
- **THEN** the app process SHALL start and serve on a documented localhost port, independent of whether Docker Compose is running
