# Generative Agents 物理执行层“可插拔技能包 (Skill Pack)”架构蓝图

本文档定义了 Generative Agents 项目物理执行层（`execute.py`）向“可插拔技能包”架构过渡的设计蓝图。该设计旨在彻底移除执行层中的硬编码行为分支，将其转变为高内聚、低耦合的技能分发器。

---

## 1. 设计哲学与铁律对齐

本架构蓝图严格遵循项目**三大铁律**：

1. **去特化（对齐铁律 3）**：干掉 `execute.py` 内部大量的 `if action == "gather"`、`elif action == "consume"` 等条件判断。执行器本身不再包含任何特定行为的业务逻辑。
2. **物理底座化（对齐铁律 2）**：将行为引发的代谢结算、资源变更归为“客观世界规律”，并封装进一个个独立的“技能包（Skill Pack）”中。物理引擎（`execute`）仅作为客观世界的时间和空间流逝驱动器，负责按步寻路和动作到货分发。
3. **易扩展性（Plug-and-Play）**：当系统引入新动作（如“钓鱼”、“种植”、“写代码”）时，核心执行层代码无需任何修改，只需编写对应的 `SkillPack` 插件并注册即可，实现零污染开发。

---

## 2. 技能包接口规范 (Interface Specification)

所有具体的物理行为均需继承自基类 `BaseSkillPack`，并实现以下规范：

```python
class BaseSkillPack:
    def __init__(self):
        self.name = ""          # 技能唯一标识（对应大模型决策输出的 action，如 "gather"）
        self.associated_xp = "" # 关联的技能树分类名称（如 "gathering"）

    def can_execute(self, persona, target, maze) -> bool:
        """
        【物理前置校验】
        检查角色和环境当前是否满足执行此动作的物理前置条件。
        - 返回 True: 允许执行。
        - 返回 False: 物理条件不满足（如背包中没有食物却要进食），执行器将中止并报错。
        """
        raise NotImplementedError

    def cognitive_decision(self, persona, target, maze, personas) -> dict:
        """
        【微认知计算接口（可选）】
        当技能启动前或在执行物理结算时，若需要进行更加细粒度的个性化抉择
        （例如：选哪样食材来做菜、对顾客生成什么样的个性化问候语气泡），
        可在此接口内调用轻量 LLM 提示词进行实时推理决策，并返回决策参数字典。
        """
        return {}

    def get_target_tiles(self, persona, target, maze) -> list:
        """
        【空间匹配】
        计算并返回此技能可交互的地图格子坐标列表（A* 寻路的目的地选择）。
        """
        raise NotImplementedError

    def on_arrive(self, persona, target, maze, personas):
        """
        【物理后果结算】
        小人物理抵达目的地格子时触发的客观结算。
        - 包含：生理代谢值变化（饱食度/精力增减）。
        - 包含：背包资源加减。
        - 包含：技能经验值结算。
        - 包含：多角色协同动作的确定性事件注入（如为双方写入服务咖啡的记忆）。
        """
        raise NotImplementedError
```

---

## 3. 执行层调度器重构设计 (`execute.py`)

重构后的 `execute.py` 仅作为格点步进器与技能包的调度器，其核心执行逻辑如下：

