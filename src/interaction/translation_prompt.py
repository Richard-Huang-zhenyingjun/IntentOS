"""Prompt builder for aggressive LLM intent translation."""
from __future__ import annotations


TRANSLATION_SYSTEM_PROMPT = """You translate a user's message into EXACTLY ONE \
action from the fixed list below, or the single word "unknown".

The robot can ONLY do these actions:
- "clean the table"                  (clear all loose items into the bin)
- "move the red block to the bin"
- "move the blue block to the bin"
- "move the yellow block to the bin"
- "put the tool in the tray"
- "take out of bin"                  (retrieve something from the bin)
- "yes"                              (confirm the pending plan)
- "no"                               (reject the pending plan)

YOUR JOB: people speak casually, vaguely, with slang, typos, or indirectly.
Map their meaning to the closest action above. Be generous - if a reasonable
person would understand which action they mean, output that action. Do NOT be
overly cautious. Only output "unknown" if the message truly matches none of
the actions (e.g. it's about something the robot cannot do).

Output ONLY the exact action string (or "unknown"). Nothing else.

Examples:
"yo toss the blue thing in the trash"        -> move the blue block to the bin
"get rid of the red one"                     -> move the red block to the bin
"the yellow block needs to go"               -> move the yellow block to the bin
"can you tidy everything up"                 -> clean the table
"clear off the table please"                 -> clean the table
"stick the screwdriver in the tray"          -> put the tool in the tray
"the tool goes in the tray"                  -> put the tool in the tray
"actually grab that back out of the bin"     -> take out of bin
"oops put it back"                           -> take out of bin
"yeah go for it"                             -> yes
"nah forget it"                              -> no
"what's the weather"                         -> unknown
"make me a sandwich"                         -> unknown
"paint the wall blue"                        -> unknown
"""


def build_prompt(user_text: str, last_object=None, last_action=None) -> str:
    """Assemble the prompt, injecting conversation context if present."""
    context_lines = []
    if last_object or last_action:
        readable_action = {
            "move_to_bin": "moving things to the bin",
            "put_in_tray": "putting the tool in the tray",
            "take_from_bin": "taking things out of the bin",
        }.get(last_action or "", None)
        if last_object:
            context_lines.append(f"The last object handled was the {last_object}.")
        if readable_action:
            context_lines.append(
                f"The last thing we were doing was {readable_action}."
            )
        context_lines.append(
            "If the user's message is a follow-up (like 'now the yellow one', "
            "'the red one too', 'put it back', 'same with the tool'), use this "
            "context to resolve it to a full action."
        )

    context_block = "\n" + "\n".join(context_lines) + "\n" if context_lines else ""
    return f"{TRANSLATION_SYSTEM_PROMPT}{context_block}\nUser: {user_text}\nAction:"
