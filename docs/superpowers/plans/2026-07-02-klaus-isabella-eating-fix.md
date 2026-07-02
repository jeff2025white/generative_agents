# Klaus Isabella Eating Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Klaus 在 Hobbs Cafe 座位区反复换座但无法进食的问题，并修复 Isabella 到床上后长时间持续休息、直到饥饿跌破危机线才切进进食的问题。

**Architecture:** 第一条补丁只修食物目标语义归一化，让 `consume`/`gather` 在咖啡馆场景统一落到可执行的 `cafe counter` 食物源，避免进入 `cafe customer seating` 这种可寻路但不可执行的假目标。第二条补丁只修 `RestSkillPack` 的生命周期，让到达后完成并释放动作，避免“体力已满但休息动作仍然挂着”的粘滞状态继续压制重新规划。

**Tech Stack:** Python 3.10, `unittest`, persona skill packs, survival planning pipeline, JSONL debug logs.

---

### Task 1: 修复咖啡馆食物目标归一化

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\food_sources.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\consume_skill.py`
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py`
- Test: `g:\generative_agents\test\test_klaus_isabella_eating_fix.py`

- [ ] **Step 1: 写失败测试，锁定咖啡馆别名必须归一到可执行食物源**

创建 `g:\generative_agents\test\test_klaus_isabella_eating_fix.py`，先写这两个测试：

```python
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.cognitive_modules.food_sources import normalize_food_source_target
from persona.cognitive_modules.skill_packs.consume_skill import ConsumeSkillPack


class KlausIsabellaEatingFixTests(unittest.TestCase):
    def test_normalize_food_source_target_maps_cafe_seating_aliases(self):
        self.assertEqual(normalize_food_source_target("cafe customer seating"), "cafe counter")
        self.assertEqual(normalize_food_source_target("Hobbs Cafe cafe customer seating"), "cafe counter")
        self.assertEqual(normalize_food_source_target("cooked meal"), "cafe counter")
        self.assertEqual(normalize_food_source_target("café"), "cafe counter")

    def test_consume_can_execute_accepts_cafe_customer_seating_address(self):
        maze = SimpleNamespace(
            access_tile=lambda tile: {"game_object": ""},
        )
        persona = SimpleNamespace(
            name="Klaus Mueller",
            scratch=SimpleNamespace(
                curr_tile=[79, 21],
                inventory={},
                act_address="the Ville:Hobbs Cafe:cafe:cafe customer seating",
            ),
        )

        self.assertTrue(ConsumeSkillPack().can_execute(persona, "cooked meal", maze))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest test.test_klaus_isabella_eating_fix.KlausIsabellaEatingFixTests.test_normalize_food_source_target_maps_cafe_seating_aliases test.test_klaus_isabella_eating_fix.KlausIsabellaEatingFixTests.test_consume_can_execute_accepts_cafe_customer_seating_address -v`

Expected: FAIL，因为当前代码不会把 `cafe customer seating` / `cooked meal` / `café` 归一成 `cafe counter`，`ConsumeSkillPack.can_execute()` 也会返回 `False`。

- [ ] **Step 3: 实现最小修复**

把 `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\food_sources.py` 改成：

```python
VALID_GATHER_FOOD_SOURCES = {
    "refrigerator",
    "stove",
    "cafe counter",
    "apple tree",
}


def normalize_food_source_target(target):
    t_lower = target.lower().strip() if target else ""
    if "refrigerator" in t_lower or "fridge" in t_lower:
        return "refrigerator"
    if "stove" in t_lower:
        return "stove"
    if "cafe customer seating" in t_lower:
        return "cafe counter"
    if "behind the cafe counter" in t_lower:
        return "cafe counter"
    if "cooked meal" in t_lower:
        return "cafe counter"
    if t_lower in {"café", "cafe"}:
        return "cafe counter"
    if "cafe" in t_lower and "counter" in t_lower:
        return "cafe counter"
    if "counter" in t_lower and "cafe" in t_lower:
        return "cafe counter"
    if "apple_tree" in t_lower or ("apple" in t_lower and "tree" in t_lower) or t_lower == "tree":
        return "apple tree"
    return target
```

