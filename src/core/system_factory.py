"""
Factory that assembles the complete system from config.

This is the ONLY place where concrete implementations are imported
and wired together. The orchestrator never knows what's behind the interfaces.
"""
from src.core.orchestrator import Orchestrator
from src.intelligence.proposer_registry import ProposerRegistry
from src.intelligence.proposer_heuristic import HeuristicProposer
from src.intelligence.proposer_gemini import GeminiProposer
from src.external.openvla.proposer_openvla import OpenVLAProposer
from src.external.openvla.action_translator_fake import FakeActionTranslator
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
from src.input.eeg.decision_source import EEGDecisionSource
from typing import Optional
import logging
import os
import yaml
import numpy as np

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

    # Week 3: OpenVLA proposer receives simulator camera provider when available.
    openvla_proposer = _build_openvla_proposer(config=config, camera_provider=sim)
    if openvla_proposer is not None:
        openvla_priority = config.get("openvla", {}).get("priority", 15)
        registry.register("openvla", openvla_proposer, priority=openvla_priority)
        print(f"[FACTORY] OpenVLA proposer registered (priority={openvla_priority})")
    
    # Week 4: Gemini proposer (if enabled)
    gemini_cfg = config.get('gemini', {})
    gemini_client = None
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
    action_translator = _build_action_translator(sim)
    hardware_bridge = _build_hardware_bridge(config, sim)
    executor = PrimitiveExecutor(
        controller,
        grasp,
        action_translator=action_translator,
        hardware_bridge=hardware_bridge,
    )
    from src.agents import AgentRegistry, ArmAgent

    arm_agent = ArmAgent(
        primitive_executor=executor,
        hardware_bridge=hardware_bridge,
    )
    agent_registry = AgentRegistry()
    agent_registry.register(arm_agent)
    _register_configured_agents(config, agent_registry)
    agent_coordinator = _build_agent_coordinator(agent_registry)
    
    # 9. Decision pipeline (Week 5)
    decision_pipeline = _build_decision_pipeline(config, events)
    
    # 10. Assemble orchestrator with injected dependencies
    orchestrator = Orchestrator(
        config=config,
        decision_pipeline=decision_pipeline,
        sim=sim,
        proposer_registry=registry,
        compiler=compiler,
        executor=executor,
        world_builder=world_builder,
        events=events  # Week 7: Event emitter for auth/trust/autonomy events
    )
    orchestrator.agent_registry = agent_registry
    orchestrator.arm_agent = arm_agent
    orchestrator.agent_coordinator = agent_coordinator
    orchestrator.gemini = gemini_client
    _attach_intentos_layer(
        system=orchestrator,
        config=config,
        agent_registry=agent_registry,
        agent_coordinator=agent_coordinator,
        gemini_adapter=gemini_client,
    )
    return orchestrator


def _register_configured_agents(config: dict, agent_registry) -> None:
    """Register optional IntentOS agents from config."""
    agents_cfg = config.get("agents", {})
    sim_cfg = agents_cfg.get("sim_agent", {})

    if not sim_cfg.get("enabled", False):
        return

    from src.agents import SimAgent, SimAgentConfig

    cfg = SimAgentConfig(
        success_rates=sim_cfg.get("success_rates", {}),
        timing_s=sim_cfg.get("timing_s"),
        seed=int(sim_cfg.get("seed", 42)),
        simulate_delays=bool(sim_cfg.get("simulate_delays", True)),
    )
    sim_agent = SimAgent(agent_id="sim_agent", cfg=cfg)
    agent_registry.register(sim_agent)
    logger.info("SimAgent registered (second agent enabled)")


def _build_agent_coordinator(agent_registry):
    """Build IntentOS coordinator from registered agents."""
    from src.coordination import AgentCoordinator, CoordinatorConfig

    return AgentCoordinator(
        agent_registry=agent_registry,
        cfg=CoordinatorConfig(
            max_parallel_agents=len(agent_registry.all_ids()),
        ),
    )


