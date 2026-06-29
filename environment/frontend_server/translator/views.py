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

from django.views.decorators.csrf import csrf_exempt
from .models import *

import threading
_translation_cache = {}
_translation_cache_lock = threading.Lock()
_translation_cache_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "temp_storage", "translation_cache.json"))

def _load_translation_cache():
  global _translation_cache
  try:
    os.makedirs(os.path.dirname(_translation_cache_file), exist_ok=True)
    if os.path.exists(_translation_cache_file):
      with open(_translation_cache_file, "r", encoding="utf-8") as f:
        _translation_cache = json.load(f)
  except Exception as e:
    print(f"Warning: Failed to load translation cache: {e}")

_load_translation_cache()

def translate_to_chinese(text):
  if not text or not isinstance(text, str):
    return text
  s = text.strip()
  if not s or s.lower() == "none":
    return text
  if not any(c.isalpha() for c in s):
    return text

  # Check cache first
  with _translation_cache_lock:
    if s in _translation_cache:
      return _translation_cache[s]
  
  import sys
  backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "reverie", "backend_server"))
  if backend_path not in sys.path:
    sys.path.append(backend_path)
  
  try:
    from persona.prompt_template.gpt_structure import ChatGPT_single_request
    prompt = (
      "Translate the following English phrase from a virtual agent simulation into natural and concise Chinese. "
      "Return ONLY the Chinese translation. Do not include any explanations, quotes, or notes.\n\n"
      f"English: {s}\n"
      "Chinese:"
    )
    translated = ChatGPT_single_request(prompt)
    if "error" in translated.lower() or not translated.strip():
      return text
    res = translated.strip()
    if res.startswith('"') and res.endswith('"'):
      res = res[1:-1].strip()
    if res.startswith("'") and res.endswith("'"):
      res = res[1:-1].strip()
      
    # Update cache
    if res and res != s:
      with _translation_cache_lock:
        _translation_cache[s] = res
        try:
          with open(_translation_cache_file, "w", encoding="utf-8") as f:
            json.dump(_translation_cache, f, ensure_ascii=False, indent=2)
        except Exception as save_err:
          print(f"Warning: Failed to save translation cache: {save_err}")
          
    return res
  except Exception as e:
    return text

