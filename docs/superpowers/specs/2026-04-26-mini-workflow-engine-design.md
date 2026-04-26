# Mini Workflow Engine Design

## Goal

Build a runnable mini workflow engine for the AI Workflow Builder assignment. The engine receives an inquiry id, fetches the inquiry from the provided Mock API, classifies it with an LLM, looks up customer data, generates a tailored reply, waits for human approval, and sends the approved reply through the Mock Email API.

The implementation should focus on orchestration completeness rather than building a broad workflow platform or UI.

## Requirement Interpretation

The assignment requires a small backend system that demonstrates:

- Workflow definitions in JSON or YAML.
- DAG-based execution order and cycle detection.
- Sequential node execution.
- Context passing between nodes.
- Exponential backoff retry for transient failures.
- LLM function/tool-use style abstraction.
- Standardized Tool interfaces.
- Commercial LLM API integration with a local fake mode for tests and demos.
- Human-in-the-loop approval with pause, resume, reject, and timeout handling.
- Unit tests for core success and error paths.

The Mock API includes `category` in inquiry data, but the workflow should still run the `classify_email` LLM task. The provided category is treated as fixture/reference data, not as a replacement for classification.

## Architecture

The design is a lightweight orchestration engine with clear boundaries:

- API layer: starts workflow runs, returns run state, and accepts approval decisions.
- Workflow loader and validator: loads YAML and validates schema, dependencies, node types, and cycles.
- Workflow executor: runs nodes in DAG order, updates run state, writes context, pauses for approval, and resumes after approval.
- Node runners: dispatch node execution by `type`.
- Tool registry: maps tool names from YAML to tool implementations.
- LLM task registry: maps LLM task names from YAML to task implementations.
- Run store: stores the current workflow run snapshot.
- Retry executor: retries transient external failures only.

This is not intended to be a full generic workflow platform. It supports the node types required by the assignment: `tool`, `llm`, and `human_approval`.

## Workflow Definition

Workflow definitions use YAML. A node has:

- `key`: workflow-local role name and context reference key.
- `type`: runner selector, one of `tool`, `llm`, `human_approval`.
- `tool`: required when `type: tool`.
- `task`: required when `type: llm`.
- `depends_on`: direct DAG dependencies.
- `inputs`: mapping from workflow context into tool/task input.
- `timeout_seconds`: required for `human_approval`.

`key` is not a UUID. It is a human-readable workflow-local name, such as `fetch_inquiry` or `send_reply_email`. Reusable behavior comes from `type + tool/task`, not from the key.

Example:

```yaml
workflow_key: customer_support_auto_reply
version: "1.0.0"

nodes:
  - key: fetch_inquiry
    type: tool
    tool: inquiry_get
    inputs:
      inquiry_id: "{{ input.inquiry_id }}"

  - key: classify_inquiry
    type: llm
    task: classify_email
    depends_on:
      - fetch_inquiry
    inputs:
      subject: "{{ nodes.fetch_inquiry.inquiry.subject }}"
      body: "{{ nodes.fetch_inquiry.inquiry.body }}"

  - key: lookup_customer
    type: tool
    tool: crm_lookup
    depends_on:
      - fetch_inquiry
    inputs:
      email: "{{ nodes.fetch_inquiry.inquiry.from }}"

  - key: generate_reply
    type: llm
    task: generate_reply
    depends_on:
      - classify_inquiry
      - lookup_customer
    inputs:
      inquiry: "{{ nodes.fetch_inquiry.inquiry }}"
      category: "{{ nodes.classify_inquiry.category }}"
      customer: "{{ nodes.lookup_customer.customer }}"

  - key: wait_for_approval
    type: human_approval
    depends_on:
      - generate_reply
    timeout_seconds: 1800
    inputs:
      subject: "{{ nodes.generate_reply.subject }}"
      body: "{{ nodes.generate_reply.body }}"

  - key: send_reply_email
    type: tool
    tool: email_send
    depends_on:
      - wait_for_approval
    inputs:
      to: "{{ nodes.fetch_inquiry.inquiry.from }}"
      subject: "{{ nodes.generate_reply.subject }}"
      body: "{{ nodes.generate_reply.body }}"
```

## Tool Contracts

Tools are deterministic code-backed capabilities. Each tool has a name and an `execute(input_data) -> dict` contract.

### `inquiry_get`

Input:

```json
{
  "inquiry_id": "INQ-002"
}
```

Output:

