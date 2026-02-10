"""
Assembled decision pipeline: Sources → Router → Filter → DecisionFrame.

This is the single object the orchestrator interacts with.
"""
import logging
from src.input.router import DecisionRouter
from src.input.filter import DecisionFilter
from src.input.types import DecisionFrame, DecisionIntent
from src.core.events import EventEmitter, EventType

logger = logging.getLogger(__name__)


class DecisionPipeline:
    """
    Complete decision processing pipeline.
    
    Orchestrator calls pipeline.tick(frame_number) and gets
    a single DecisionFrame back. Pipeline handles all source
    reading, routing, filtering, and logging internally.
    """
    
    def __init__(
        self,
        router: DecisionRouter,
        decision_filter: DecisionFilter,
        events: EventEmitter = None,
    ):
        self.router = router
        self.filter = decision_filter
        self.events = events
    
    def tick(self, frame_number: int) -> DecisionFrame:
        """
        Execute one frame of the decision pipeline.
        
        Returns:
            Filtered DecisionFrame
        """
        # Step 1: Read and route
        intent, source_type, quality, raw_intents = self.router.read_all()
        
        # Step 2: Filter
        frame = self.filter.filter(
            intent=intent,
            source_type=source_type,
            quality=quality,
            frame_number=frame_number,
            raw_intents=raw_intents,
        )
        
        # Step 3: Log significant events
        if self.events and frame.intent != DecisionIntent.NONE:
            self.events.emit(
                EventType.DECISION_RECEIVED,
                frame=frame_number,
                data={
                    'intent': frame.intent.value,
                    'source': frame.source_type.value,
                    'quality': frame.quality,
                    'filter_action': frame.filter_action.value,
                    'filter_reason': frame.filter_reason,
                    'raw_intents': raw_intents,
                }
            )
        
        return frame


