"""Trusted, code-first workflow graph definitions.

This module describes allowed workflow topology. It is deliberately not a
runtime or state store: Postgres and the existing domain services remain
authoritative.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from enum import StrEnum


class WorkflowKind(StrEnum):
    INITIATIVE_OUTREACH = "initiative_outreach"
    LISTED_JOB_SEARCH = "listed_job_search"
    APPLICATION_PREPARATION = "application_preparation"
    PRIVILEGED_SENDING = "privileged_sending"


class NodeKind(StrEnum):
    DETERMINISTIC = "deterministic"
    AGENT = "agent"
    BARRIER = "barrier"
    HUMAN_INTERRUPT = "human_interrupt"
    PRIVILEGED_SIDE_EFFECT = "privileged_side_effect"


class SideEffectClass(StrEnum):
    NONE = "none"
    DATABASE = "database"
    EXTERNAL = "external"
    PRIVILEGED_EXTERNAL = "privileged_external"


class JoinSemantics(StrEnum):
    DIRECT = "direct"
    FAN_OUT = "fan_out"
    ALL_PARENTS = "all_parents"
    ANY_PARENT = "any_parent"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounds retries of one node execution, independently of graph cycles."""

    max_attempts: int = 1
    max_elapsed_seconds: int | None = None
    budget_key: str | None = None

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("RetryPolicy.max_attempts must be at least 1.")
        if self.max_elapsed_seconds is not None and self.max_elapsed_seconds < 1:
            raise ValueError("RetryPolicy.max_elapsed_seconds must be positive.")


@dataclass(frozen=True, slots=True)
class CycleBound:
    """Application-owned hard bound on traversing a cyclic node or edge."""

    max_traversals: int
    counter_key: str

    def __post_init__(self) -> None:
        if self.max_traversals < 1:
            raise ValueError("CycleBound.max_traversals must be at least 1.")
        if not self.counter_key.strip():
            raise ValueError("CycleBound.counter_key must not be blank.")


@dataclass(frozen=True, slots=True)
class NodeDefinition:
    node_id: str
    executor_key: str
    kind: NodeKind
    input_contract_ids: tuple[str, ...] = ()
    output_contract_ids: tuple[str, ...] = ()
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_seconds: int | None = None
    concurrency_class: str = "default"
    side_effect: SideEffectClass = SideEffectClass.NONE
    idempotency_strategy: str | None = None
    cycle_bound: CycleBound | None = None

    def __post_init__(self) -> None:
        if self.timeout_seconds is not None and self.timeout_seconds < 1:
            raise ValueError("NodeDefinition.timeout_seconds must be positive.")


@dataclass(frozen=True, slots=True)
class EdgeDefinition:
    edge_id: str
    source: str
    destination: str
    predicate_key: str
    reason_code: str
    join: JoinSemantics = JoinSemantics.DIRECT
    requires_review: bool = False
    required_artifact_ids: tuple[str, ...] = ()
    cycle_bound: CycleBound | None = None


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    definition_id: str
    version: int
    workflow_kinds: tuple[WorkflowKind, ...]
    nodes: tuple[NodeDefinition, ...]
    edges: tuple[EdgeDefinition, ...]
    start_node_id: str
    terminal_node_ids: frozenset[str]

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("WorkflowDefinition.version must be at least 1.")
        object.__setattr__(self, "terminal_node_ids", frozenset(self.terminal_node_ids))


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    source_node_id: str
    edge_id: str
    destination_node_id: str
    reason_code: str
    predicate_facts: tuple[tuple[str, str], ...] = ()
    artifact_references: tuple[str, ...] = ()
    domain_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NodeExecutionContext:
    workspace_id: str
    graph_definition_id: str
    graph_version: int
    graph_run_id: str
    node_id: str
    campaign_id: str | None = None
    task_id: str | None = None
    scoped_entity_ids: tuple[str, ...] = ()
    attempt: int = 1
    input_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GraphRegistry:
    """Keys implemented by trusted application code."""

    executor_keys: frozenset[str]
    predicate_keys: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "executor_keys", frozenset(self.executor_keys))
        object.__setattr__(self, "predicate_keys", frozenset(self.predicate_keys))


