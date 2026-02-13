"""
Factory that assembles the complete system from config.

This is the ONLY place where concrete implementations are imported
and wired together. The orchestrator never knows what's behind the interfaces.
"""
from src.core.orchestrator import Orchestrator
from src.intelligence.proposer_registry import ProposerRegistry
from src.intelligence.proposer_heuristic import HeuristicProposer
from src.intelligence.proposer_gemini import GeminiProposer
from src.intelligence.scene_summarizer import SceneSummarizer
from src.planning.plan_compiler import PlanCompiler
from src.execution.primitive_executor import PrimitiveExecutor
from src.worlds.messy_table_world import build_messy_table
from src.robot.simulator import RobotSimulator
from src.robot.controller import RobotController
from src.robot.grasp import GraspController
from src.robot.joint_discovery import discover_gripper_joints

# Week 5: Decision pipeline
from src.input.pipeline import DecisionPipeline
from src.input.router import DecisionRouter
from src.input.filter import DecisionFilter
from src.input.policies import DecisionPolicy
from src.input.source_keyboard import KeyboardSource
from src.input.source_eeg_mock import MockEEGSource

# Week 6: Real EEG source
from src.input.eeg.eeg_source import EEGDecisionSource
from typing import Optional
import logging
import yaml

logger = logging.getLogger(__name__)

# Week 4: Event system (optional)
try:
    from src.core.events import EventEmitter
except ImportError:
    EventEmitter = None


def load_config(config_path: str) -> dict:
    """Load YAML config from disk."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def build_system(config: dict) -> Orchestrator:
    """
    Assemble the complete system from config.
    
    This is the composition root - the only place where
    concrete types are known and wired together.
    
    Week 3: All concrete implementations are created here.
    Orchestrator receives only interfaces and abstract dependencies.
    """
    # 1. Hardware layer (robot simulator)
    # Use headless mode for testing (can be overridden in config)
    use_gui = config.get('simulator', {}).get('use_gui', False)
    sim = RobotSimulator(config, use_gui=use_gui)
    
    # 2. Robot controllers (created here, passed to executor)
    controller = RobotController(config, sim)
    gripper_joints = discover_gripper_joints(sim.robot_id)
    if len(gripper_joints) < 2:
        raise RuntimeError("Gripper joints not found in URDF - check gripper attachment")
    print(f"[FACTORY] Gripper joints: {gripper_joints}")
    grasp = GraspController(sim, config.get("gripper", {}))
    
    # 3. Scene summarizer (Week 3: extracted as class)
    scene_summarizer = SceneSummarizer(config)
    
    # 4. World builder function (injected into orchestrator)
    # The orchestrator will call this to build the world
    world_builder = build_messy_table
    
    # 5. Event emitter (Week 4: for Gemini logging)
    events_enabled = config.get('logging', {}).get('events_enabled', False)
    events_path = config.get('logging', {}).get('events_path')
    events = EventEmitter(enabled=events_enabled, log_path=events_path) if EventEmitter else None
    
    # 6. Proposer registry (with fallback)
    registry = ProposerRegistry()
    heuristic = HeuristicProposer(config)
    registry.register("heuristic", heuristic, priority=0, is_fallback=True)
    
    # Week 4: Gemini proposer (if enabled)
    gemini_cfg = config.get('gemini', {})
    if gemini_cfg.get('enabled', False):
        gemini_client = _build_gemini_client(config)
        gemini_proposer = GeminiProposer(
            client=gemini_client,
            config=config,
            events=events
        )
        registry.register("gemini", gemini_proposer, priority=10)
        print("[FACTORY] Gemini proposer registered (priority=10)")
    else:
        print("[FACTORY] Gemini disabled, using heuristic only")
    
    # Set execution-phase gating
    blocked = set(config.get('proposers', {}).get('blocked_states', ['executing']))
    registry.set_blocked_states(blocked)
    
    # 7. Plan compiler (implements PlanCompilerBase interface)
    compiler = PlanCompiler(config)
    
    # 8. Primitive executor (concrete implementation)
    executor = PrimitiveExecutor(controller, grasp)
    
    # 9. Decision pipeline (Week 5)
    decision_pipeline = _build_decision_pipeline(config, events)
    
    # 10. Assemble orchestrator with injected dependencies
    return Orchestrator(
        config=config,
        decision_pipeline=decision_pipeline,
        sim=sim,
        proposer_registry=registry,
        compiler=compiler,
        executor=executor,
        world_builder=world_builder,
        events=events  # Week 7: Event emitter for auth/trust/autonomy events
    )


def _build_gemini_client(config: dict):
    """Build appropriate Gemini client based on config"""
    gemini_cfg = config.get('gemini', {})
    
    use_fake = gemini_cfg.get('use_fake_client', False)
    
    if use_fake:
        from src.external.gemini.client_fake import FakeGeminiClient
        print("[FACTORY] Using FAKE Gemini client")
        return FakeGeminiClient()
    else:
        from src.external.gemini.client import RealGeminiClient
        return RealGeminiClient(config)


def _build_decision_pipeline(config: dict, events: EventEmitter) -> DecisionPipeline:
    """Build decision pipeline from config"""
    policy = DecisionPolicy.from_config(config)
    
    # Build router
    router = DecisionRouter(policy)
    
    # Register sources based on config
    sources_enabled = config.get('input', {}).get('sources_enabled', ['keyboard'])
    
    if 'keyboard' in sources_enabled:
        keyboard = KeyboardSource(config)
        router.register_source('keyboard', keyboard)
        print("[FACTORY] Registered keyboard source")
    
    # Week 6: Real EEG source (if enabled)
    if 'eeg' in sources_enabled:
        eeg_source = _build_eeg_source(config)
        if eeg_source:
            eeg_source.start()  # Begin acquisition
            router.register_source('eeg', eeg_source)
            print("[FACTORY] Registered real EEG source")
        else:
            print("[FACTORY] EEG enabled but source unavailable, skipping")
    
    # Week 5: Mock EEG source (for testing without hardware)
    if 'mock_eeg' in sources_enabled:
        mock_eeg = MockEEGSource(config)
        router.register_source('eeg', mock_eeg)
        print("[FACTORY] Registered mock EEG source")
    
    # Build filter
    decision_filter = DecisionFilter(config)
    
    # Assemble pipeline
    return DecisionPipeline(
        router=router,
        decision_filter=decision_filter,
        events=events,
    )


def _build_eeg_source(config: dict) -> Optional[EEGDecisionSource]:
    """Build EEG source from config"""
    eeg_cfg = config.get('eeg', {})
    
    if not eeg_cfg.get('enabled', False):
        return None
    
    backend = eeg_cfg.get('backend', 'brainlink')
    
    if backend == 'replay':
        from src.input.eeg.device_replay import ReplayDevice
        replay_file = eeg_cfg.get('replay_file', 'tests/fixtures/eeg/synthetic_session.csv')
        device = ReplayDevice(replay_file, real_time=eeg_cfg.get('replay_realtime', False))
        print(f"[FACTORY] Using EEG replay device: {replay_file}")
    elif backend == 'brainlink':
        from src.input.eeg.device_brainlink import BrainLinkDevice
        device = BrainLinkDevice(config)
        print("[FACTORY] Using BrainLink device")
    else:
        logger.warning(f"[FACTORY] Unknown EEG backend: {backend}")
        return None
    
    return EEGDecisionSource(device=device, config=config)
