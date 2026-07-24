from dataclasses import FrozenInstanceError

import pytest

from backend.app.workflow.graph import (
    APPLICATION_PREPARATION_REGISTRY,
    COORDINATED_RESEARCH_REGISTRY,
    PRIVILEGED_SENDING_CHECKPOINTS,
    PRIVILEGED_SENDING_REGISTRY,
    CycleBound,
    EdgeDefinition,
    GraphRegistry,
    GraphValidationError,
    NodeDefinition,
    NodeKind,
    SideEffectClass,
    WorkflowDefinition,
    WorkflowKind,
    assert_mandatory_checkpoints_before,
    assert_ordered_checkpoints_before,
    application_preparation_v1,
    coordinated_research_v1,
    privileged_sending_v1,
    validate_workflow_definition,
)


def _registry(*, executors: str = "run", predicates: str = "always") -> GraphRegistry:
    return GraphRegistry(frozenset({executors}), frozenset({predicates}))


def _node(
    node_id: str,
    *,
    kind: NodeKind = NodeKind.DETERMINISTIC,
    side_effect: SideEffectClass = SideEffectClass.NONE,
    idempotency_strategy: str | None = None,
) -> NodeDefinition:
    return NodeDefinition(
        node_id=node_id,
        executor_key="run",
        kind=kind,
        side_effect=side_effect,
        idempotency_strategy=idempotency_strategy,
    )


def _definition(
    nodes: tuple[NodeDefinition, ...],
    edges: tuple[EdgeDefinition, ...],
    *,
    start: str = "start",
    terminals: frozenset[str] = frozenset({"done"}),
) -> WorkflowDefinition:
    return WorkflowDefinition(
        definition_id="test",
        version=1,
        workflow_kinds=(WorkflowKind.INITIATIVE_OUTREACH,),
        nodes=nodes,
        edges=edges,
        start_node_id=start,
        terminal_node_ids=terminals,
    )


def _edge(
    edge_id: str,
    source: str,
    destination: str,
    *,
    cycle_bound: CycleBound | None = None,
) -> EdgeDefinition:
    return EdgeDefinition(
        edge_id=edge_id,
        source=source,
        destination=destination,
        predicate_key="always",
        reason_code=edge_id,
        cycle_bound=cycle_bound,
    )


def test_coordinated_research_v1_is_valid_and_stable() -> None:
    definition = coordinated_research_v1()

    validate_workflow_definition(definition, COORDINATED_RESEARCH_REGISTRY)

    assert definition.definition_id == "coordinated_research"
    assert definition.version == 1
    assert definition.start_node_id == "compile_plan"
    assert definition.terminal_node_ids == frozenset({"research_complete"})
    assert {node.node_id for node in definition.nodes} == {
        "compile_plan",
        "await_plan_confirmation",
        "materialize_targets",
        "research_target",
        "import_and_record_attempts",
        "classify_target_terminal",
        "shared_budget_decision",
        "all_targets_barrier",
        "scope_assessment",
        "rank_and_retain",
        "research_complete",
    }


def test_definitions_are_immutable() -> None:
    definition = coordinated_research_v1()

    with pytest.raises(FrozenInstanceError):
        definition.version = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        (
            _definition(
                (_node("start"), _node("start"), _node("done")),
                (_edge("next", "start", "done"),),
            ),
            "Duplicate node ID 'start'",
        ),
        (
            _definition(
                (_node("start"), _node("done")),
                (
                    _edge("next", "start", "done"),
                    _edge("next", "start", "done"),
                ),
            ),
            "Duplicate edge ID 'next'",
        ),
        (
            _definition((_node("done"),), (), start="missing"),
            "Start node 'missing' does not exist",
        ),
        (
            _definition((_node("start"),), (), terminals=frozenset()),
            "At least one terminal node is required",
        ),
        (
            _definition(
                (_node("start"), _node("done")),
                (_edge("bad", "start", "missing"),),
            ),
            "unknown destination node 'missing'",
        ),
        (
            _definition(
                (_node("start"), _node("orphan"), _node("done")),
                (_edge("next", "start", "done"),),
            ),
            "Node 'orphan' is unreachable",
        ),
        (
            _definition(
                (_node("start"), _node("middle"), _node("done")),
                (_edge("next", "start", "middle"),),
            ),
            "Non-terminal node 'middle' has no outgoing edge",
        ),
    ],
)
def test_invalid_topology_has_actionable_error(
    definition: WorkflowDefinition,
    message: str,
) -> None:
    with pytest.raises(GraphValidationError, match=message):
        validate_workflow_definition(definition, _registry())


