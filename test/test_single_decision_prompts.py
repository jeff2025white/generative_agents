
import sys
import os
import json
import time
import datetime
from pathlib import Path
from unittest.mock import patch

# Add project root to sys.path
root = Path(__file__).parent.parent
backend_server_path = root / "reverie" / "backend_server"
sys.path.append(str(backend_server_path))
os.chdir(str(backend_server_path))

from maze import Maze
from persona.persona import Persona
from persona.cognitive_modules.plan import decide_demand_action
import persona.prompt_template.gpt_structure as gpt_structure
from llm_api_config import get_default_decision_request_config

def test_single_persona_decision():
    print("=== 单人决策提示词及耗时测试 (使用 Flash 模型) ===")
    
    # 强制启用联合决策流水线 (推荐的 Flash 优化方案)
    os.environ["ENABLE_JOINT_DECISION_PIPELINE"] = "1"
    # 强制禁用语义缓存以查看真实 API 行为
    os.environ["ENABLE_SEMANTIC_DECISION_CACHE"] = "0"
    
    # 1. 清空全局缓存
    gpt_structure._cache = {}
    
    # 2. 加载基础环境
    maze = Maze("the_ville")
    storage_path = str(root / "environment" / "frontend_server" / "storage" / "base_the_ville_isabella_maria_klaus" / "personas" / "Isabella Rodriguez")
    persona = Persona("Isabella Rodriguez", storage_path)
    
    # 3. 设置模拟状态
    persona.scratch.satiety = 15.0
    persona.scratch.inventory = {}
    persona.scratch.curr_time = datetime.datetime(2026, 7, 4, 10, 0, 0)
    persona.scratch.curr_tile = (70, 70) # 设置一个有效的起始位置
    
    print(f"NPC: {persona.name}")
    print(f"当前状态: 饱食度={persona.scratch.satiety}, 背包={persona.scratch.inventory}")
    print(f"目标模型配置: {get_default_decision_request_config()}")
    
    # 4. 拦截并打印 Prompt
    # 注意：我们需要直接在 gpt_structure 模块中替换函数，确保所有引用都生效
    original_request = gpt_structure.ChatGPT_request
    
    def mocked_chatgpt_request(prompt, prompt_kind="generic", metadata=None, request_config=None):
        config = request_config or {}
        model_name = config.get("model", "unknown")
        
        print(f"\n" + "="*60)
        print(f"【PROMPT 类别】: {prompt_kind}")
        print(f"【使用模型】: {model_name}")
        print(f"【PROMPT 内容】:\n{prompt}")
        print("="*60 + "\n")
        
        start_at = time.perf_counter()
        res = original_request(prompt, prompt_kind, metadata, request_config)
        duration = (time.perf_counter() - start_at) * 1000
        
        print(f"【响应结果】: {res}")
        print(f"【实际耗时】: {duration:.2f} ms\n")
        return res

    gpt_structure.ChatGPT_request = mocked_chatgpt_request
    
    print("--- 开始触发决策 (Joint Decision Pipeline) ---")
    start_total = time.perf_counter()
    
    # 触发决策
    act_address = decide_demand_action(persona, maze)
    
    total_duration = (time.perf_counter() - start_total) * 1000
    print(f"--- 决策完成 ---")
    print(f"最终行动地址: {act_address}")
    print(f"NPC 动作描述: {persona.scratch.act_description}")
    print(f"总流程耗时: {total_duration:.2f} ms")

if __name__ == "__main__":
    try:
        test_single_persona_decision()
    except Exception as e:
        print(f"测试出错: {e}")
        import traceback
        traceback.print_exc()
