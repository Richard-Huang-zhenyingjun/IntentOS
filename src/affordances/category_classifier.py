"""Category Classifier - Convert detector labels to object categories."""

from dataclasses import dataclass
from typing import Tuple, Optional, List
from affordances.affordance_schema import ObjectCategory


@dataclass
class CategoryResult:
    """Result of category classification"""
    category: ObjectCategory
    confidence: float  # 0.0-1.0
    reason: str  # Human-readable explanation
    raw_label: str  # Original detector label
    
    # Metadata for logging
    method: str  # "keyword_match", "ML_classifier", etc.
    alternatives: List[ObjectCategory] = None  # Other possible categories
    
    def __post_init__(self):
        """Initialize alternatives if None"""
        if self.alternatives is None:
            self.alternatives = []


class CategoryClassifier:
    """
    Convert detector labels to object categories
    
    Week 3: Simple keyword matching (deterministic, fast)
    Week 6+: Can be replaced with ML classifier
    
    Design principle: 
    - Conservative (prefer UNKNOWN over wrong guess)
    - Transparent (always explain reasoning)
    - Extensible (easy to add new categories)
    """
    
    def __init__(self, config: dict):
        self.config = config
        
        # Confidence thresholds
        self.min_confidence = config.get('min_category_confidence', 0.5)
        self.high_confidence_threshold = config.get('high_confidence_threshold', 0.9)
        
        # Keyword mapping (category → list of keywords)
        self.keyword_map = self._build_keyword_map()
        
        # Statistics
        self.total_classifications = 0
        self.unknown_count = 0
    
    def _build_keyword_map(self) -> dict:
        """
        Build keyword mapping from config or defaults
        
        Format: {ObjectCategory: [list of keywords]}
        """
        # Default mappings
        default_map = {
            ObjectCategory.LAMP: ['lamp', 'light', 'bulb', 'lantern', 'torch'],
            ObjectCategory.DOOR: ['door', 'gate', 'entrance', 'doorway'],
            ObjectCategory.CUP: ['cup', 'mug', 'glass', 'tumbler', 'chalice'],
            ObjectCategory.PHONE: ['phone', 'mobile', 'smartphone', 'cellphone', 'iphone', 'android'],
            ObjectCategory.BOOK: ['book', 'novel', 'textbook', 'manual', 'magazine'],
            ObjectCategory.BOTTLE: ['bottle', 'flask', 'container', 'jar'],
        }
        
        # Allow config override
        custom_map = self.config.get('category_keywords', {})
        
        # Merge (custom overrides default)
        final_map = default_map.copy()
        for cat_str, keywords in custom_map.items():
            category = ObjectCategory.from_string(cat_str)
            if category != ObjectCategory.UNKNOWN:
                final_map[category] = keywords
        
        return final_map
    
    def classify(self, 
                 tracked_label: str,
                 bbox: Tuple[int, int, int, int],
                 confidence: float,
                 frame: Optional = None) -> CategoryResult:
        """
        Classify object into category
        
        Args:
            tracked_label: Label from object detector (Week 1)
            bbox: Bounding box (x, y, w, h)
            confidence: Detection confidence from tracker
            frame: Optional frame for visual features (unused in Week 3)
        
        Returns:
            CategoryResult with category and confidence
        """
        self.total_classifications += 1
        
        # Normalize label
        label_lower = tracked_label.lower().strip()
        
        # Try keyword matching
        matches = []
        for category, keywords in self.keyword_map.items():
            for keyword in keywords:
                if keyword in label_lower:
                    # Calculate match confidence
                    # Exact match = high confidence
                    # Partial match = medium confidence
                    if label_lower == keyword:
                        match_conf = 0.95
                        match_type = "exact"
                    elif label_lower.startswith(keyword) or label_lower.endswith(keyword):
                        match_conf = 0.85
                        match_type = "prefix/suffix"
                    else:
                        match_conf = 0.70
                        match_type = "substring"
                    
                    # Factor in detection confidence
                    combined_conf = match_conf * confidence
                    
                    matches.append({
                        'category': category,
                        'confidence': combined_conf,
                        'keyword': keyword,
                        'match_type': match_type
                    })
        
        # No matches → UNKNOWN
        if len(matches) == 0:
            self.unknown_count += 1
            return CategoryResult(
                category=ObjectCategory.UNKNOWN,
                confidence=0.0,
                reason=f"No keyword match for '{tracked_label}'",
                raw_label=tracked_label,
                method="keyword_match",
                alternatives=[]
            )
        
        # Sort by confidence
        matches.sort(key=lambda m: m['confidence'], reverse=True)
        best_match = matches[0]
        
        # Check if confident enough
        if best_match['confidence'] < self.min_confidence:
            return CategoryResult(
                category=ObjectCategory.UNKNOWN,
                confidence=best_match['confidence'],
                reason=f"Low confidence ({best_match['confidence']:.2f}) for '{tracked_label}'",
                raw_label=tracked_label,
                method="keyword_match",
                alternatives=[m['category'] for m in matches[:3]]
            )
        
        # Success
        return CategoryResult(
            category=best_match['category'],
            confidence=best_match['confidence'],
            reason=f"Matched keyword '{best_match['keyword']}' ({best_match['match_type']})",
            raw_label=tracked_label,
            method="keyword_match",
            alternatives=[m['category'] for m in matches[1:3]]  # Top 2 alternatives
        )
    
    def get_statistics(self) -> dict:
        """Return classification statistics"""
        return {
            'total_classifications': self.total_classifications,
            'unknown_count': self.unknown_count,
            'unknown_rate': self.unknown_count / max(1, self.total_classifications)
        }