```python
# 技能注册中心 (Skill Registry)
from persona.cognitive_modules.skill_packs import (
    GatherSkillPack,
    ConsumeSkillPack,
    RestSkillPack,
    BrewCoffeeSkillPack
)

SKILL_REGISTRY = {
    "gather": GatherSkillPack(),
    "consume": ConsumeSkillPack(),
    "rest": RestSkillPack(),
    "brew": BrewCoffeeSkillPack()
}

def execute(persona, maze, personas, plan):
    # 1. 基础 A* 格点步进执行（弹出下一格并返回）
    ret = step_towards_destination(persona, maze, plan)
    
    # 2. 提取大模型指令中的动作名称
    act_event = persona.scratch.act_event
    action = act_event[1] if (len(act_event) > 1 and act_event[1]) else ""
    target = act_event[2] if (len(act_event) > 2 and act_event[2]) else ""
    
    # 3. 物理抵达（planned_path 弹空且路径已设）
    if not persona.scratch.planned_path and persona.scratch.act_path_set:
        if not getattr(persona.scratch, 'survival_applied', False):
            persona.scratch.survival_applied = True
            
            # 从注册中心匹配技能包
            skill = SKILL_REGISTRY.get(action.lower())
            if skill:
                # 触发物理前置校验
                if skill.can_execute(persona, target, maze):
                    # 执行客观结算
                    skill.on_arrive(persona, target, maze, personas)
                else:
                    print(f"=== [物理冲突] {persona.name} 无法执行 {action}，物理前置未满足 ===")
            else:
                # 默认后备处理（对于无结算动作，仅作普通抵达）
                pass
                
    return ret, persona.scratch.act_pronunciatio, f"{persona.scratch.act_description} @ {persona.scratch.act_address}"
```

---

## 4. 具体技能包实现范例 (Implementation Examples)

### 4.1 采集技能包 (`GatherSkillPack`)
```python
class GatherSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "gather"
        self.associated_xp = "gathering"

    def can_execute(self, persona, target, maze):
        # 只要地图上存在目标资源即可
        return persona.s_mem.find_nearest_object(target) is not None

    def on_arrive(self, persona, target, maze, personas):
        # 1. 物理产出结算
        if "apple_tree" in target.lower():
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 2
            print(f"=== [技能物理结算] {persona.name} 从苹果树采集苹果 x2 ===")
        elif "refrigerator" in target.lower():
            persona.scratch.inventory["apple"] = persona.scratch.inventory.get("apple", 0) + 1
            
        # 2. 经验结算
        persona.scratch.skills[self.associated_xp]["xp"] += 10
        # (经验值满触发升级，提升角色 learned ISS)
```

### 4.2 进食消费技能包 (`ConsumeSkillPack`)
```python
class ConsumeSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "consume"
        self.associated_xp = "cooking"

    def can_execute(self, persona, target, maze):
        # 物理规则约束：背包中必须持有要消费的食物项
        item_key = target.strip().lower()
        return persona.scratch.inventory.get(item_key, 0) > 0

    def on_arrive(self, persona, target, maze, personas):
        # 1. 背包消耗结算
        item_key = target.strip().lower()
        persona.scratch.inventory[item_key] -= 1
        
        # 2. 生理代谢回满
        persona.scratch.satiety = min(100.0, persona.scratch.satiety + 40.0)
        persona.scratch.health = min(100.0, persona.scratch.health + 5.0)
        
        # 3. 烹饪技能结算
        persona.scratch.skills[self.associated_xp]["xp"] += 10
        print(f"=== [技能物理结算] {persona.name} 食用了 {target}，恢复饱食度至 {persona.scratch.satiety:.1f} ===")
```

### 4.3 需大模型参与的烹饪技能包 (`CookSkillPack`)

当执行复杂行为（例如烹饪、复杂的社交接待或手工制造）时，物理动作的细节可能需要实时大模型的“微认知计算”参与。以下是一个融合了 LLM 决策的烹饪技能包实现：