在 `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\consume_skill.py` 顶部补导入，并在 `can_execute()` / `on_arrive()` 的目标判断处先归一：

```python
from persona.cognitive_modules.food_sources import normalize_food_source_target


def can_execute(self, persona, target, maze) -> bool:
    normalized_target = normalize_food_source_target(target)
    item_key = normalized_target.strip().lower()
    ...
    act_addr = normalize_food_source_target(persona.scratch.act_address.lower() if persona.scratch.act_address else "")
```

在 `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\plan.py` 的 `survival_direct` 分支，把当前错误的座位优先级替换为 `cafe counter`：

```python
if not in_inv:
  print(f"[{persona.name}] 背包中没有 {target}！修改动作为 Gather 从环境获取。")
  action = "Gather"
  if "behind the cafe counter" in objs_list or "cafe customer seating" in objs_list:
    target = "cafe counter"
  else:
    target = "refrigerator" if "refrigerator" in objs_list else "apple tree"
  address = persona.s_mem.find_nearest_object(target) or address
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest test.test_klaus_isabella_eating_fix.KlausIsabellaEatingFixTests.test_normalize_food_source_target_maps_cafe_seating_aliases test.test_klaus_isabella_eating_fix.KlausIsabellaEatingFixTests.test_consume_can_execute_accepts_cafe_customer_seating_address -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add test/test_klaus_isabella_eating_fix.py reverie/backend_server/persona/cognitive_modules/food_sources.py reverie/backend_server/persona/cognitive_modules/skill_packs/consume_skill.py reverie/backend_server/persona/cognitive_modules/plan.py
git commit -m "fix: normalize cafe meal targets to executable food sources"
```

### Task 2: 修复 Rest 动作粘滞导致的延迟进食

**Files:**
- Modify: `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\rest_skill.py`
- Modify: `g:\generative_agents\test\test_klaus_isabella_eating_fix.py`
- Read: `g:\generative_agents\reverie\backend_server\persona\memory_structures\scratch.py`

- [ ] **Step 1: 写失败测试，锁定 rest 到达后必须释放动作**

把下面测试追加到 `g:\generative_agents\test\test_klaus_isabella_eating_fix.py`：

```python
from persona.cognitive_modules.skill_packs.rest_skill import RestSkillPack


class KlausIsabellaEatingFixTests(unittest.TestCase):
    def test_rest_on_arrive_marks_action_completed_and_releases_plan(self):
        persona = SimpleNamespace(
            name="Isabella Rodriguez",
            scratch=SimpleNamespace(
                stamina=60.0,
                curr_step=115,
                act_command={"skill_id": "rest", "target": "bed"},
                act_event=("Isabella Rodriguez", "rest", "bed"),
                act_description="lying down on the bed to rest",
                act_address="the Ville:Isabella Rodriguez's apartment:main room:bed",
                planned_path=[[73, 14]],
                act_path_set=True,
                skills={},
                mark_action_completed=lambda **kwargs: setattr(persona, "_completed", kwargs),
            ),
        )

        RestSkillPack().on_arrive(persona, "bed", None, {})

        self.assertEqual(persona.scratch.stamina, 100.0)
        self.assertEqual(persona.scratch.planned_path, [])
        self.assertFalse(persona.scratch.act_path_set)
        self.assertIn("action_command", persona._completed)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest test.test_klaus_isabella_eating_fix.KlausIsabellaEatingFixTests.test_rest_on_arrive_marks_action_completed_and_releases_plan -v`

Expected: FAIL，因为当前 `RestSkillPack.on_arrive()` 只恢复体力，不会 `mark_action_completed()`，也不会释放当前动作。

