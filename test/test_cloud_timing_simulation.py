
import sys
import os
import time
from pathlib import Path

# Add project root to sys.path
root = Path(__file__).parent.parent
sys.path.append(str(root / "reverie" / "backend_server"))

from persona.prompt_template.gpt_structure import ChatGPT_request, _resolve_request_config
from llm_api_config import get_task_route_request_config

def simulate_cloud_call():
    print("=== 开始模拟云模型调用计时 ===")
    
    # 模拟一个典型的 action_translation 任务
    task_type = "translation"
    config = get_task_route_request_config(task_type)
    
    # 拼凑一个大约 4000 字符的 prompt (模拟日志中的长度)
    base_prompt = "You are a translator. Translate the following NPC action into Chinese: "
    payload = "Isabella is walking to the cafe to get some coffee because she is feeling a bit tired and needs a caffeine boost." * 40
    dummy_prompt = base_prompt + payload
    
    print(f"任务类型: {task_type}")
    print(f"使用模型: {config['model']}")
    print(f"Prompt 长度: {len(dummy_prompt)} 字符")
    
    start_time = time.perf_counter()
    
    # 强制不使用缓存 (通过添加随机后缀)
    unique_prompt = dummy_prompt + f"\n[Timestamp: {time.time()}]"
    
    response = ChatGPT_request(
        unique_prompt, 
        prompt_kind="timing_simulation",
        request_config=config,
        metadata={"simulation": True, "task": "action_translation"}
    )
    
    end_time = time.perf_counter()
    total_duration = (end_time - start_time) * 1000
    
    print(f"\n--- 调用结果 ---")
    print(f"响应内容: {response[:100]}...")
    print(f"实际总耗时 (Perf Counter): {total_duration:.2f} ms")
    
    print("\n检查日志文件以确认记录...")
    log_path = root / "logs" / "ollama_request_timing.jsonl"
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            last_line = f.readlines()[-1]
            print(f"最新日志条目: {last_line.strip()}")
    else:
        print("警告: 未找到日志文件。")

if __name__ == "__main__":
    simulate_cloud_call()