class GraphValidationError(ValueError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(errors)
        super().__init__("Invalid workflow graph:\n- " + "\n- ".join(self.errors))


def validate_workflow_definition(
    definition: WorkflowDefinition,
    registry: GraphRegistry,
) -> None:
    """Raise actionable errors if a trusted definition is unsafe or malformed."""

    errors: list[str] = []
    nodes: dict[str, NodeDefinition] = {}
    duplicate_node_ids: set[str] = set()
    for node in definition.nodes:
        if not node.node_id.strip():
            errors.append("Node IDs must not be blank.")
            continue
        if node.node_id in nodes:
            duplicate_node_ids.add(node.node_id)
        else:
            nodes[node.node_id] = node
    for node_id in sorted(duplicate_node_ids):
        errors.append(f"Duplicate node ID '{node_id}'.")

    edges: dict[str, EdgeDefinition] = {}
    duplicate_edge_ids: set[str] = set()
    for edge in definition.edges:
        if not edge.edge_id.strip():
            errors.append("Edge IDs must not be blank.")
            continue
        if edge.edge_id in edges:
            duplicate_edge_ids.add(edge.edge_id)
        else:
            edges[edge.edge_id] = edge
    for edge_id in sorted(duplicate_edge_ids):
        errors.append(f"Duplicate edge ID '{edge_id}'.")

    if definition.start_node_id not in nodes:
        errors.append(f"Start node '{definition.start_node_id}' does not exist.")
    if not definition.terminal_node_ids:
        errors.append("At least one terminal node is required.")
    for terminal_id in sorted(definition.terminal_node_ids):
        if terminal_id not in nodes:
            errors.append(f"Terminal node '{terminal_id}' does not exist.")

    outgoing: dict[str, list[EdgeDefinition]] = {node_id: [] for node_id in nodes}
    for edge in definition.edges:
        if edge.source not in nodes:
            errors.append(
                f"Edge '{edge.edge_id}' has unknown source node '{edge.source}'."
            )
        if edge.destination not in nodes:
            errors.append(
                f"Edge '{edge.edge_id}' has unknown destination node "
                f"'{edge.destination}'."
            )
        if edge.source in nodes and edge.destination in nodes:
            outgoing[edge.source].append(edge)
        if edge.predicate_key not in registry.predicate_keys:
            errors.append(
                f"Edge '{edge.edge_id}' uses unregistered predicate "
                f"'{edge.predicate_key}'."
            )
        if not edge.reason_code.strip():
            errors.append(f"Edge '{edge.edge_id}' must declare a reason code.")

    for node in definition.nodes:
        if node.executor_key not in registry.executor_keys:
            errors.append(
                f"Node '{node.node_id}' uses unregistered executor "
                f"'{node.executor_key}'."
            )
        if node.node_id not in definition.terminal_node_ids and not outgoing.get(
            node.node_id
        ):
            errors.append(f"Non-terminal node '{node.node_id}' has no outgoing edge.")
        if node.node_id in definition.terminal_node_ids and outgoing.get(node.node_id):
            errors.append(f"Terminal node '{node.node_id}' has outgoing edges.")
        if node.kind is NodeKind.PRIVILEGED_SIDE_EFFECT:
            if node.side_effect is not SideEffectClass.PRIVILEGED_EXTERNAL:
                errors.append(
                    f"Privileged node '{node.node_id}' must use side-effect class "
                    "'privileged_external'."
                )
            if not node.idempotency_strategy or not node.idempotency_strategy.strip():
                errors.append(
                    f"Privileged node '{node.node_id}' must declare an "
                    "idempotency strategy."
                )
        elif node.side_effect is SideEffectClass.PRIVILEGED_EXTERNAL:
            errors.append(
                f"Node '{node.node_id}' declares a privileged external side effect "
                "but is not a privileged_side_effect node."
            )

    for edge in definition.edges:
        source = nodes.get(edge.source)
        destination = nodes.get(edge.destination)
        if (
            source is not None
            and destination is not None
            and source.kind is NodeKind.AGENT
            and destination.kind is NodeKind.PRIVILEGED_SIDE_EFFECT
        ):
            errors.append(
                f"Agent node '{source.node_id}' must not connect directly to "
                f"privileged node '{destination.node_id}' (edge '{edge.edge_id}')."
            )

    if definition.start_node_id in nodes:
        reachable = _reachable_from(definition.start_node_id, outgoing)
        for node_id in sorted(set(nodes) - reachable):
            errors.append(
                f"Node '{node_id}' is unreachable from start node "
                f"'{definition.start_node_id}'."
            )

    unbounded_cycle = _find_unbounded_cycle(nodes, definition.edges)
    if unbounded_cycle:
        errors.append(
            "Unbounded cycle detected; every cycle must traverse a node or edge "
            f"with a CycleBound: {' -> '.join(unbounded_cycle)}."
        )

    if errors:
        raise GraphValidationError(errors)


def assert_mandatory_checkpoints_before(
    definition: WorkflowDefinition,
    *,
    privileged_target_id: str,
    checkpoint_node_ids: Collection[str],
) -> None:
    """Prove every start-to-target path passes each mandatory checkpoint.

    For each checkpoint, the function removes it and searches for a remaining
    path to the privileged target. A witness path is included on failure.
    """

    nodes = {node.node_id: node for node in definition.nodes}
    target = nodes.get(privileged_target_id)
    errors: list[str] = []
    if target is None:
        errors.append(f"Privileged target '{privileged_target_id}' does not exist.")
    elif target.kind is not NodeKind.PRIVILEGED_SIDE_EFFECT:
        errors.append(
            f"Target '{privileged_target_id}' is not a privileged_side_effect node."
        )

    unknown = sorted(set(checkpoint_node_ids) - set(nodes))
    for checkpoint in unknown:
        errors.append(f"Mandatory checkpoint '{checkpoint}' does not exist.")

    if errors:
        raise GraphValidationError(errors)

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in definition.edges:
        if edge.source in nodes and edge.destination in nodes:
            adjacency[edge.source].append(edge.destination)
    for destinations in adjacency.values():
        destinations.sort()

    for checkpoint in sorted(set(checkpoint_node_ids)):
        witness = _path_avoiding(
            definition.start_node_id,
            privileged_target_id,
            adjacency,
            forbidden=checkpoint,
        )
        if witness is not None:
            errors.append(
                f"Path to privileged target '{privileged_target_id}' bypasses "
                f"mandatory checkpoint '{checkpoint}': {' -> '.join(witness)}."
            )

    if errors:
        raise GraphValidationError(errors)


def assert_ordered_checkpoints_before(
    definition: WorkflowDefinition,
    *,
    privileged_target_id: str,
    ordered_checkpoint_node_ids: Collection[str],
) -> None:
    """Prove every start-to-target path crosses checkpoints in declared order.

    Unlike the mandatory-checkpoint assertion, this detects a path that contains
    all checkpoints but reaches a later checkpoint before an earlier one.
    """

    nodes = {node.node_id: node for node in definition.nodes}
    target = nodes.get(privileged_target_id)
    checkpoints = tuple(ordered_checkpoint_node_ids)
    errors: list[str] = []
    if target is None:
        errors.append(f"Privileged target '{privileged_target_id}' does not exist.")
    elif target.kind is not NodeKind.PRIVILEGED_SIDE_EFFECT:
        errors.append(
            f"Target '{privileged_target_id}' is not a privileged_side_effect node."
        )
    if len(checkpoints) != len(set(checkpoints)):
        errors.append("Ordered mandatory checkpoints must be unique.")
    for checkpoint in sorted(set(checkpoints) - set(nodes)):
        errors.append(f"Mandatory checkpoint '{checkpoint}' does not exist.")
    if privileged_target_id in checkpoints:
        errors.append(
            f"Privileged target '{privileged_target_id}' must not also be an "
            "ordered checkpoint."
        )
    if errors:
        raise GraphValidationError(errors)

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in definition.edges:
        if edge.source in nodes and edge.destination in nodes:
            adjacency[edge.source].append(edge.destination)
    for destinations in adjacency.values():
        destinations.sort()

    witness = _path_violating_checkpoint_order(
        definition.start_node_id,
        privileged_target_id,
        adjacency,
        checkpoints,
    )
    if witness is not None:
        raise GraphValidationError(
            (
                f"Path to privileged target '{privileged_target_id}' does not "
                f"cross checkpoints in required order "
                f"{' -> '.join(checkpoints)}: {' -> '.join(witness)}.",
            )
        )


def _reachable_from(
    start_node_id: str,
    outgoing: dict[str, list[EdgeDefinition]],
) -> set[str]:
    seen: set[str] = set()
    pending = [start_node_id]
    while pending:
        node_id = pending.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        pending.extend(edge.destination for edge in outgoing.get(node_id, ()))
    return seen


def _find_unbounded_cycle(
    nodes: dict[str, NodeDefinition],
    edges: tuple[EdgeDefinition, ...],
) -> list[str] | None:
    """Find a cycle that avoids every explicitly bounded node and edge."""

    unbounded_nodes = {
        node_id for node_id, node in nodes.items() if node.cycle_bound is None
    }
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in unbounded_nodes}
    for edge in edges:
        if (
            edge.cycle_bound is None
            and edge.source in unbounded_nodes
            and edge.destination in unbounded_nodes
        ):
            adjacency[edge.source].append(edge.destination)
    for destinations in adjacency.values():
        destinations.sort()

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node_id: str) -> list[str] | None:
        if node_id in visiting:
            cycle_start = stack.index(node_id)
            return [*stack[cycle_start:], node_id]
        if node_id in visited:
            return None
        visiting.add(node_id)
        stack.append(node_id)
        for destination in adjacency[node_id]:
            cycle = visit(destination)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node_id)
        visited.add(node_id)
        return None

    for node_id in sorted(adjacency):
        cycle = visit(node_id)
        if cycle:
            return cycle
    return None