- [ ] **Step 3: 实现最小修复**

把 `g:\generative_agents\reverie\backend_server\persona\cognitive_modules\skill_packs\rest_skill.py` 的 `on_arrive()` 收尾改成：

```python
def on_arrive(self, persona, target, maze, personas):
    before_stamina = persona.scratch.stamina
    before_snapshot = capture_attribute_snapshot(persona)
    persona.scratch.stamina = min(100.0, persona.scratch.stamina + 40.0)
    after_snapshot = capture_attribute_snapshot(persona)
    attribute_effects = compute_attribute_effects(before_snapshot, after_snapshot)
    append_debug_log(
        "skill_execution_debug.jsonl",
        {
            "persona": persona.name,
            "skill": "rest",
            "event": "on_arrive_end",
            "target": target,
            "stamina_before": before_stamina,
            "stamina_after": persona.scratch.stamina,
        }
    )
    record_stat_change_experience(
        persona,
        f"{persona.name} rested at {target} and recovered stamina.",
        {"rest", "sleep", "stamina", str(target).lower()},
        attribute_effects,
        poignancy=6.0,
        predicate="changed",
        obj="rest_recovery",
    )
    persona.scratch.mark_action_completed(
        action_command=persona.scratch.act_command,
        action_event=persona.scratch.act_event,
        action_description=persona.scratch.act_description,
        action_address=persona.scratch.act_address,
    )
    persona.scratch.planned_path = []
    persona.scratch.act_path_set = False
```

- [ ] **Step 4: 跑整组聚焦测试**

Run: `python -m unittest test.test_klaus_isabella_eating_fix -v`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add test/test_klaus_isabella_eating_fix.py reverie/backend_server/persona/cognitive_modules/skill_packs/rest_skill.py
git commit -m "fix: release completed rest actions so hunger can replan"
```

### Task 3: 做一次行为回归验证

**Files:**
- Read: `g:\generative_agents\logs\action_execution_debug.jsonl`
- Read: `g:\generative_agents\logs\skill_execution_debug.jsonl`
- Read: `g:\generative_agents\logs\decision_stability.jsonl`
- Read: `g:\generative_agents\environment\frontend_server\storage\sim_20260702_140322\movement\90.json`

- [ ] **Step 1: 运行聚焦回归测试**

Run: `python -m unittest test.test_klaus_isabella_eating_fix test.test_decision_stability -v`

Expected: PASS

- [ ] **Step 2: 复现 Klaus/Isabella 场景**

重新跑你刚才的仿真，让两个人再次进入低饱食区间。

Expected:
- Klaus 不再在 `Hobbs Cafe` 座位区反复 `skill_blocked`
- Isabella 到床后不会一直抱着 `rest` 动作直到 `satiety < 30`

- [ ] **Step 3: 用精确过滤检查日志**

Run:

```bash
Select-String -Path "g:\generative_agents\logs\skill_execution_debug.jsonl" -Pattern 'Klaus Mueller|skill_blocked|cafe customer seating|cafe counter'
```

Run:

```bash
Select-String -Path "g:\generative_agents\logs\decision_stability.jsonl" -Pattern 'Isabella Rodriguez|plan_suspended|physiological_crisis|switch_accepted'
```

Expected:
- Klaus 的 `consume` 不再连续对 `cafe customer seating` / `cooked meal` 失败
- Isabella 在体力恢复后能重新规划，不需要一直等到硬阈值危机才切进进食

- [ ] **Step 4: 最终提交**

```bash
git add test/test_klaus_isabella_eating_fix.py reverie/backend_server/persona/cognitive_modules/food_sources.py reverie/backend_server/persona/cognitive_modules/skill_packs/consume_skill.py reverie/backend_server/persona/cognitive_modules/skill_packs/rest_skill.py reverie/backend_server/persona/cognitive_modules/plan.py
git commit -m "fix: unblock eating after cafe target drift and sticky rest"
```
