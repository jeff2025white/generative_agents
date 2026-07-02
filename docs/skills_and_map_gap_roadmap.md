# Skills 缺口与地图设施资源补全路线图

本文档用于回答两个紧密相关的问题：

1. 当前为什么会出现“大模型意图合理，但动作承接不住”的现象
2. 地图上哪些设施、资源和可交互对象应该有，但当前 3 人基线并没有完整暴露出来

本文档的目标不是限制大模型去适应一个过于狭窄的沙盒，而是反过来推动：

- `skills` 更丰富
- 地图更接近真实生活空间
- 环境能承接更多真实世界式意图

---

## 1. 结论先行

当前系统的主瓶颈，更像是：

- 世界能力不够丰富
- 地图设施暴露不完整
- 很多高频日常意图只能被压缩到少数 generic skill

而不是：

- 大模型必须被强行驯化成只会“沙盒规则思维”

换句话说，当前更应该做的是：

```text
扩技能
+ 补设施
+ 补资源
+ 补对象可供性
```

而不是继续强化一套越来越重的“世界宪法”。

---

## 2. 当前 skill 体系现状

当前正式注册的 skill 主要分成 4 组：

### 2.1 生存类

- `gather`
- `consume`
- `rest`

### 2.2 生产/服务类

- `cook`
- `brew`
- `serve`

### 2.3 社交/表达类

- `chat with`
- `sing`

### 2.4 泛化兜底类

- `use`
- `work`
- `study`
- `leisure_use`

当前主要问题不在于“一个 skill 都没有”，而在于：

- 生存类已经有比较清晰的闭环
- 非生存类大量落到 `GenericActivitySkillPack`
- `GenericActivitySkillPack` 只做数值变化，不区分对象语义和物理后果

这会导致：

- `fitness machine`
- `tv`
- `game console`
- `pool table`
- `bookshelf`
- `desk`

这些对象虽然在语言上有差别，但最终常常只落成同样的 generic 结算。

---

## 3. 当前 skill 缺口判断

## 3.1 已经相对稳定的部分

### 觅食与进食

当前这条链已经相对稳定：

```text
低饱食
-> Gather
-> 背包获得食物
-> follow-up Consume
-> 饱食度恢复
```

说明：

- `gather`
- `consume`
- `rest`

这几个基础生存 skill 已经具备继续演进的价值，不是当前第一瓶颈。

## 3.2 真正薄弱的部分

### 对象型日常行为

当前最容易承接不住的，是这种意图：

- 去器械锻炼
- 去桌前学习/写作
- 用游戏机娱乐
- 看电视放松
- 去某个空间观察、停留、整理、准备

这些动作的共同问题是：

- 模型的高层意图通常是合理的
- 但系统里没有足够细的专门 skill
- 最后只能压缩进：
  - `use`
  - `work`
  - `study`
  - `leisure_use`

结果就是：

- 行为可执行，但不真实
- skill 命中率看起来不低，但“命中的都是泛 skill”
- 日志可解释性很差

---

## 4. 当前最缺的 skill 类型

下面不是最终完整清单，而是当前最值得优先扩的那一批。

## 4.1 生存增强类

这些 skill 不是当前完全没有，而是链条还不够完整。

- `inspect_object`
  - 检查对象状态，如冰箱里是否有食物、器械是否可用
- `search_resource`
  - 在空间中寻找目标资源，而不是直接神谕式知道对象
- `prepare_food`
  - 从“拿到原料”过渡到“可食用成品”
- `store_item`
  - 存放/整理背包物品
- `discard_item`
  - 丢弃无效物品
- `wait`
  - 合理等待，而不是不断重规划
- `observe_environment`
  - 以低成本方式扫描周边对象和状态

## 4.2 日常生活类

这些是最可能提升“真实世界感”的技能。

- `exercise`
  - 对应 `fitness machine / lifting weight / gym-like area`
- `watch`
  - 对应 `tv`
- `play_game`
  - 对应 `game console / pool table`
- `read`
  - 对应 `bookshelf / library table`
- `write`
  - 对应 `desk / computer`
- `clean`
  - 对应 kitchen / bathroom / shared space
- `organize`
  - 对应 shelf / desk / closet / storage
- `groom`
  - 对应 bathroom sink / mirror-like future objects

## 4.3 社交与协作类

这些会直接提升“是否能在真实环境里活下去”的观察价值。

- `ask_for_help`
- `request_resource`
- `offer_help`
- `trade`
- `assist`
- `follow_person`
- `warn`
- `wait_for_service`

当前只靠 `chat with` 还远远不够，因为真实环境里的社交并不是只有对话。

---

## 5. 当前地图静态上“应有”的设施骨架

从静态地图定义看，`the_ville` 本身并不贫瘠，底图已经给了相对丰富的空间层次。

## 5.1 已定义 sector

静态上已经定义的主要 sector 包括：

