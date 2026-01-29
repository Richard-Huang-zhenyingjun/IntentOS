"""Week 6 Tests - State Inference and Context-Aware Affordances"""

import pytest
from affordances.state_estimator import StateEstimator
from affordances.constraint_evaluator import ConstraintEvaluator
from affordances.state_schema import ObjectStateEstimate, LampState, DoorState, PhoneState
from affordances.affordance_schema import AffordanceType
from execution.smart_world_sim import SmartWorldSim


class TestStateInferenceAffordances:
    """Week 6 tests: state-aware affordances"""
    
    def test_high_confidence_lamp_on_shows_turn_off(self):
        """INVARIANT: Confident lamp ON → only TURN_OFF affordance"""
        config = {'min_state_confidence': 0.7}
        evaluator = ConstraintEvaluator(config)
        
        # High confidence lamp is ON
        estimate = ObjectStateEstimate(
            object_id="lamp_001",
            category="lamp",
            state=LampState.ON.value,
            confidence=0.9,
            method="world_state_hint",
            reason="Lamp is ON from simulator",
            evidence={'power': 'on'},
            timestamp=1.0,
            frame_id=1
        )
        
        constraints = evaluator.evaluate(estimate)
        
        # Should allow TURN_OFF only
        assert constraints.allow_specific == True
        assert AffordanceType.TURN_OFF in constraints.allowed_actions
        assert AffordanceType.TURN_ON not in constraints.allowed_actions
        assert len(constraints.allowed_actions) == 1
    
    def test_high_confidence_lamp_off_shows_turn_on(self):
        """INVARIANT: Confident lamp OFF → only TURN_ON affordance"""
        config = {'min_state_confidence': 0.7}
        evaluator = ConstraintEvaluator(config)
        
        # High confidence lamp is OFF
        estimate = ObjectStateEstimate(
            object_id="lamp_001",
            category="lamp",
            state=LampState.OFF.value,
            confidence=0.9,
            method="world_state_hint",
            reason="Lamp is OFF from simulator",
            evidence={'power': 'off'},
            timestamp=1.0,
            frame_id=1
        )
        
        constraints = evaluator.evaluate(estimate)
        
        # Should allow TURN_ON only
        assert constraints.allow_specific == True
        assert AffordanceType.TURN_ON in constraints.allowed_actions
        assert AffordanceType.TURN_OFF not in constraints.allowed_actions
        assert len(constraints.allowed_actions) == 1
    
    def test_low_confidence_lamp_uses_toggle(self):
        """INVARIANT: Uncertain lamp state → TOGGLE_POWER fallback"""
        config = {'min_state_confidence': 0.7, 'fallback_confidence': 0.4}
        evaluator = ConstraintEvaluator(config)
        
        # Low confidence (but above block threshold)
        estimate = ObjectStateEstimate(
            object_id="lamp_001",
            category="lamp",
            state=LampState.ON.value,
            confidence=0.5,  # Between 0.4 and 0.7
            method="visual_heuristic",
            reason="Uncertain brightness",
            evidence={},
            timestamp=1.0,
            frame_id=1,
            uncertain=True
        )
        
        constraints = evaluator.evaluate(estimate)
        
        # Should require toggle
        assert constraints.require_toggle == True
        assert AffordanceType.TOGGLE_POWER in constraints.allowed_actions
        assert AffordanceType.TURN_OFF not in constraints.allowed_actions
        assert len(constraints.allowed_actions) == 1
    
    def test_very_low_confidence_blocks(self):
        """INVARIANT: Too uncertain (< 0.4) → blocked"""
        config = {'fallback_confidence': 0.4}
        evaluator = ConstraintEvaluator(config)
        
        # Very low confidence
        estimate = ObjectStateEstimate(
            object_id="lamp_001",
            category="lamp",
            state=LampState.UNKNOWN.value,
            confidence=0.2,  # < 0.4
            method="visual_heuristic",
            reason="No clear evidence",
            evidence={},
            timestamp=1.0,
            frame_id=1,
            too_uncertain=True
        )
        
        constraints = evaluator.evaluate(estimate)
        
        # Should block
        assert constraints.block_all == True
        assert len(constraints.allowed_actions) == 0
    
    def test_door_open_shows_close(self):
        """INVARIANT: Confident door OPEN → only CLOSE"""
        config = {'min_state_confidence': 0.7}
        evaluator = ConstraintEvaluator(config)
        
        estimate = ObjectStateEstimate(
            object_id="door_001",
            category="door",
            state=DoorState.OPEN.value,
            confidence=0.85,
            method="world_state_hint",
            reason="Door is OPEN",
            evidence={'position': 'open'},
            timestamp=1.0,
            frame_id=1
        )
        
        constraints = evaluator.evaluate(estimate)
        
        assert constraints.allow_specific == True
        assert AffordanceType.CLOSE in constraints.allowed_actions
        assert AffordanceType.OPEN not in constraints.allowed_actions
        assert len(constraints.allowed_actions) == 1
    
    def test_door_closed_shows_open(self):
        """INVARIANT: Confident door CLOSED → only OPEN"""
        config = {'min_state_confidence': 0.7}
        evaluator = ConstraintEvaluator(config)
        
        estimate = ObjectStateEstimate(
            object_id="door_001",
            category="door",
            state=DoorState.CLOSED.value,
            confidence=0.85,
            method="world_state_hint",
            reason="Door is CLOSED",
            evidence={'position': 'closed'},
            timestamp=1.0,
            frame_id=1
        )
        
        constraints = evaluator.evaluate(estimate)
        
        assert constraints.allow_specific == True
        assert AffordanceType.OPEN in constraints.allowed_actions
        assert AffordanceType.CLOSE not in constraints.allowed_actions
        assert len(constraints.allowed_actions) == 1
    
    def test_phone_screen_off_shows_wake(self):
        """INVARIANT: Confident screen OFF → only WAKE"""
        config = {'min_state_confidence': 0.7}
        evaluator = ConstraintEvaluator(config)
        
        estimate = ObjectStateEstimate(
            object_id="phone_001",
            category="phone",
            state=PhoneState.SCREEN_OFF.value,
            confidence=0.8,
            method="visual_heuristic",
            reason="Dark screen detected",
            evidence={'brightness': 0.1},
            timestamp=1.0,
            frame_id=1
        )
        
        constraints = evaluator.evaluate(estimate)
        
        assert constraints.allow_specific == True
        assert AffordanceType.WAKE in constraints.allowed_actions
        assert AffordanceType.SLEEP not in constraints.allowed_actions
        assert len(constraints.allowed_actions) == 1
    
    def test_phone_screen_on_shows_sleep(self):
        """INVARIANT: Confident screen ON → only SLEEP"""
        config = {'min_state_confidence': 0.7}
        evaluator = ConstraintEvaluator(config)
        
        estimate = ObjectStateEstimate(
            object_id="phone_001",
            category="phone",
            state=PhoneState.SCREEN_ON.value,
            confidence=0.8,
            method="visual_heuristic",
            reason="Bright screen detected",
            evidence={'brightness': 0.9},
            timestamp=1.0,
            frame_id=1
        )
        
        constraints = evaluator.evaluate(estimate)
        
        assert constraints.allow_specific == True
        assert AffordanceType.SLEEP in constraints.allowed_actions
        assert AffordanceType.WAKE not in constraints.allowed_actions
        assert len(constraints.allowed_actions) == 1
    
    def test_options_list_bounded_to_one(self):
        """INVARIANT: State-aware produces exactly 1 option (cognitive load limit)"""
        config = {'min_state_confidence': 0.7}
        evaluator = ConstraintEvaluator(config)
        
        # Test lamp ON
        estimate_lamp_on = ObjectStateEstimate(
            object_id="lamp_001",
            category="lamp",
            state=LampState.ON.value,
            confidence=0.9,
            method="world_state_hint",
            reason="Lamp is ON",
            evidence={'power': 'on'},
            timestamp=1.0,
            frame_id=1
        )
        
        constraints = evaluator.evaluate(estimate_lamp_on)
        assert len(constraints.allowed_actions) == 1, "Should have exactly 1 specific action"
        
        # Test door OPEN
        estimate_door_open = ObjectStateEstimate(
            object_id="door_001",
            category="door",
            state=DoorState.OPEN.value,
            confidence=0.85,
            method="world_state_hint",
            reason="Door is OPEN",
            evidence={'position': 'open'},
            timestamp=1.0,
            frame_id=1
        )
        
        constraints = evaluator.evaluate(estimate_door_open)
        assert len(constraints.allowed_actions) == 1, "Should have exactly 1 specific action"
    
    def test_world_state_trumps_visual(self):
        """INVARIANT: World state has higher confidence than visual"""
        config = {
            'use_world_state_hint': True,
            'lamp': {
                'world_state_confidence': 0.9,
                'visual_confidence': 0.6
            }
        }
        
        world = SmartWorldSim({}, seed=42)
        world.ensure_object("lamp_001", "lamp", 1.0)
        world.objects["lamp_001"].state = {'power': 'on'}
        
        estimator = StateEstimator(config, world)
        
        estimate = estimator.estimate(
            object_id="lamp_001",
            category="lamp",
            bbox=(100, 100, 50, 50),
            frame=None,  # No frame provided
            timestamp=1.0,
            frame_id=1
        )
        
        # Should use world state
        assert estimate.method == 'world_state_hint'
        assert estimate.confidence == 0.9
        assert estimate.state == LampState.ON.value
    
    def test_unknown_state_defaults_to_unknown(self):
        """INVARIANT: No evidence → state=UNKNOWN, confidence=0.0"""
        config = {'use_world_state_hint': False}
        
        estimator = StateEstimator(config, world=None)
        
        estimate = estimator.estimate(
            object_id="lamp_001",
            category="lamp",
            bbox=(100, 100, 50, 50),
            frame=None,  # No frame
            timestamp=1.0,
            frame_id=1
        )
        
        # Should be unknown
        assert estimate.state == LampState.UNKNOWN.value
        assert estimate.confidence == 0.0
        assert estimate.method == 'default'
        assert estimate.too_uncertain == True
    
    def test_confidence_thresholds_enforced(self):
        """INVARIANT: Confidence thresholds create three tiers"""
        config = {
            'min_state_confidence': 0.7,
            'fallback_confidence': 0.4
        }
        evaluator = ConstraintEvaluator(config)
        
        # Tier 1: High confidence (>= 0.7) → specific actions
        estimate_high = ObjectStateEstimate(
            object_id="lamp_001", category="lamp", state=LampState.ON.value,
            confidence=0.8, method="world_state_hint", reason="High conf",
            evidence={}, timestamp=1.0, frame_id=1
        )
        constraints_high = evaluator.evaluate(estimate_high)
        assert constraints_high.allow_specific == True
        
        # Tier 2: Medium confidence (0.4-0.7) → toggle
        estimate_medium = ObjectStateEstimate(
            object_id="lamp_001", category="lamp", state=LampState.ON.value,
            confidence=0.5, method="visual_heuristic", reason="Medium conf",
            evidence={}, timestamp=1.0, frame_id=1, uncertain=True
        )
        constraints_medium = evaluator.evaluate(estimate_medium)
        assert constraints_medium.require_toggle == True
        
        # Tier 3: Low confidence (< 0.4) → blocked
        estimate_low = ObjectStateEstimate(
            object_id="lamp_001", category="lamp", state=LampState.UNKNOWN.value,
            confidence=0.2, method="default", reason="Low conf",
            evidence={}, timestamp=1.0, frame_id=1, too_uncertain=True
        )
        constraints_low = evaluator.evaluate(estimate_low)
        assert constraints_low.block_all == True
    
    def test_state_enums_conversion(self):
        """INVARIANT: State enums convert correctly from world state"""
        # Test LampState
        assert LampState.from_world_state({'power': 'on'}) == LampState.ON
        assert LampState.from_world_state({'power': 'off'}) == LampState.OFF
        assert LampState.from_world_state({'power': 'unknown'}) == LampState.UNKNOWN
        
        # Test DoorState
        assert DoorState.from_world_state({'position': 'open'}) == DoorState.OPEN
        assert DoorState.from_world_state({'position': 'closed'}) == DoorState.CLOSED
        assert DoorState.from_world_state({'position': 'unknown'}) == DoorState.UNKNOWN
        
        # Test PhoneState
        assert PhoneState.from_world_state({'screen': 'screen_on'}) == PhoneState.SCREEN_ON
        assert PhoneState.from_world_state({'screen': 'screen_off'}) == PhoneState.SCREEN_OFF
        assert PhoneState.from_world_state({'screen': 'unknown'}) == PhoneState.UNKNOWN
    
    def test_state_estimate_factory_unknown(self):
        """INVARIANT: create_unknown factory creates valid unknown estimate"""
        estimate = ObjectStateEstimate.create_unknown(
            object_id="lamp_001",
            category="lamp",
            reason="No evidence available",
            timestamp=1.0,
            frame_id=1
        )
        
        assert estimate.state == 'unknown'
        assert estimate.confidence == 0.0
        assert estimate.method == 'default'
        assert estimate.too_uncertain == True
        assert estimate.uncertain == False


