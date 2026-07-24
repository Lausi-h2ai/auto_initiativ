# ADR-0003: Application-Owned Workflow Graph

## Status

Proposed

## Context

Auto Initiativ already executes graph-shaped workflows, but their topology is implicit and distributed across `WorkflowEngine.process()`, reconciliation methods, route-level task creation, database status strings, and runtime files.

The current implicit graph includes:

- Campaign planning, a persisted versioned `ResearchPlan`, and a user-confirmation stop.
- One target-scoped `AgentTask` per geographic or remote target.
- Bounded research fan-out, target attempt tracking, and candidate collection.
- A deterministic shared-budget lease cycle.
- A fan-in barrier after all targets become `covered`, `exhausted`, or `failed`.
- Deterministic scope filtering, ranking, and retention.
- Conditional contact research or application drafting.
- Retries that eventually block for review.
- A separately implemented send path with evaluation, approval snapshot, transactional reservation, provider attempt, and pre/post audit records.

This is difficult to inspect as one system. The large task-type dispatch, string statuses, and reconciliation branches also make legal transitions, idempotency, recovery behavior, and safety invariants harder to test directly.

The current implementation has migration hazards that an explicit graph layer must address rather than hide:

- Task selection and the transition from `queued` to `running` are not claimed in one database compare-and-set operation, so multiple workers could select the same task.
- General enqueue dedupe is a query followed by an insert and is not backed by a semantic database uniqueness constraint.
- A process may crash after launching an external agent runtime but before persisting its `run_id`, creating an uncertain launch outcome.
- `locked_at` is recorded, but stale-lock ownership and recovery are not yet a complete lease protocol.
- Some downstream task creation, source-node completion, domain mutations, and audit writes are committed separately.
- Status strings describe several different state machines (`AgentTask`, campaign, target, plan, reservation, and provider delivery) and must not be collapsed into one generic status.
- Retrying an irreversible or uncertain provider outcome would be unsafe.

The graph layer must strengthen the existing principle: agents produce candidate files; the application makes decisions and owns authority.

The directly governing code-consumed schema inspected for this decision is `research_plan.schema.json`. This ADR changes no input, output, or API schema.

## Decision

Introduce a small, code-defined, application-owned workflow graph layer. Do not migrate orchestration to LangGraph, the OpenAI Agents SDK, or another graph runtime at this stage.

Postgres remains the sole durable and authoritative source of workflow and domain state. Graph definitions describe allowed execution; they are not a second state store. Pi RPC remains the restricted agent runtime, and agent output remains untrusted until schema validation and backend import.

### Goals

- Make nodes, legal transitions, joins, cycles, human stops, and terminal states explicit and versioned.
- Keep routing, policy, limits, dedupe, review blocking, and irreversible decisions deterministic.
- Improve idempotency, concurrency safety, crash recovery, auditability, and graph-level testing.
- Reuse the current persistence model for a low-risk research pilot.
- Make the sending boundary structurally unreachable from agent-controlled routing.

### Non-Goals

- Building a general-purpose workflow framework.
- Turning deterministic operations into agents.
- Allowing agents to create nodes, edges, graph definitions, budgets, or approvals.
- Replacing Postgres with framework checkpoints or runtime files.
- Replacing Pi RPC.
- Unifying all domain state machines into one graph status.
- Changing sending policy, enabling sending, or implementing a new email adapter.
- Modeling every helper function as a node.

### Graph Primitives

The initial internal API will use typed Python definitions:

- `WorkflowDefinition`: stable `definition_id`, integer `version`, supported workflow kind, nodes, edges, start node, and terminal nodes.
- `NodeDefinition`: stable `node_id`, executor key, node kind, input/output contract identifiers, retry policy, timeout, concurrency class, and side-effect classification.
- `EdgeDefinition`: stable `edge_id`, source, destination, deterministic predicate key, reason code, join semantics, and optional review requirement.
- `TransitionDecision`: source, selected edge, destination, reason code, facts used by the predicate, and artifact/domain references.
- `NodeExecutionContext`: workspace, graph/version, campaign, task, scoped entity identifiers, attempt, and immutable input references.

Stable identifiers are persisted; Python function names and display labels are not identifiers. Graph definitions are trusted application code and must pass topology validation at startup and in tests.

Node kinds are limited to:

- `deterministic`: application code only.
- `agent`: a narrowly scoped file-producing Pi RPC workload.
- `barrier`: deterministic fan-in/dependency evaluation.
- `human_interrupt`: a persisted pause requiring an authorized application action.
- `privileged_side_effect`: an application-owned facade with additional static and runtime guards.

Edges are selected only by registered backend predicates. Agent output may supply schema-valid evidence to a predicate, but it may not name the next node or authorize a transition.

### State and Version Ownership

Graph state is a projection over authoritative Postgres rows and immutable artifact references, not a mutable framework-owned JSON blob. Existing campaign, plan, target, discovery, domain, gate, reservation, and audit rows retain their own state machines.