def _path_avoiding(
    start: str,
    destination: str,
    adjacency: dict[str, list[str]],
    *,
    forbidden: str,
) -> list[str] | None:
    if start == forbidden:
        return None
    pending: deque[tuple[str, list[str]]] = deque([(start, [start])])
    seen = {start}
    while pending:
        node_id, path = pending.popleft()
        if node_id == destination:
            return path
        for next_node in adjacency.get(node_id, ()):
            if next_node != forbidden and next_node not in seen:
                seen.add(next_node)
                pending.append((next_node, [*path, next_node]))
    return None


def _path_violating_checkpoint_order(
    start: str,
    destination: str,
    adjacency: dict[str, list[str]],
    checkpoints: tuple[str, ...],
) -> list[str] | None:
    checkpoint_positions = {
        checkpoint: position for position, checkpoint in enumerate(checkpoints)
    }

    def advance(node_id: str, next_position: int) -> tuple[int, bool]:
        position = checkpoint_positions.get(node_id)
        if position is None or position < next_position:
            return next_position, False
        if position == next_position:
            return next_position + 1, False
        return next_position, True

    next_position, invalid = advance(start, 0)
    if invalid:
        return [start]
    pending: deque[tuple[str, int, list[str]]] = deque(
        [(start, next_position, [start])]
    )
    seen = {(start, next_position)}
    while pending:
        node_id, next_position, path = pending.popleft()
        if node_id == destination:
            if next_position != len(checkpoints):
                return path
            continue
        for next_node in adjacency.get(node_id, ()):
            advanced, invalid = advance(next_node, next_position)
            next_path = [*path, next_node]
            if invalid:
                return next_path
            state = (next_node, advanced)
            if state not in seen:
                seen.add(state)
                pending.append((next_node, advanced, next_path))
    return None


