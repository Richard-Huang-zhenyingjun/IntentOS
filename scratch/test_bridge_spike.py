import sys

import yaml

sys.path.insert(0, ".")

from src.core.system_factory import build_system
from src.interaction.confirm_bridge import run_spike_test


with open("configs/default.yaml") as f:
    cfg = yaml.safe_load(f)

cfg.setdefault("hardware", {})["backend"] = "simulator"
cfg.setdefault("eeg", {})["backend"] = "sim"
cfg.setdefault("gemini", {})["enabled"] = False
cfg.setdefault("input", {})["sources_enabled"] = ["keyboard"]
cfg.setdefault("openvla", {})["enabled"] = False
cfg.setdefault("simulator", {})["use_gui"] = False

system = build_system(cfg)

from src.intentos import IntentOSConfig, IntentOSOrchestrator
from src.kernel import ExecutionKernel
from src.planning import IntentPlanner, PlannerConfig


kernel = ExecutionKernel(
    phase2_orchestrator=system,
    phase2_auth_manager=system.auth_manager,
    invariant_checker=system.executor._invariant_checker,
)
planner = IntentPlanner(
    agent_registry=system.agent_registry,
    cfg=PlannerConfig(llm_enabled=False),
)
intentos = IntentOSOrchestrator(
    kernel=kernel,
    agent_registry=system.agent_registry,
    planner=planner,
    cfg=IntentOSConfig(),
)

try:
    result = run_spike_test(system, intentos)
    print("\nFinal result:", result)
finally:
    system.close()