def translate_movements_in_place(movements):
  if not movements or "persona" not in movements:
    return movements
  for persona_name, p_data in movements["persona"].items():
    # 1. description
    desc = p_data.get("description", "")
    if desc:
      if "@" in desc:
        act_part, loc_part = desc.split("@", 1)
        translated_act = translate_to_chinese(act_part.strip())
        translated_loc = translate_to_chinese(loc_part.strip())
        p_data["description"] = f"{translated_act} @ {translated_loc}"
      else:
        p_data["description"] = translate_to_chinese(desc)
    
    # 2. next_action
    next_act = p_data.get("next_action", "")
    if next_act:
      p_data["next_action"] = translate_to_chinese(next_act)
      
    # 3. chat
    chat_data = p_data.get("chat")
    if chat_data:
      translated_chat = []
      for speaker, utterance in chat_data:
        translated_chat.append([speaker, translate_to_chinese(utterance)])
      p_data["chat"] = translated_chat
      
    # 4. last_chat
    last_chat = p_data.get("last_chat", "")
    if last_chat and last_chat != "None at the moment":
      if ": " in last_chat:
        speaker, utterance = last_chat.split(": ", 1)
        translated_utterance = translate_to_chinese(utterance)
        p_data["last_chat"] = f"{speaker}: {translated_utterance}"
      else:
        p_data["last_chat"] = translate_to_chinese(last_chat)
      
  return movements

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

  # We first read the active sim_code to filter results correctly
  if not check_if_file_exists(f_curr_sim_code):
    context = {}
    template = "home/error_start_backend.html"
    return render(request, template, context)

  with open(f_curr_sim_code) as json_file:  
    sim_code = json.load(json_file)["sim_code"]

  # Try to find the latest step that has completed movement data in the database
  latest_completed = SimState.objects.filter(sim_code=sim_code, is_movement_ready=True).order_by('-step').first()
  if latest_completed:
    step = latest_completed.step
  else:
    # If no completed step is found, fall back to the absolute latest step in SimState
    latest_state = SimState.objects.filter(sim_code=sim_code).order_by('-step').first()
    if latest_state:
      step = latest_state.step
    else:
      # File-based fallback
      if check_if_file_exists(f_curr_step):
        with open(f_curr_step) as json_file:  
          step = json.load(json_file)["step"]
        os.remove(f_curr_step)
      else:
        file_count = []
        env_dir = f"storage/{sim_code}/environment"
        if os.path.exists(env_dir):
          for i in find_filenames(env_dir, ".json"):
            x = i.split("/")[-1].strip()
            if x[0] != ".": 
              file_count += [int(x.split(".")[0])]
        
        move_files = []
        move_dir = f"storage/{sim_code}/movement"
        if os.path.exists(move_dir):
          for i in find_filenames(move_dir, ".json"):
            x = i.split("/")[-1].strip()
            if x[0] != ".": 
              move_files += [int(x.split(".")[0])]

        if move_files:
          step = max(move_files)
        elif file_count:
          step = max(file_count)
        else:
          step = 0

  persona_names = []
  persona_names_set = set()
  
  sim_persona_dir = f"storage/{sim_code}/personas"
  if not os.path.exists(sim_persona_dir):
    sim_persona_dir = f"compressed_storage/{sim_code}/personas"
    
  if os.path.exists(sim_persona_dir):
    for i in find_filenames(sim_persona_dir, ""): 
      x = i.split("/")[-1].strip()
      if x[0] != ".": 
        persona_names += [[x, x.replace(" ", "_")]]
        persona_names_set.add(x)

  persona_init_pos = []
  file_count = []
  env_dir = f"storage/{sim_code}/environment"
  if os.path.exists(env_dir):
    for i in find_filenames(env_dir, ".json"):
      x = i.split("/")[-1].strip()
      if x[0] != ".": 
        file_count += [int(x.split(".")[0])]

  if not file_count:
    # Try reading from SimState environment field
    try:
      sim_state = SimState.objects.get(sim_code=sim_code, step=step)
      if sim_state.environment and sim_state.environment != "{}":
        persona_init_pos_dict = json.loads(sim_state.environment)
        for key, val in persona_init_pos_dict.items(): 
          if key in persona_names_set: 
            persona_init_pos += [[key, val["x"], val["y"]]]
    except SimState.DoesNotExist:
      pass
      
    if not persona_init_pos:
      context = {}
      template = "home/error_start_backend.html"
      return render(request, template, context)
  else:
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
  
  # Translate scratch variables
  translated_scratch = scratch.copy()
  for field in ["innate", "learned", "currently", "lifestyle", "daily_plan_req"]:
    if field in scratch:
      translated_scratch[field] = translate_to_chinese(scratch[field])

  # Copy and translate associative memory nodes
  translated_event = []
  for node in a_mem_event:
    n = node.copy()
    n["description"] = translate_to_chinese(node.get("description", ""))
    translated_event.append(n)

  translated_thought = []
  for node in a_mem_thought:
    n = node.copy()
    n["description"] = translate_to_chinese(node.get("description", ""))
    translated_thought.append(n)

  translated_chat = []
  for node in a_mem_chat:
    n = node.copy()
    n["description"] = translate_to_chinese(node.get("description", ""))
    translated_chat.append(n)
  
  context = {"sim_code": sim_code,
             "step": step,
             "persona_name": persona_name, 
             "persona_name_underscore": persona_name_underscore, 
             "scratch": translated_scratch,
             "spatial": spatial,
             "a_mem_event": translated_event,
             "a_mem_chat": translated_chat,
             "a_mem_thought": translated_thought}
  template = "persona_state/persona_state.html"
  return render(request, template, context)


def path_tester(request):
  context = {}
  template = "path_tester/path_tester.html"
  return render(request, template, context)


@csrf_exempt
def process_environment(request): 
  data = json.loads(request.body)
  step = data["step"]
  sim_code = data["sim_code"]
  environment = data["environment"]

  # Record that frontend is active (heartbeat)
  try:
    os.makedirs("temp_storage", exist_ok=True)
    with open(f"temp_storage/frontend_active_{sim_code}.json", "w", encoding="utf-8") as f:
      json.dump({"last_active": time.time()}, f)
  except Exception as e:
    print(f"Error marking frontend active in process_environment: {e}")

  # Save to Database
  sim_state, created = SimState.objects.get_or_create(sim_code=sim_code, step=step)
  sim_state.environment = json.dumps(environment)
  sim_state.save()

  # Write-Through to Disk
  curr_env_file = f"storage/{sim_code}/environment/{step}.json"
  os.makedirs(os.path.dirname(curr_env_file), exist_ok=True)
  with open(curr_env_file, "w") as outfile:
    outfile.write(json.dumps(environment, indent=2))

  return HttpResponse("received")