Each new graph run pins `definition_id` and `version`. A run continues on its pinned definition unless an explicit, audited, data-preserving migration exists. Deploying a new definition never silently changes an active run.

Initially, `AgentTask` remains the node-execution record. The first implementation may add graph correlation fields through an additive migration, including:

- `graph_definition_id`
- `graph_version`
- `graph_run_id`
- `node_id`
- `execution_key`
- `parent_execution_ids_json`

Dedicated `workflow_runs`, `node_runs`, `node_dependencies`, or `transition_events` tables should be added only when the pilot proves that `AgentTask` plus `AuditLog` is insufficient. Postgres migrations remain additive and are verified against Postgres for concurrency semantics.

### Transition and Safety Invariants

Every transition must:

1. Load authoritative state in the workspace scope.
2. Evaluate a registered deterministic predicate.
3. Fail closed if required state, evidence, or a definition is missing.
4. Atomically record the decision and create any downstream work.
5. Emit a stable reason code and correlation identifiers.

The graph runtime may schedule work but may not bypass existing schema import, policy, gate, reservation, or audit services.

Static validation must reject:

- Unknown nodes, edges, predicates, or executors.
- Non-terminal nodes without an outgoing edge.
- Unbounded cycles.
- Agent nodes with edges to privileged provider operations.
- A privileged side-effect node without an idempotency strategy.
- A path to the send facade that does not pass every declared sending checkpoint.

Dynamic routing must never be based on free-form model prose.

### Idempotency, Concurrency, and Recovery

Every execution receives a deterministic `execution_key`, derived from the workspace, graph definition/version, graph run, node, scoped entity, and logical generation such as a research lease number. Postgres enforces uniqueness for active/materialized work. Payload hashes may detect conflicting reuse, but random task IDs are not idempotency keys.

Worker claiming must use an atomic Postgres claim, such as `SELECT ... FOR UPDATE SKIP LOCKED` inside a short transaction or a conditional `UPDATE ... WHERE status IN (...) RETURNING ...`. SQLite tests cannot establish this guarantee.

Completion of a node, transition recording, downstream task creation, and relevant application-state changes should share one transaction where possible. External work uses prepare/execute/reconcile phases:

- Persist a prepared attempt and stable external invocation key before launch.
- Launch outside the database transaction.
- Persist or rediscover the runtime identifier.
- Reconcile repeatedly and idempotently.

Locks become renewable leases with owner, acquired time, heartbeat/expiry, and attempt identity. Recovery may reclaim only an expired lease. It must first inspect the prepared attempt and external runtime state so it does not duplicate a still-running agent.

Retries are bounded by attempts, elapsed time, and budget. A retry creates or advances a logical attempt without changing the graph version. Side effects distinguish:

- Known-unsent: eligible for an explicitly permitted retry.
- Provider accepted: terminal.
- Outcome uncertain: terminally blocked for reconciliation; never automatically retried.

Cancellation is persisted, propagated to unfinished descendants where safe, and does not erase completed work or audit history.

### Research Pilot Topology

The first graph implementation is the coordinated research workflow for both `initiative_outreach` and `listed_job_search`:

```text
compile_plan
  -> await_plan_confirmation
  -> materialize_targets
  -> [research_target] fan-out
  -> import_and_record_attempts
  -> classify_target_terminal
  -> shared_budget_decision
       -> [research_target] bounded cycle, or
       -> all_targets_barrier
  -> scope_assessment
  -> rank_and_retain
  -> research_complete
```

Important semantics:

- Confirmation is a real persisted interrupt; no research edge is legal before the confirmed plan hash matches.
- Each target remains isolated and retains its required attempts and initial allocation.
- Fan-out respects both plan `max_parallel_targets` and an application-wide concurrency ceiling.
- Shared-budget leases are allocated only by deterministic backend code, are numbered for idempotency, and have hard lease/count/time bounds.
- The barrier opens only when every target is `covered`, `exhausted`, or `failed`, with partial failure represented explicitly.
- Missing geographic or remote evidence remains `needs_review`; explicit conflicts may be excluded deterministically.
- Merge, dedupe, scope assessment, ranking, and retention are deterministic nodes even when their inputs include agent-produced evidence.
- Downstream contact or drafting tasks are outside the pilot graph initially; current behavior continues until a later version models that subgraph.

The pilot will first run in shadow mode: calculate and audit intended transitions while existing orchestration remains authoritative. Differences are treated as defects or specification gaps, not automatically applied.

### Privileged Sending Boundary

Sending is a separate privileged subgraph/facade and is not part of the research pilot. No generic graph executor and no agent node may invoke an email adapter.

If modeled later, the only legal path is:

```text
validated_send_intent
  -> authorized_approval_snapshot
  -> deterministic_evaluate_only_gate
  -> transactional_reservation
  -> provider_attempt
  -> audited_sent | audited_known_unsent | audited_outcome_uncertain
```