COORDINATED_RESEARCH_EXECUTOR_KEYS = frozenset(
    {
        "research.compile_plan",
        "research.await_plan_confirmation",
        "research.materialize_targets",
        "research.run_target_agent",
        "research.import_and_record_attempts",
        "research.classify_target_terminal",
        "research.allocate_shared_budget",
        "research.all_targets_barrier",
        "research.scope_assessment",
        "research.rank_and_retain",
        "research.complete",
    }
)

COORDINATED_RESEARCH_PREDICATE_KEYS = frozenset(
    {
        "always",
        "research.plan_hash_confirmed",
        "research.each_materialized_target",
        "research.target_run_reconciled",
        "research.target_classified",
        "research.shared_lease_available",
        "research.shared_budget_exhausted_or_targets_terminal",
        "research.all_targets_terminal",
    }
)

COORDINATED_RESEARCH_REGISTRY = GraphRegistry(
    executor_keys=COORDINATED_RESEARCH_EXECUTOR_KEYS,
    predicate_keys=COORDINATED_RESEARCH_PREDICATE_KEYS,
)


def coordinated_research_v1() -> WorkflowDefinition:
    """Version 1 shadow topology for both coordinated research campaign kinds."""

    deterministic = NodeKind.DETERMINISTIC
    return WorkflowDefinition(
        definition_id="coordinated_research",
        version=1,
        workflow_kinds=(
            WorkflowKind.INITIATIVE_OUTREACH,
            WorkflowKind.LISTED_JOB_SEARCH,
        ),
        start_node_id="compile_plan",
        terminal_node_ids=frozenset({"research_complete"}),
        nodes=(
            NodeDefinition(
                "compile_plan",
                "research.compile_plan",
                deterministic,
                output_contract_ids=("research_plan.schema.json",),
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="workspace_campaign_plan_generation",
            ),
            NodeDefinition(
                "await_plan_confirmation",
                "research.await_plan_confirmation",
                NodeKind.HUMAN_INTERRUPT,
                input_contract_ids=("research_plan.schema.json",),
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="confirmed_plan_hash",
            ),
            NodeDefinition(
                "materialize_targets",
                "research.materialize_targets",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="plan_hash_target_id",
            ),
            NodeDefinition(
                "research_target",
                "research.run_target_agent",
                NodeKind.AGENT,
                retry_policy=RetryPolicy(
                    max_attempts=3,
                    max_elapsed_seconds=3600,
                    budget_key="target_research_budget",
                ),
                timeout_seconds=3600,
                concurrency_class="research_target",
                side_effect=SideEffectClass.EXTERNAL,
                idempotency_strategy="target_lease_number",
            ),
            NodeDefinition(
                "import_and_record_attempts",
                "research.import_and_record_attempts",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="research_run_artifact_hash",
            ),
            NodeDefinition(
                "classify_target_terminal",
                "research.classify_target_terminal",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="target_attempt_generation",
            ),
            NodeDefinition(
                "shared_budget_decision",
                "research.allocate_shared_budget",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="target_shared_lease_number",
            ),
            NodeDefinition(
                "all_targets_barrier",
                "research.all_targets_barrier",
                NodeKind.BARRIER,
            ),
            NodeDefinition(
                "scope_assessment",
                "research.scope_assessment",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="campaign_research_generation",
            ),
            NodeDefinition(
                "rank_and_retain",
                "research.rank_and_retain",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="campaign_research_generation",
            ),
            NodeDefinition(
                "research_complete",
                "research.complete",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="campaign_research_generation",
            ),
        ),
        edges=(
            EdgeDefinition(
                "plan_compiled",
                "compile_plan",
                "await_plan_confirmation",
                "always",
                "research_plan_compiled",
            ),
            EdgeDefinition(
                "plan_confirmed",
                "await_plan_confirmation",
                "materialize_targets",
                "research.plan_hash_confirmed",
                "confirmed_plan_hash_matches",
                requires_review=True,
            ),
            EdgeDefinition(
                "targets_materialized",
                "materialize_targets",
                "research_target",
                "research.each_materialized_target",
                "research_target_materialized",
                join=JoinSemantics.FAN_OUT,
            ),
            EdgeDefinition(
                "target_reconciled",
                "research_target",
                "import_and_record_attempts",
                "research.target_run_reconciled",
                "target_runtime_reconciled",
            ),
            EdgeDefinition(
                "attempts_recorded",
                "import_and_record_attempts",
                "classify_target_terminal",
                "research.target_classified",
                "target_attempts_recorded",
            ),
            EdgeDefinition(
                "target_classified",
                "classify_target_terminal",
                "shared_budget_decision",
                "research.target_classified",
                "target_terminal_state_classified",
            ),
            EdgeDefinition(
                "shared_budget_lease",
                "shared_budget_decision",
                "research_target",
                "research.shared_lease_available",
                "bounded_shared_budget_lease_allocated",
                cycle_bound=CycleBound(
                    max_traversals=3,
                    counter_key="target_shared_lease_count",
                ),
            ),
            EdgeDefinition(
                "research_fan_in",
                "shared_budget_decision",
                "all_targets_barrier",
                "research.shared_budget_exhausted_or_targets_terminal",
                "shared_budget_closed",
                join=JoinSemantics.ALL_PARENTS,
            ),
            EdgeDefinition(
                "all_targets_terminal",
                "all_targets_barrier",
                "scope_assessment",
                "research.all_targets_terminal",
                "all_targets_covered_exhausted_or_failed",
            ),
            EdgeDefinition(
                "scope_assessed",
                "scope_assessment",
                "rank_and_retain",
                "always",
                "scope_assessment_complete",
            ),
            EdgeDefinition(
                "candidates_ranked",
                "rank_and_retain",
                "research_complete",
                "always",
                "research_candidates_ranked_and_retained",
            ),
        ),
    )


