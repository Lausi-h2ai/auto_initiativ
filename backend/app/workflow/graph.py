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

