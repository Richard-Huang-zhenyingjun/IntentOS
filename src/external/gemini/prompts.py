"""
Prompt templates for Gemini scene analysis.

Design principles:
- Output MUST be JSON only (no prose, no markdown)
- Schema is minimal and strict
- Prompt includes explicit examples of valid output
- Prompt includes explicit "if unsure, return NONE"
"""
from src.interfaces.scene_summary import SceneSummary


# The actual prompt text — this IS the interface to Gemini
SCENE_ANALYSIS_PROMPT = """You are a robotic scene analyzer. Analyze the scene and decide if the robot should clean the table.

RESPOND WITH ONLY A JSON OBJECT. No markdown, no explanation, no backticks.

Valid response schemas:

If table needs cleaning:
{{"proposal_type": "CLEAN_TABLE", "object_ids": [5, 8, 12], "rationale": "brief reason"}}

If table is clean or no action needed:
{{"proposal_type": "NONE", "rationale": "brief reason"}}

Rules:
- proposal_type MUST be exactly "CLEAN_TABLE" or "NONE"
- object_ids MUST be a list of integer object IDs from the scene
- object_ids MUST only contain IDs listed in the scene description
- rationale MUST be under 200 characters
- Do NOT include any text outside the JSON object

Scene description:
{scene_text}"""


def build_scene_text(scene: SceneSummary) -> str:
    """
    Convert SceneSummary into text description for Gemini.
    
    Includes only what Gemini needs to make a proposal decision.
    Does NOT include internal system state, FSM state, or trust metrics.
    """
    lines = []
    lines.append(f"Table present: {'yes' if scene.table_id is not None else 'no'}")
    lines.append(f"Objects on table: {len(scene.objects_on_table)}")
    lines.append(f"Total objects in scene: {len(scene.objects)}")
    lines.append(f"Clutter score: {scene.clutter_score:.2f} (0=clean, 1=very messy)")
    
    if scene.objects_on_table:
        lines.append("")
        lines.append("Objects on table:")
        for obj in scene.objects_on_table:
            x, y, z = obj.pos_xyz
            category_str = f", category={obj.category}" if obj.category else ""
            lines.append(f"  - id={obj.object_id}, position=({x:.3f}, {y:.3f}, {z:.3f}){category_str}")
    
    lines.append("")
    lines.append(f"Bin zone center: ({scene.bin_zone_center[0]:.2f}, {scene.bin_zone_center[1]:.2f}, {scene.bin_zone_center[2]:.2f})")
    lines.append(f"Bin zone radius: {scene.bin_zone_radius:.2f}")
    
    return "\n".join(lines)


def build_prompt(scene: SceneSummary) -> str:
    """Build complete prompt for Gemini"""
    scene_text = build_scene_text(scene)
    return SCENE_ANALYSIS_PROMPT.format(scene_text=scene_text)


