# Skill Integration Checklist

This checklist covers what a new skill must register so it can:

- be parsed from LLM output
- be executed by the runtime
- participate in motive-aware planning
- be written into memory and retrieved as experience

Use this when adding a brand-new skill or when promoting an existing ad-hoc action into a first-class system skill.

## 1. Runtime Registration

The skill must be executable by the runtime.

- Add a `SkillPack` implementation under `reverie/backend_server/persona/cognitive_modules/skill_packs/`
- Register every supported verb / alias in `reverie/backend_server/persona/cognitive_modules/skill_packs/__init__.py`
- Ensure the registered key is the same string the executor will look up from `parsed_action`

If this layer is missing:

- the planner may output the action
- but `execute.py` will fail to find a matching handler in `SKILL_REGISTRY`

## 2. Parse Registration

The parser must normalize raw action text into the correct canonical skill id.

- Add the new action and aliases to `normalize_skill_id()` in `reverie/backend_server/persona/cognitive_modules/action_command_utils.py`
- Add any context-sensitive correction rules needed before passthrough

Typical examples:

- alias normalization: `treat`, `bandaging` -> `bandage`
- mistranslation repair: `consume + reading a book` -> `study`
- context repair: `gather + nap on sofa` -> `rest`

If this layer is missing:

- the action may normalize to `None`
- or drift into the wrong existing skill

## 3. Intent Registration

The skill must map into the correct intent family.

- Add or update `infer_intent_family()` in `reverie/backend_server/persona/cognitive_modules/action_command_utils.py`
- Choose the family based on what need the action is directly trying to resolve

Examples:

- `gather / consume / request food` -> `restore_satiety`
- `rest` -> `restore_stamina`
- `bandage` -> `restore_health`
- `leisure_use / daydream / sing` when used for comfort -> `restore_mood`
- `hide` -> `safety`
- `occupy` -> `status`
- `smash` -> `autonomy`
- `plan` -> `meaning`

If this layer is missing:

- the action can still execute
- but motive-aware planning, experience retrieval, and failure learning will treat it as generic or `unknown`

## 4. Motive Mapping

If the intent family is meant to represent a dominant motive, it must map back to that motive.

- Update `_dominant_motive_from_intent_family()` in `reverie/backend_server/persona/cognitive_modules/plan.py`

This is especially important for:

- non-`restore_*` families such as `safety`, `status`, `autonomy`, `meaning`
- alias families such as `social`, `recognition`, `control`, `capability`

If this layer is missing:

- action records may carry `intent_family`
- but `dominant_motive` can remain `None`

## 5. Prompt / Schema Registration

The prompt layer must know the action is valid.

- Add the action category or variant to `reverie/backend_server/persona/prompt_template/v2/action_schema.json`
- Update prompt text that enumerates allowed action categories
- Update validator allowlists in `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`
- Update translation prompt examples if needed

Common files:

- `reverie/backend_server/persona/prompt_template/v2/action_schema.json`
- `reverie/backend_server/persona/prompt_template/v2/demand_decision_v1.txt`
- `reverie/backend_server/persona/prompt_template/v2/action_translation_v1.txt`
- `reverie/backend_server/persona/prompt_template/run_gpt_prompt.py`

If this layer is missing:

- the LLM may never choose the action
- or the validator may reject it even if the LLM outputs it

## 6. Plan-to-Action Translation

If the action uses a top-level category such as `Consume`, `Rest`, or `Treat`, the planner must know how to instantiate it into runtime command data.

- Update the action materialization branch in `reverie/backend_server/persona/cognitive_modules/plan.py`
- Set:
  - `act_address`
  - `act_description`
  - `act_duration`
  - `act_event`
  - `act_command`
  - any object-side event metadata if needed

If this layer is missing:

- the prompt may choose the action category
- but the runtime will not know how to turn it into executable state

## 7. Experience Write Path

If the skill should produce reusable experience, verify it reaches the memory pipeline correctly.

- Ensure `build_action_command()` carries `intent_family`
- Ensure outcome records for the action have meaningful `skill_id`, `target`, `detail`, and `target_address`
- Verify `score_action_outcome()` can promote it when appropriate
- If the skill needs strong success/failure guidance, extend `build_experience_priority_unit()` in `reverie/backend_server/persona/cognitive_modules/action_outcomes.py`

Notes:

- ordinary episodic experience can still be written without a custom priority unit
- but strong avoid/prefer guidance usually requires custom handling in `build_experience_priority_unit()`

## 8. Constraint / Stability Integration

If the new skill resolves a critical need, it should be recognized by decision-stability and interruption logic.

Check `reverie/backend_server/persona/memory_structures/scratch.py` for:

- commit window handling
- same-family oscillation suppression
- critical need switching
- suspended-action resume rules
- "currently resolving this need" checks

This matters most for families like:

- `restore_satiety`
- `restore_stamina`
- `restore_health`
- `restore_mood`

## 9. Experience Retrieval Integration

If the new family should be used in intent memory retrieval, confirm support exists in:

- `reverie/backend_server/persona/cognitive_modules/intent_memory.py`

Check:

- `_INTENT_KEYWORDS`
- `_family_still_needs_attention()`
- `infer_memory_focus()`
- `build_intent_focal_points()`

If this layer is missing:

- experience may be stored
- but not actively retrieved when the need becomes urgent

## 10. Recommended Smoke Test

After integration, verify all of the following with a quick local test:

1. `normalize_skill_id("<alias>")` returns the intended canonical skill
2. `infer_intent_family("<skill>")` returns the intended family
3. `build_action_command(...)` contains the correct `skill_id` and `intent_family`
4. The skill name exists in `SKILL_REGISTRY`
5. If prompt-layer exposed, the action category is allowed by prompt validation
6. A sample outcome can be promoted into memory as expected

## Minimal Definition Of "Fully Integrated"

A skill is fully integrated only if all of the following are true:

- runtime can execute it
- parser can normalize it
- intent system can classify it
- prompt layer can emit it
- planner can materialize it
- memory system can store and later retrieve its outcomes

If only the first item is done, the skill is merely executable.
If only the first two are done, the skill is parseable but not motive-aware.
If all layers are done, the skill becomes a true first-class system action.
