# Restore Satiety Loop Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `gather/consume refrigerator` re-planning loops after a successful food pickup when satiety is already healthy, without replacing LLM decision-making with hardcoded behavior rules.

**Architecture:** Fix the semantic bug where `last_decision_signature` is treated as an active action after the action has already completed, then tighten intent-memory fallback so recent `restore_satiety` activity only biases retrieval when satiety is still genuinely low. Add a narrow execution-layer safety net in `GatherSkillPack.can_execute()` so a persona standing on the same refrigerator with food already in inventory cannot burn another 20s-40s plan cycle on redundant `gather`.

**Tech Stack:** Python 3, `unittest`, existing persona scratch state, intent-memory retrieval, skill execution prechecks, JSONL step/debug logs.

---

### Task 1: Fix Active Signature Semantics

**Files:**
- Create: `g:\generative_agents\test\test_restore_satiety_loop_guard.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\memory_structures\scratch.py`

- [ ] **Step 1: Write the failing test**

```python
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from persona.memory_structures.scratch import Scratch


class RestoreSatietyLoopGuardTests(unittest.TestCase):
    def test_completed_action_is_not_reported_as_active_signature(self):
        scratch = Scratch("")
        scratch.last_decision_signature = {
            "intent_family": "restore_satiety",
            "skill_id": "gather",
            "target": "refrigerator",
        }
        scratch.act_command = None
        scratch.act_event = None
        scratch.act_address = None
        scratch.planned_path = []

        self.assertIsNone(scratch.get_active_decision_signature())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test.test_restore_satiety_loop_guard.RestoreSatietyLoopGuardTests.test_completed_action_is_not_reported_as_active_signature -v`

Expected: FAIL because `get_active_decision_signature()` currently returns `last_decision_signature` even when there is no active action.

- [ ] **Step 3: Write minimal implementation**

Update `g:\generative_agents\reverie\backend_server\persona\memory_structures\scratch.py` so `get_active_decision_signature()` only reports a currently active action, not the most recent accepted decision:

```python
def get_active_decision_signature(self):
    if not (self.act_command or self.act_event or self.act_address):
        return None
    return build_decision_signature(
        self.act_command,
        action_event=self.act_event,
        action_description=self.act_description,
        action_address=self.act_address,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest test.test_restore_satiety_loop_guard.RestoreSatietyLoopGuardTests.test_completed_action_is_not_reported_as_active_signature -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add test/test_restore_satiety_loop_guard.py reverie/backend_server/persona/memory_structures/scratch.py
git commit -m "fix: stop completed satiety actions from masquerading as active"
```

### Task 2: Stop False Restore-Satiety Memory Focus

**Files:**
- Modify: `g:\generative_agents\test\test_restore_satiety_loop_guard.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\intent_memory.py`

- [ ] **Step 1: Write the failing test**

Append this test to `g:\generative_agents\test\test_restore_satiety_loop_guard.py`:

```python
from types import SimpleNamespace
import persona.cognitive_modules.intent_memory as intent_memory


class RestoreSatietyLoopGuardTests(unittest.TestCase):
    def test_recent_gather_does_not_force_food_memory_when_satiety_is_healthy(self):
        persona = SimpleNamespace(
            scratch=SimpleNamespace(
                satiety=78.3,
                stamina=98.8,
                health=100.0,
                mood=99.7,
                inventory={"apple": 1},
                recent_completed_action_signature={
                    "intent_family": "restore_satiety",
                    "skill_id": "gather",
                    "target": "refrigerator",
                },
            )
        )

        result = intent_memory.infer_memory_focus(persona, action_signature={})
        self.assertIsNone(result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test.test_restore_satiety_loop_guard.RestoreSatietyLoopGuardTests.test_recent_gather_does_not_force_food_memory_when_satiety_is_healthy -v`

Expected: FAIL because `infer_memory_focus()` currently inherits `recent_completed_action_signature.intent_family == "restore_satiety"` regardless of the current satiety value.