The existing send service remains authoritative for the exact approval, payload-freeze, gate, reservation, provider, and audit semantics. The graph calls that facade rather than reimplementing its checks. Static path tests and runtime assertions must prove the provider attempt is unreachable without all checkpoints. `outcome_uncertain` remains blocking and reservation-protected.

### Observability

Every node attempt and transition records:

- Graph definition/version, graph run, node, execution, and parent identifiers.
- Workspace and scoped campaign/target/company/job identifiers.
- Attempt number, lease owner, timestamps, and terminal outcome.
- Transition edge and stable reason codes.
- Input/output artifact references and hashes, not duplicated authoritative payloads.
- Runtime/model attribution for agent nodes.
- Duration, retry, budget, and candidate/attempt counts where applicable.

The dashboard may render planned topology and actual path, but audit records and domain rows remain authoritative. Sensitive prompt or provider payloads must not be copied into general graph telemetry.

## Migration Stages

1. **Specify and validate:** add internal graph types, the research definition, topology validation, and unit tests without changing execution.
2. **Shadow transitions:** evaluate the graph beside current orchestration and audit mismatches.
3. **Harden persistence:** add correlation/idempotency fields and Postgres constraints; implement atomic claims and lease recovery.
4. **Pilot cutover:** use the graph dispatcher for coordinated research while retaining existing node executors and reconciliation code.
5. **Extract executors:** reduce the task-type switch by registering existing launch/reconcile handlers without changing their agent contracts.
6. **Extend deliberately:** model contact/drafting only after the research pilot is stable.
7. **Model sending last:** expose only the privileged send facade and add path-invariant and crash-recovery tests before any cutover.

Each stage is independently deployable, additive, and reversible by disabling new dispatch for new runs. Active runs stay pinned to their definition version.

## Testing

Required tests include:

- Topology reachability, valid terminals, registered handlers, and bounded cycles.
- Snapshot tests for definition identifiers and versions.
- Transition-table tests for every edge and fail-closed default.
- Plan-hash confirmation and human-interrupt tests.
- Fan-out limits, partial target failure, barrier, and shared-budget exhaustion tests.
- Postgres tests for atomic claims, execution-key uniqueness, competing workers, and lease expiry.
- Crash tests before launch, after launch/before runtime ID persistence, during reconciliation, and during atomic downstream materialization.
- Idempotent replay and duplicate webhook/poll-style reconciliation tests.
- Workspace-isolation and cancellation-propagation tests.
- Property/path tests proving no agent-controlled path reaches provider send and every send path crosses validation, approval, gate, reservation, and audit checkpoints.
- Provider-known-unsent versus outcome-uncertain recovery tests.

## Consequences

- Workflow behavior becomes reviewable, versioned, and testable as topology instead of being inferred from branches.
- Existing Postgres state, Pi RPC runtimes, schemas, and safety services can be reused.
- Research concurrency and recovery become safer before automation expands.
- The project gains definition/version and transition concepts that require migrations and operational tooling.
- During shadow and cutover stages, old and new orchestration representations temporarily coexist and mismatch handling adds complexity.
- Poor node granularity could create state explosion; nodes must remain meaningful responsibility, barrier, or transaction boundaries.
- A diagram can overstate certainty. Schema validation, evidence provenance, confidence, review flags, and deterministic gates remain mandatory.

## Pitfalls to Avoid

- Treating a graph framework checkpoint as authoritative beside Postgres.
- Letting agent output choose an edge, allocate shared budget, or declare coverage.
- Adding a node for every helper function.
- Reusing a completed execution key with different inputs.
- Claiming tasks with a non-atomic read-then-write sequence.
- Relaunching after an uncertain external launch without reconciliation.
- Assuming SQLite validates Postgres locking or partial-unique-index behavior.
- Migrating active runs implicitly to a new graph version.
- Retrying provider `outcome_uncertain`.
- Copying sending checks into graph predicates and allowing the two implementations to drift.
- Expanding agent tools or permissions because nodes look isolated.

## Alternatives Considered

### Keep the Implicit Workflow

Rejected as the long-term design. It works, but legal transitions, joins, cycles, recovery, and safety paths remain distributed and difficult to verify.

### Adopt LangGraph Now

Rejected for now. Its checkpoint and execution model would overlap with Postgres, `AgentTask`, Pi RPC state, and existing reconciliation. The migration and dual-source-of-truth risk outweigh near-term benefit.

### Adopt the OpenAI Agents SDK Now

Rejected for now. Auto Initiativ does not need another agent loop or handoff runtime. Application-owned deterministic orchestration and the existing restricted Pi RPC boundary better match its authority model.

### Store the Entire Workflow State in One JSON Document

Rejected. It would weaken relational constraints, workspace scoping, concurrency control, auditability, and domain-specific state machines.

### Rewrite All Workflows at Once

Rejected. A shadowed research pilot provides fan-out, fan-in, cycles, budgets, and review behavior without placing email side effects in the first migration.