def test_unregistered_executor_and_predicate_are_rejected() -> None:
    definition = _definition(
        (_node("start"), _node("done")),
        (
            EdgeDefinition(
                "next",
                "start",
                "done",
                "missing_predicate",
                "test_reason",
            ),
        ),
    )

    with pytest.raises(GraphValidationError) as exc_info:
        validate_workflow_definition(
            definition,
            GraphRegistry(frozenset(), frozenset()),
        )

    assert "unregistered executor 'run'" in str(exc_info.value)
    assert "unregistered predicate 'missing_predicate'" in str(exc_info.value)


def test_privileged_node_requires_class_and_idempotency() -> None:
    definition = _definition(
        (
            _node("start"),
            _node("send", kind=NodeKind.PRIVILEGED_SIDE_EFFECT),
            _node("done"),
        ),
        (_edge("to_send", "start", "send"), _edge("sent", "send", "done")),
    )

    with pytest.raises(GraphValidationError) as exc_info:
        validate_workflow_definition(definition, _registry())

    assert "must use side-effect class 'privileged_external'" in str(exc_info.value)
    assert "must declare an idempotency strategy" in str(exc_info.value)


def test_agent_must_not_connect_directly_to_privileged_node() -> None:
    definition = _definition(
        (
            _node("start", kind=NodeKind.AGENT),
            _node(
                "send",
                kind=NodeKind.PRIVILEGED_SIDE_EFFECT,
                side_effect=SideEffectClass.PRIVILEGED_EXTERNAL,
                idempotency_strategy="reservation_id",
            ),
            _node("done"),
        ),
        (_edge("to_send", "start", "send"), _edge("sent", "send", "done")),
    )

    with pytest.raises(GraphValidationError, match="must not connect directly"):
        validate_workflow_definition(definition, _registry())


def test_unbounded_cycle_is_rejected() -> None:
    definition = _definition(
        (_node("start"), _node("retry"), _node("done")),
        (
            _edge("begin", "start", "retry"),
            _edge("again", "retry", "start"),
            _edge("finish", "retry", "done"),
        ),
    )

    with pytest.raises(GraphValidationError, match="Unbounded cycle detected"):
        validate_workflow_definition(definition, _registry())


def test_every_cycle_must_cross_a_bound_not_just_share_a_component_with_one() -> None:
    definition = _definition(
        (_node("start"), _node("a"), _node("b"), _node("done")),
        (
            _edge("to_a", "start", "a"),
            _edge("a_to_b", "a", "b"),
            _edge("bounded_back", "b", "start", cycle_bound=CycleBound(2, "leases")),
            _edge("unbounded_back", "b", "a"),
            _edge("finish", "b", "done"),
        ),
    )

    with pytest.raises(GraphValidationError, match=r"a -> b -> a"):
        validate_workflow_definition(definition, _registry())


def test_cycle_with_explicit_bound_is_valid() -> None:
    definition = _definition(
        (_node("start"), _node("retry"), _node("done")),
        (
            _edge("begin", "start", "retry"),
            _edge(
                "again",
                "retry",
                "start",
                cycle_bound=CycleBound(2, "retry_count"),
            ),
            _edge("finish", "retry", "done"),
        ),
    )

    validate_workflow_definition(definition, _registry())


def _sending_definition(*, include_bypass: bool) -> WorkflowDefinition:
    nodes = (
        _node("validated"),
        _node("approved"),
        _node("gate"),
        _node("reserved"),
        _node(
            "provider_attempt",
            kind=NodeKind.PRIVILEGED_SIDE_EFFECT,
            side_effect=SideEffectClass.PRIVILEGED_EXTERNAL,
            idempotency_strategy="reservation_id",
        ),
        _node("done"),
    )
    edges = [
        _edge("validated_to_approved", "validated", "approved"),
        _edge("approved_to_gate", "approved", "gate"),
        _edge("gate_to_reserved", "gate", "reserved"),
        _edge("reserved_to_provider", "reserved", "provider_attempt"),
        _edge("provider_to_done", "provider_attempt", "done"),
    ]
    if include_bypass:
        edges.append(_edge("unsafe_bypass", "validated", "provider_attempt"))
    return _definition(nodes, tuple(edges), start="validated")


def test_mandatory_checkpoint_invariant_accepts_safe_sending_path() -> None:
    definition = _sending_definition(include_bypass=False)
    validate_workflow_definition(definition, _registry())

    assert_mandatory_checkpoints_before(
        definition,
        privileged_target_id="provider_attempt",
        checkpoint_node_ids=("validated", "approved", "gate", "reserved"),
    )


def test_mandatory_checkpoint_invariant_reports_bypass_witness() -> None:
    definition = _sending_definition(include_bypass=True)
    validate_workflow_definition(definition, _registry())

    with pytest.raises(GraphValidationError) as exc_info:
        assert_mandatory_checkpoints_before(
            definition,
            privileged_target_id="provider_attempt",
            checkpoint_node_ids=("approved", "gate", "reserved"),
        )

    error = str(exc_info.value)
    assert "bypasses mandatory checkpoint 'approved'" in error
    assert "validated -> provider_attempt" in error