```python
class CookSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "cook"
        self.associated_xp = "cooking"

    def can_execute(self, persona, target, maze):
        # 物理前置：必须在厨房器具（如 stove）附近，且背包里拥有至少一种食材
        return len(persona.scratch.inventory) > 0

    def cognitive_decision(self, persona, target, maze, personas) -> dict:
        """
        微认知决策：调用轻量大模型，根据角色当前的背包食材，
        自主决定要烹饪哪道菜肴，并生成一句烹饪时的内心独白。
        """
        ingredients = list(persona.scratch.inventory.keys())
        prompt = f"你目前拥有的原料有: {ingredients}。你正站在炉灶前准备做饭。请写出你要做的菜肴名称(dish)和你的内心独白(monologue)。"
        
        # 调用大模型辅助决策
        response = call_mini_llm(persona, prompt)
        return {
            "dish": response.get("dish", "cooked apple"),
            "monologue": response.get("monologue", "Let's make something tasty.")
        }

    def on_arrive(self, persona, target, maze, personas):
        # 1. 物理抵达后，触发微大模型认知，决定具体菜色与自言自语
        decision = self.cognitive_decision(persona, target, maze, personas)
        dish = decision["dish"]
        
        # 2. 扣除原材料背包，加入成品食物
        ingredients = list(persona.scratch.inventory.keys())
        if ingredients:
            raw_item = ingredients[0]
            persona.scratch.inventory[raw_item] -= 1
        persona.scratch.inventory[dish] = persona.scratch.inventory.get(dish, 0) + 1
        
        # 3. 经验值和代谢值客观结算
        persona.scratch.skills[self.associated_xp]["xp"] += 15
        
        # 4. 生成小人的头顶气泡独白（反馈给虚拟世界）
        persona.scratch.act_pronunciatio = "🍳"
        print(f"=== [大模型辅助技能结算] {persona.name} 烹饪了 {dish}! 内心独白: {decision['monologue']} ===")
```

---

## 5. 新增技能扩展指南

当需要向虚拟世界中添加新技能时，开发者仅需遵循以下三步：
1. **编写技能插件**：在 `persona/cognitive_modules/skill_packs/` 下新建 Python 文件并实现 `BaseSkillPack` 接口。
2. **注册技能**：在 `execute.py` 的 `SKILL_REGISTRY` 中添加键值对。
3. **大模型认知对齐**：在大模型的规划或生存规划模板（如 `survival_decision_v1.txt`）的 `Choose one action from:` 说明中加入新动作的名称，大模型即可在适当的生存和日常决策中自主选择执行该技能。

---

## 6. 针对当前小人的候选技能包列表 (Candidate Skill Packs for Current Personas)

根据 Isabella Rodriguez、Klaus Mueller、Maria Lopez 目前在小镇日常生活中的所有实际活动，我们可以抽象并实现以下八个**对应技能包**，用以全面接管他们的行为：

### 1. 睡眠与恢复技能包 (`SleepSkillPack`)
*   **目标动作**：`sleeping` (睡觉), `dreaming` (做梦), `resting` (在床上躺着)。
*   **物理前置 (can_execute)**：必须位于自己的卧室且临近床铺（`bed`）。
*   **微认知决策 (cognitive_decision)**：可由大模型依据当天情绪决定是否说梦话，或记录睡眠梦境。
*   **物理结算 (on_arrive)**：精力值（Stamina）开始高效回复。

### 2. 学习、书写与研究技能包 (`StudySkillPack`)
*   **目标动作**：`writing research paper` (写论文), `studying physics` (学物理), `reviewing notes` (复习笔记), `reading` (看书)。
*   **物理前置 (can_execute)**：必须位于配有书桌（`desk`）、椅子（`chair`）或图书馆就餐区的区域。
*   **微认知决策 (cognitive_decision)**：调用轻量 LLM 根据角色身份决定当前研究的小专题（如：写“社会学的咖啡馆影响”还是“物理的力学公式”），并更新其 personal_knowledge（个人知识库）。
*   **物理结算 (on_arrive)**：获取对应的学习 XP，提升智力或科研等级。

### 3. 游戏直播技能包 (`GamingSkillPack`)
*   **目标动作**：`streaming games on Twitch` (在Twitch直播游戏), `gaming` (打游戏), `setting up streaming equipment` (调试直播设备)。
*   **物理前置 (can_execute)**：必须在自己的卧室，且靠近配有电脑的电脑桌（`desk`）。
*   **微认知决策 (cognitive_decision)**：大模型生成今天直播的游戏名称、直播标题以及向观众打招呼的互动台词。
*   **物理结算 (on_arrive)**：结算直播收益（金钱加成），并提升娱乐经验（XP）。

### 4. 晨间整理与盥洗技能包 (`GroomingSkillPack`)
*   **目标动作**：`brushing teeth` (刷牙), `washing face` (洗脸), `styling hair` (整理发型), `getting dressed` (穿衣服), `applying makeup` (化妆)。
*   **物理前置 (can_execute)**：必须靠近浴室的水槽（`sink`）、镜子（`mirror`）或衣柜（`closet`）。
*   **物理结算 (on_arrive)**：精神状态提升，Stamina 轻微恢复。

