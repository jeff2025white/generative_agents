# Generative Agents: Interactive Simulacra of Human Behavior 

<p align="center" width="100%">
<img src="cover.png" alt="Smallville" style="width: 80%; min-width: 300px; display: block; margin: auto;">
</p>

本仓库是我们研究论文《[Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442)》（生成式智能体：人类行为的交互式模拟）的配套代码。它包含了我们用于模拟可信人类行为的生成式智能体核心模拟模块及其游戏环境。在下文中，我们记录了在本地机器上设置模拟环境以及将模拟录制并作为演示动画进行回放的步骤。

## 💡 架构设计铁律 (Three Golden Rules of Agent Architecture)
本项目的底层设计哲学是**“LLM决策大脑 + 物理规则沙盒”**。在对模拟器进行任何二次开发和逻辑重构时，请时刻牢记并严格遵守以下铁律：

*   **铁律 1：认知大脑（LLM）负责“随机应变”**  
    智能体不应遵循死板的预设行为脚本。系统在每一步将足够的环境状态、生理数值及记忆上下文组装并塞给大模型，由大模型这个“认知大脑”给出具体方案和行动（自主决策）。
*   **铁律 2：硬编码仅负责“物理底座”**  
    代码应当且仅应当用于构建底层世界的“客观规律”（如代谢值衰减、生命值扣减、物理碰撞与阻挡等约束），作为不可逾越的物理和生理规则。
*   **铁律 3：消除行为与社交逻辑的硬编码（去特化）**  
    一切属于社会学或人际交互的行为逻辑（例如：进食前必须等待服务员端咖啡、主动找某人对话等），决不能通过死板的逻辑代码硬编码写死，而应通过底层物理事件或属性改变，由大模型大脑自主决定行动方案。

---

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Isabella_Rodriguez.png" alt="Generative Isabella">   环境设置
要设置您的环境，您需要安装并运行 Ollama，生成配置了 API 密钥和本地 Ollama 服务的 `utils.py` 文件，并安装所需的软件包。

