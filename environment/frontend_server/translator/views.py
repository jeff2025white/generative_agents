"""
Author: Joon Sung Park (joonspk@stanford.edu)
File: views.py
"""
import os
import string
import random
import json
from os import listdir
import os
import re
import requests as http_requests

import datetime
from django.shortcuts import render, redirect, HttpResponseRedirect
from django.http import HttpResponse, JsonResponse
from global_methods import *

from django.contrib.staticfiles.templatetags.staticfiles import static
from .models import *

def landing(request): 
  context = {}
  template = "landing/landing.html"
  return render(request, template, context)


def demo(request, sim_code, step, play_speed="2"): 
  move_file = f"compressed_storage/{sim_code}/master_movement.json"
  meta_file = f"compressed_storage/{sim_code}/meta.json"
  step = int(step)
  play_speed_opt = {"1": 1, "2": 2, "3": 4,
                    "4": 8, "5": 16, "6": 32}
  if play_speed not in play_speed_opt: play_speed = 2
  else: play_speed = play_speed_opt[play_speed]

  # Loading the basic meta information about the simulation.
  meta = dict() 
  with open (meta_file) as json_file: 
    meta = json.load(json_file)

  sec_per_step = meta["sec_per_step"]
  start_datetime = datetime.datetime.strptime(meta["start_date"] + " 00:00:00", 
                                              '%B %d, %Y %H:%M:%S')
  for i in range(step): 
    start_datetime += datetime.timedelta(seconds=sec_per_step)
  start_datetime = start_datetime.strftime("%Y-%m-%dT%H:%M:%S")

  # Loading the movement file
  raw_all_movement = dict()
  with open(move_file) as json_file: 
    raw_all_movement = json.load(json_file)
 
  # Loading all names of the personas
  persona_names = dict()
  persona_names = []
  persona_names_set = set()
  for p in list(raw_all_movement["0"].keys()): 
    persona_names += [{"original": p, 
                       "underscore": p.replace(" ", "_"), 
                       "initial": p[0] + p.split(" ")[-1][0]}]
    persona_names_set.add(p)

  # <all_movement> is the main movement variable that we are passing to the 
  # frontend. Whereas we use ajax scheme to communicate steps to the frontend
  # during the simulation stage, for this demo, we send all movement 
  # information in one step. 
  all_movement = dict()

  # Preparing the initial step. 
  # <init_prep> sets the locations and descriptions of all agents at the
  # beginning of the demo determined by <step>. 
  init_prep = dict() 
  for int_key in range(step+1): 
    key = str(int_key)
    val = raw_all_movement[key]
    for p in persona_names_set: 
      if p in val: 
        init_prep[p] = val[p]
  persona_init_pos = dict()
  for p in persona_names_set: 
    persona_init_pos[p.replace(" ","_")] = init_prep[p]["movement"]
  all_movement[step] = init_prep

  # Finish loading <all_movement>
  for int_key in range(step+1, len(raw_all_movement.keys())): 
    all_movement[int_key] = raw_all_movement[str(int_key)]

  context = {"sim_code": sim_code,
             "step": step,
             "persona_names": persona_names,
             "persona_init_pos": json.dumps(persona_init_pos), 
             "all_movement": json.dumps(all_movement), 
             "start_datetime": start_datetime,
             "sec_per_step": sec_per_step,
             "play_speed": play_speed,
             "mode": "demo"}
  template = "demo/demo.html"

  return render(request, template, context)


def UIST_Demo(request): 
  return demo(request, "March20_the_ville_n25_UIST_RUN-step-1-141", 2160, play_speed="3")


def home(request):
  f_curr_sim_code = "temp_storage/curr_sim_code.json"
  f_curr_step = "temp_storage/curr_step.json"

  if not check_if_file_exists(f_curr_step): 
    context = {}
    template = "home/error_start_backend.html"
    return render(request, template, context)

  with open(f_curr_sim_code) as json_file:  
    sim_code = json.load(json_file)["sim_code"]
  
  with open(f_curr_step) as json_file:  
    step = json.load(json_file)["step"]

  os.remove(f_curr_step)

  persona_names = []
  persona_names_set = set()
  for i in find_filenames(f"storage/{sim_code}/personas", ""): 
    x = i.split("/")[-1].strip()
    if x[0] != ".": 
      persona_names += [[x, x.replace(" ", "_")]]
      persona_names_set.add(x)

  persona_init_pos = []
  file_count = []
  for i in find_filenames(f"storage/{sim_code}/environment", ".json"):
    x = i.split("/")[-1].strip()
    if x[0] != ".": 
      file_count += [int(x.split(".")[0])]
  curr_json = f'storage/{sim_code}/environment/{str(max(file_count))}.json'
  with open(curr_json) as json_file:  
    persona_init_pos_dict = json.load(json_file)
    for key, val in persona_init_pos_dict.items(): 
      if key in persona_names_set: 
        persona_init_pos += [[key, val["x"], val["y"]]]

  context = {"sim_code": sim_code,
             "step": step, 
             "persona_names": persona_names,
             "persona_init_pos": persona_init_pos,
             "mode": "simulate"}
  template = "home/home.html"
  return render(request, template, context)


