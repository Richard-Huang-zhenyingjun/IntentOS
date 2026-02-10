from src.core.metrics import MetricsCollector


def test_metrics_collector_counts_events():
    """MetricsCollector accurately counts from event stream."""
    collector = MetricsCollector("test_session")

    collector.process_event({"type": "proposal_generated", "data": {}})
    collector.process_event({"type": "proposal_generated", "data": {}})
    collector.process_event({"type": "confirmed", "data": {}})

    metrics = collector.finalize()
    assert metrics.proposals_generated == 2
    assert metrics.proposals_confirmed == 1


def test_metrics_false_executions_always_zero():
    """False executions counter starts at zero and stays zero."""
    collector = MetricsCollector("test_session")

    collector.process_event({"type": "proposal_generated", "data": {}})
    collector.process_event({"type": "confirmed", "data": {}})
    collector.process_event({"type": "trust_updated", "data": {"task_trust": 0.8}})

    metrics = collector.finalize()
    assert metrics.false_executions == 0