### 步骤 1. 安装与运行 Ollama
本系统在本地使用 **Ollama** 来生成向量嵌入（Embedding）以及运行本地语言模型。
1. 请前往 [Ollama 官网](https://ollama.com/) 下载并安装 Ollama。
2. 安装后，确保 Ollama 服务在后台运行。系统默认使用 `nomic-embed-text` 生成向量嵌入（在启动时会自动拉取）。
3. （可选）如果想在本地调用翻译或聊天对话，可以在本地下载 `qwen2.5:7b` 或 `deepseek-r1:8b` 等模型（可运行 `ollama pull qwen2.5:7b`）。

### 步骤 2. 生成 Utils 文件
在 `reverie/backend_server` 文件夹（即 `reverie.py` 所在的目录）中，新建一个名为 `utils.py` 的文件，并将以下内容复制粘贴到该文件中：
```python
# API 配置（用于对话生成，可选用 DeepSeek 或 OpenAI）
openai_api_key = "<Your DeepSeek/OpenAI API>"
openai_api_base = "https://api.deepseek.com/v1" # 若使用 OpenAI 官方接口，可留空或设为 "https://api.openai.com/v1"
gpt35_model = "deepseek-chat" # 或 "gpt-3.5-turbo"
gpt4_model = "deepseek-chat"  # 或 "gpt-4"

# 本地 Ollama 配置（用于向量嵌入生成）
ollama_api_base = "http://localhost:11434/v1"
embedding_model = "nomic-embed-text"

# 填写您的名字
key_owner = "<Name>"

maze_assets_loc = "../../environment/frontend_server/static_dirs/assets"
env_matrix = f"{maze_assets_loc}/the_ville/matrix"
env_visuals = f"{maze_assets_loc}/the_ville/visuals"

fs_storage = "../../environment/frontend_server/storage"
fs_temp_storage = "../../environment/frontend_server/temp_storage"

collision_block_id = "32125"

# 详细输出
debug = True
```
请根据您的实际情况，将 `<Your DeepSeek/OpenAI API>` 替换为您的 API 密钥，并将 `<Name>` 替换为您的名字。
 
### 步骤 3. 安装 requirements.txt
安装 `requirements.txt` 文件中列出的所有依赖项（强烈建议先创建并激活虚拟环境）。关于 Python 版本的说明：我们在 Python 3.9.12 上测试了我们的环境。

## 🚀 极速启动（Windows 一键运行）
我们在项目根目录下提供了一键启动脚本 `start.bat`。该脚本会自动为您处理以下事务：
1. 检查并关闭任何先前残留运行的 Django 或 Reverie 服务器进程。
2. 检测本地是否运行了 Ollama 服务，若未运行则在后台自动拉起并等待启动。
3. 检查 Ollama 本地是否拥有 `nomic-embed-text` 向量嵌入模型，若缺失则自动下载。
4. 启动 Django 前端环境服务器。
5. 启动 Reverie 模拟器后端服务器，并自动载入包含 Isabella, Maria 和 Klaus 的 3 智能体初始地图（默认自动运行 8640 步，即游戏内的一天）。

**使用方法**：
双击运行项目根目录下的 `start.bat` 即可。当所有服务器启动完成后，在浏览器中访问 [http://localhost:8000/simulator_home](http://localhost:8000/simulator_home) 即可查看模拟。

---

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Klaus_Mueller.png" alt="Generative Klaus">   运行模拟（手动方式）
如果您不使用 `start.bat`，也可以按照以下手动步骤启动两个服务器：环境服务器和智能体模拟服务器。

### 步骤 1. 启动环境服务器
同样，该环境是作为一个 Django 项目实现的，因此您需要启动 Django 服务器。为此，首先在命令行中导航至 `environment/frontend_server`（即 `manage.py` 所在的目录）。然后运行以下命令：

    python manage.py runserver

接着，在您常用的浏览器中访问 [http://localhost:8000/](http://localhost:8000/)。如果您看到一条显示 "Your environment server is up and running" 的消息，说明您的服务器运行正常。在运行模拟时，请确保环境服务器持续运行，因此请保持此命令行窗口处于打开状态！（注意：建议使用 Chrome 或 Safari 浏览器。Firefox 可能会产生一些前端显示的小故障，但不会干扰实际模拟的运行。）

### 步骤 2. 启动模拟服务器
打开另一个命令行窗口（在步骤 1 中使用的窗口应该仍在运行环境服务器，请保持其原样）。导航至 `reverie/backend_server` 并运行 `reverie.py`。

    python reverie.py
这将启动模拟服务器。命令行中将出现以下提示："Enter the name of the forked simulation: "。要开始一个包含 Isabella Rodriguez、Maria Lopez 和 Klaus Mueller 的 3 智能体模拟，请输入：
    
    base_the_ville_isabella_maria_klaus
接着，提示会要求："Enter the name of the new simulation: "。输入任意名称来表示您当前的模拟（例如，暂时输入 "test-simulation" 即可）。

    test-simulation
保持模拟器服务器运行。此时，它会显示以下提示："Enter option: "

### 步骤 3. 运行并保存模拟
在浏览器中，导航至 [http://localhost:8000/simulator_home](http://localhost:8000/simulator_home)。您应该能看到 Smallville 的地图，以及地图上活动智能体的列表。您可以使用键盘方向键在地图上移动。请保持此标签页打开。要在模拟服务器中运行模拟，请在响应 "Enter option" 提示时输入以下命令：

    run <step-count>
请注意，您需要将上面的 `<step-count>` 替换为一个整数，表示您想要模拟的游戏步数。例如，如果您想模拟一整天（8640 步），应该输入 `run 8640`。游戏中的一步代表游戏时间 10 秒。

> [!NOTE]
> **游戏时间与现实世界时间的关系**：
> * **后端模拟运行阶段**：由于运行智能体需要调用大语言模型进行认知与决策（已优化为多线程并行），每一步（游戏内10秒）在现实中需要大约 **2~10秒**（取决于接口/本地模型响应速度）。模拟游戏里的一天（8640步）大约需要 **2.4小时 至 12小时**。
> * **前端回放/演示阶段**：回放时以浏览器 60 FPS 渲染，速度由 URL 的最后一个参数控制：
>   * **速度 1 (极慢)**：每步耗时约 0.53 秒，播放完整一天需约 **76.8 分钟**。
>   * **速度 2 (默认)**：每步耗时约 0.27 秒，播放完整一天需约 **38.4 分钟**。
>   * **速度 3 (中等)**：每步耗时约 0.13 秒，播放完整一天需约 **19.2 分钟**。
>   * **速度 4 (较快)**：每步耗时约 0.07 秒，播放完整一天需约 **9.6 分钟**。
>   * **速度 5 (极快)**：每步耗时约 0.03 秒，播放完整一天需约 **4.8 分钟**。
>   * **速度 6 (最快)**：每步耗时约 0.017 秒，播放完整一天需约 **2.4 分钟**。


您的模拟应该正在运行，并且您会看到智能体在浏览器的地图上移动。模拟运行结束后，将重新显示 "Enter option" 提示。此时，您可以通过重新输入 run 命令并指定所需的游戏步数来模拟更多步骤，输入 `exit` 退出模拟且不保存，或者输入 `fin` 保存并退出。

在下次运行模拟服务器时，您可以通过提供您保存的模拟名称作为 fork 的模拟来访问它。这将允许您从上次中断的地方重新开始模拟。

### 步骤 4. 回放模拟
只要您的环境服务器正在运行，您就可以通过在浏览器中导航到以下地址来回放已经运行过的模拟：`http://localhost:8000/replay/<simulation-name>/<starting-time-step>`。请务必将 `<simulation-name>` 替换为您要回放的模拟名称，并将 `<starting-time-step>` 替换为您希望开始回放的整数时间步。

例如，通过访问以下链接，您将启动一个预先模拟好的示例，从时间步 1 开始：  
[http://localhost:8000/replay/July1_the_ville_isabella_maria_klaus-step-3-20/1/](http://localhost:8000/replay/July1_the_ville_isabella_maria_klaus-step-3-20/1/)

### 步骤 5. 演示模拟
您可能会注意到，回放中所有的角色精灵（sprites）看起来都是相同的。我们想说明的是，回放功能主要用于调试目的，并未优先考虑优化模拟文件夹的大小或视觉效果。为了使用适当的角色精灵正确演示模拟，您需要先压缩模拟。为此，请使用文本编辑器打开位于 `reverie` 目录下的 `compress_sim_storage.py` file 文件。然后，以目标模拟的名称作为输入执行 `compress` 函数。通过这样做，模拟文件将被压缩，从而为演示做好准备。

要启动演示，请在浏览器中访问以下地址：`http://localhost:8000/demo/<simulation-name>/<starting-time-step>/<simulation-speed>`。注意，`<simulation-name>` 和 `<starting-time-step>` 表示的含义与前文相同。`<simulation-speed>` 可以用来控制演示速度，其中 1 最慢，5 最快。例如，访问以下链接将启动一个预先模拟好的示例，从时间步 1 开始，演示速度为中等：  
[http://localhost:8000/demo/July1_the_ville_isabella_maria_klaus-step-3-20/1/3/](http://localhost:8000/demo/July1_the_ville_isabella_maria_klaus-step-3-20/1/3/)

### 提示
我们注意到，当达到每小时速率限制时，OpenAI 的 API 可能会挂起。当发生这种情况时，您可能需要重新启动模拟。目前，我们建议在进行过程中经常保存模拟，以确保在确实需要停止并重新运行时尽可能少地丢失模拟进度。运行这些模拟（至少在 2023 年初）可能会非常昂贵，尤其是当环境中有很多智能体时。

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Maria_Lopez.png" alt="Generative Maria">   模拟存储位置
您保存的所有模拟都将位于 `environment/frontend_server/storage`，所有压缩后的演示都将位于 `environment/frontend_server/compressed_storage`。 

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Sam_Moore.png" alt="Generative Sam">   自定义

有两种方法可以可选地自定义您的模拟。 

### 编写并加载智能体历史
第一种方法是在模拟开始时使用独特的历史记录初始化智能体。为此，您需要 1) 使用其中一个基础模拟启动您的模拟，以及 2) 编写并加载智能体历史。具体来说，步骤如下：

#### 步骤 1. 启动基础模拟 
仓库中包含两个基础模拟：包含 25 个智能体的 `base_the_ville_n25`，以及包含 3 个智能体的 `base_the_ville_isabella_maria_klaus`。按照上文步骤 2 之前的步骤加载其中一个基础模拟。 

#### 步骤 2. 加载历史文件 
然后，当提示 "Enter option: " 时，您应该通过输入以下命令来加载智能体历史：

    call -- load history the_ville/<history_file_name>.csv
请注意，您需要将 `<history_file_name>` 替换为已有的历史文件名。仓库中包含两个历史文件作为示例：用于 `base_the_ville_n25` 的 `agent_history_init_n25.csv`，和用于 `base_the_ville_isabella_maria_klaus` 的 `agent_history_init_n3.csv`。这些文件包含了每个智能体的分号分隔记忆记录列表——加载它们会将记忆记录插入到智能体的记忆流中。

#### 步骤 3. 进一步自定义 
要通过编写您自己的历史文件来自定义初始化，请将您的文件放在以下文件夹中：`environment/frontend_server/static_dirs/assets/the_ville`。自定义历史文件的列格式必须与包含的示例历史文件匹配。因此，我们建议通过复制和粘贴仓库中已有的文件开始此过程。

### 创建新的基础模拟
对于更深度的自定义，您需要编写自己的基础模拟文件。最直接的方法是复制和粘贴现有的基础模拟文件夹，根据您的要求对其进行重命名和编辑。如果您决定保持智能体名称不变，此过程将会更简单。但是，如果您希望更改他们的名字或增加 Smallville 地图可以容纳的智能体数量，您可能需要使用 [Tiled](https://www.mapeditor.org/) 地图编辑器直接编辑地图。


## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Eddy_Lin.png" alt="Generative Eddy">   作者与引用 

**作者：** Joon Sung Park, Joseph C. O'Brien, Carrie J. Cai, Meredith Ringel Morris, Percy Liang, Michael S. Bernstein

如果您在项目中使用此仓库中的代码或数据，请引用我们的论文。 
```
@inproceedings{Park2023GenerativeAgents,  
author = {Park, Joon Sung and O'Brien, Joseph C. and Cai, Carrie J. and Morris, Meredith Ringel and Liang, Percy and Bernstein, Michael S.},  
title = {Generative Agents: Interactive Simulacra of Human Behavior},  
year = {2023},  
publisher = {Association for Computing Machinery},  
address = {New York, NY, USA},  
booktitle = {In the 36th Annual ACM Symposium on User Interface Software and Technology (UIST '23)},  
keywords = {Human-AI interaction, agents, generative AI, large language models},  
location = {San Francisco, CA, USA},  
series = {UIST '23}
}
```

## <img src="https://joonsungpark.s3.amazonaws.com:443/static/assets/characters/profile/Wolfgang_Schulz.png" alt="Generative Wolfgang">   致谢

我们鼓励您支持以下三位为本项目设计游戏资产的杰出艺术家，特别是如果您计划在自己的项目中使用此处包含的资产： 
* 背景艺术：[PixyMoon (@_PixyMoon\_)](https://twitter.com/_PixyMoon_)
* 家具/室内设计：[LimeZu (@lime_px)](https://twitter.com/lime_px)
* 角色设计：[ぴぽ (@pipohi)](https://twitter.com/pipohi)

此外，我们要感谢 Lindsay Popowski、Philip Guo、Michael Terry 以及高级行为科学研究中心（CASBS）社区的洞见、讨论和支持。最后，Smallville 中出现的所有地点均灵感来源于 Joon 在本科和研究生阶段经常光顾的真实地点——他感谢那里的每个人多年来对他的款待和支持。
