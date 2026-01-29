"""Affordance Engine - Orchestrates category classification and affordance generation."""

from typing import Optional, List
from affordances.affordance_schema import (
    AffordanceSet, ObjectCategory, AffordanceOption, AffordanceType, AffordanceRisk
)
from affordances.category_classifier import CategoryClassifier, CategoryResult
from affordances.affordance_registry import AffordanceRegistry
from affordances.state_estimator import StateEstimator
from affordances.constraint_evaluator import ConstraintEvaluator
from affordances.state_schema import ObjectStateEstimate, SafetyConstraints
from vision.tracking_schema import TrackedObject


class AffordanceEngine:
    """
    Generate affordance sets with safety checks (ENHANCED for Week 6)
    
    Week 5: Category-based affordances (toggle only)
    Week 6: State-aware affordances (specific actions when confident)
    
    Pipeline:
    1. Validate inputs (scope exists, no ambiguity)
    2. Classify category
    3. Estimate state (NEW Week 6)
    4. Evaluate constraints (NEW Week 6)
    5. Generate affordances (state-aware)
    6. Apply safety filters
    7. Return AffordanceSet (or blocked)
    
    CRITICAL: This engine NEVER triggers execution
    It only suggests - decisions happen elsewhere
    """
    
    def __init__(self, config: dict, seed: int = 42, world=None):
        self.config = config
        self.seed = seed
        
        # Week 5 components
        self.classifier = CategoryClassifier(config.get('category_classifier', {}))
        self.registry = AffordanceRegistry(config.get('affordance_registry', {}))
        
        # Week 6 components (NEW)
        self.use_state_inference = config.get('use_state_inference', True)
        if self.use_state_inference:
            self.state_estimator = StateEstimator(
                config=config.get('state_inference', {}),
                world=world
            )
            self.constraint_evaluator = ConstraintEvaluator(
                config=config.get('state_inference', {})
            )
        else:
            self.state_estimator = None
            self.constraint_evaluator = None
        
        # Thresholds
        self.min_category_confidence = config.get('min_category_confidence', 0.5)
        self.min_affordance_confidence = config.get('min_affordance_confidence', 0.6)
        
        # State
        self.last_affordance_set: Optional[AffordanceSet] = None
        self.last_state_estimate: Optional[ObjectStateEstimate] = None
        
        # Statistics
        self.total_computations = 0
        self.total_blocked = 0
        self.state_aware_count = 0
        self.toggle_fallback_count = 0
    
    def compute(self,
                scoped_object: Optional[TrackedObject],
                ambiguity: bool,
                frame_id: int,
                timestamp: float,
                frame: Optional = None,
                bbox: Optional[tuple] = None) -> AffordanceSet:
        """
        Compute affordances for scoped object (MODIFIED for Week 6)
        
        New pipeline:
        1. Validate inputs (scope, ambiguity) - Week 5
        2. Classify category - Week 5
        3. Estimate state - NEW Week 6
        4. Evaluate constraints - NEW Week 6
        5. Generate affordances (state-aware) - MODIFIED Week 6
        6. Filter by confidence - Week 5
        7. Return AffordanceSet
        
        Args:
            scoped_object: Stable scoped object from Week 2 (or None)
            ambiguity: Is there ambiguity in focus selection?
            frame_id: Current frame ID
            timestamp: Current timestamp
            frame: Optional frame for visual classification
            bbox: Optional bbox tuple (x, y, w, h) for state estimation
        
        Returns:
            AffordanceSet (may be blocked)
        """
        self.total_computations += 1
        
        # === BLOCKING RULES (Week 5, unchanged) ===
        
        if scoped_object is None:
            self.total_blocked += 1
            return AffordanceSet.create_blocked(
                object_id="none",
                object_label="none",
                reason="No object in scope",
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        if ambiguity:
            self.total_blocked += 1
            return AffordanceSet.create_blocked(
                object_id=scoped_object.track_id,
                object_label=scoped_object.label,
                reason="Ambiguity detected - waiting for clarity",
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        # === STEP 1: Classify category (Week 5) ===
        
        category_result = self.classifier.classify(
            tracked_label=scoped_object.label,
            bbox=scoped_object.bbox,
            confidence=scoped_object.confidence,
            frame=frame
        )
        
        if category_result.category == ObjectCategory.UNKNOWN:
            self.total_blocked += 1
            return AffordanceSet.create_blocked(
                object_id=scoped_object.track_id,
                object_label=scoped_object.label,
                reason=f"Unknown object type: {category_result.reason}",
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        if category_result.confidence < self.min_category_confidence:
            self.total_blocked += 1
            return AffordanceSet.create_blocked(
                object_id=scoped_object.track_id,
                object_label=scoped_object.label,
                reason=f"Low category confidence ({category_result.confidence:.2f})",
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        # === STEP 2: Estimate state (NEW Week 6) ===
        
        state_estimate = None
        constraints = None
        
        if self.use_state_inference and self.state_estimator:
            state_estimate = self.state_estimator.estimate(
                object_id=scoped_object.track_id,
                category=category_result.category.value,
                bbox=bbox or scoped_object.bbox,
                frame=frame,
                timestamp=timestamp,
                frame_id=frame_id
            )
            self.last_state_estimate = state_estimate
            
            # === STEP 3: Evaluate constraints (NEW Week 6) ===
            
            if self.constraint_evaluator:
                constraints = self.constraint_evaluator.evaluate(state_estimate)
                
                # Check if blocked by constraints
                if constraints.block_all:
                    self.total_blocked += 1
                    return AffordanceSet.create_blocked(
                        object_id=scoped_object.track_id,
                        object_label=scoped_object.label,
                        reason=constraints.reason,
                        timestamp=timestamp,
                        frame_id=frame_id
                    )
        
        # === STEP 4: Generate affordances (MODIFIED for Week 6) ===
        
        if constraints and constraints.allow_specific:
            # Use specific state-aware affordances
            affordances = self._generate_specific_affordances(
                category=category_result.category,
                state_estimate=state_estimate,
                constraints=constraints
            )
            self.state_aware_count += 1
        elif constraints and constraints.require_toggle:
            # Use toggle fallback
            affordances = self._generate_toggle_affordances(
                category=category_result.category,
                constraints=constraints
            )
            self.toggle_fallback_count += 1
        else:
            # Week 5 fallback (no state inference)
            affordances = self.registry.get_affordances(category_result.category)
        
        # === STEP 5: Filter by confidence (Week 5) ===
        
        filtered_affordances = [
            aff for aff in affordances
            if aff.confidence >= self.min_affordance_confidence
        ]
        
        if len(filtered_affordances) == 0:
            self.total_blocked += 1
            return AffordanceSet.create_empty(
                object_id=scoped_object.track_id,
                object_label=scoped_object.label,
                category=category_result.category,
                reason="All affordances filtered (low confidence)",
                timestamp=timestamp,
                frame_id=frame_id
            )
        
        # === SUCCESS: Create affordance set ===
        
        affordance_set = AffordanceSet(
            object_id=scoped_object.track_id,
            object_label=scoped_object.label,
            category=category_result.category,
            category_confidence=category_result.confidence,
            options=filtered_affordances,
            blocked=False,
            block_reason="",
            timestamp=timestamp,
            frame_id=frame_id,
            reasoning={
                'category_method': category_result.method,
                'category_reason': category_result.reason,
                'num_affordances': len(filtered_affordances),
                'affordance_types': [aff.affordance_type.value for aff in filtered_affordances],
                'state_aware': constraints.allow_specific if constraints else False,
                'state_estimate': {
                    'state': state_estimate.state,
                    'confidence': state_estimate.confidence,
                    'method': state_estimate.method,
                    'reason': state_estimate.reason
                } if state_estimate else None
            }
        )
        
        self.last_affordance_set = affordance_set
        return affordance_set
    
    def _generate_specific_affordances(self,
                                      category: ObjectCategory,
                                      state_estimate: ObjectStateEstimate,
                                      constraints: SafetyConstraints) -> List[AffordanceOption]:
        """
        Generate specific state-aware affordances
        
        Week 6: One specific action per state
        Example: Lamp ON → [Turn Off]
        """
        affordances = []
        
        for action_type in constraints.allowed_actions:
            # Create affordance option
            option = self._create_affordance_option(
                action_type=action_type,
                category=category.value,
                state=state_estimate.state,
                confidence=state_estimate.confidence,
                reason=constraints.reason,
                evidence=state_estimate.evidence
            )
            affordances.append(option)
        
        return affordances
    
    def _generate_toggle_affordances(self,
                                    category: ObjectCategory,
                                    constraints: SafetyConstraints) -> List[AffordanceOption]:
        """
        Generate toggle fallback affordances
        
        Week 6: Safe toggle when state uncertain
        Example: Lamp state uncertain → [Toggle Power]
        """
        affordances = []
        
        for action_type in constraints.allowed_actions:
            option = self._create_toggle_option(
                action_type=action_type,
                category=category.value,
                confidence=constraints.confidence,
                reason=constraints.reason
            )
            affordances.append(option)
        
        return affordances
    
    def _create_affordance_option(self,
                                 action_type: AffordanceType,
                                 category: str,
                                 state: str,
                                 confidence: float,
                                 reason: str,
                                 evidence: dict) -> AffordanceOption:
        """Create specific affordance option"""
        
        # Generate title and description
        if action_type == AffordanceType.TURN_ON:
            title = "Turn On"
            description = f"Turn the {category} on"
            risk = AffordanceRisk.LOW
        elif action_type == AffordanceType.TURN_OFF:
            title = "Turn Off"
            description = f"Turn the {category} off"
            risk = AffordanceRisk.LOW
        elif action_type == AffordanceType.OPEN:
            title = "Open"
            description = f"Open the {category}"
            risk = AffordanceRisk.MEDIUM
        elif action_type == AffordanceType.CLOSE:
            title = "Close"
            description = f"Close the {category}"
            risk = AffordanceRisk.MEDIUM
        elif action_type == AffordanceType.WAKE:
            title = "Wake"
            description = f"Wake the {category} screen"
            risk = AffordanceRisk.LOW
        elif action_type == AffordanceType.SLEEP:
            title = "Sleep"
            description = f"Sleep the {category} screen"
            risk = AffordanceRisk.LOW
        else:
            title = action_type.value.replace('_', ' ').title()
            description = f"{title} {category}"
            risk = AffordanceRisk.UNKNOWN
        
        return AffordanceOption(
            affordance_type=action_type,
            title=title,
            description=description,
            risk=risk,
            requires_confirmation=True,
            reason=reason,
            confidence=confidence,
            metadata={
                'state_aware': True,
                'current_state': state,
                'evidence': evidence
            }
        )
    
    def _create_toggle_option(self,
                             action_type: AffordanceType,
                             category: str,
                             confidence: float,
                             reason: str) -> AffordanceOption:
        """Create toggle fallback option"""
        
        if action_type == AffordanceType.TOGGLE_POWER:
            title = "Toggle Power"
            description = f"Toggle the {category} on or off"
        elif action_type == AffordanceType.TOGGLE_OPEN:
            title = "Toggle Door"
            description = f"Open or close the {category}"
        elif action_type == AffordanceType.TOGGLE_SCREEN:
            title = "Toggle Screen"
            description = f"Wake or sleep the {category} screen"
        else:
            title = action_type.value.replace('_', ' ').title()
            description = f"{title} {category}"
        
        return AffordanceOption(
            affordance_type=action_type,
            title=title,
            description=description,
            risk=AffordanceRisk.LOW,
            requires_confirmation=True,
            reason=reason,
            confidence=confidence,
            metadata={
                'state_aware': False,
                'fallback': True
            }
        )
    
    def get_statistics(self) -> dict:
        """Get engine statistics"""
        classifier_stats = self.classifier.get_statistics()
        
        stats = {
            'total_computations': self.total_computations,
            'total_blocked': self.total_blocked,
            'block_rate': self.total_blocked / max(1, self.total_computations),
            'classifier': classifier_stats,
            'state_aware_count': self.state_aware_count,
            'toggle_fallback_count': self.toggle_fallback_count,
            'state_aware_rate': self.state_aware_count / max(1, self.total_computations)
        }
        
        if self.use_state_inference:
            if self.state_estimator:
                stats['state_estimator'] = self.state_estimator.get_statistics()
            if self.constraint_evaluator:
                stats['constraint_evaluator'] = self.constraint_evaluator.get_statistics()
        
        return stats
    
    def reset(self):
        """Reset engine state"""
        self.last_affordance_set = None
        self.last_state_estimate = None
        self.total_computations = 0
        self.total_blocked = 0
        self.state_aware_count = 0
        self.toggle_fallback_count = 0

