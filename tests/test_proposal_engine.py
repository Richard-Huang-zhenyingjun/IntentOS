"""Tests for ProposalEngine."""
from src.planning import ExecutionProposal, ProposalEngine
from src.planning.proposal_engine import (
    UNCERTAINTY_ABORT_THRESHOLD,
    UNCERTAINTY_CHECKPOINT_THRESHOLD,
    UNCERTAINTY_WARN_THRESHOLD,
)
from src.task_graph import (
    ConfirmationPolicy,
    TaskGraph,
    TaskNode,
    UncertaintySignals,
)


def uncertainty_for_combined(target: float) -> UncertaintySignals:
    # With perception=1 and history=1, combined = 0.30 * simulation_risk.
    # This helper also allows target > 0.30 by lowering perception/history.
    if target <= 0.30:
        return UncertaintySignals(
            perception_confidence=1.0,
            execution_history_rate=1.0,
            simulation_risk=target / 0.30,
        )
    remainder = target - 0.30
    inv_each = remainder / 0.70
    return UncertaintySignals(
        perception_confidence=1.0 - inv_each,
        execution_history_rate=1.0 - inv_each,
        simulation_risk=1.0,
    )


def make_node(
    node_id="n1",
    action_type="reach",
    policy=ConfirmationPolicy.CHECKPOINT,
    uncertainty=None,
):
    return TaskNode(
        node_id=node_id,
        action_type=action_type,
        agent_id="arm",
        parameters={},
        depends_on=[],
        confirmation_policy=policy,
        uncertainty=uncertainty or uncertainty_for_combined(0.1),
    )


def make_graph(nodes, goal="clean the table"):
    return TaskGraph(
        graph_id="g1",
        goal=goal,
        nodes=nodes,
        created_at=0.0,
    )


def test_propose_returns_execution_proposal_for_valid_graph():
    engine = ProposalEngine()
    graph = make_graph([make_node()])

    proposal = engine.propose(graph, plan_source="llm", proposal_id="p1")

    assert isinstance(proposal, ExecutionProposal)
    assert proposal.proposal_id == "p1"
    assert proposal.graph_id == "g1"
    assert proposal.step_count == 1
    assert proposal.estimated_duration_s == 2.0


def test_summary_is_single_line_and_human_readable():
    engine = ProposalEngine()
    graph = make_graph(
        [
            make_node("n1", "reach"),
            make_node("n2", "grasp"),
            make_node("n3", "move"),
            make_node("n4", "release"),
        ]
    )

    proposal = engine.propose(graph, plan_source="llm", proposal_id="p1")

    assert "\n" not in proposal.summary
    assert "Clean the table" in proposal.summary
    assert "4 steps" in proposal.summary
    assert len(proposal.summary) <= 120


def test_low_uncertainty_llm_has_no_warning():
    engine = ProposalEngine()
    graph = make_graph(
        [make_node(uncertainty=uncertainty_for_combined(UNCERTAINTY_WARN_THRESHOLD - 0.01))]
    )

    proposal = engine.propose(graph, plan_source="llm", proposal_id="p1")

    assert proposal.warning is None
    assert proposal.uncertainty_level == "low"


def test_heuristic_plan_warning_mentions_heuristic():
    engine = ProposalEngine()
    graph = make_graph([make_node()])

    proposal = engine.propose(graph, plan_source="heuristic", proposal_id="p1")

    assert proposal.warning is not None
    assert "heuristic" in proposal.warning.lower()


def test_medium_uncertainty_generates_warning():
    engine = ProposalEngine()
    graph = make_graph(
        [make_node(uncertainty=uncertainty_for_combined(UNCERTAINTY_WARN_THRESHOLD + 0.01))]
    )

    proposal = engine.propose(graph, plan_source="llm", proposal_id="p1")

    assert proposal.uncertainty_level == "medium"
    assert proposal.warning is not None
    assert "High uncertainty" in proposal.warning


def test_high_uncertainty_requires_confirmation():
    engine = ProposalEngine()
    graph = make_graph(
        [
            make_node(
                policy=ConfirmationPolicy.NEVER,
                uncertainty=uncertainty_for_combined(
                    UNCERTAINTY_CHECKPOINT_THRESHOLD + 0.01
                ),
            )
        ]
    )

    proposal = engine.propose(graph, plan_source="llm", proposal_id="p1")

    assert proposal.uncertainty_level == "high"
    assert proposal.requires_confirmation


def test_abort_when_uncertainty_above_abort_threshold():
    engine = ProposalEngine()
    graph = make_graph(
        [
            make_node(
                policy=ConfirmationPolicy.NEVER,
                uncertainty=uncertainty_for_combined(UNCERTAINTY_ABORT_THRESHOLD + 0.01),
            )
        ]
    )

    proposal = engine.propose(graph, plan_source="llm", proposal_id="p1")

    assert proposal.uncertainty_level == "abort"
    assert proposal.warning is not None
    assert "Human intervention required" in proposal.warning
    assert "CANNOT EXECUTE" in proposal.summary


def test_checkpoint_or_always_policy_requires_confirmation():
    engine = ProposalEngine()
    for policy in (ConfirmationPolicy.CHECKPOINT, ConfirmationPolicy.ALWAYS):
        graph = make_graph([make_node(policy=policy)])
        proposal = engine.propose(graph, plan_source="llm", proposal_id="p1")
        assert proposal.requires_confirmation


def test_never_policy_low_uncertainty_can_skip_confirmation():
    engine = ProposalEngine()
    graph = make_graph([make_node(policy=ConfirmationPolicy.NEVER)])

    proposal = engine.propose(graph, plan_source="llm", proposal_id="p1")

    assert not proposal.requires_confirmation


def test_always_policy_warning_mentions_irreversible():
    engine = ProposalEngine()
    graph = make_graph([make_node(policy=ConfirmationPolicy.ALWAYS)])

    proposal = engine.propose(graph, plan_source="llm", proposal_id="p1")

    assert proposal.warning is not None
    assert "irreversible" in proposal.warning.lower()