def replay(request, sim_code, step): 
  sim_code = sim_code
  step = int(step)

  persona_names = []
  persona_names_set = set()
  for i in find_filenames(f"storage/{sim_code}/personas", ""): 
    x = i.split("/")[-1].strip()
    if x[0] != ".": 
      persona_names += [[x, x.replace(" ", "_")]]
      persona_names_set.add(x)

  persona_init_pos = []
  file_count = []
  for i in find_filenames(f"storage/{sim_code}/environment", ".json"):
    x = i.split("/")[-1].strip()
    if x[0] != ".": 
      file_count += [int(x.split(".")[0])]
  curr_json = f'storage/{sim_code}/environment/{str(max(file_count))}.json'
  with open(curr_json) as json_file:  
    persona_init_pos_dict = json.load(json_file)
    for key, val in persona_init_pos_dict.items(): 
      if key in persona_names_set: 
        persona_init_pos += [[key, val["x"], val["y"]]]

  context = {"sim_code": sim_code,
             "step": step,
             "persona_names": persona_names,
             "persona_init_pos": persona_init_pos, 
             "mode": "replay"}
  template = "home/home.html"
  return render(request, template, context)


def replay_persona_state(request, sim_code, step, persona_name): 
  sim_code = sim_code
  step = int(step)

  persona_name_underscore = persona_name
  persona_name = " ".join(persona_name.split("_"))
  memory = f"storage/{sim_code}/personas/{persona_name}/bootstrap_memory"
  if not os.path.exists(memory): 
    memory = f"compressed_storage/{sim_code}/personas/{persona_name}/bootstrap_memory"

  with open(memory + "/scratch.json") as json_file:  
    scratch = json.load(json_file)

  with open(memory + "/spatial_memory.json") as json_file:  
    spatial = json.load(json_file)

  with open(memory + "/associative_memory/nodes.json") as json_file:  
    associative = json.load(json_file)

  a_mem_event = []
  a_mem_chat = []
  a_mem_thought = []

  for count in range(len(associative.keys()), 0, -1): 
    node_id = f"node_{str(count)}"
    node_details = associative[node_id]

    if node_details["type"] == "event":
      a_mem_event += [node_details]

    elif node_details["type"] == "chat":
      a_mem_chat += [node_details]

    elif node_details["type"] == "thought":
      a_mem_thought += [node_details]
  
  context = {"sim_code": sim_code,
             "step": step,
             "persona_name": persona_name, 
             "persona_name_underscore": persona_name_underscore, 
             "scratch": scratch,
             "spatial": spatial,
             "a_mem_event": a_mem_event,
             "a_mem_chat": a_mem_chat,
             "a_mem_thought": a_mem_thought}
  template = "persona_state/persona_state.html"
  return render(request, template, context)


def path_tester(request):
  context = {}
  template = "path_tester/path_tester.html"
  return render(request, template, context)


def process_environment(request): 
  """
  <FRONTEND to BACKEND> 
  This sends the frontend visual world information to the backend server. 
  It does this by writing the current environment representation to 
  "storage/environment.json" file. 

  ARGS:
    request: Django request
  RETURNS: 
    HttpResponse: string confirmation message. 
  """
  # f_curr_sim_code = "temp_storage/curr_sim_code.json"
  # with open(f_curr_sim_code) as json_file:  
  #   sim_code = json.load(json_file)["sim_code"]

  data = json.loads(request.body)
  step = data["step"]
  sim_code = data["sim_code"]
  environment = data["environment"]

  with open(f"storage/{sim_code}/environment/{step}.json", "w") as outfile:
    outfile.write(json.dumps(environment, indent=2))

  return HttpResponse("received")


def update_environment(request): 
  """
  <BACKEND to FRONTEND> 
  This sends the backend computation of the persona behavior to the frontend
  visual server. 
  It does this by reading the new movement information from 
  "storage/movement.json" file.

  ARGS:
    request: Django request
  RETURNS: 
    HttpResponse
  """
  # f_curr_sim_code = "temp_storage/curr_sim_code.json"
  # with open(f_curr_sim_code) as json_file:  
  #   sim_code = json.load(json_file)["sim_code"]

  data = json.loads(request.body)
  step = data["step"]
  sim_code = data["sim_code"]

  response_data = {"<step>": -1}
  if (check_if_file_exists(f"storage/{sim_code}/movement/{step}.json")):
    with open(f"storage/{sim_code}/movement/{step}.json") as json_file: 
      response_data = json.load(json_file)
      response_data["<step>"] = step

  return JsonResponse(response_data)


def path_tester_update(request): 
  """
  Processing the path and saving it to path_tester_env.json temp storage for 
  conducting the path tester. 

  ARGS:
    request: Django request
  RETURNS: 
    HttpResponse: string confirmation message. 
  """
  data = json.loads(request.body)
  camera = data["camera"]

  with open(f"temp_storage/path_tester_env.json", "w") as outfile:
    outfile.write(json.dumps(camera, indent=2))

  return HttpResponse("received")


