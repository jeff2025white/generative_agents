# 地图补点文件定位说明

本文档对应方案 `A1`，目标是把上一份 backlog 里最优先的 8 个补点，继续映射到**具体应修改的文件层**。

核心不是马上改地图，而是先回答三个问题：

- 这个补点现在是“已经铺在静态地图里”还是“只有名字没有 tile”？
- 真正要补它时，应该改 `special_blocks/*.csv`、`maze/*.csv`，还是 `bootstrap_memory`？
- 对当前 `base_the_ville_isabella_maria_klaus` 基线，补完后要不要同步处理初始空间记忆？

---

## 1. 先说结论：地图补点有 3 种模式

结合 `maze.py` 的装载方式，可以把补点分成 3 类。

### 模式 A：静态地图已经铺好，只是当前基线没认知到

这种情况说明：

- `special_blocks/*.csv` 已有定义
- `maze/*.csv` 已经有对应 tile
- 但 `storage/.../bootstrap_memory/spatial_memory.json` 没把它带进当前基线

这类补点**不一定要改地图本身**，最小动作是二选一：

- 直接补当前基线的 `bootstrap_memory/spatial_memory.json`
- 或者重建一次基线初始化记忆，让 persona 从静态地图重新生成空间记忆

### 模式 B：对象名已经注册，但没有铺到目标 tile

这种情况说明：

- `game_object_blocks.csv` 已有对象编号
- 但 `game_object_maze.csv` 里没有放到你想要的 arena

这类补点至少需要：

- 修改 `maze/game_object_maze.csv`
- 然后更新 `bootstrap_memory` 或重建初始化记忆

### 模式 C：对象连静态定义都没有

这种情况说明：

- `game_object_blocks.csv` 里还没有这个对象
- `game_object_maze.csv` 里当然也没有 tile

这类补点至少需要：

- 先给 `special_blocks/game_object_blocks.csv` 新增对象编号
- 再修改 `maze/game_object_maze.csv`
- 最后更新 `bootstrap_memory` 或重建初始化记忆

---

## 2. 文件层职责

结合 `reverie/backend_server/maze.py`，这几层文件的职责已经很明确：

- `environment/frontend_server/static_dirs/assets/the_ville/matrix/special_blocks/sector_blocks.csv`
  - 定义 sector 编号和名称
- `environment/frontend_server/static_dirs/assets/the_ville/matrix/special_blocks/arena_blocks.csv`
  - 定义 arena 编号和名称
- `environment/frontend_server/static_dirs/assets/the_ville/matrix/special_blocks/game_object_blocks.csv`
  - 定义 game object 编号和名称
- `environment/frontend_server/static_dirs/assets/the_ville/matrix/maze/sector_maze.csv`
  - 把 sector 编号铺到 tile
- `environment/frontend_server/static_dirs/assets/the_ville/matrix/maze/arena_maze.csv`
  - 把 arena 编号铺到 tile
- `environment/frontend_server/static_dirs/assets/the_ville/matrix/maze/game_object_maze.csv`
  - 把 object 编号铺到 tile
- `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/*/bootstrap_memory/spatial_memory.json`
  - 决定当前 3 人基线开局“知道哪些空间和对象”

因此：

- arena 已存在且已铺 tile，但 persona 不知道：改 `bootstrap_memory` 或重建
- object 已有编号，但没放进目标房间：改 `game_object_maze.csv`
- object 连编号都没有：先改 `game_object_blocks.csv`，再改 `game_object_maze.csv`

---

## 3. 8 个优先补点逐项定位

下面按当前最推荐的 8 个点逐个给出文件落点。

## 3.1 `Dorm for Oak Hill College -> kitchen`

### 当前状态

- `arena_blocks.csv` 已定义：`32173 -> Dorm for Oak Hill College -> kitchen`
- `arena_maze.csv` 已铺 tile：共 `15` 个 tile
- 采样坐标范围：`x=118..124, y=45..49`
- 这个 kitchen 里已经有：
  - `toaster`
  - `kitchen sink`
  - `refrigerator`
  - `cooking area`