APPLICATION_PREPARATION_EXECUTOR_KEYS = frozenset(
    {
        "application.decide_contact",
        "application.run_contact_research_agent",
        "application.validate_contact_candidate",
        "application.run_drafting_agent",
        "application.validate_candidate_artifacts",
        "application.await_authorized_review",
        "application.mark_ready",
        "application.mark_blocked",
    }
)

APPLICATION_PREPARATION_PREDICATE_KEYS = frozenset(
    {
        "application.contact_is_usable",
        "application.contact_requires_remediation",
        "application.contact_is_blocked",
        "application.agent_artifacts_reconciled",
        "application.contact_candidate_is_valid",
        "application.contact_remediation_retry_available",
        "application.contact_remediation_exhausted",
        "application.candidate_artifacts_valid",
        "application.candidate_artifacts_need_review",
        "application.candidate_artifacts_blocked",
        "application.authorized_review_approved",
        "application.authorized_review_rejected",
    }
)

APPLICATION_PREPARATION_REGISTRY = GraphRegistry(
    executor_keys=APPLICATION_PREPARATION_EXECUTOR_KEYS,
    predicate_keys=APPLICATION_PREPARATION_PREDICATE_KEYS,
)


def application_preparation_v1() -> WorkflowDefinition:
    """Static candidate-artifact topology; existing runtime remains authoritative."""

    deterministic = NodeKind.DETERMINISTIC
    return WorkflowDefinition(
        definition_id="application_preparation",
        version=1,
        workflow_kinds=(WorkflowKind.APPLICATION_PREPARATION,),
        start_node_id="contact_decision",
        terminal_node_ids=frozenset({"application_ready", "application_blocked"}),
        nodes=(
            NodeDefinition(
                "contact_decision",
                "application.decide_contact",
                deterministic,
                input_contract_ids=("contact_candidate.schema.json",),
            ),
            NodeDefinition(
                "contact_research",
                "application.run_contact_research_agent",
                NodeKind.AGENT,
                output_contract_ids=("contact_candidate.schema.json",),
                retry_policy=RetryPolicy(
                    max_attempts=2,
                    max_elapsed_seconds=1800,
                    budget_key="contact_remediation_budget",
                ),
                timeout_seconds=900,
                concurrency_class="contact_research",
                side_effect=SideEffectClass.EXTERNAL,
                idempotency_strategy="company_contact_remediation_generation",
            ),
            NodeDefinition(
                "validate_contact_candidate",
                "application.validate_contact_candidate",
                deterministic,
                input_contract_ids=("contact_candidate.schema.json",),
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="contact_candidate_artifact_hash",
            ),
            NodeDefinition(
                "draft_candidate_artifacts",
                "application.run_drafting_agent",
                NodeKind.AGENT,
                input_contract_ids=(
                    "master_cv_profile.schema.json",
                    "contact_candidate.schema.json",
                ),
                output_contract_ids=("email_draft.schema.json",),
                retry_policy=RetryPolicy(
                    max_attempts=2,
                    max_elapsed_seconds=3600,
                    budget_key="application_drafting_budget",
                ),
                timeout_seconds=1800,
                concurrency_class="application_draft",
                side_effect=SideEffectClass.EXTERNAL,
                idempotency_strategy="application_draft_generation",
            ),
            NodeDefinition(
                "validate_candidate_artifacts",
                "application.validate_candidate_artifacts",
                deterministic,
                input_contract_ids=(
                    "email_draft.schema.json",
                    "master_cv_profile.schema.json",
                ),
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="application_artifact_set_hash",
            ),
            NodeDefinition(
                "await_application_review",
                "application.await_authorized_review",
                NodeKind.HUMAN_INTERRUPT,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="application_review_decision_id",
            ),
            NodeDefinition(
                "application_ready",
                "application.mark_ready",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="application_artifact_set_hash",
            ),
            NodeDefinition(
                "application_blocked",
                "application.mark_blocked",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="application_block_reason_generation",
            ),
        ),
        edges=(
            EdgeDefinition(
                "use_existing_contact",
                "contact_decision",
                "draft_candidate_artifacts",
                "application.contact_is_usable",
                "schema_valid_sourced_professional_contact_available",
            ),
            EdgeDefinition(
                "remediate_contact",
                "contact_decision",
                "contact_research",
                "application.contact_requires_remediation",
                "contact_requires_bounded_agent_remediation",
            ),
            EdgeDefinition(
                "block_unsafe_contact",
                "contact_decision",
                "application_blocked",
                "application.contact_is_blocked",
                "contact_policy_blocked",
            ),
            EdgeDefinition(
                "reconcile_contact_candidate",
                "contact_research",
                "validate_contact_candidate",
                "application.agent_artifacts_reconciled",
                "contact_candidate_artifact_reconciled",
                required_artifact_ids=("contact_candidate.schema.json",),
            ),
            EdgeDefinition(
                "accept_contact_candidate",
                "validate_contact_candidate",
                "draft_candidate_artifacts",
                "application.contact_candidate_is_valid",
                "contact_candidate_deterministically_validated",
            ),
            EdgeDefinition(
                "retry_contact_remediation",
                "validate_contact_candidate",
                "contact_research",
                "application.contact_remediation_retry_available",
                "bounded_contact_remediation_retry_allocated",
                cycle_bound=CycleBound(
                    max_traversals=1,
                    counter_key="contact_remediation_retry_count",
                ),
            ),
            EdgeDefinition(
                "block_exhausted_contact_remediation",
                "validate_contact_candidate",
                "application_blocked",
                "application.contact_remediation_exhausted",
                "contact_remediation_exhausted_or_unsafe",
            ),
            EdgeDefinition(
                "reconcile_draft_candidate",
                "draft_candidate_artifacts",
                "validate_candidate_artifacts",
                "application.agent_artifacts_reconciled",
                "draft_candidate_artifacts_reconciled",
                required_artifact_ids=("email_draft.schema.json",),
            ),
            EdgeDefinition(
                "candidate_artifacts_ready",
                "validate_candidate_artifacts",
                "application_ready",
                "application.candidate_artifacts_valid",
                "schema_claims_sources_and_attachments_valid",
            ),
            EdgeDefinition(
                "candidate_artifacts_need_review",
                "validate_candidate_artifacts",
                "await_application_review",
                "application.candidate_artifacts_need_review",
                "candidate_artifacts_require_authorized_review",
                requires_review=True,
            ),
            EdgeDefinition(
                "candidate_artifacts_blocked",
                "validate_candidate_artifacts",
                "application_blocked",
                "application.candidate_artifacts_blocked",
                "schema_claim_source_or_attachment_validation_blocked",
            ),
            EdgeDefinition(
                "authorized_review_approved",
                "await_application_review",
                "application_ready",
                "application.authorized_review_approved",
                "authorized_review_approved_reviewable_artifacts",
                requires_review=True,
            ),
            EdgeDefinition(
                "authorized_review_rejected",
                "await_application_review",
                "application_blocked",
                "application.authorized_review_rejected",
                "authorized_review_rejected_or_unresolved",
                requires_review=True,
            ),
        ),
    )