- `artist's co-living space`
- `Arthur Burton's apartment`
- `Ryan Park's apartment`
- `Isabella Rodriguez's apartment`
- `Giorgio Rossi's apartment`
- `Carlos Gomez's apartment`
- `The Rose and Crown Pub`
- `Hobbs Cafe`
- `Oak Hill College`
- `Johnson Park`
- `Harvey Oak Supply Store`
- `The Willows Market and Pharmacy`
- `Adam Smith's house`
- `Yuriko Yamamoto's house`
- `Moore family's house`
- `Tamara Taylor and Carmen Ortiz's house`
- `Moreno family's house`
- `Lin family's house`
- `Dorm for Oak Hill College`

说明当前底图其实已经预埋了：

- 公共商业空间
- 学院空间
- 多种住宅空间
- 合租空间
- 户外空间

---

## 5.2 已定义 arena

静态 arena 已包含：

- `main room`
- `bathroom`
- `common room`
- `kitchen`
- `garden`
- `classroom`
- `library`
- `hallway`
- `park`
- `cafe`
- `pub`
- `store`
- `supply store`
- 多个具体角色房间

这意味着从空间骨架上看，地图已经有能力承接：

- 居住
- 学习
- 就餐
- 购物
- 公园活动
- 合租互动

但问题是：

- 当前 3 人基线记忆并没有完整暴露这些空间
- 很多 arena 虽然存在，但对象填充或初始化使用还不完整

---

## 5.3 已定义 game object

静态定义里已经有不少有潜力的对象：

- `bed`
- `desk`
- `closet`
- `shelf`
- `easel`
- `bathroom sink`
- `shower`
- `toilet`
- `kitchen sink`
- `refrigerator`
- `toaster`
- `cooking area`
- `common room table`
- `common room sofa`
- `guitar`
- `microphone`
- `bar customer seating`
- `behind the bar counter`
- `behind the cafe counter`
- `cafe customer seating`
- `piano`
- `blackboard`
- `game console`
- `computer desk`
- `computer`
- `library sofa`
- `bookshelf`
- `library table`
- `classroom student seating`
- `classroom podium`
- `behind the pharmacy counter`
- `behind the grocery counter`
- `pharmacy store shelf`
- `grocery store shelf`
- `pharmacy store counter`
- `grocery store counter`
- `supply store product shelf`
- `behind the supply store counter`
- `supply store counter`
- `dorm garden`
- `house garden`
- `garden chair`
- `park garden`
- `harp`
- `lifting weight`
- `pool table`

这说明：

- 地图对象定义已经比当前 skill 生态更丰富
- 当前的主要限制，并不是地图静态完全没东西，而是“动态场景没有把这些能力用起来”

---

## 6. 当前 3 人基线里已经暴露出来的设施

从当前 `base_the_ville_isabella_maria_klaus` 的空间记忆来看，真正被 3 人世界明确暴露的公共设施，主要有：

### 学院与宿舍

- `Oak Hill College`
  - `library`
  - `classroom`
  - `hallway`
- `Dorm for Oak Hill College`
  - `Klaus Mueller's room`
  - `common room`
  - `man's bathroom`
  - `woman's bathroom`
  - `garden`

### 商业设施

- `Hobbs Cafe`
- `The Rose and Crown Pub`
- `The Willows Market and Pharmacy`
- `Harvey Oak Supply Store`

### 户外

- `Johnson Park`

### 已暴露对象

- `refrigerator`
- `piano`
- `game console`
- `pool table`
- `bed`
- `desk`
- `closet`
- `bookshelf`
- `library table`
- `blackboard`
- `classroom podium`
- `cafe customer seating`
- `bar customer seating`

当前这套暴露对象已经足够说明：

- 大模型并不是完全无物可用
- 但对象语义与 skill 生态之间还不匹配

---

## 7. 地图上“应有但当前没有充分暴露/利用”的设施与资源

下面是下一步最值得补的部分。

## 7.1 住宅空间没有被完整拉进当前基线

静态上已经有大量住宅，但当前 3 人基线并未完整覆盖：

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

这些空间的价值不只是“扩大地图”，而是补出更多真实生活场景：

- 家庭厨房
- 家庭储物
- 卧室休息
- 合租互动
- 花园与户外活动

---

## 7.2 厨房设施仍然不够完整

当前食物系统允许的合法来源是：

- `refrigerator`
- `stove`
- `cafe counter`
- `apple tree`

但当前地图/基线中明显存在问题：

- `refrigerator` 有
- `stove` 基本没有稳定暴露
- `apple tree` 几乎没有落地
- 厨房虽然有 `cooking area / toaster / kitchen sink`
  - 但离真实做饭链还差关键设施和资源定义

这会导致：

- 生存逻辑虽然闭环了
- 但“真实做饭”仍然承接不足

建议补充：

- `stove`
- `pan`
- `pot`
- `dining table`
- `food shelf / pantry`
- `raw ingredients`
  - 面包
  - 鸡蛋
  - 牛奶
  - 蔬菜
  - 肉类
- `trash bin`

---

## 7.3 健身/娱乐设施与行为目标不匹配

当前 resolver 和高频意图里，已经出现：