也就是说，这个补点不是“地图里没有厨房”，而是“当前基线没把厨房带进空间记忆”。

### 当前缺口

- `Klaus Mueller` 的 `spatial_memory.json` 没有 `Dorm for Oak Hill College -> kitchen`
- `Maria Lopez` 的 `spatial_memory.json` 也没有

### 应修改文件

- 必须：
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Klaus Mueller/bootstrap_memory/spatial_memory.json`
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Maria Lopez/bootstrap_memory/spatial_memory.json`
- 可选替代：
  - 不手改 JSON，改为跑一次新的初始化/探索生成流程

### 是否需要改静态地图

- 不需要改 `arena_blocks.csv`
- 不需要改 `arena_maze.csv`
- 不需要改 `game_object_maze.csv`

### 结论

- 这是标准的**模式 A**

---

## 3.2 `stove`

### 当前状态

- `game_object_blocks.csv` 中没有 `stove`
- `game_object_maze.csv` 中也没有 `stove`

### 推荐落点

第一批最适合放在：

- `Dorm for Oak Hill College -> kitchen`

原因：

- 这个 arena 已存在且已铺好 tile
- 当前饮食链合法来源里本来就有 `stove`
- 放在 dorm kitchen 可以直接服务当前 2 个宿舍角色

### 应修改文件

- 必须：
  - `environment/frontend_server/static_dirs/assets/the_ville/matrix/special_blocks/game_object_blocks.csv`
  - `environment/frontend_server/static_dirs/assets/the_ville/matrix/maze/game_object_maze.csv`
- 然后处理：
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Klaus Mueller/bootstrap_memory/spatial_memory.json`
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Maria Lopez/bootstrap_memory/spatial_memory.json`
  - 或统一重建初始化记忆

### 是否需要改 arena / sector

- 不需要
- 直接挂到现有 `Dorm kitchen` 即可

### 结论

- 这是标准的**模式 C**

---

## 3.3 `apple tree`

### 当前状态

- `game_object_blocks.csv` 中没有 `apple tree`
- `game_object_maze.csv` 中也没有 `apple tree`

### 推荐落点

第一批最适合放在：

- `Johnson Park -> park`

现有证据：

- `arena_blocks.csv` 已定义：`32142 -> Johnson Park -> park`
- `arena_maze.csv` 已铺 tile：`137` 个 tile
- 坐标范围：`x=21..35, y=41..51`
- 当前已有对象：`park garden`

### 应修改文件

- 必须：
  - `environment/frontend_server/static_dirs/assets/the_ville/matrix/special_blocks/game_object_blocks.csv`
  - `environment/frontend_server/static_dirs/assets/the_ville/matrix/maze/game_object_maze.csv`
- 然后处理：
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Klaus Mueller/bootstrap_memory/spatial_memory.json`
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Maria Lopez/bootstrap_memory/spatial_memory.json`
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Isabella Rodriguez/bootstrap_memory/spatial_memory.json`
  - 或统一重建初始化记忆

### 是否需要改 arena / sector

- 不需要
- `Johnson Park -> park` 已经足够承接

### 结论

- 这是标准的**模式 C**

---

## 3.4 `lifting weight`

### 当前状态

- `game_object_blocks.csv` 已定义：`32272 -> lifting weight`
- `game_object_maze.csv` 已有铺设：共 `2` 个 tile
- 当前落点在：
  - `Dorm for Oak Hill College -> Wolfgang Schulz's room`

这说明它不是“地图完全没有”，而是“放在当前基线几乎不可见的位置”。

### 推荐落点

为了让当前基线更容易触发锻炼行为，第一批建议再补到：

- `Dorm for Oak Hill College -> common room`

现有证据：

- `arena_blocks.csv` 已定义：`32163 -> Dorm for Oak Hill College -> common room`
- `arena_maze.csv` 已铺 tile：`71` 个 tile
- 坐标范围：`x=113..123, y=46..54`
- 当前已有对象：
  - `common room sofa`
  - `common room table`
  - `pool table`

### 应修改文件

