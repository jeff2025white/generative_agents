# Generative Agents 模拟器后台命令操作指南

本指南整理了在运行 **Generative Agents**（生成式智能体）模拟器后端服务 `reverie.py` 时，在交互式命令行提示符 `Enter option: ` 处可以使用的所有指令。

---

## 1. 基础控制与保存指令

这些指令用于控制模拟器本身的运行状态、进度保存与安全退出。

| 命令 | 描述 | 示例 | 备注 |
| :--- | :--- | :--- | :--- |
| `save` | 保存当前的模拟进度。 | `save` | 进度会被写入 `environment/frontend_server/storage/<sim-name>` 目录。 |
| `fin` <br> `f` <br> `finish` <br> `save and finish` | 保存当前的模拟进度，并**安全退出**模拟器。 | `fin` | 推荐的正常退出方式。 |
| `exit` | **直接退出**模拟器而不保存进度。 | `exit` | **警告**：该操作会**彻底删除**当前模拟的所有已存临时和进度数据。 |

---

## 2. 模拟运行指令

用于驱动模拟世界中的时间向前推进。

| 命令 | 描述 | 示例 | 备注 |
| :--- | :--- | :--- | :--- |
| `run <step-count>` | 向前运行指定步数的模拟。 | `run 100` | 每一游戏步代表游戏内时间 **10 秒**。<br> 运行 100 步相当于模拟 1000 秒（约 16.7 分钟）。 |

---

## 3. 数据加载与初始化指令

用于在模拟世界初始化时加载外部预设配置。

| 命令 | 描述 | 示例 | 备注 |
| :--- | :--- | :--- | :--- |
| `call -- load history the_ville/<file_name>.csv` | 在启动阶段为所有智能体批量加载初始记忆历史。 | `call -- load history the_ville/agent_history_init_n3.csv` | 必须在模拟刚启动且处于 `Enter option: ` 提示时输入。<br> 配置文件需存放在 `environment/frontend_server/static_dirs/assets/the_ville/` 目录下。 |

---

## 4. 智能体（Persona）状态查询指令

用于探测、监控或调试特定智能体的记忆流、日程安排、位置和交互缓冲。

| 命令 | 描述 | 示例 | 备注 |
| :--- | :--- | :--- | :--- |
| `print persona schedule <Persona Name>` | 打印智能体已被拆解后的**今日日程表摘要**（Decomposed Schedule）。 | `print persona schedule Isabella Rodriguez` | 展示智能体当前的具体行为安排。 |
| `print all persona schedule` | 打印当前世界中**所有**智能体的今日日程表摘要。 | `print all persona schedule` | 方便快速浏览全体智能体的今日计划。 |
| `print hourly org persona schedule <Persona Name>` | 打印智能体原始的、每小时计划的日程安排表（未拆解版）。 | `print hourly org persona schedule Isabella Rodriguez` | 查阅智能体未经时间细化拆解的初始计划。 |
| `print persona current tile <Persona Name>` | 打印智能体当前在地图上的瓦片坐标 `(x, y)`。 | `print persona current tile Isabella Rodriguez` | 对应游戏地图瓦片坐标，有助于调试寻路和碰撞。 |
| `print persona chatting with buffer <Persona Name>` | 打印智能体与其他智能体的聊天缓冲状态。 | `print persona chatting with buffer Isabella Rodriguez` | 显示智能体正在与谁对话，以及对话的计数/频率。 |
| `print persona associative memory (event) <Persona Name>` | 打印智能体关联记忆流中的所有**事件（Event）**记录序列。 | `print persona associative memory (event) Isabella Rodriguez` | 查阅智能体经历和观察到的所有事件。 |
| `print persona associative memory (thought) <Persona Name>` | 打印智能体关联记忆流中的所有**想法/反思（Thought）**记录序列。 | `print persona associative memory (thought) Isabella Rodriguez` | 查阅智能体对事件的思考与高层级反思。 |
| `print persona associative memory (chat) <Persona Name>` | 打印智能体关联记忆流中的所有**对话/聊天（Chat）**记录序列。 | `print persona associative memory (chat) Isabella Rodriguez` | 查阅智能体与其他角色对话的历史记忆。 |
| `print persona spatial memory <Persona Name>` | 以树状结构输出该智能体对 Smallville 城镇空间结构的**空间记忆树**。 | `print persona spatial memory Isabella Rodriguez` | 展示智能体脑海里对房屋、家具、地图层级的分布认知。 |
| `call -- analysis <Persona Name>` | 启动与指定智能体的**无状态交互会话**。 | `call -- analysis Isabella Rodriguez` | 用于调试和测试，可以直接向智能体提问或对话，但**不会**存入智能体的记忆流中。 |

---

## 5. 地图与环境查询指令

用于探测模拟世界的当前时间、特定瓦片的状态和发生的事件。

| 命令 | 描述 | 示例 | 备注 |
| :--- | :--- | :--- | :--- |
| `print current time` | 打印模拟世界当前的虚拟日期时间，以及目前已走的总步数。 | `print current time` | 输出格式例如：`June 25, 2022, 00:00:00`。 |
| `print tile event <x>, <y>` | 打印指定坐标瓦片上正在发生的所有事件描述。 | `print tile event 50, 30` | 格式为 `x, y`（用逗号分隔）。 |
| `print tile details <x>, <y>` | 打印指定坐标瓦片的详细属性信息。 | `print tile details 50, 30` | 包含阻挡状态、所属房间、包含的家具等。 |

---

## 6. 其他辅助调试指令

| 命令 | 描述 | 示例 | 备注 |
| :--- | :--- | :--- | :--- |
| `start path tester mode` | 开启路径测试服务。 | `start path tester mode` | **警告**：此操作会**清空并删除**当前 fork 的模拟文件夹。退出后需要重启才能运行普通模拟。 |