- `fitness machine`
- `exercise machine`
- `tv`

但静态对象里真正稳定存在的是：

- `lifting weight`
- `pool table`
- `game console`
- `piano`
- `guitar`
- `microphone`
- `harp`

这说明现在有一个典型错位：

- 语言目标词比地图对象更现代、更口语化
- 地图对象虽然不少，但没有形成稳定的“娱乐/锻炼设施簇”

建议新增或明确暴露：

- `fitness machine`
- `exercise bike`
- `treadmill`
- `tv`
- `board game table`
- `music corner`
- `art workstation`

这样可以让：

- `exercise`
- `watch`
- `play_game`
- `practice_music`
- `paint`

这些 skill 有真实目标承接。

---

## 7.4 户外食物与自然资源过少

如果目标是观察更接近真实世界的生存行为，当前自然资源还太少。

当前明显缺：

- `apple tree`
- `fruit tree`
- `water source`
- `bench`
- `shade area`
- `outdoor table`

建议补充：

- `apple tree`
- `berry bush`
- `park bench`
- `picnic table`
- `community garden`

这样不仅能增强生存，也能增强休闲、社交与观察行为。

---

## 7.5 商店空间可买但不可“真正购物”

当前地图已经有：

- 药店
- 杂货店
- 供应店

也有对象：

- `grocery store shelf`
- `pharmacy store shelf`
- `supply store product shelf`
- 各种柜台

但如果没有下面这些资源定义，商店就仍然只是“背景板”：

- 商品库存
- 商品类型
- 价格/交换逻辑
- 购买 skill
- 结账/交易 skill

建议补充资源类型：

- 食品
- 药品
- 清洁用品
- 工具
- 娱乐物品

建议补充 skill：

- `browse_shop`
- `buy_item`
- `pay`
- `compare_goods`

---

## 8. 设施、资源、技能的联动补全建议

下一步不要只补地图，也不要只补 skill。  
最有效的是做“三联补全”：

```text
设施
+ 资源
+ skill
```

下面给出一版建议。

## 8.1 厨房链

### 设施

- `stove`
- `pantry`
- `dining table`
- `trash bin`

### 资源

- `bread`
- `egg`
- `milk`
- `vegetable`
- `raw meat`

### skill

- `inspect_food`
- `prepare_food`
- `cook_food`
- `store_food`
- `clean_kitchen`

## 8.2 健身娱乐链

### 设施

- `fitness machine`
- `exercise bike`
- `treadmill`
- `tv`
- `board game table`

### 资源

- 无需复杂消耗资源，先以设备状态为主

### skill

- `exercise`
- `watch`
- `play_game`
- `practice_music`
- `paint`

## 8.3 商店采购链

### 设施

- 强化现有 store/supply/pharmacy 对象状态

### 资源

- 可购买物品清单
- 商品库存
- 价格标签

### skill

- `browse_shop`
- `buy_item`
- `pay`
- `request_item`

## 8.4 户外生存链

### 设施

- `apple tree`
- `berry bush`
- `park bench`
- `community garden`

### 资源

- 水果
- 可采摘资源

### skill

- `forage`
- `harvest`
- `rest_outdoor`
- `observe_environment`

---

## 9. 推荐优先级

## P0：马上做

这批能最快改善“世界太窄”的问题。

- 在地图中真正落地 `stove`
- 在地图中真正落地 `apple tree`
- 补一个专门的 `ExerciseSkillPack`
- 补一个专门的 `Watch/PlayGame` 方向 skill
- 给 `tv / fitness machine / treadmill` 增加真实对象或等价对象

## P1：紧接着做

- 暴露更多住宅与家庭厨房
- 补齐 `Dorm kitchen` 的对象
- 让 `shop/pharmacy/supply store` 支持基础购买逻辑
- 把 `easel / guitar / microphone / harp` 真正接入专门 skill

## P2：之后做

- 社交协作 skill
- 户外资源链
- 家务/整理/清洁链
- 更细的生产与工作行为

---

## 10. 一个重要判断标准

后续每补一轮地图或 skill，都建议观察这几个指标：

- `generic skill` 占比是否下降
- `skill_missing` 是否下降
- 高层自然语言意图是否更容易落到具体 skill
- 日常活动是否不再总是压缩成 `use/work/leisure_use`
- 地址解析是否更少落到错误对象

如果这些指标改善，说明方向是对的：

- 不是把模型驯化得更死
- 而是让世界更能承接模型的真实意图

---

## 11. 最终建议

下一步最推荐的不是继续加规则，而是：

1. 先补一批高频设施  
   `stove / apple tree / tv / fitness machine / treadmill`

2. 再补一批高频 skill  
   `exercise / watch / play_game / inspect_object / prepare_food`

3. 同时把部分“静态存在但基线没暴露”的住宅、厨房、花园空间真正接入当前可见地图

这样做能更接近你的真实目标：

**观察大模型在一个越来越接近真实世界的环境中，是否能逐渐形成稳定生存与日常行为。**

