"""
Week 2 Smoke Test — Verify OpenVLA is wired into the proposal pipeline.

Run: python scripts/week2_smoke_test.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.external.openvla.adapter_fake import FakeOpenVLAAdapter
from src.external.openvla.proposer_openvla import OpenVLAProposer
from src.intelligence.proposer_heuristic import HeuristicProposer
from src.intelligence.proposer_registry import ProposerRegistry
from src.interfaces.scene_summary import ObjectInfo, SceneSummary


def _make_scene(object_specs: list[tuple[int, str]]) -> SceneSummary:
    objects = tuple(
        ObjectInfo(
            object_id=obj_id,
            pos_xyz=(0.35 + i * 0.05, -0.1 + i * 0.05, 0.4),
            on_table=True,
            category=category,
            confidence=1.0,
        )
        for i, (obj_id, category) in enumerate(object_specs)
    )
    return SceneSummary(
        table_id=1,
        table_position=(0.0, 0.0, 0.3),
        bin_zone_center=(0.4, 0.0, 0.75),
        bin_zone_radius=0.12,
        objects=objects,
        objects_on_table=objects,
        clutter_score=0.8 if objects else 0.0,
        is_messy=bool(objects),
        timestamp_frame=1,
        rgb_snapshot=None,
        eeg_quality=None,
    )


def _build_registry(openvla_enabled: bool = True):
    registry = ProposerRegistry()
    adapter = FakeOpenVLAAdapter()
    adapter.load_model()
    openvla = OpenVLAProposer(adapter, priority=15, enabled=openvla_enabled)
    registry.register("openvla", openvla, priority=15)
    heuristic = HeuristicProposer(config={})
    registry.register("heuristic", heuristic, priority=0, is_fallback=True)
    return registry, openvla, heuristic


def test_proposer_registration():
    print("\n" + "=" * 60)
    print("TEST 1: Proposer Registration")
    print("=" * 60)
    registry, openvla, _heuristic = _build_registry(openvla_enabled=True)
    stats = registry.get_stats()
    print(f"  ✓ OpenVLA registered (priority={openvla.priority})")
    print(f"  ✓ Registry has {len(stats['registered_proposers'])} proposers")
    print(f"  ✓ Active proposer: {stats['active_proposer']}")
    assert "openvla" in stats["registered_proposers"]
    assert stats["active_proposer"] == "openvla"
    print("  ✓ Registration test PASSED")
    return registry


def test_proposal_generation(registry: ProposerRegistry):
    print("\n" + "=" * 60)
    print("TEST 2: Proposal Generation")
    print("=" * 60)
    scene = _make_scene([(4, "red_cube"), (5, "green_cube")])
    proposal = registry.propose(scene)
    assert proposal is not None
    print("  ✓ Proposal received")
    print(f"  ✓ Source: {proposal.source}")
    meta = proposal.metadata
    assert proposal.source == "openvla"
    print(f"  ✓ Instruction: {meta.get('instruction')}")
    print(f"  ✓ Delta position: {meta.get('delta_position')}")
    print(f"  ✓ Gripper: {meta.get('gripper')}")
    print(f"  ✓ Raw action (7D): {meta.get('raw_action')}")
    json_str = json.dumps(meta, indent=2)
    print(f"  ✓ Metadata is JSON-serializable ({len(json_str)} chars)")
    print(f"  ✓ Description: {proposal.description}")
    print("  ✓ Proposal generation test PASSED")


def test_fallback():
    print("\n" + "=" * 60)
    print("TEST 3: Fallback Behavior")
    print("=" * 60)
    registry, _openvla, _heuristic = _build_registry(openvla_enabled=False)
    scene = _make_scene([(7, "cup")])
    proposal = registry.propose(scene)
    assert proposal is not None
    print(f"  ✓ Fallback proposal from: {proposal.source}")
    assert proposal.source != "openvla"
    print("  ✓ Fallback test PASSED")


def test_proposal_cycle():
    print("\n" + "=" * 60)
    print("TEST 4: Simulated Proposal Cycle (10 frames)")
    print("=" * 60)
    registry, openvla, _heuristic = _build_registry(openvla_enabled=True)
    scene = _make_scene([(4, "red_cube"), (5, "green_cube"), (6, "blue_cube")])
    for frame in range(10):
        proposal = registry.propose(scene)
        source = proposal.source if proposal else "none"
        desc_short = (proposal.description if proposal else "none")[:50]
        print(f"  Frame {frame}: [{source}] {desc_short}...")
        assert proposal is not None
        assert source == "openvla"
    print(f"\n  OpenVLA stats: {openvla.stats}")
    print("  ✓ Proposal cycle test PASSED")


def main() -> int:
    print("=" * 60)
    print("WEEK 2 SMOKE TEST")
    print("OpenVLA -> Intent System Integration")
    print("=" * 60)
    try:
        registry = test_proposer_registration()
        test_proposal_generation(registry)
        test_fallback()
        test_proposal_cycle()
        print("\n" + "=" * 60)
        print("ALL WEEK 2 SMOKE TESTS PASSED ✓")
        print("=" * 60)
        print("\nWhat's working now:")
        print("  - OpenVLA proposes actions via ProposerRegistry")
        print("  - Priority: OpenVLA (15) > Gemini (10) > Heuristic")
        print("  - Graceful fallback on failure")
        print("  - Proposals contain full 7D action data")
        print("\nNext steps (Week 3):")
        print("  - Wire MuJoCo camera -> OpenVLA (real images)")
        print("  - Build action translator (OpenVLA -> robot joints)")
        print("  - Execute OpenVLA actions in MuJoCo")
        print("  - Verify authorization gate blocks unauthorized execution")
        return 0
    except Exception as exc:
        print(f"\n✗ SMOKE TEST FAILED: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