- 必须：
  - `environment/frontend_server/static_dirs/assets/the_ville/matrix/maze/game_object_maze.csv`
- 然后处理：
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Klaus Mueller/bootstrap_memory/spatial_memory.json`
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Maria Lopez/bootstrap_memory/spatial_memory.json`
  - 或统一重建初始化记忆

### 是否需要改 `game_object_blocks.csv`

- 不需要
- 因为 `lifting weight` 编号已经存在

### 结论

- 这是标准的**模式 B**

---

## 3.5 `computer desk`

### 当前状态

- `game_object_blocks.csv` 已定义：`32220 -> computer desk`
- `game_object_maze.csv` 已有铺设：共 `1` 个 tile
- 当前落点在：
  - `Ryan Park's apartment -> main room`

这说明它也是“地图里有，但落点不服务当前基线”的情况。

### 推荐落点

第一批建议补到：

- `Oak Hill College -> library`

现有证据：

- `arena_blocks.csv` 已定义：`32191 -> Oak Hill College -> library`
- `arena_maze.csv` 已铺 tile：`67` 个 tile
- 坐标范围：`x=118..124, y=19..29`
- 当前已有对象：
  - `bookshelf`
  - `library sofa`
  - `library table`

### 应修改文件

- 必须：
  - `environment/frontend_server/static_dirs/assets/the_ville/matrix/maze/game_object_maze.csv`
- 然后处理：
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Klaus Mueller/bootstrap_memory/spatial_memory.json`
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Maria Lopez/bootstrap_memory/spatial_memory.json`
  - 或统一重建初始化记忆

### 是否需要改 `game_object_blocks.csv`

- 不需要
- 因为 `computer desk` 编号已经存在

### 结论

- 这是标准的**模式 B**

---

## 3.6 `toaster`

### 当前状态

- `game_object_blocks.csv` 已定义：`32248 -> toaster`
- `game_object_maze.csv` 已有铺设：共 `2` 个 tile
- 当前已存在于：
  - `artist's co-living space -> kitchen`
  - `Dorm for Oak Hill College -> kitchen`

也就是说，`toaster` 其实已经落在我们最想要的 `Dorm kitchen` 里了。

### 当前缺口

不是地图没放，而是：

- `Dorm kitchen` 没进入 `Klaus` / `Maria` 的初始空间记忆

### 应修改文件

- 必须：
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Klaus Mueller/bootstrap_memory/spatial_memory.json`
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Maria Lopez/bootstrap_memory/spatial_memory.json`
- 可选替代：
  - 统一重建初始化记忆

### 是否需要改静态地图

- 不需要改 `game_object_blocks.csv`
- 不需要改 `game_object_maze.csv`

### 结论

- 这是标准的**模式 A**

---

## 3.7 `tv`

### 当前状态

- `game_object_blocks.csv` 中没有 `tv`
- `game_object_maze.csv` 中也没有 `tv`

### 推荐落点

最小可行补法有两个候选：

- `Dorm for Oak Hill College -> common room`
- `Isabella Rodriguez's apartment -> main room`

如果只做一处、优先服务更多人，建议先放：

- `Dorm for Oak Hill College -> common room`

如果想让当前 3 人基线都能较快接触到 `tv`，建议同时放两处：

- `Dorm common room`
- `Isabella main room`

现有 arena 均已存在并已铺 tile，因此不需要先扩 arena。

### 应修改文件

- 必须：
  - `environment/frontend_server/static_dirs/assets/the_ville/matrix/special_blocks/game_object_blocks.csv`
  - `environment/frontend_server/static_dirs/assets/the_ville/matrix/maze/game_object_maze.csv`