def test_application_preparation_v1_is_valid_and_agents_only_produce_candidates() -> None:
    definition = application_preparation_v1()

    validate_workflow_definition(definition, APPLICATION_PREPARATION_REGISTRY)

    assert definition.definition_id == "application_preparation"
    assert definition.version == 1
    assert definition.terminal_node_ids == frozenset(
        {"application_ready", "application_blocked"}
    )
    nodes = {node.node_id: node for node in definition.nodes}
    assert {
        node.node_id for node in definition.nodes if node.kind is NodeKind.AGENT
    } == {"contact_research", "draft_candidate_artifacts"}
    assert nodes["contact_research"].retry_policy.max_attempts == 2
    assert nodes["contact_research"].output_contract_ids == (
        "contact_candidate.schema.json",
    )
    assert nodes["draft_candidate_artifacts"].output_contract_ids == (
        "email_draft.schema.json",
    )
    assert {
        edge.destination
        for edge in definition.edges
        if nodes[edge.source].kind is NodeKind.AGENT
    } == {"validate_contact_candidate", "validate_candidate_artifacts"}
    retry = next(
        edge for edge in definition.edges if edge.edge_id == "retry_contact_remediation"
    )
    assert retry.cycle_bound == CycleBound(
        max_traversals=1,
        counter_key="contact_remediation_retry_count",
    )


def test_privileged_sending_v1_is_valid_ordered_and_contains_no_agents() -> None:
    definition = privileged_sending_v1()

    validate_workflow_definition(definition, PRIVILEGED_SENDING_REGISTRY)
    assert_mandatory_checkpoints_before(
        definition,
        privileged_target_id="provider_attempt",
        checkpoint_node_ids=PRIVILEGED_SENDING_CHECKPOINTS,
    )
    assert_ordered_checkpoints_before(
        definition,
        privileged_target_id="provider_attempt",
        ordered_checkpoint_node_ids=PRIVILEGED_SENDING_CHECKPOINTS,
    )

    assert definition.definition_id == "privileged_sending"
    assert definition.version == 1
    assert not any(node.kind is NodeKind.AGENT for node in definition.nodes)
    assert definition.terminal_node_ids == frozenset(
        {
            "audited_sent",
            "audited_known_unsent",
            "audited_outcome_uncertain",
        }
    )


def test_ordered_checkpoint_invariant_rejects_reordered_path() -> None:
    definition = _sending_definition(include_bypass=False)
    reordered_edges = tuple(
        edge
        for edge in definition.edges
        if edge.edge_id not in {"validated_to_approved", "approved_to_gate"}
    ) + (
        _edge("validated_to_gate", "validated", "gate"),
        _edge("gate_to_approved", "gate", "approved"),
        _edge("approved_to_reserved", "approved", "reserved"),
    )
    reordered = _definition(
        definition.nodes,
        reordered_edges,
        start="validated",
    )
    validate_workflow_definition(reordered, _registry())

    with pytest.raises(GraphValidationError, match="required order") as exc_info:
        assert_ordered_checkpoints_before(
            reordered,
            privileged_target_id="provider_attempt",
            ordered_checkpoint_node_ids=("validated", "approved", "gate", "reserved"),
        )

    assert "validated -> gate" in str(exc_info.value)


def test_privileged_definition_rejects_direct_agent_provider_privilege() -> None:
    safe = privileged_sending_v1()
    nodes = tuple(
        NodeDefinition(
            node_id=node.node_id,
            executor_key=node.executor_key,
            kind=NodeKind.AGENT if node.node_id == "transactional_reservation" else node.kind,
            input_contract_ids=node.input_contract_ids,
            output_contract_ids=node.output_contract_ids,
            retry_policy=node.retry_policy,
            timeout_seconds=node.timeout_seconds,
            concurrency_class=node.concurrency_class,
            side_effect=node.side_effect,
            idempotency_strategy=node.idempotency_strategy,
            cycle_bound=node.cycle_bound,
        )
        for node in safe.nodes
    )
    unsafe = WorkflowDefinition(
        definition_id=safe.definition_id,
        version=safe.version,
        workflow_kinds=safe.workflow_kinds,
        nodes=nodes,
        edges=safe.edges,
        start_node_id=safe.start_node_id,
        terminal_node_ids=safe.terminal_node_ids,
    )

    with pytest.raises(GraphValidationError, match="must not connect directly"):
        validate_workflow_definition(unsafe, PRIVILEGED_SENDING_REGISTRY)