class TestStateSafetyInvariants:
    """Critical safety tests for Week 6 state inference"""
    
    def test_never_guess_when_uncertain(self):
        """SAFETY INVARIANT: System never forces 51/49 choice"""
        config = {'fallback_confidence': 0.4}
        evaluator = ConstraintEvaluator(config)
        
        # Borderline confidence (just below threshold)
        estimate = ObjectStateEstimate(
            object_id="lamp_001",
            category="lamp",
            state=LampState.ON.value,
            confidence=0.39,  # Just below 0.4
            method="visual_heuristic",
            reason="Very uncertain",
            evidence={},
            timestamp=1.0,
            frame_id=1,
            too_uncertain=True
        )
        
        constraints = evaluator.evaluate(estimate)
        
        # Should block, not guess
        assert constraints.block_all == True
        assert len(constraints.allowed_actions) == 0
    
    def test_state_inference_read_only(self):
        """SAFETY INVARIANT: State inference never modifies world state"""
        config = {'use_world_state_hint': True}
        
        world = SmartWorldSim({}, seed=42)
        world.ensure_object("lamp_001", "lamp", 1.0)
        original_state = world.objects["lamp_001"].state.copy()
        
        estimator = StateEstimator(config, world)
        
        # Estimate state
        estimator.estimate(
            object_id="lamp_001",
            category="lamp",
            bbox=(100, 100, 50, 50),
            frame=None,
            timestamp=1.0,
            frame_id=1
        )
        
        # World state should be unchanged
        assert world.objects["lamp_001"].state == original_state
    
    def test_max_one_affordance_per_confident_state(self):
        """SAFETY INVARIANT: Confident state → exactly 1 affordance"""
        config = {'min_state_confidence': 0.7}
        evaluator = ConstraintEvaluator(config)
        
        # Test all three categories
        categories_and_states = [
            ("lamp", LampState.ON.value),
            ("lamp", LampState.OFF.value),
            ("door", DoorState.OPEN.value),
            ("door", DoorState.CLOSED.value),
            ("phone", PhoneState.SCREEN_ON.value),
            ("phone", PhoneState.SCREEN_OFF.value),
        ]
        
        for category, state in categories_and_states:
            estimate = ObjectStateEstimate(
                object_id=f"{category}_001",
                category=category,
                state=state,
                confidence=0.9,
                method="world_state_hint",
                reason=f"{category} in state {state}",
                evidence={},
                timestamp=1.0,
                frame_id=1
            )
            
            constraints = evaluator.evaluate(estimate)
            
            assert len(constraints.allowed_actions) == 1, \
                f"{category} state {state} should produce exactly 1 affordance"
    
    def test_toggle_is_safe_fallback(self):
        """SAFETY INVARIANT: Toggle works regardless of actual state"""
        # This is tested by SmartWorldSim - toggle always flips state
        # regardless of what state inference thinks
        world = SmartWorldSim({}, seed=42)
        world.ensure_object("lamp_001", "lamp", 1.0)
        
        from execution.action_schema import ActionRequest, ActionType
        
        # Set lamp to ON
        world.objects["lamp_001"].state = {'power': 'on'}
        
        # Toggle it (even if state inference is wrong)
        request = ActionRequest.create(
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type=ActionType.TOGGLE_POWER,
            timestamp=1.0
        )
        
        before, after = world.apply_action(request)
        
        assert before['power'] == 'on'
        assert after['power'] == 'off'
        
        # Toggle again
        request2 = ActionRequest.create(
            object_id="lamp_001",
            object_label="lamp",
            category="lamp",
            action_type=ActionType.TOGGLE_POWER,
            timestamp=2.0
        )
        
        before2, after2 = world.apply_action(request2)
        
        assert before2['power'] == 'off'
        assert after2['power'] == 'on'