@csrf_exempt
def update_environment(request): 
  data = json.loads(request.body)
  step = data["step"]
  sim_code = data["sim_code"]

  # Record that frontend is active (heartbeat)
  try:
    os.makedirs("temp_storage", exist_ok=True)
    with open(f"temp_storage/frontend_active_{sim_code}.json", "w", encoding="utf-8") as f:
      json.dump({"last_active": time.time()}, f)
  except Exception as e:
    print(f"Error marking frontend active in update_environment: {e}")

  response_data = {"<step>": -1}
  
  # Try Database first
  try:
    sim_state = SimState.objects.get(sim_code=sim_code, step=step)
    if sim_state.is_movement_ready:
      response_data = json.loads(sim_state.movement)
      response_data["<step>"] = step
      response_data = translate_movements_in_place(response_data)
      return JsonResponse(response_data)
  except SimState.DoesNotExist:
    pass

  # Fallback to Disk
  move_file = f"storage/{sim_code}/movement/{step}.json"
  if (check_if_file_exists(move_file)):
    with open(move_file) as json_file: 
      response_data = json.load(json_file)
      response_data["<step>"] = step
      response_data = translate_movements_in_place(response_data)

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

    chat_active_file = None
    try:
        data = json.loads(request.body)
        sim_code = data["sim_code"]
        persona_name_underscore = data["persona_name"]
        persona_name = persona_name_underscore.replace("_", " ")
        user_message = data["user_message"]
        conversation_history = data.get("conversation_history", [])

        # Chat active file lock removed.
        pass

        # === 6. Queue the chat message as a PendingAction for backend simulation integration ===
        try:
            latest_state = SimState.objects.filter(sim_code=sim_code).order_by('-step').first()
            step = latest_state.step if latest_state else 0
            
            pending_action = SimPendingAction.objects.create(
                sim_code=sim_code,
                persona_name=persona_name,
                step=step,
                action_type="chat",
                content=f"User said: {user_message}"
            )
        except Exception as queue_err:
            return JsonResponse({"error": f"Failed to queue pending action: {str(queue_err)}"}, status=500)

        # === 7. Poll database and wait for the backend to process the step and write response ===
        import time
        reply = None
        for _ in range(150): # Max wait 30 seconds (150 * 0.2s)
            time.sleep(0.2)
            try:
                # Refresh from DB
                act = SimPendingAction.objects.get(id=pending_action.id)
                if act.response:
                    reply = act.response
                    break
            except Exception:
                break

        if reply is None:
            reply = "我听到了你的声音，创造者。"

        # Strip deepseek thoughts if any
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
    finally:
        pass


@csrf_exempt
def api_init_sim(request):
  if request.method != "POST":
    return JsonResponse({"error": "POST required"}, status=400)
  
  data = json.loads(request.body)
  sim_code = data["sim_code"]
  step = data["step"]
  
  sim_state, created = SimState.objects.get_or_create(sim_code=sim_code, step=step)
  sim_state.is_movement_ready = False
  sim_state.save()
  
  # Write to temp_storage/curr_sim_code.json for backwards-compatibility
  f_curr_sim_code = "temp_storage/curr_sim_code.json"
  os.makedirs(os.path.dirname(f_curr_sim_code), exist_ok=True)
  with open(f_curr_sim_code, "w") as outfile:
    json.dump({"sim_code": sim_code}, outfile, indent=2)
    
  return JsonResponse({"status": "success"})


@csrf_exempt
def api_get_environment(request):
  sim_code = request.GET.get("sim_code")
  step = int(request.GET.get("step"))
  
  try:
    sim_state = SimState.objects.get(sim_code=sim_code, step=step)
    if sim_state.environment and sim_state.environment != "{}":
      return JsonResponse(json.loads(sim_state.environment))
  except (SimState.DoesNotExist, ValueError):
    pass
    
  return JsonResponse({"ready": False}, status=404)


@csrf_exempt
def api_post_movement(request):
  if request.method != "POST":
    return JsonResponse({"error": "POST required"}, status=400)
    
  data = json.loads(request.body)
  sim_code = data["sim_code"]
  step = data["step"]
  movements = data["movements"]
  
  # We keep movements in their original English on the dashboard cards to maximize performance
  
  # Save to Database
  sim_state, created = SimState.objects.get_or_create(sim_code=sim_code, step=step)
  sim_state.movement = json.dumps(movements)
  sim_state.is_movement_ready = True
  sim_state.save()
  
  # Periodic cleanup: every 50 steps, delete old rows to prevent DB bloat
  if step > 0 and step % 50 == 0:
    try:
      cutoff = step - 100
      if cutoff > 0:
        SimState.objects.filter(sim_code=sim_code, step__lt=cutoff).delete()
    except Exception:
      pass
  
  # Write-Through to Disk (Persistence)
  curr_move_file = f"storage/{sim_code}/movement/{step}.json"
  os.makedirs(os.path.dirname(curr_move_file), exist_ok=True)
  with open(curr_move_file, "w") as outfile:
    outfile.write(json.dumps(movements, indent=2))
    
  return JsonResponse({"status": "success"})


