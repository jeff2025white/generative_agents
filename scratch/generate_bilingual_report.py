# -*- coding: utf-8 -*-
import json
import os

def generate_report():
    json_path = "scratch/prompt_trace_135.json"
    if not os.path.exists(json_path):
        print("Error: scratch/prompt_trace_135.json not found")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    demand_thinking = data.get("demand_thinking", {})
    action_translation = data.get("action_translation", {})

    dt_prompt = demand_thinking.get("prompt") or ""
    dt_response = demand_thinking.get("response") or ""
    at_prompt = action_translation.get("prompt") or ""
    at_response = action_translation.get("response") or ""

    report = []
    report.append("# Klaus Mueller Step 135 完整提示词与响应报告 (中英对照)\n")
    report.append("本报告整理了 Klaus Mueller 在 Step 135 遭遇 `target_inventory_empty` 失败循环时，大模型接收到的**第一阶段决策提示词（Stage 1 Prompt）**与**第二阶段翻译提示词（Stage 2 Prompt）**的完整原文及其中文对照翻译。\n")

    report.append("---")
    report.append("## 第一阶段：自然语言决策思考 (Stage 1: Demand Thinking)\n")
    report.append("该阶段用于生成角色的自然语言“思考（Thought）”与“推理（Reasoning）”。\n")
    
    report.append("### 1.1 阶段 1 完整提示词内容 (Stage 1 Complete Prompt)")
    report.append("```text")
    report.append(dt_prompt)
    report.append("```\n")

    report.append("### 1.2 阶段 1 中文对照翻译 (Stage 1 Chinese Translation)")
    report.append("#### 【决策胶囊 (Decision Capsule)】")
    report.append("- **当前时间**：2026年7月11日（星期六）上午 08:22")
    report.append("- **决策优先级**：dominant_motive_guidance > current_feasibility_and_latest_failure > 即时生理紧迫性 > 可达的局部选项 > 进行中的局部职责 > 长期目标与身份。主导动机是下一步即时行动中最强的内部理由。只有硬性物理约束、执行不可能性，或最新的具体失败反馈，才能迫使系统从主导动机退回到其他选择。不要把所有信息等权看待。")
    report.append("- **最近失败记录 1**：向 Isabella Rodriguez 发起 request 失败，原因为 `target_inventory_empty`（目标背包为空）。")
    report.append("- **最近失败记录 2**：向 Isabella Rodriguez 发起 request 失败，原因为 `target_inventory_empty`（目标背包为空）。")
    report.append("- **上一动作状态**：无 | 执行状态=失败 | 目标=isabella rodriguez | 失败原因=目标背包为空")
    report.append("- **驱动力满足方式定义**：satiety(饱腹感)=寻找食物; stamina(精力)=休息与恢复; health(健康)=避免受伤与治疗; safety(安全)=避险; mood(心情)=情绪修复; belonging(归属感)=社交连接; status(地位)=认可与声望; autonomy(自主性)=自我主导; competence(胜任感)=掌控与效能; meaning(意义)=目标与价值。")
    report.append("- **动机状态**：主导动机=satiety(黄色警告)，次要动机=mood。自我感觉：*“我有些饿了，我想尽快吃点东西；我情绪有点低落，想尽快放松一下。”*")
    report.append("  - 动机推理详情：主导饥饿值=39.9（安全线=50.0，临界线=25.0，已低于安全范围，必须在下一步行动中体现，不能当成背景噪音，若忽略则会快速恶化）。次要心情值=50.0（安全线=58.0，临界线=35.0）。策略自由度：仅在能改善主导需求的可达性、杠杆率或可靠性时，才允许进行短暂聪明的绕道。")

    report.append("\n#### 【可达的本地资源与场所】")
    report.append("- **refrigerator (冰箱)**：可获取/储存食物。")
    report.append("- **apple tree (苹果树)**：可获取食物。")
    report.append("- **common room sofa (休息室沙发)**：休息/放松。")
    report.append("- **library sofa (图书馆沙发)**：休息/阅读。")

    report.append("\n#### 【社交与协作上下文】")
    report.append("- 附近没有激活的特殊协作任务或等待状态。")

    report.append("\n#### 【既往经验/记忆】")
    report.append("- 没有检索到特别相关的强经验指导。")
    report.append("- **经验指导规则**：优先考虑近期实例级别的经验，而非久远的通用记忆。如果某个特定实例最近失败了，优先选择另一个可行的实例或可行的源。")
    report.append("- **检索到的相关食物经验**：")
    report.append("  - 成功经验：Klaus Mueller 曾向 Isabella Rodriguez 请求苹果并成功获得。")
    report.append("  - 进行中动作经验：Klaus 正在向 Isabella 索要食物。")

    report.append("\n#### 【背景身份与设定 (Background Identity)】")
    report.append("- **姓名**：Klaus Mueller")
    report.append("- **年龄**：37")
    report.append("- **天生特质**：好问、爱学习、爱反思")
    report.append("- **习得特质**：Klaus Mueller 是 Oak Hill College 的一名物理/社会学专业学生。He is passionate about social justice and loves to...")
    report.append("- **长期目标**：首先，在这个沙盒世界里活下去并保持基本健康状态。我需要稳定的食物、休息与安全。其次，发挥自己的学术特长。")
    report.append("- **当前情境**：Klaus 正在撰写关于社会学的论文，经常在图书馆和咖啡馆进行观察和研究。")
    report.append("- **生活方式**：Klaus Mueller 大约晚上 11 点睡觉，上午 7 点起床。")
    report.append("- **其他人状态预测**：")
    report.append("  - **Isabella Rodriguez** (当前可达)：她是咖啡馆老板，总是乐于助人。**当前推荐使用建议：在重复失败的环境物品（如冰箱）之前，向她请求食物（Request food）或进行食物交易（Trade）**。")

    report.append("\n#### 【沙盒世界物理规则 (Sandbox World Rules)】")
    report.append("- 世界遵循硬性可行性约束。你只有一个肉体，同一时间只能站在一个格子上，只能在可达空间移动。")
    report.append("- 每一步只能选择一个即时动作。下一步移动必须是具体的、本地的、此刻物理可执行的。")
    report.append("- 遵循因果律：如果你背包里没有可食用食物，`Consume` 是无效的，除非食物是先通过 `Gather`、收到、`Request` 或 `Trade` 物理获得的。")
    report.append("- **失败是真实的证据**：如果上一个目标不可达或返回 `path_not_found`，**不要立即重复相同的失败动作**。改变目标或改变方式。如果资源被发现是空的，**接受这个物理事实并切换到其他可行来源**，而不是装作世界没有改变。")

    report.append("\n#### 【决策优先级与输出要求 (Priority Rules & Requirements)】")
    report.append("1. 当前主导动机拥有最高内部决策权重。")
    report.append("2. 只有当硬性物理可行性和最近失败反馈使主导动作不可行时，才允许偏离主导动机。")
    report.append("3. 不要把所有信息等权看待。如果目标在 `InvalidTargets` 列表中，则当前步骤被完全禁用。")
    report.append("- **输出格式要求**：以 Klaus 的第一人称口吻写一小段规划段落。第一句话必须明确指出下一步即时可行的具体行动。必须明确指出当前最紧迫的内部需求（饥饿）。如果前一个动作失败了，选择新的即时方法。只有当主导选项完全被物理不可行性或最近失败反馈阻塞时，才使用备选方案。")
    
    report.append("\n### 1.3 阶段 1 模型输出结果 (Stage 1 Response)")
    if isinstance(dt_response, dict):
        report.append("```json\n" + json.dumps(dt_response, indent=2, ensure_ascii=False) + "\n```")
    else:
        report.append(str(dt_response or ""))

    report.append("\n---")
    report.append("## 第二阶段：动作翻译 (Stage 2: Action Translation)\n")
    report.append("该阶段将阶段 1 生成的自然语言意图翻译为物理引擎可执行的 JSON 动作指令。\n")

    report.append("### 2.1 阶段 2 完整提示词内容 (Stage 2 Complete Prompt)")
    report.append("```text")
    report.append(at_prompt)
    report.append("```\n")

    report.append("### 2.2 阶段 2 中文对照翻译 (Stage 2 Chinese Translation)")
    report.append("你是一个沙盒模拟世界的精确物理翻译引擎。你的工作是将 Klaus 的自然语言意图翻译成世界物理引擎可以执行的标准物理命令 JSON 对象。")
    report.append("请将阶段 1 的 thought 视为权威的即时意图。使用动作模式（Action Schema）的分类规则，选择最直接匹配的分类和目标。")

    report.append("\n#### 【允许的动作模式分类定义】")
    report.append("- **Consume (消费)**: 吃/喝背包里的食物，恢复饱腹感。允许目标：苹果、熟食、零食等。")
    report.append("- **Gather (采集)**: 从资源容器中采集食物加入背包。允许目标：冰箱 (refrigerator)、炉灶 (stove)、咖啡柜台 (cafe counter)、苹果树 (apple tree)。")
    report.append("- **Rest (休息)**: 睡觉恢复精力。允许目标：床 (bed)、沙发 (sofa) 等。")
    report.append("- **Request (请求/索要)**: 向另一个人索要具体的资源、物品、访问权或即时帮助。允许目标：Isabella Rodriguez、Maria Lopez。")
    report.append("- **Trade (交易)**: 与另一个人交换物品或价值。允许目标：Isabella Rodriguez。")
    report.append("（……省略其他未命中分类定义如 Avoid、Work、Rob、Recreate 等……）")

    report.append("\n#### 【转换目标 (Translate Intention)】")
    report.append("- **待翻译意图**：“我会去 Hobbs Cafe 向 Isabella Rodriguez 索要一份零食，因为她向来待人热情，可能会提供一些东西来帮助我解决眼前的饥饿并改善我的心情。”")
    report.append("- **经验守卫 (Experience Guard)**：无强效的近期经验守卫。")
    report.append("- **收敛指导**：直接翻译 thought 中的意图，不要发散。翻译成最直接的动作类别。")

    report.append("\n#### 【输出 JSON 格式要求】")
    report.append("仅响应合法的 JSON 对象，包含 `action`、`target` ... 五个字段。")

    report.append("\n### 2.3 阶段 2 模型输出结果 (Stage 2 Response)")
    report.append("```json")
    if isinstance(at_response, dict):
        report.append(json.dumps(at_response, indent=2, ensure_ascii=False))
    else:
        report.append(str(at_response or ""))
    report.append("```\n")

    report.append("---")
    report.append("## 核心瓶颈深度总结 (Bilingual Prompt Logic Gap)")
    report.append("通过完整的中文版对照报告，我们可以锁定失败循环的症结：")
    report.append("1. **最新失败结果被正面引导掩盖**：提示词中虽然被注入了 `LastAction: failure_reason=target_inventory_empty`，但他人关系部分（Other People）生成的 `suggested_use_now` 却写着：`Request food or trade for food access before repeating a failed object target.` (建议在重复失败的环境物品前，先去向 Isabella 请求食物)。大模型在综合权衡时，将“系统推荐动作”和“曾成功向她要过苹果”的正面记忆，凌驾于“刚刚失败了”的负面结果之上，从而决定继续尝试。")
    report.append("2. **缺乏硬性规避指令**：因为 `target_inventory_empty` 得分仅为 `0.54`，未超过 `0.55` 门槛，所以它只以“近期最近历史（RecentResult）”形式出现，没有作为“必须规避的动作阻断（InvalidTargets / Experience Guard）”直接禁用 Isabella。这导致大模型利用推理漏洞进行自我说服，不断重新发起索要，产生长达 30 步的死循环。")

    # Write report
    out_path = "/Users/gun/.gemini/antigravity-ide/brain/a95c9e1c-28dd-4a25-88fa-16c074f15345/prompt_trace_analysis.md"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print(f"Bilingual report written to {out_path}")

if __name__ == "__main__":
    generate_report()
