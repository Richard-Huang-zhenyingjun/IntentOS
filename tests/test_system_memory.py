"""Tests for SystemMemory."""

import json

import pytest

from src.world_model.system_memory import (
    DEFAULT_SUCCESS_RATE,
    RECENCY_WINDOW,
    SystemMemory,
)


@pytest.fixture
def memory(tmp_path):
    return SystemMemory(path=str(tmp_path / "test_memory.json"))


class TestObjectMemory:
    def test_default_rate_when_no_history(self, memory):
        assert memory.object_success_rate("red_block", "reach") == DEFAULT_SUCCESS_RATE

    def test_success_rate_after_recording(self, memory):
        memory.record_object_action("red_block", "reach", True)
        memory.record_object_action("red_block", "reach", True)
        memory.record_object_action("red_block", "reach", False)
        rate = memory.object_success_rate("red_block", "reach")
        assert abs(rate - 2 / 3) < 0.01

    def test_different_objects_independent(self, memory):
        memory.record_object_action("red_block", "reach", True)
        memory.record_object_action("blue_cup", "reach", False)
        assert memory.object_success_rate("red_block", "reach") == 1.0
        assert memory.object_success_rate("blue_cup", "reach") == 0.0

    def test_recency_window_trims_to_last_entries(self, memory):
        for i in range(RECENCY_WINDOW + 5):
            memory.record_object_action("cup", "reach", success=i >= 5)

        assert memory.object_success_rate("cup", "reach") == 1.0


class TestStrategyMemory:
    def test_preferred_source_returned_after_enough_attempts(self, memory):
        for _ in range(4):
            memory.record_plan_outcome("clean_table", "llm", True)
        for _ in range(4):
            memory.record_plan_outcome("clean_table", "heuristic", False)
        assert memory.preferred_plan_source("clean_table") == "llm"

    def test_no_preference_without_history(self, memory):
        assert memory.preferred_plan_source("unknown_goal") is None

    def test_no_preference_with_insufficient_attempts(self, memory):
        memory.record_plan_outcome("clean_table", "llm", True)
        assert memory.preferred_plan_source("clean_table") is None


class TestFailureMemory:
    def test_recent_failures_returns_last_10_only(self, memory):
        for i in range(12):
            memory.record_failure(f"n{i}", "reach", "arm", "failure")

        failures = memory.recent_failures()

        assert len(failures) == 10
        assert failures[0]["node_id"] == "n2"
        assert failures[-1]["node_id"] == "n11"

    def test_recent_failures_filters_by_action(self, memory):
        memory.record_failure("n1", "reach", "arm", "object not found")
        memory.record_failure("n2", "grasp", "arm", "grasp slip")

        failures = memory.recent_failures("grasp")

        assert len(failures) == 1
        assert failures[0]["node_id"] == "n2"

    def test_failure_patterns_trimmed_to_100(self, memory):
        for i in range(105):
            memory.record_failure(f"n{i}", "reach", "arm", "failure")

        assert len(memory._data["failure_patterns"]) == 100
        assert memory.recent_failures()[-1]["node_id"] == "n104"


class TestPersistence:
    def test_memory_persists_across_instances(self, tmp_path):
        path = str(tmp_path / "persist_test.json")
        m1 = SystemMemory(path)
        m1.record_object_action("red_block", "reach", True)
        m1.increment_session()

        m2 = SystemMemory(path)
        assert m2.object_success_rate("red_block", "reach") == 1.0
        assert m2.summary()["session_count"] == 1

    def test_corrupt_file_starts_fresh(self, tmp_path):
        path = tmp_path / "corrupt.json"
        path.write_text("not valid json {{{")
        m = SystemMemory(str(path))
        assert m.object_success_rate("any", "reach") == DEFAULT_SUCCESS_RATE

    def test_session_count_increments_and_persists(self, tmp_path):
        path = str(tmp_path / "sessions.json")
        m1 = SystemMemory(path)
        m1.increment_session()
        m1.increment_session()

        m2 = SystemMemory(path)

        assert m2.summary()["session_count"] == 2
        assert m2.summary()["last_updated"] is not None

    def test_save_is_atomic_no_tmp_file_left(self, tmp_path):
        path = tmp_path / "atomic.json"
        memory = SystemMemory(str(path))

        memory.record_object_action("red_block", "reach", True)

        assert path.exists()
        assert not path.with_suffix(".tmp.json").exists()
        with open(path) as file:
            data = json.load(file)
        assert data["objects"]["red_block"]["reach"] == [1]


class TestSummary:
    def test_summary_counts_objects_actions_and_failures(self, memory):
        memory.record_object_action("red_block", "reach", True)
        memory.record_object_action("red_block", "grasp", False)
        memory.record_object_action("blue_block", "reach", True)
        memory.record_failure("n1", "grasp", "arm", "slip")

        summary = memory.summary()

        assert summary["objects_tracked"] == 2
        assert summary["total_object_actions"] == 3
        assert summary["failure_patterns"] == 1