@csrf_exempt
def api_get_pending_actions(request):
  if request.method == "POST":
    # Acknowledge and mark processed
    data = json.loads(request.body)
    processed_ids = data.get("processed_ids", [])
    SimPendingAction.objects.filter(id__in=processed_ids).update(processed=True)
    return JsonResponse({"status": "acknowledged"})
    
  # GET request to retrieve actions
  sim_code = request.GET.get("sim_code")
  actions = SimPendingAction.objects.filter(sim_code=sim_code, processed=False)
  actions_data = []
  for act in actions:
    actions_data.append({
      "id": act.id,
      "persona_name": act.persona_name,
      "action_type": act.action_type,
      "content": act.content,
      "step": act.step
    })
  return JsonResponse(actions_data, safe=False)


@csrf_exempt
def api_post_instruction(request):
  if request.method != "POST":
    return JsonResponse({"error": "POST required"}, status=400)
    
  data = json.loads(request.body)
  sim_code = data["sim_code"]
  persona_name = data["persona_name"].replace("_", " ")
  instruction = data["instruction"]
  
  latest_state = SimState.objects.filter(sim_code=sim_code).order_by('-step').first()
  step = latest_state.step if latest_state else 0
  
  action = SimPendingAction.objects.create(
    sim_code=sim_code,
    persona_name=persona_name,
    step=step,
    action_type="instruction",
    content=instruction
  )
  return JsonResponse({"status": "queued", "id": action.id})


@csrf_exempt
def api_get_persona_schedule(request):
  """
  获取指定小人当日的每日核心需求(daily_req)和实时日程行动清单(f_daily_schedule)。
  """
  sim_code = request.GET.get("sim_code")
  persona_name = request.GET.get("persona_name").replace("_", " ")
  
  memory = f"storage/{sim_code}/personas/{persona_name}/bootstrap_memory"
  if not os.path.exists(memory): 
    memory = f"compressed_storage/{sim_code}/personas/{persona_name}/bootstrap_memory"
      
  if not os.path.exists(memory):
    return JsonResponse({"error": f"Persona '{persona_name}' not found"}, status=404)
      
  try:
    with open(memory + "/scratch.json", encoding="utf-8") as json_file:  
      scratch = json.load(json_file)
      
    daily_req = scratch.get("daily_req", [])
    translated_daily_req = [translate_to_chinese(req) for req in daily_req]
    
    f_daily_schedule = scratch.get("f_daily_schedule", [])
    translated_schedule = []
    for act, duration in f_daily_schedule:
      translated_schedule.append([translate_to_chinese(act), duration])

    return JsonResponse({
      "persona_name": persona_name,
      "daily_req": translated_daily_req,
      "f_daily_schedule": translated_schedule
    })
  except Exception as e:
    return JsonResponse({"error": str(e)}, status=500)


def api_get_persona_memories(request):
  """
  获取指定小人的最新记忆列表。
  """
  sim_code = request.GET.get("sim_code")
  persona_name = request.GET.get("persona_name").replace("_", " ")
  
  memory = f"storage/{sim_code}/personas/{persona_name}/bootstrap_memory"
  if not os.path.exists(memory): 
    memory = f"compressed_storage/{sim_code}/personas/{persona_name}/bootstrap_memory"
      
  if not os.path.exists(memory):
    return JsonResponse({"error": f"Persona '{persona_name}' not found"}, status=404)
      
  try:
    nodes_path = os.path.join(memory, "associative_memory", "nodes.json")
    if not os.path.exists(nodes_path):
      return JsonResponse({"memories": []})
      
    with open(nodes_path, encoding="utf-8") as json_file:  
      nodes_data = json.load(json_file)
    
    # Extract nodes details
    memories = []
    for node_id, node_details in nodes_data.items():
      # Filter for event or thought types to show meaningful memories
      if node_details.get("type") in ["event", "thought"]:
        memories.append({
          "id": node_id,
          "created": node_details.get("created", ""),
          "type": node_details.get("type", ""),
          "description": translate_to_chinese(node_details.get("description", "")),
          "poignancy": node_details.get("poignancy", 1)
        })
        
    # Sort memories by node index descending (latest first)
    def get_node_index(m):
      try:
        return int(m["id"].split("_")[1])
      except:
        return 0
    memories.sort(key=get_node_index, reverse=True)
    
    return JsonResponse({
      "persona_name": persona_name,
      "memories": memories
    })
  except Exception as e:
    return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def api_translate_memories(request):
  """
  On-demand translation of a list of retrieved memories to Chinese.
  """
  if request.method == "POST":
    try:
      data = json.loads(request.body)
      memories = data.get("memories", [])
      translated_mems = []
      for mem in memories:
        m = mem.copy()
        if "description" in m:
          m["description"] = translate_to_chinese(m["description"])
        translated_mems.append(m)
      return JsonResponse({"memories": translated_mems})
    except Exception as e:
      return JsonResponse({"error": str(e)}, status=500)
  return JsonResponse({"error": "POST method required"}, status=400)