PRIVILEGED_SENDING_EXECUTOR_KEYS = frozenset(
    {
        "sending.validate_send_intent",
        "sending.freeze_authorized_approval_snapshot",
        "sending.evaluate_only_gate",
        "sending.reserve_transactionally",
        "sending.attempt_provider_via_privileged_facade",
        "sending.audit_sent",
        "sending.audit_known_unsent",
        "sending.audit_outcome_uncertain",
    }
)

PRIVILEGED_SENDING_PREDICATE_KEYS = frozenset(
    {
        "sending.intent_valid",
        "sending.intent_invalid_known_unsent",
        "sending.approval_authorized_and_payload_frozen",
        "sending.approval_missing_or_changed_known_unsent",
        "sending.evaluate_only_passed",
        "sending.evaluate_only_blocked_known_unsent",
        "sending.reservation_created",
        "sending.reservation_failed_known_unsent",
        "sending.provider_accepted",
        "sending.provider_rejected_known_unsent",
        "sending.provider_outcome_uncertain",
    }
)

PRIVILEGED_SENDING_REGISTRY = GraphRegistry(
    executor_keys=PRIVILEGED_SENDING_EXECUTOR_KEYS,
    predicate_keys=PRIVILEGED_SENDING_PREDICATE_KEYS,
)