def _attach_intentos_layer(
    system: Orchestrator,
    config: dict,
    agent_registry,
    agent_coordinator=None,
    gemini_adapter=None,
) -> None:
    """Attach IntentOS 3B layer without changing the Phase 2 return object."""
    from src.intentos import IntentOSConfig, IntentOSOrchestrator
    from src.kernel import ExecutionKernel
    from src.planning import IntentPlanner, PlannerConfig

    gemini_cfg = config.get("gemini", {})
    timeout_s = gemini_cfg.get("timeout_sec")
    if timeout_s is None and "timeout_ms" in gemini_cfg:
        timeout_s = float(gemini_cfg["timeout_ms"]) / 1000.0
    if timeout_s is None:
        timeout_s = 10.0

    planner_cfg = PlannerConfig(
        llm_enabled=bool(gemini_cfg.get("enabled", False)),
        llm_timeout_s=float(timeout_s),
    )

    planner = IntentPlanner(
        agent_registry=agent_registry,
        cfg=planner_cfg,
        gemini_adapter=gemini_adapter if planner_cfg.llm_enabled else None,
    )
    execution_kernel = ExecutionKernel(system)
    intentos = IntentOSOrchestrator(
        kernel=execution_kernel,
        agent_registry=agent_registry,
        planner=planner,
        cfg=IntentOSConfig(planner=planner_cfg),
        coordinator=agent_coordinator,
    )

    system.execution_kernel = execution_kernel
    system.intentos_planner = planner
    system.intentos = intentos


def _build_gemini_client(config: dict):
    """Build appropriate Gemini client based on config"""
    gemini_cfg = config.get('gemini', {})
    
    use_fake = gemini_cfg.get('use_fake_client', False)
    
    if use_fake:
        from src.external.gemini.client_fake import FakeGeminiClient
        print("[FACTORY] Using FAKE Gemini client")
        return FakeGeminiClient()
    else:
        if not os.environ.get("GEMINI_API_KEY"):
            logger.warning(
                "Gemini enabled but GEMINI_API_KEY is not set; "
                "calls will fall back to clarification."
            )
        from src.external.gemini.client import RealGeminiClient
        return RealGeminiClient(config)


def _build_openvla_proposer(config: dict, camera_provider=None) -> Optional[OpenVLAProposer]:
    """Build OpenVLA proposer from config (fake by default for CPU/CI safety)."""
    openvla_cfg = config.get("openvla", {})
    if not openvla_cfg.get("enabled", False):
        logger.info("[FACTORY] OpenVLA proposer disabled")
        return None

    backend = openvla_cfg.get("backend")
    if backend is None:
        backend = "fake" if openvla_cfg.get("use_fake", True) else "real"

    if backend == "fake":
        from src.external.openvla.adapter import OpenVLAAdapter

        adapter = OpenVLAAdapter(backend="fake")
        adapter.load_model()
        print("[FACTORY] Using FAKE OpenVLA adapter")
    elif backend == "real":
        try:
            from src.external.openvla.adapter import OpenVLAAdapter

            adapter = OpenVLAAdapter(
                backend="real",
                device=openvla_cfg.get("device", "auto"),
                dtype=openvla_cfg.get("dtype", openvla_cfg.get("torch_dtype", "bfloat16")),
            )
            adapter.load_model()
            print("[FACTORY] Using REAL OpenVLA adapter")
        except Exception as exc:
            logger.warning("[FACTORY] OpenVLA real adapter failed (%s); falling back to fake", exc)
            from src.external.openvla.adapter import OpenVLAAdapter

            adapter = OpenVLAAdapter(backend="fake")
            adapter.load_model()
            print("[FACTORY] Using FAKE OpenVLA adapter (fallback)")
    else:
        logger.warning("[FACTORY] Unknown OpenVLA backend: %s", backend)
        return None

    return OpenVLAProposer(
        openvla_adapter=adapter,
        camera_provider=camera_provider,
        camera_name=openvla_cfg.get("camera_name", "overhead"),
        priority=openvla_cfg.get("priority", 15),
        enabled=True,
    )


def _build_action_translator(sim):
    """
    Build action translator for OpenVLA trajectory primitives.

    If running with a MuJoCo backend exposing _model/_data, use real translator.
    Otherwise use fake translator for PyBullet/test environments.
    """
    model = getattr(sim, "_model", None)
    data = getattr(sim, "_data", None)
    if model is not None and data is not None:
        try:
            from src.external.openvla.action_translator import ActionTranslator

            print("[FACTORY] Using REAL ActionTranslator")
            return ActionTranslator(model=model, data=data, ee_site_name="end_effector")
        except Exception as exc:
            logger.warning("[FACTORY] Real ActionTranslator failed (%s); falling back to fake", exc)

    print("[FACTORY] Using FAKE ActionTranslator")
    return FakeActionTranslator()