- [ ] **Step 3: Write minimal implementation**

Add a small helper and gate the recent-family fallback in `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\intent_memory.py`:

```python
def _family_still_needs_attention(persona, intent_family):
  thresholds = _ATTRIBUTE_PRIORITY_THRESHOLDS
  if intent_family == "restore_satiety":
    return getattr(persona.scratch, "satiety", 100.0) < thresholds["satiety"]
  if intent_family == "restore_stamina":
    return getattr(persona.scratch, "stamina", 100.0) < thresholds["stamina"]
  if intent_family == "restore_health":
    return getattr(persona.scratch, "health", 100.0) < thresholds["health"]
  if intent_family == "restore_mood":
    return getattr(persona.scratch, "mood", 100.0) < thresholds["mood"]
  return False


def infer_memory_focus(persona, action_signature=None):
  signature = action_signature or {}
  intent_family = signature.get("intent_family")
  if intent_family in {"restore_satiety", "restore_stamina", "restore_health", "restore_mood"}:
    return intent_family

  recent_signature = getattr(persona.scratch, "recent_completed_action_signature", None) or {}
  recent_family = recent_signature.get("intent_family")

  if getattr(persona.scratch, "satiety", 100.0) < 40.0:
    return "restore_satiety"
  if getattr(persona.scratch, "stamina", 100.0) < 40.0:
    return "restore_stamina"
  if getattr(persona.scratch, "health", 100.0) < 70.0:
    return "restore_health"
  if getattr(persona.scratch, "mood", 100.0) < 50.0:
    return "restore_mood"
  if recent_family in {"restore_satiety", "restore_stamina", "restore_health", "restore_mood"}:
    if _family_still_needs_attention(persona, recent_family):
      return recent_family
  return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest test.test_restore_satiety_loop_guard.RestoreSatietyLoopGuardTests.test_completed_action_is_not_reported_as_active_signature test.test_restore_satiety_loop_guard.RestoreSatietyLoopGuardTests.test_recent_gather_does_not_force_food_memory_when_satiety_is_healthy -v`

Expected: PASS for both tests

- [ ] **Step 5: Commit**

```bash
git add test/test_restore_satiety_loop_guard.py reverie/backend_server/persona/cognitive_modules/intent_memory.py
git commit -m "fix: prevent healthy satiety states from reloading food memories"
```

### Task 3: Add A Narrow Gather Safety Net

**Files:**
- Modify: `g:\generative_agents\test\test_restore_satiety_loop_guard.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\gather_skill.py`

- [ ] **Step 1: Write the failing test**

Append this test to `g:\generative_agents\test\test_restore_satiety_loop_guard.py`:

```python
from types import SimpleNamespace
from persona.cognitive_modules.skill_packs.gather_skill import GatherSkillPack


class RestoreSatietyLoopGuardTests(unittest.TestCase):
    def test_recent_healthy_refrigerator_gather_is_blocked(self):
        maze = SimpleNamespace(
            get_tile_path=lambda tile, key: "refrigerator" if key == "game_object" else None
        )
        scratch = SimpleNamespace(
            curr_tile=[122, 45],
            satiety=78.3,
            inventory={"apple": 1},
            curr_step=20,
            recent_completed_action_step=19,
            recent_completed_action_signature={
                "intent_family": "restore_satiety",
                "skill_id": "gather",
                "target": "refrigerator",
            },
            is_recent_duplicate_action=lambda signature, within_steps=2: False,
            act_address="the Ville:Dorm for Oak Hill College:kitchen:refrigerator",
        )
        persona = SimpleNamespace(name="Maria Lopez", scratch=scratch, s_mem=SimpleNamespace(find_nearest_object=lambda target: None))

        result = GatherSkillPack().can_execute(persona, "refrigerator", maze)
        self.assertFalse(result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test.test_restore_satiety_loop_guard.RestoreSatietyLoopGuardTests.test_recent_healthy_refrigerator_gather_is_blocked -v`