```json
{
  "inquiry": {
    "inquiry_id": "INQ-002",
    "from": "minsu.kim@example.com",
    "subject": "카드 결제가 계속 실패합니다",
    "body": "...",
    "category": "billing",
    "status": "pending"
  }
}
```

### `crm_lookup`

Input:

```json
{
  "email": "minsu.kim@example.com"
}
```

Output:

```json
{
  "customer": {
    "customer_id": "C001",
    "name": "김민수",
    "email": "minsu.kim@example.com",
    "plan": "Enterprise",
    "status": "active",
    "recent_tickets": [],
    "tags": ["vip"]
  }
}
```

### `email_send`

Input:

```json
{
  "to": "minsu.kim@example.com",
  "subject": "Re: 카드 결제가 계속 실패합니다",
  "body": "안녕하세요..."
}
```

Output:

```json
{
  "message_id": "msg-abc123",
  "status": "sent",
  "to": "minsu.kim@example.com",
  "sent_at": "2026-04-26T00:00:00Z"
}
```

The generated email body remains in `context.nodes.generate_reply.body`; `email_send` stores only delivery result data.

## LLM Task Contracts

LLM task outputs should include only values consumed by later nodes.

### `classify_email`

Input:

```json
{
  "subject": "카드 결제가 계속 실패합니다",
  "body": "Enterprise 플랜 갱신을 위해..."
}
```

Output:

```json
{
  "category": "billing"
}
```

The category must be one of:

- `billing`
- `technical`
- `account`
- `feature_request`
- `general`

Invalid categories fail with `LLM_OUTPUT_VALIDATION_ERROR`.

### `generate_reply`

Input:

```json
{
  "inquiry": {},
  "category": "billing",
  "customer": {}
}
```

Output:

```json
{
  "subject": "Re: 카드 결제가 계속 실패합니다",
  "body": "안녕하세요..."
}
```

The task prompt includes the assignment's category response guidelines, customer plan rules, and prohibited response rules from code-side policy data.

## Run Store

The store keeps the current run snapshot. It should store data required to resume execution and inspect failures, not duplicate every provider response field.

Minimal run shape:

```json
{
  "run_id": "run_123",
  "workflow_key": "customer_support_auto_reply",
  "status": "WAITING_APPROVAL",
  "current_node_key": "wait_for_approval",
  "context": {
    "input": {
      "inquiry_id": "INQ-002"
    },
    "nodes": {
      "fetch_inquiry": {
        "inquiry": {}
      },
      "classify_inquiry": {
        "category": "billing"
      },
      "lookup_customer": {
        "customer": {}
      },
      "generate_reply": {
        "subject": "Re: 카드 결제가 계속 실패합니다",
        "body": "안녕하세요..."
      }
    }
  },
  "node_states": {
    "fetch_inquiry": {
      "status": "COMPLETED"
    },
    "classify_inquiry": {
      "status": "COMPLETED"
    },
    "lookup_customer": {
      "status": "COMPLETED"
    },
    "generate_reply": {
      "status": "COMPLETED"
    },
    "wait_for_approval": {
      "status": "WAITING"
    },
    "send_reply_email": {
      "status": "PENDING"
    }
  },
  "approval": {
    "node_key": "wait_for_approval",
    "subject": "Re: 카드 결제가 계속 실패합니다",
    "body": "안녕하세요...",
    "deadline_at": "2026-04-26T00:30:00Z"
  },
  "error": null
}
```

`context.nodes` stores successful node outputs. `node_states` stores execution status, attempts, and node-level error data. A failed node does not write success output into context.

For the assignment MVP, the store can be in memory. The README should explain that SQLite, PostgreSQL, or Redis would replace this for durable production pause/resume.

## Execution Flow

The main workflow run is:

1. `fetch_inquiry`: fetch inquiry by `inquiry_id`.
2. `classify_inquiry`: classify inquiry subject and body.
3. `lookup_customer`: fetch customer data by inquiry sender email.
4. `generate_reply`: create response subject and body from inquiry, category, customer data, guidelines, and plan rules.
5. `wait_for_approval`: pause with `WAITING_APPROVAL`.
6. `send_reply_email`: send only after approval.

`classify_inquiry` and `lookup_customer` both depend on `fetch_inquiry`. The MVP executor may run nodes sequentially even when multiple nodes are available.

## Validation

Workflow validation runs after loading YAML and before execution.

Required validation:

