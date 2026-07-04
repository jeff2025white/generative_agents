# 地图优先补全清单

本文档是方案 A 的直接产物，用来回答：

- 当前 `base_the_ville_isabella_maria_klaus` 这套 3 人基线，地图里优先应该补哪些对象
- 哪些是**静态地图已经定义，但当前基线没有暴露**
- 哪些是**静态地图里都还没有，但为了更接近真实世界，建议新增**

这份清单尽量精确到：

```text
sector -> arena -> object
```

---

## 1. 当前判断标准

本清单基于两层对照：

### 1.1 静态地图定义

来源：

- `sector_blocks.csv`
- `arena_blocks.csv`
- `game_object_blocks.csv`

它代表“理论上地图应有的骨架”。

### 1.2 当前 3 人基线已暴露内容

来源：

- `storage/base_the_ville_isabella_maria_klaus/personas/*/bootstrap_memory/spatial_memory.json`

它代表“当前仿真基线里人物真正知道并能稳定感知到的设施与对象”。

---

## 2. 当前基线最核心的问题

当前地图不是完全没有东西，而是出现了 3 类明显缺口：

- 整片住宅与生活空间没有进入当前基线
- 关键厨房/户外生存对象没有真正落地
- 娱乐/锻炼目标词已经出现，但地图里缺少相应现代对象

这会直接导致：

- `exercise / watch / prepare_food / observe_environment` 这类意图承接困难
- 目标解析只能退到 generic object 或 arena
- 很多本来合理的行为看起来像“模型不会”，但本质是“地图没给身体能力”

---

## 3. 第一类：静态已定义，但当前基线未暴露

这类最值得优先补，因为：

- 地图底层已经有定义
- 不需要先改地图规范
- 更像是“把已有资源接进当前世界”

## 3.1 整片缺失的 sector

下面这些 sector 静态地图里已经存在，但当前 3 人基线里完全没进入空间记忆：

- `artist's co-living space`
- `Arthur Burton's apartment`
- `Ryan Park's apartment`
- `Giorgio Rossi's apartment`
- `Carlos Gomez's apartment`
- `Adam Smith's house`
- `Yuriko Yamamoto's house`
- `Moore family's house`
- `Tamara Taylor and Carmen Ortiz's house`
- `Moreno family's house`
- `Lin family's house`

### 为什么优先级高

- 这些空间能直接增加“真实居住场景”
- 会补出厨房、卫生间、卧室、共用空间、花园
- 能自然承接：
  - 做饭
  - 整理
  - 休息
  - 观察
  - 社交协作

---

## 3.2 当前基线缺失的关键 arena

下面这些 arena 在静态地图中存在，但当前 3 人基线没有暴露，优先建议从高价值空间开始接入。

### P0 级：立即值得暴露

#### `Dorm for Oak Hill College -> kitchen`

当前宿舍已经有：

- `common room`
- `bathroom`
- `garden`
- `Klaus/Maria 房间`

但缺：

- `kitchen`

这是当前最不合理的空洞之一，因为：

- 宿舍场景本来就应该能承接做饭/取食/整理
- 但现在学生宿舍没有真正可用厨房

#### `Isabella Rodriguez's apartment -> bathroom`

当前 Isabella 公寓只暴露了：

- `main room`

缺：

- `bathroom`

这会削弱：

- 清洁
- 洗漱
- 卫生相关行为

#### `Ayesha Khan's room`
#### `Wolfgang Schulz's room`

这两个房间静态已定义，但当前基线未暴露。  
如果后续要扩更多角色或增加生活多样性，它们是很自然的补点。

### P1 级：第二批应接入

#### `artist's co-living space -> common room`
#### `artist's co-living space -> kitchen`

这是非常有价值的一组空间：

- 合租 common room 天然适合社交与协作
- kitchen 天然适合饮食链与共享资源
- 还能够承接艺术类对象

#### 家庭住宅中的这些 arena

- `common room`
- `kitchen`
- `garden`
- `bathroom`

尤其包括：

- `Tamara Taylor and Carmen Ortiz's house`
- `Moreno family's house`
- `Lin family's house`

这些空间一旦接入，会直接让“家庭生活”变得更像真实世界。

---

## 3.3 当前静态已定义、但基线未暴露的关键对象

下面这些对象在 `game_object_blocks.csv` 已有定义，但当前基线里没有出现。

### 高优先级缺失对象

- `lifting weight`
- `computer desk`
- `toaster`
- `guitar`
- `easel`
- `garden chair`
- `house garden`
- `harp`

---

## 4. 第二类：静态已定义对象的精确补点建议

这一部分不是泛泛地说“补对象”，而是尽量给出更适合的落点。

## 4.1 `Dorm for Oak Hill College -> kitchen`

### 应优先补入对象

- `refrigerator`
- `kitchen sink`
- `cooking area`
- `toaster`
- `common room table` 或 dining-like table

### 原因

- 当前宿舍没有厨房，会让学生日常生存高度依赖咖啡馆或房间冰箱
- `toaster` 已经在静态对象里定义，但当前基线未暴露
- 这是补“低成本真实感”的最佳位置

---

## 4.2 `Dorm for Oak Hill College -> common room`

当前 common room 已有：

- `common room sofa`
- `pool table`
- `common room table`

### 建议补点

- `lifting weight`
- `game console`

### 原因

- 当前高频意图里已经有“锻炼”“休闲”“用器械”
- 静态对象里已有 `lifting weight`
- 在 dorm common room 暴露它，能最直接支撑 `exercise`