def chat_with_persona(request):
    """
    Web API: 用户通过网页与角色对话。
    POST 请求，JSON 格式：
    {
      "sim_code": "sim_20260624_192342",
      "persona_name": "Isabella_Rodriguez",  // 下划线分隔
      "user_message": "你今天有什么计划？",
      "conversation_history": [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！我是Isabella..."}
      ]
    }
    返回 JSON：
    {
      "reply": "角色的回复文本",
      "persona_name": "Isabella Rodriguez"
    }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        data = json.loads(request.body)
        sim_code = data["sim_code"]
        persona_name_underscore = data["persona_name"]
        persona_name = persona_name_underscore.replace("_", " ")
        user_message = data["user_message"]
        conversation_history = data.get("conversation_history", [])

        # === 1. 加载角色的 scratch.json（身份信息） ===
        memory_base = f"storage/{sim_code}/personas/{persona_name}/bootstrap_memory"
        if not os.path.exists(memory_base):
            return JsonResponse({"error": f"Persona '{persona_name}' not found in sim '{sim_code}'"}, status=404)

        with open(f"{memory_base}/scratch.json", encoding="utf-8") as f:
            scratch = json.load(f)

        # === 2. 加载角色的 associative_memory/nodes.json（记忆流） ===
        with open(f"{memory_base}/associative_memory/nodes.json", encoding="utf-8") as f:
            nodes = json.load(f)

        # 提取最近的事件和想法（最多各取 10 条）
        recent_events = []
        recent_thoughts = []
        for count in range(len(nodes.keys()), 0, -1):
            node_id = f"node_{count}"
            if node_id not in nodes:
                continue
            node = nodes[node_id]
            if node["type"] == "event" and len(recent_events) < 10:
                recent_events.append(node["description"])
            elif node["type"] == "thought" and len(recent_thoughts) < 10:
                recent_thoughts.append(node["description"])
            if len(recent_events) >= 10 and len(recent_thoughts) >= 10:
                break

        # === 3. 构建角色身份上下文（ISS - Identity Stable Set） ===
        iss = f"""Name: {scratch.get('name', persona_name)}
Age: {scratch.get('age', 'unknown')}
Innate traits: {scratch.get('innate', '')}
Learned traits: {scratch.get('learned', '')}
Currently: {scratch.get('currently', '')}
Lifestyle: {scratch.get('lifestyle', '')}
Daily plan requirement: {scratch.get('daily_plan_req', '')}
Current time: {scratch.get('curr_time', '')}"""

        # === 4. 构建系统 Prompt ===
        events_str = "\n".join(f"- {e}" for e in recent_events) if recent_events else "No recent events."
        thoughts_str = "\n".join(f"- {t}" for t in recent_thoughts) if recent_thoughts else "No recent thoughts."

        system_prompt = f"""You are {persona_name}, a character in a small town called Smallville.
Here is your basic information:
{iss}

Your recent experiences:
{events_str}

Your recent thoughts:
{thoughts_str}

Current action: {scratch.get('act_description', 'idle')}
Current location: {scratch.get('act_address', 'unknown')}

Instructions:
- Stay in character as {persona_name} at all times.
- Respond naturally based on your personality, memories, and current situation.
- Keep responses concise (1-3 sentences).
- If the user speaks Chinese, respond in Chinese. If the user speaks English, respond in English.
- Do not break character or mention that you are an AI."""

        # === 5. 构建对话消息列表 ===
        messages = [{"role": "system", "content": system_prompt}]

        # 添加历史对话（最多保留最近 10 轮）
        for msg in conversation_history[-20:]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        # 添加当前用户消息
        messages.append({"role": "user", "content": user_message})

        # === 6. 调用 Ollama 本地模型 ===
        # Ollama 提供 OpenAI 兼容 API：http://localhost:11434/v1/chat/completions
        ollama_response = http_requests.post(
            "http://localhost:11434/v1/chat/completions",
            json={
                "model": "qwen2.5:7b",  # 可改为 "deepseek-r1:8b"
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 300,
                "stream": False
            },
            timeout=60
        )
        ollama_response.raise_for_status()
        result = ollama_response.json()
        reply = result["choices"][0]["message"]["content"].strip()

        # 清理 deepseek-r1 的 <think>...</think> 标签（如果使用 deepseek-r1 模型）
        import re
        reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL).strip()

        return JsonResponse({
            "reply": reply,
            "persona_name": persona_name
        })

    except FileNotFoundError as e:
        return JsonResponse({"error": f"File not found: {str(e)}"}, status=404)
    except http_requests.exceptions.ConnectionError:
        return JsonResponse({"error": "Cannot connect to Ollama. Is it running on localhost:11434?"}, status=503)
    except http_requests.exceptions.Timeout:
        return JsonResponse({"error": "Ollama response timed out"}, status=504)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)