- 然后处理：
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Klaus Mueller/bootstrap_memory/spatial_memory.json`
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Maria Lopez/bootstrap_memory/spatial_memory.json`
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Isabella Rodriguez/bootstrap_memory/spatial_memory.json`
  - 或统一重建初始化记忆

### 是否需要改 arena / sector

- 不需要
- 直接挂到现有 common room / main room 即可

### 结论

- 这是标准的**模式 C**

---

## 3.8 `fitness machine`

### 当前状态

- `game_object_blocks.csv` 中没有 `fitness machine`
- `game_object_maze.csv` 中也没有 `fitness machine`

### 推荐落点

如果按“第一批最小改动”原则，建议先补在：

- `Dorm for Oak Hill College -> common room`

原因：

- 该 arena 已存在
- 当前 `Klaus` / `Maria` 已知这个 common room
- 不需要先新建 gym sector / arena

长期更合理的方案是后续新增专门 gym 或 sports arena，但不属于这批 8 点的最小落地范围。

### 应修改文件

- 必须：
  - `environment/frontend_server/static_dirs/assets/the_ville/matrix/special_blocks/game_object_blocks.csv`
  - `environment/frontend_server/static_dirs/assets/the_ville/matrix/maze/game_object_maze.csv`
- 然后处理：
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Klaus Mueller/bootstrap_memory/spatial_memory.json`
  - `environment/frontend_server/storage/base_the_ville_isabella_maria_klaus/personas/Maria Lopez/bootstrap_memory/spatial_memory.json`
  - 或统一重建初始化记忆

### 是否需要改 arena / sector

- 这批最小方案下不需要
- 如果后续要做更真实的锻炼系统，再考虑新增 gym 相关 arena

### 结论

- 这是标准的**模式 C**

---

## 4. 一张总表

| 补点 | 当前真实状态 | 首要修改文件 | 是否需要改 `bootstrap_memory` |
| --- | --- | --- | --- |
| `Dorm kitchen` | arena 已存在且已铺 tile，但基线未认知 | `personas/*/bootstrap_memory/spatial_memory.json` 或重建 | 是 |
| `stove` | 静态对象未定义 | `game_object_blocks.csv` + `game_object_maze.csv` | 是 |
| `apple tree` | 静态对象未定义 | `game_object_blocks.csv` + `game_object_maze.csv` | 是 |
| `lifting weight` | 对象已定义且已铺在 Wolfgang 房间 | `game_object_maze.csv` | 是 |
| `computer desk` | 对象已定义且已铺在 Ryan 公寓 | `game_object_maze.csv` | 是 |
| `toaster` | 对象已定义且已铺在 Dorm kitchen，但基线未认知 | `personas/*/bootstrap_memory/spatial_memory.json` 或重建 | 是 |
| `tv` | 静态对象未定义 | `game_object_blocks.csv` + `game_object_maze.csv` | 是 |
| `fitness machine` | 静态对象未定义 | `game_object_blocks.csv` + `game_object_maze.csv` | 是 |

---

## 5. 最推荐的实施顺序

如果下一步真的开始改文件，我建议按下面顺序推进。

### 第一步：先做“只改记忆层”的低风险补点

- `Dorm kitchen`
- `toaster`

这一步的价值是：

- 不碰静态地图
- 直接验证“只是世界认知缺失，还是地图本体也有问题”

### 第二步：再做“已有对象换落点”的低成本补点

- `lifting weight -> Dorm common room`
- `computer desk -> Oak Hill College library`

这一步只需要改：

- `maze/game_object_maze.csv`

### 第三步：最后做“新增对象类型”的补点

- `stove`
- `apple tree`
- `tv`
- `fitness machine`

这一步才需要同时改：

- `special_blocks/game_object_blocks.csv`
- `maze/game_object_maze.csv`

---

## 6. 最终建议

如果下一步目标是“尽快让当前 3 人基线变得更像真实世界”，最推荐的策略不是一次性大改整张地图，而是按下面的节奏：

- 先确认 `Dorm kitchen` 这类静态已存在内容，只靠补 `bootstrap_memory` 是否就能显著改善行为
- 再把 `lifting weight`、`computer desk` 这种“有对象但落错位置”的资源迁到当前基线高频 arena
- 最后再新增 `stove`、`apple tree`、`tv`、`fitness machine` 这类全新对象类型

这样做的好处是：

- 每一步都能单独验证
- 更容易定位行为变化到底来自“地图认知”还是“地图物体”
- 不会一下子把空间、对象、技能三层问题混在一起