### 5. 休闲与多媒体娱乐技能包 (`RecreationSkillPack`)
*   **目标动作**：`watching TV` (看电视), `relaxing in dorm room` (宿舍内放松)。
*   **物理前置 (can_execute)**：靠近电视（`tv`）或沙发（`sofa`）。
*   **微认知决策 (cognitive_decision)**：大模型随机抽取电视播放的节目单（如“今日新闻”、“体育直播”），并返回小人对该节目的内心吐槽。
*   **物理结算 (on_arrive)**：Stamina 恢复，并清空大脑紧张状态。

### 6. 进食消费技能包 (`ConsumeSkillPack`)
*   **目标动作**：`eating breakfast` (吃早餐), `having lunch` (吃午餐), `having dinner` (吃晚餐), `drinking coffee` (喝咖啡)。
*   **物理前置 (can_execute)**：背包中持有对应食物或饮料。
*   **物理结算 (on_arrive)**：扣减背包资源，饱食度（Satiety）+40，生命值（Health）+5。

### 7. 咖啡与饮品服务技能包 (`CoffeeServiceSkillPack`)
*   **目标动作**：`brewing coffee` (煮咖啡), `serving coffee to Klaus` (给 Klaus 送咖啡)。
*   **物理前置 (can_execute)**：位于 Hobbs Cafe，且靠近咖啡机（`coffee maker`）或餐桌。
*   **物理结算 (on_arrive)**：
    *   煮咖啡时，使咖啡机状态更新为“正忙/正在煮”。
    *   送咖啡时，在顾客对应的餐桌格点注入 `"served"` 状态事件，并同步为服务员和顾客注入“已提供服务”的社会协作记忆（协同记忆同步）。

### 8. 基础食物烹饪技能包 (`CookSkillPack`)
*   **目标动作**：`preparing dinner` (准备晚饭), `cooking` (做饭)。
*   **物理前置 (can_execute)**：靠近厨房炉灶（`stove`）或微波炉，且背包中有可烹饪的原料。
*   **微认知决策 (cognitive_decision)**：大模型基于背包食材决策做什么菜，并生成内心独白。
*   **物理结算 (on_arrive)**：扣减原料，产出成品菜肴放入背包，增加 Cooking XP。

### 9. 复杂聊天与社交技能包 (`ChatSkillPack`) [已实现 / 第一款复杂技能包]
*   **目标动作**：`monologue` (内心独白), `chat with` (社交交谈), `creator_comm` / `communicate` (与造物主沟通)。
*   **物理前置 (can_execute)**：内心独白与造物主沟通无物理限制（返回 True）；社交交谈要求目标小人已在相同区域或附近。
*   **微认知决策 (cognitive_decision)**：
    *   *内心独白*：依据当前活动、性情与状态生成中文独白内容及心情 Emoji。
    *   *社交交谈*：检索近期记忆，决定在交谈中诚实分享、夸大内容或进行造谣（Spreading Rumors/Gossip）。
    *   *与造物主沟通*：解析来自观察者（我）的文本/指令，产生敬畏/ Devotion/冲突心理，并拟定回复以及后续可能需要去执行的执行任务。
*   **物理结算 (on_arrive)**：
    *   *内心独白*：小人头上显示对应 Emoji，自言自语并存入想法记忆，同时恢复少量精力（Stamina +8.0）。
    *   *社交交谈*：模拟多轮对话，同步对话历史至双方的 memory tree 中。提取受体小人学到的传闻并单独增加事件记忆；双方各恢复精力（Stamina +15.0）。
    *   *与造物主沟通*：通过 sqlite3 直接更新 Django 数据库表 `translator_simpendingaction` 的回复和 processed 状态。同时如果生成了遵从任务（如 "go sleep"），会在其下一秒动作规划中通过 `add_new_action` 强行覆盖为对应目标物理实体的物理动作（如前往床铺睡觉）。