def _build_hardware_bridge(config: dict, sim):
    """
    Build optional sim-to-real hardware bridge.

    Default PyBullet simulation keeps using RobotController directly. A bridge is
    created only for explicit real hardware, or for MuJoCo backends exposing
    _model/_data.
    """
    hardware_cfg = config.get("hardware", {})
    backend_name = hardware_cfg.get("backend", "simulator")

    joint_limits = _load_hardware_joint_limits(hardware_cfg)

    if backend_name in ("hardware", "real"):
        from src.execution.hardware_bridge import HardwareBridge

        arm_controller = _build_arm_controller(config)
        if not hardware_cfg.get("dry_run", False) and hardware_cfg.get("real", {}).get("auto_connect", True):
            arm_controller.connect()
        print("[FACTORY] Using HARDWARE arm bridge")
        return HardwareBridge(_HardwareArmBackendAdapter(arm_controller), joint_limits=joint_limits)

    if backend_name in ("simulator", "sim"):
        model = getattr(sim, "_model", None)
        data = getattr(sim, "_data", None)
        if model is not None and data is not None:
            from src.execution.hardware_bridge import HardwareBridge, SimBackend

            print("[FACTORY] Using SIM hardware bridge")
            return HardwareBridge(SimBackend(model, data), joint_limits=joint_limits)
        return None

    logger.warning("[FACTORY] Unknown hardware backend: %s", backend_name)
    return None


def _build_arm_controller(cfg: dict):
    """Build real-arm controller from config. Simulator backend returns None."""
    hw_cfg = cfg.get("hardware", {})
    backend = hw_cfg.get("backend", "simulator")

    if backend in ("simulator", "sim"):
        return None

    if backend in ("hardware", "real"):
        from src.robot.hardware.arm_controller import HardwareArmController
        from src.robot.hardware.serial_controller import SerialConfig, SerialController

        real_cfg = hw_cfg.get("real", {})
        dry_run = hw_cfg.get("dry_run", False)

        if dry_run:
            from src.robot.hardware.serial_controller_fake import FakeSerialController

            serial = FakeSerialController()
            serial.connect()
            logger.info("Hardware arm: DRY RUN mode (fake serial controller)")
        else:
            serial_cfg = SerialConfig(
                port=real_cfg["port"],
                baud=int(real_cfg.get("baud", 115200)),
                arduino_reset_delay_s=float(real_cfg.get("arduino_reset_delay_s", 2.0)),
            )
            serial = SerialController(serial_cfg)

        return HardwareArmController.from_config(cfg, serial_ctrl=serial)

    raise ValueError(
        f"Unknown hardware backend: {backend!r}. Expected: simulator | hardware"
    )


class _HardwareArmBackendAdapter:
    """Adapter from HardwareArmController to HardwareBridge backend protocol."""

    def __init__(self, controller):
        self._controller = controller

    def apply_joints(self, commands) -> None:
        from src.robot.hardware.arm_controller import N_JOINTS

        joint_positions = np.zeros(N_JOINTS, dtype=float)
        for command in commands:
            if command.joint_idx < N_JOINTS:
                joint_positions[command.joint_idx] = command.angle_rad
        if not self._controller.move_to_joint_positions(joint_positions):
            raise RuntimeError("HardwareArmController rejected joint command")

    def emergency_stop(self) -> None:
        self._controller.emergency_stop()

    def is_connected(self) -> bool:
        serial = getattr(self._controller, "_serial", None)
        return bool(getattr(serial, "is_connected", False))


def _load_hardware_joint_limits(hardware_cfg: dict) -> list[tuple[float, float]]:
    limits = hardware_cfg.get("joint_limits_rad")
    limits_are_degrees = False
    if limits is None and hardware_cfg.get("joint_limits"):
        limits = hardware_cfg.get("joint_limits")
        limits_are_degrees = True
    if limits is None and hardware_cfg.get("config_path"):
        try:
            with open(hardware_cfg["config_path"], "r") as f:
                loaded = yaml.safe_load(f) or {}
            nested = loaded.get("hardware", loaded)
            limits = nested.get("joint_limits_rad")
            if limits is None and nested.get("joint_limits"):
                limits = nested.get("joint_limits")
                limits_are_degrees = True
        except FileNotFoundError:
            logger.warning("[FACTORY] Hardware config not found: %s", hardware_cfg["config_path"])
    if not limits:
        return []
    if limits_are_degrees:
        return [(float(np.deg2rad(lo)), float(np.deg2rad(hi))) for lo, hi in limits]
    return [(float(lo), float(hi)) for lo, hi in limits]


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
    elif backend == 'simulated':
        from src.input.eeg.eeg_source_simulated import SimulatedEEGSource
        device = SimulatedEEGSource(config)
        print("[FACTORY] Using simulated EEG source")
    elif backend == 'brainlink':
        from src.input.eeg.device_brainlink import BrainLinkDevice
        device = BrainLinkDevice(config)
        print("[FACTORY] Using BrainLink device")
    else:
        logger.warning(f"[FACTORY] Unknown EEG backend: {backend}")
        return None
    
    return EEGDecisionSource(source=device, config=config)
