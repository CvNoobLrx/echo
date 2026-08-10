# Echo Core Specification

## Requirement: Echo product identity

Echo MUST expose the user-visible Chinese name `回声` and English name `Echo`. Product package names, application metadata, container names, database defaults and search index prefixes MUST use the `echo` identity.

### Scenario: User opens the application

- Given the Echo stack is running
- When the user opens the web application or API documentation
- Then the displayed product identity is Echo/回声
- And no Comet/彗记 product identity is displayed

## Requirement: Focused personal AI workspace

Echo MUST retain authentication, personal model configuration, knowledge bases, document ingestion, memory management, graph memory retrieval, streaming chat and optional web search.

### Scenario: User asks a question

- Given the user has configured the required models
- When the user submits a chat message
- Then Echo streams the response over SSE
- And the Agent can retrieve personal knowledge and memory
- And the Agent can use web search when enabled and needed

## Requirement: Asynchronous core processing

Echo MUST retain non-periodic asynchronous document, memory and image processing. Echo MUST NOT run a periodic scheduler or proactive task system.

### Scenario: Worker starts

- When the asynchronous worker starts
- Then it consumes only retained non-periodic queues
- And no Beat service, periodic schedule or proactive task heartbeat is required

## Requirement: Retained assistant modules

Echo MUST expose deep research, verifier loops, personas, skills, group chat, human-chat simulation, favorites, notifications, dashboard statistics, voice input, tracing and cost accounting.

### Scenario: User navigates Echo

- When an authenticated user views navigation and settings
- Then routes and controls for the retained assistant modules are present
- And their API route groups and user-isolated data structures are registered

## Requirement: Removed modules

Echo MUST NOT expose emotion analysis, music, memory communities, scheduled/proactive tasks or sharing.

### Scenario: Removed capabilities stay absent

- When an authenticated user views navigation and settings
- Then no route or control for emotion, music, memory communities, scheduled tasks or sharing is present
- And no Beat service or scheduling Agent tool is registered

## Requirement: Core infrastructure

Echo MUST use PostgreSQL, Elasticsearch with IK analysis, Neo4j and Redis, plus API, worker and web application services. No scheduler container is permitted.

### Scenario: Compose configuration is rendered

- When Docker Compose parses the development or production configuration
- Then only the four storage services and retained application services are defined
- And a Beat service is absent