---

## 4.3 `Oak Hill College -> library`

当前 library 已有：

- `library sofa`
- `library table`
- `bookshelf`

### 建议补点

- `computer desk`
- `computer`

### 原因

- `computer desk` 在静态对象中已定义，但当前基线没暴露
- 这会自然支撑：
  - `read`
  - `write`
  - `study`
  - `research`

---

## 4.4 `artist's co-living space`

### common room 建议补点

- `easel`
- `guitar`
- `harp`
- `microphone`

### kitchen 建议补点

- `refrigerator`
- `kitchen sink`
- `cooking area`
- `toaster`

### 原因

- 这是最适合承接“创作/排练/共同生活”的地方
- 现有对象定义已经够支撑一批艺术与娱乐 skill
- 但当前基线完全没有把它们接进来

---

## 4.5 家庭住宅 garden / common room

### garden 建议补点

- `house garden`
- `garden chair`

### common room / main room 建议补点

- `desk`
- `shelf`
- `computer desk`

### 原因

- 当前户外生活几乎只有 `park garden` 和 `dorm garden`
- 家庭花园缺失会让居住空间非常“室内化”
- `garden chair` 已静态定义，补进去成本低但真实感收益高

---

## 5. 第三类：静态地图里都还没有，但强烈建议新增

这类不是“暴露已有资源”，而是“地图规范本身应升级”。

## 5.1 厨房生存对象

当前最明显缺失：

- `stove`
- `pantry`
- `dining table`
- `trash bin`

### 为什么必须补

- 当前食物合法来源里有 `stove`
- 但静态对象中根本没有 `stove`
- 这会形成系统规则和地图设施的直接断裂

所以 `stove` 是当前最值得立刻新增的对象之一。

---

## 5.2 户外食物资源

当前最明显缺失：

- `apple tree`
- `berry bush`
- `park bench`
- `community garden`

### 为什么必须补

- 当前合法食物来源里有 `apple tree`
- 但地图静态对象与当前基线里都没有
- 这让“户外觅食”只停留在规则层，没有真实落点

---

## 5.3 现代娱乐对象

当前最明显缺失：

- `tv`
- `fitness machine`
- `exercise machine`
- `treadmill`
- `exercise bike`

### 为什么必须补

- 当前语言意图和 resolver 已经频繁出现这些词
- 但静态地图没有对应对象
- 这会使目标解析被迫退回到：
  - `pool table`
  - `common room`
  - 或其他语义接近对象

这类错配会直接污染实验结果。

---

## 6. 最推荐的优先补全顺序

下面给出一版可直接执行的顺序。

## P0：立刻补

### 设施 / arena

- `Dorm for Oak Hill College -> kitchen`
- `Isabella Rodriguez's apartment -> bathroom`

### 静态已定义对象

- `lifting weight`
- `computer desk`
- `toaster`

### 静态未定义但建议新增

- `stove`
- `apple tree`
- `tv`
- `fitness machine`

### 这批的价值

- 直接补齐：
  - 饮食链
  - 学习/工作链
  - 锻炼链
  - 娱乐链

---

## P1：第二批补

### sector / arena

- `artist's co-living space -> common room`
- `artist's co-living space -> kitchen`
- `Tamara Taylor and Carmen Ortiz's house -> common room / kitchen / garden`
- `Lin family's house -> common room / kitchen / garden`
- `Moreno family's house -> common room / kitchen / garden`

### 对象

- `easel`
- `guitar`
- `harp`
- `garden chair`
- `house garden`

### 这批的价值

- 补艺术、家庭、合租、户外生活
- 增强非生存型真实日常行为

---

## P2：第三批补

### sector

- 其余单人公寓和家庭住宅全面接入当前基线

### 新增对象

- `berry bush`
- `park bench`
- `community garden`
- `treadmill`
- `exercise bike`

### 这批的价值

- 进一步接近真实世界，而不是只补“刚好能跑通动作”的对象

---

## 7. 一张精简执行表

下面这张表可以直接作为下一步补地图的 backlog。

## 7.1 静态已定义但当前基线没暴露

- `Dorm for Oak Hill College -> kitchen -> refrigerator / kitchen sink / cooking area / toaster`
- `Dorm for Oak Hill College -> common room -> lifting weight / game console`
- `Oak Hill College -> library -> computer desk / computer`
- `artist's co-living space -> common room -> easel / guitar / harp / microphone`
- `artist's co-living space -> kitchen -> refrigerator / kitchen sink / cooking area / toaster`
- `家庭住宅 -> garden -> house garden / garden chair`
- `Isabella Rodriguez's apartment -> bathroom -> bathroom sink / shower / toilet`

## 7.2 静态地图都还没有，建议新增

- `厨房链 -> stove / pantry / dining table / trash bin`
- `户外生存链 -> apple tree / berry bush / park bench / community garden`
- `娱乐锻炼链 -> tv / fitness machine / treadmill / exercise bike`

---

## 8. 最终建议

如果你下一步真的要开始补地图，我最推荐的第一批不是“到处加很多东西”，而是这 8 个点：

- `Dorm kitchen`
- `stove`
- `apple tree`
- `lifting weight`
- `computer desk`
- `toaster`
- `tv`
- `fitness machine`

因为这 8 个点能最直接支撑：

- 生存
- 学习
- 锻炼
- 娱乐

同时又能显著降低“模型意图合理，但地图没有身体能力承接”的问题。

