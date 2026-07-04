# Generative Agents — 地图补点与物理技能库扩展路线图

本文档汇总了项目在地图物理设施缺失、三人仿真基线（Isabella, Maria, Klaus）空间认知缺口以及新物理技能扩展方面的痛点分析、优先补全清单及底层文件定位实施指南。

---

## 目录
1. [痛点分析：意图合理但动作承接不足](#1-痛点分析意图合理但动作承接不足)
2. [静态底图定义 vs 3人基线暴露现状](#2-静态底图定义-vs-3人基线暴露现状)
3. [技能库扩展路线图 (Skills Backlog)](#3-技能库扩展路线图-skills-backlog)
4. [地图设施补全优先级清单 (P0 / P1 / P2)](#4-地图设施补全优先级清单-p0--p1--p2)
5. [地图补点技术实施与文件定位 (Patch Guide)](#5-地图补点技术实施与文件定位-patch-guide)
   - [5.1 地图补点三种模式](#51-地图补点三种模式)
   - [5.2 8个高频可交互对象补点实施方案](#52-8个高频可交互对象补点实施方案)

---

## 1. 痛点分析：意图合理但动作承接不足

在沙盒模拟中，常常出现“大模型脑部生成的意图完全合理，但底层动作和物体状态承接不住”的工程问题（如：小人打算去锻炼、想去厨房烧饭，但最后都只能回退到泛化的 use/work 动作，或直接因为找不到相应家具导致 A* 寻路崩溃重决策）。

**核心结论**：系统当前的瓶颈不在于大模型没有逻辑，而在于**物理小镇地图暴露不完整，底层资源点缺失，且缺乏语义化、细粒度的可交互动作支持**。我们应当“补充环境设施、扩充技能包以匹配真实物理世界”，而不是强行缩窄大模型的智能空间。

---

## 2. 静态底图定义 vs 3人基线暴露现状

地图资产可对照以下两层数据：

1.  **底图静态定义**（源自 `sector_blocks.csv`, `arena_blocks.csv`, `game_object_blocks.csv`）：代表理论上的小镇骨架，包含了各种商业中心（Hobbs Cafe, Willows Pharmacy）、学院、公园以及十余个居民住宅区（Arthur, Ryan, Giorgio... 等公寓与独栋别墅），以及 `toaster`, `shower`, `bed`, `tv`, `computer`, `easel` 等丰富的家具定义。
2.  **3人基线实际暴露范围**（源自 `personas/*/bootstrap_memory/spatial_memory.json`）：仅包含 Hobbs Cafe、宿舍（Dorm）部分房间、学院图书馆等极少公共场所。绝大多数静态住宅、厨房家电和健身设施由于没有写入小人的初始空间记忆，对其表现为不可达。

这种“信息割裂”导致许多合理的日常意图最后只能回退为 generic object 或 generic use 结算。

---

## 3. 技能库扩展路线图 (Skills Backlog)

为承接大模型自由思考产出的日常行为，技能库需要逐步由 generic use 升级为专业语义结算：

### 3.1 基础生存类 (已稳定闭环)
*   `gather` (采集)、`consume` (进食)、`rest` (休息/睡觉)。

### 3.2 待扩展的日常行为类 (急需提升真实感)
*   **日常生活**：`read` (阅读 $\rightarrow$ 对应 bookshelf/library table)、`write/study` (写作 $\rightarrow$ 对应 desk/computer)、`groom` (洗漱 $\rightarrow$ 对应 bathroom sink/mirror)、`exercise` (健身 $\rightarrow$ 对应 gym/fitness machine)。
*   **环境观察**：`inspect_object` (检查冰箱是否有苹果)、`observe_environment` (低开销地感应周围动态事件)。
*   **社交协作**：`wait_for_service` (在咖啡馆排队)、`ask_for_help` (求助)、`trade` (道具与物资置换)。

---

## 4. 地图设施补全优先级清单 (P0 / P1 / P2)

为支持智能体代谢与 ReAct 求生，必须优先把未暴露的底图设施接进 Baseline：

### P0 级：生存与核心代谢相关（立刻补入）
1.  **Dorm for Oak Hill College $\rightarrow$ `kitchen`**：整个宿舍的核心厨房，包含 `refrigerator` (冰箱) 和 `stove` (炉灶)。
2.  **户外公共资源 $\rightarrow$ `apple tree` (苹果树)**：在公园（Johnson Park）或宿舍花园暴露苹果树资源。
3.  **宿舍与住宅公共区 $\rightarrow$ `tv` (电视) 和 `sofa` (沙发)**：承接 Recreate 放松意图。

### P1 级：居住空间与职业技能相关（第二批补入）
1.  **整片缺失的 sector 住宅区**：如 `Arthur Burton's apartment`、`Ryan Park's apartment`、`Lin family's house`，增加真实居住与睡眠区域。
2.  **Dorm $\rightarrow$ `common room`**：补全 `computer desk` (电脑桌)、`computer` (电脑)，用以承接 Klaus 撰写论文与打游戏的职业动作。

### P2 级：娱乐、锻炼与扩展（第三批补入）
1.  **运动空间 $\rightarrow$ `gym-like area`**：暴露 `lifting weight` (杠铃)、`fitness machine` (健身器械)，承接锻炼和锻炼 XP。
2.  **学院与商业周边**：如 `Oak Hill College -> library` 书架补点。

---

## 5. 地图补点技术实施与文件定位 (Patch Guide)

### 5.1 地图补点三种模式
当要为基线小镇新增或补全一个可交互对象时，技术上属于以下三种模式之一：

*   **模式 A：静态底图已经画好，只是当前 Baseline 角色脑海中没认知**
    *   *判断*：在 `game_object_blocks.csv` 里可以搜到该物体坐标，但小人的 `spatial_memory.json` 里没有该层级 KV。
    *   *动作*：**无需修改底图 CSV**。只需直接修改角色 bootstrap 目录下的 `spatial_memory.json`，在对应的 sector $\rightarrow$ arena $\rightarrow$ object 字典树下写入该物体名称即可。
*   **模式 B：静态底图存在该对象名称，但没有铺设到目标坐标瓦片**
    *   *判断*：该对象类型已注册，但目标区域的 tile 没有涂上这个对象的 ID。
    *   *动作*：必须首先修改 `game_object_blocks.csv`，在对应的 `(x, y)` 瓦片网格上填入该物体名称以完成物理实体铺设；然后再把该对象名字加入小人的 `spatial_memory.json`。
*   **模式 C：对象连底图静态定义都没有**
    *   *判断*：如地图中不存在“苹果树”这一对象类型。
    *   *动作*：
        1. 在 `game_object_blocks.csv` 中挑选空闲地块，涂上新的对象名称（如 `apple_tree`）；
        2. 将新对象加入小人的 `spatial_memory.json` 中；
        3. 在 `backend_server/maze.py` 的可交互物品列表（以及执行层 addresses 校验）中注册该新类。

### 5.2 8个高频可交互对象补点实施方案

#### 1) 宿舍厨房 stove (炉灶)
*   **模式**：模式 A。
*   **底图状态**：静态底图已定义于 `Dorm for Oak Hill College:kitchen:stove` (坐标 63, 14)。
*   **实施方案**：在 Klaus, Isabella, Maria 对应的 `spatial_memory.json` 中的 `"Dorm for Oak Hill College"` $\rightarrow$ `"kitchen"` 数组下追加字符串 `"stove"`。

#### 2) 宿舍厨房 toaster (烤面包机)
*   **模式**：模式 A。
*   **底图状态**：底图已定义 (坐标 64, 15)。
*   **实施方案**：在三人的 `spatial_memory.json` 的 `"kitchen"` 下追加 `"toaster"` 字段。

#### 3) 户外 apple tree (苹果树)
*   **模式**：模式 C (新增对象)。
*   **底图状态**：底图未定义。
*   **实施方案**：
    *   在 `game_object_blocks.csv` 中选取宿舍花园 (坐标 53, 9) 标记为 `apple_tree`；
    *   在三人的 `spatial_memory.json` 中的 `"Dorm for Oak Hill College"` $\rightarrow$ `"garden"` 数组下追加 `"apple_tree"`；
    *   在 `maze.py` 中注册 `apple_tree` 并标记为食物产出源。

#### 4) 健身器械 fitness machine (健身房)
*   **模式**：模式 B (对象存在但没有铺设坐标)。
*   **底图状态**：已注册，但底图瓦片未挂载。
*   **实施方案**：
    *   在 `game_object_blocks.csv` 选取空闲坐标涂上 `fitness machine`；
    *   在小人的 `spatial_memory.json` 的目标 sector $\rightarrow$ arena 中追加 `"fitness machine"`。

#### 5) 电脑电脑桌 computer & computer desk
*   **模式**：模式 A。
*   **底图状态**：静态地图已铺好 `Dorm for Oak Hill College:Klaus Mueller's room:computer desk` (坐标 63, 21)。
*   **实施方案**：在 Klaus 的 `spatial_memory.json` 对应的卧室下追加 `"computer desk"` 与 `"computer"`。

#### 6) 宿舍电视 tv
*   **模式**：模式 A。
*   **底图状态**：已铺设在 `Dorm for Oak Hill College:common room:tv` (坐标 60, 26)。
*   **实施方案**：在三人的 `spatial_memory.json` 的 `"common room"` 下追加 `"tv"`。

#### 7) 宿舍哑铃/杠铃 lifting weight
*   **模式**：模式 A。
*   **底图状态**：已铺设在 `Dorm for Oak Hill College:common room:lifting weight` (坐标 56, 26)。
*   **实施方案**：在三人的 `spatial_memory.json` 的 `"common room"` 下追加 `"lifting weight"`。