Expected: FAIL because `GatherSkillPack.can_execute()` currently returns `True` whenever the persona is standing on a valid refrigerator tile.

- [ ] **Step 3: Write minimal implementation**

Insert a targeted precheck near the top of `GatherSkillPack.can_execute()` in `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\gather_skill.py`:

```python
inventory = getattr(persona.scratch, "inventory", {}) or {}
recent_signature = getattr(persona.scratch, "recent_completed_action_signature", None) or {}
recent_step = getattr(persona.scratch, "recent_completed_action_step", None)
curr_step = getattr(persona.scratch, "curr_step", None)
satiety = float(getattr(persona.scratch, "satiety", 100.0))
has_food_inventory = any(v > 0 for v in inventory.values())

if (
    clean_target == "refrigerator"
    and has_food_inventory
    and satiety >= 40.0
    and recent_signature == {
        "intent_family": "restore_satiety",
        "skill_id": "gather",
        "target": "refrigerator",
    }
    and recent_step is not None
    and curr_step is not None
    and curr_step - recent_step <= 6
):
    append_debug_log(
        "skill_execution_debug.jsonl",
        {
            "persona": persona.name,
            "skill": "gather",
            "event": "can_execute",
            "result": False,
            "reason": "recent_healthy_refrigerator_gather",
            "target": target,
            "clean_target": clean_target,
            "satiety": satiety,
            "inventory": inventory,
            "recent_completed_action_signature": recent_signature,
        }
    )
    return False
```

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest test.test_restore_satiety_loop_guard -v`

Expected: PASS for all three loop-guard tests

- [ ] **Step 5: Commit**

```bash
git add test/test_restore_satiety_loop_guard.py reverie/backend_server/persona/cognitive_modules/skill_packs/gather_skill.py
git commit -m "fix: block redundant healthy refrigerator gathers"
```

### Task 4: Verify With Existing Timing Logs

**Files:**
- Read: `g:\generative_agents\logs\step_timing.jsonl`
- Read: `g:\generative_agents\logs\decision_stability.jsonl`
- Read: `g:\generative_agents\logs\skill_execution_debug.jsonl`

- [ ] **Step 1: Run the focused unit suite**

Run: `python -m unittest test.test_restore_satiety_loop_guard test.test_intent_memory_retrieval -v`

Expected: PASS

- [ ] **Step 2: Reproduce the refrigerator scenario**

Run the same backend simulation flow used for the earlier repro and let it advance through the first refrigerator pickup after satiety recovers above 40.

Expected:
- No new `decide_demand_action_timing` entries with `restore_satiety` and `total_ms > 10000` immediately after a healthy `gather refrigerator`
- No repeated `skill_blocked` / `recent_duplicate_action` lines every ~20-40 seconds for the same persona and refrigerator target

- [ ] **Step 3: Check logs with exact filters**

Run:

```bash
Select-String -Path "g:\generative_agents\logs\step_timing.jsonl" -Pattern '"event": "decide_demand_action_timing"|restore_satiety|slow'
```

Run:

```bash
Select-String -Path "g:\generative_agents\logs\decision_stability.jsonl" -Pattern 'switch_blocked|same_family_internal_oscillation|post_consume_hold'
```

Run:

```bash
Select-String -Path "g:\generative_agents\logs\skill_execution_debug.jsonl" -Pattern 'recent_healthy_refrigerator_gather|recent_duplicate_action|followup_consume_scheduled'
```

Expected:
- Healthy refrigerator pickups do not produce another 20s-40s `restore_satiety` plan on the next few steps
- `recent_healthy_refrigerator_gather` appears only as a narrow safety block, not as a frequent steady-state event

- [ ] **Step 4: Commit**

```bash
git add test/test_restore_satiety_loop_guard.py reverie/backend_server/persona/memory_structures/scratch.py reverie/backend_server/persona/cognitive_modules/intent_memory.py reverie/backend_server/persona/cognitive_modules/skill_packs/gather_skill.py
git commit -m "test: verify satiety loop guard against refrigerator repro"
```