PRIVILEGED_SENDING_CHECKPOINTS = (
    "validated_send_intent",
    "authorized_approval_snapshot",
    "deterministic_evaluate_only_gate",
    "transactional_reservation",
)


def privileged_sending_v1() -> WorkflowDefinition:
    """Static privileged facade topology; no generic graph runtime may send."""

    deterministic = NodeKind.DETERMINISTIC
    known_unsent = "audited_known_unsent"
    return WorkflowDefinition(
        definition_id="privileged_sending",
        version=1,
        workflow_kinds=(WorkflowKind.PRIVILEGED_SENDING,),
        start_node_id="validated_send_intent",
        terminal_node_ids=frozenset(
            {
                "audited_sent",
                known_unsent,
                "audited_outcome_uncertain",
            }
        ),
        nodes=(
            NodeDefinition(
                "validated_send_intent",
                "sending.validate_send_intent",
                deterministic,
                input_contract_ids=("send_intent.schema.json",),
            ),
            NodeDefinition(
                "authorized_approval_snapshot",
                "sending.freeze_authorized_approval_snapshot",
                NodeKind.HUMAN_INTERRUPT,
                input_contract_ids=("send_intent.schema.json",),
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="reviewer_batch_intent_payload_hash",
            ),
            NodeDefinition(
                "deterministic_evaluate_only_gate",
                "sending.evaluate_only_gate",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="intent_snapshot_gate_generation",
            ),
            NodeDefinition(
                "transactional_reservation",
                "sending.reserve_transactionally",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="send_intent_reservation_unique_constraints",
            ),
            NodeDefinition(
                "provider_attempt",
                "sending.attempt_provider_via_privileged_facade",
                NodeKind.PRIVILEGED_SIDE_EFFECT,
                timeout_seconds=120,
                concurrency_class="privileged_email_provider",
                side_effect=SideEffectClass.PRIVILEGED_EXTERNAL,
                idempotency_strategy="send_reservation_id",
            ),
            NodeDefinition(
                "audited_sent",
                "sending.audit_sent",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="reservation_provider_result",
            ),
            NodeDefinition(
                known_unsent,
                "sending.audit_known_unsent",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="reservation_or_precondition_result",
            ),
            NodeDefinition(
                "audited_outcome_uncertain",
                "sending.audit_outcome_uncertain",
                deterministic,
                side_effect=SideEffectClass.DATABASE,
                idempotency_strategy="reservation_uncertain_outcome",
            ),
        ),
        edges=(
            EdgeDefinition(
                "send_intent_valid",
                "validated_send_intent",
                "authorized_approval_snapshot",
                "sending.intent_valid",
                "send_intent_schema_and_references_valid",
            ),
            EdgeDefinition(
                "send_intent_invalid",
                "validated_send_intent",
                known_unsent,
                "sending.intent_invalid_known_unsent",
                "send_intent_invalid_no_provider_attempt",
            ),
            EdgeDefinition(
                "approval_authorized",
                "authorized_approval_snapshot",
                "deterministic_evaluate_only_gate",
                "sending.approval_authorized_and_payload_frozen",
                "authorized_approval_payload_frozen",
                requires_review=True,
            ),
            EdgeDefinition(
                "approval_not_authorized",
                "authorized_approval_snapshot",
                known_unsent,
                "sending.approval_missing_or_changed_known_unsent",
                "approval_missing_changed_or_unauthorized_no_provider_attempt",
                requires_review=True,
            ),
            EdgeDefinition(
                "evaluate_only_passed",
                "deterministic_evaluate_only_gate",
                "transactional_reservation",
                "sending.evaluate_only_passed",
                "deterministic_evaluate_only_gate_passed",
            ),
            EdgeDefinition(
                "evaluate_only_blocked",
                "deterministic_evaluate_only_gate",
                known_unsent,
                "sending.evaluate_only_blocked_known_unsent",
                "deterministic_gate_blocked_no_provider_attempt",
            ),
            EdgeDefinition(
                "reservation_created",
                "transactional_reservation",
                "provider_attempt",
                "sending.reservation_created",
                "transactional_send_reservation_created",
            ),
            EdgeDefinition(
                "reservation_failed",
                "transactional_reservation",
                known_unsent,
                "sending.reservation_failed_known_unsent",
                "transactional_reservation_failed_no_provider_attempt",
            ),
            EdgeDefinition(
                "provider_accepted",
                "provider_attempt",
                "audited_sent",
                "sending.provider_accepted",
                "provider_accepted_and_result_audited",
            ),
            EdgeDefinition(
                "provider_rejected_known_unsent",
                "provider_attempt",
                known_unsent,
                "sending.provider_rejected_known_unsent",
                "provider_rejected_before_accept_and_result_audited",
            ),
            EdgeDefinition(
                "provider_outcome_uncertain",
                "provider_attempt",
                "audited_outcome_uncertain",
                "sending.provider_outcome_uncertain",
                "provider_outcome_uncertain_and_terminally_blocked",
            ),
        ),
    )
