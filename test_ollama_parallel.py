# -*- coding: utf-8 -*-
"""
Ollama Concurrency Check Script (Ollama 并发运行检测脚本)
------------------------------------------------------
Usage:
  ..\venv\Scripts\python test_ollama_parallel.py
  (或直接使用您激活了虚拟环境的 python 运行)
"""

import threading
import requests
import time
import sys

# 设置 Ollama API 地址和测试用模型
url = "http://localhost:11434/api/generate"
model_name = "qwen2.5:7b"

payload = {
    "model": model_name,
    "prompt": "Write a 150-word story about a space explorer finding a new planet.",
    "stream": False,
    "options": {
        "temperature": 0.5
    }
}

# 用于记录各个请求的启动和结束时间
results = {}
lock = threading.Lock()

def make_request(request_id):
    start_time = time.time()
    start_str = time.strftime("%H:%M:%S", time.localtime(start_time))
    print(f"[请求 {request_id}] 启动时间: {start_str}")
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        end_time = time.time()
        end_str = time.strftime("%H:%M:%S", time.localtime(end_time))
        elapsed = end_time - start_time
        print(f"[请求 {request_id}] 完成时间: {end_str} (耗时: {elapsed:.2f}s)")
        
        res_data = response.json()
        tokens = res_data.get('eval_count', 0)
        
        with lock:
            results[request_id] = {
                "start": start_time,
                "end": end_time,
                "elapsed": elapsed,
                "tokens": tokens,
                "success": True
            }
    except Exception as e:
        print(f"[请求 {request_id}] 运行失败: {e}")
        with lock:
            results[request_id] = {
                "success": False,
                "error": str(e)
            }

# 创建并启动并发线程
t1 = threading.Thread(target=make_request, args=(1,))
t2 = threading.Thread(target=make_request, args=(2,))

print("=" * 60)
print(f"正在向 Ollama ({model_name}) 发送 2 路并发生成测试请求...")
print("=" * 60)

global_start = time.time()
t1.start()
t2.start()

t1.join()
t2.join()

global_end = time.time()
total_elapsed = global_end - global_start

print("=" * 60)
print("所有请求测试完成，正在进行并发性自动诊断...\n")

# 诊断逻辑
success_requests = [r for r in results.values() if r["success"]]
if len(success_requests) < 2:
    print("[错误] 未能成功获取足够数量的推理响应，请检查 Ollama 是否正常启动并已下载 qwen2.5:7b 模型。")
    sys.exit(1)

req1, req2 = success_requests[0], success_requests[1]
sum_individual_elapsed = req1["elapsed"] + req2["elapsed"]
parallel_ratio = total_elapsed / sum_individual_elapsed

print(f"-> 单独测试耗时总和 (串行期望): {sum_individual_elapsed:.2f} 秒")
print(f"-> 双路并发实际总耗时 (并行实测): {total_elapsed:.2f} 秒")
print(f"-> 并行效率比值: {parallel_ratio:.2%}\n")

if parallel_ratio < 0.70:
    print("[SUCCESS] 【诊断结果】Ollama 处于 [并行运行] 状态！")
    print("   两个请求的计算在显卡上重叠执行，并发配置（OLLAMA_NUM_PARALLEL）工作正常。")
else:
    print("[WARNING] 【诊断结果】Ollama 处于 [串行排队] 状态！")
    print("   两个请求排队依次执行。请检查后台 OLLAMA_NUM_PARALLEL 变量是否设置正确，并确保显存充足。")
print("=" * 60)