- YAML/schema parsing succeeds.
- Node keys are unique.
- `depends_on` references existing node keys.
- The graph has no cycles.
- `type` is supported.
- `type: tool` has `tool`.
- `type: llm` has `task`.
- `type: human_approval` has `timeout_seconds`.

Input path existence is validated at execution time when rendering node inputs. Missing input paths fail the node with an input mapping error.

## Retry

Retry is not applied to every operation. It is applied only to transient external failures.

Retryable examples:

- HTTP timeout.
- Connection reset.
- HTTP `408`, `429`, `500`, `502`, `503`, `504`.
- OpenAI rate limit or service unavailable errors.

Non-retryable examples:

- Workflow validation errors.
- Missing input mapping paths.
- Mock CRM `404 Customer not found`.
- `401` or `403` authentication errors.
- Invalid LLM output schema.
- Human rejection.

If a node exhausts retries, the run fails and the node records attempts and error details:

```json
{
  "status": "FAILED",
  "current_node_key": "send_reply_email",
  "node_states": {
    "send_reply_email": {
      "status": "FAILED",
      "attempts": 3,
      "error": {
        "code": "EMAIL_SEND_FAILED",
        "message": "Email service temporarily unavailable",
        "retryable": true
      }
    }
  },
  "error": {
    "node_key": "send_reply_email",
    "code": "EMAIL_SEND_FAILED",
    "message": "send_reply_email failed after 3 attempts"
  }
}
```

## Approval Contract

The approval node pauses execution and stores the generated subject/body for review.

Approval API accepts:

```json
{
  "decision": "approve"
}
```

or:

```json
{
  "decision": "reject",
  "reason": "답변 내용이 부정확함"
}
```

Approval behavior:

- `approve`: `WAITING_APPROVAL -> RUNNING`, then execute `send_reply_email`.
- `reject`: `WAITING_APPROVAL -> REJECTED`, do not send email.
- deadline exceeded: `WAITING_APPROVAL -> TIMED_OUT`, do not send email.

## API Contract

### Start workflow run

```http
POST /workflow-runs
```

Request:

```json
{
  "workflow_key": "customer_support_auto_reply",
  "inquiry_id": "INQ-002"
}
```

Response:

```json
{
  "run_id": "run_123",
  "status": "WAITING_APPROVAL",
  "current_node_key": "wait_for_approval"
}
```

### Get workflow run

```http
GET /workflow-runs/{run_id}
```

Response includes run status, current node, context, node states, approval data, and error data.

### Submit approval decision

```http
POST /workflow-runs/{run_id}/approval
```

Request:

```json
{
  "decision": "approve"
}
```

or:

```json
{
  "decision": "reject",
  "reason": "답변 내용이 부정확함"
}
```

## Mock Server

The Mock API server is treated as an external dependency and should be run with Docker Compose:

```bash
cd mock-server
docker compose up --build
```

The workflow engine uses:

- `MOCK_API_BASE_URL=http://localhost:8080`
- `MOCK_API_KEY=mock-api-key-12345`

## Testing Strategy

Automated tests should avoid real OpenAI calls. They should use a fake LLM and fake or mocked tools for deterministic behavior.

Core tests:

- Workflow validation rejects duplicate keys.
- Workflow validation rejects missing dependencies.
- Workflow validation rejects cycles.
- Workflow validation rejects unknown node types.
- DAG execution order respects dependencies.
- Context output from one node is used as input to later nodes.
- Run pauses at `wait_for_approval`.
- Approve resumes and sends email.
- Reject prevents email send.
- Approval deadline produces timeout.
- `email_send` retries after transient failure and succeeds.
- `email_send` fails the run after retry exhaustion.
- Fake LLM returns only the required task outputs.

OpenAI integration is verified manually by setting `OPENAI_API_KEY` and selecting the OpenAI provider. It is not part of default automated tests because it requires network access, can cost money, and is nondeterministic.

## Security and Limitations

Security:

- Keep Mock API and OpenAI keys in environment variables.
- Do not commit real OpenAI keys.
- Approval API is unauthenticated in the assignment MVP; production use would require authentication and authorization.
- LLM prompts should include only the customer context needed for reply generation.
- Generation prompts must include prohibited response rules from the assignment.

Limitations:

- Run store is in memory.
- Execution is sequential.
- Parallel branches, conditional branching, and a visual workflow builder are out of scope.
- The engine supports only the assignment node types: `tool`, `llm`, and `human_approval`.
