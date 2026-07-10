"""
Author: Joon Sung Park (joonspk@stanford.edu)
File: views.py
"""
import os
import string
import random
import json
import time
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
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_translation_cache_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "temp_storage", "translation_cache.json"))
_status_translation_config = None


def _active_sim_code_file():
  return os.path.join(_project_root, "environment", "frontend_server", "temp_storage", "curr_sim_code.json")


def _get_active_sim_code():
  try:
    with open(_active_sim_code_file(), "r", encoding="utf-8") as f:
      payload = json.load(f)
    sim_code = str(payload.get("sim_code", "") or "").strip()
    return sim_code or None
  except Exception:
    return None


def _scoped_translation_cache_key(cache_key, sim_code=None):
  normalized_key = str(cache_key or "").strip()
  if not normalized_key:
    return normalized_key
  active_sim_code = str(sim_code or _get_active_sim_code() or "").strip()
  if not active_sim_code:
    return normalized_key
  return f"{active_sim_code}::{normalized_key}"


def _mark_frontend_active(sim_code):
  """Persist a lightweight heartbeat so backend lock-step knows the page is alive."""
  try:
    os.makedirs("temp_storage", exist_ok=True)
    with open(f"temp_storage/frontend_active_{sim_code}.json", "w", encoding="utf-8") as f:
      json.dump({"last_active": time.time()}, f)
  except Exception as e:
    print(f"Error marking frontend active: {e}")

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

def _get_translation_cache(cache_key):
  with _translation_cache_lock:
    scoped_key = _scoped_translation_cache_key(cache_key)
    return _translation_cache.get(scoped_key)


def _set_translation_cache(cache_key, translated_value):
  with _translation_cache_lock:
    scoped_key = _scoped_translation_cache_key(cache_key)
    _translation_cache[scoped_key] = translated_value
    try:
      with open(_translation_cache_file, "w", encoding="utf-8") as f:
        json.dump(_translation_cache, f, ensure_ascii=False, indent=2)
    except Exception as save_err:
      print(f"Warning: Failed to save translation cache: {save_err}")


def _get_status_translation_config():
  """加载状态页专用的 DeepSeek 配置，优先环境变量，其次回退到项目内预留配置。"""
  global _status_translation_config
  if _status_translation_config:
    return _status_translation_config

  config = {
    "api_key": os.environ.get("DEEPSEEK_API_KEY", "").strip(),
    "api_base": os.environ.get("DEEPSEEK_API_BASE", "").strip() or "https://api.deepseek.com/v1",
    "model": os.environ.get("DEEPSEEK_MODEL", "").strip() or "deepseek-chat",
  }
  if config["api_key"]:
    _status_translation_config = config
    return _status_translation_config

  try:
    import sys

    backend_path = os.path.abspath(
      os.path.join(os.path.dirname(__file__), "..", "..", "..", "reverie", "backend_server")
    )
    if backend_path not in sys.path:
      sys.path.append(backend_path)
    from llm_api_config import get_status_translation_config
    project_config = get_status_translation_config()
  except Exception:
    return None

  config.update(project_config)

  if not config["api_key"]:
    return None

  _status_translation_config = config
  return _status_translation_config


def translate_to_chinese(text):
  if not text or not isinstance(text, str):
    return text
  s = text.strip()
  if not s or s.lower() == "none":
    return text
  if not any(c.isalpha() for c in s):
    return text

  # Check cache first
  cached = _get_translation_cache(s)
  if cached is not None:
    return cached
  
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
      _set_translation_cache(s, res)
          
    return res
  except Exception as e:
    return text


def translate_to_chinese_with_deepseek(text):
  """状态页专用翻译：直接调用 DeepSeek 在线接口，避免切换全局 LLM 配置。"""
  if not text or not isinstance(text, str):
    return text
  s = text.strip()
  if not s or s.lower() == "none":
    return text
  if not any(c.isalpha() for c in s):
    return text

  cache_key = f"deepseek::{s}"
  cached = _get_translation_cache(cache_key)
  if cached is not None:
    return cached

  config = _get_status_translation_config()
  if not config:
    return translate_to_chinese(text)

  payload = {
    "model": config["model"],
    "messages": [
      {
        "role": "system",
        "content": "You are a concise translation engine. Translate virtual simulation text into natural Chinese. Return only the Chinese translation.",
      },
      {
        "role": "user",
        "content": (
          "Translate the following English phrase from a virtual agent simulation into natural and concise Chinese. "
          "Return ONLY the Chinese translation. Do not include any explanations, quotes, or notes.\n\n"
          f"English: {s}\n"
          "Chinese:"
        ),
      },
    ],
    "temperature": 0,
  }

  try:
    response = http_requests.post(
      f'{config["api_base"].rstrip("/")}/chat/completions',
      headers={
        "Authorization": f'Bearer {config["api_key"]}',
        "Content-Type": "application/json",
      },
      json=payload,
      timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    translated = (
      data.get("choices", [{}])[0]
      .get("message", {})
      .get("content", "")
    )
    if not translated or "error" in translated.lower():
      return text

    res = translated.strip()
    if res.startswith('"') and res.endswith('"'):
      res = res[1:-1].strip()
    if res.startswith("'") and res.endswith("'"):
      res = res[1:-1].strip()
    if not res:
      return text

    if res != s:
      _set_translation_cache(cache_key, res)
    return res
  except Exception:
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


def _coerce_bool(value, default=False):
  if value is None:
    return default
  if isinstance(value, bool):
    return value
  return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _get_max_step_from_dir(dir_path):
  max_step = None
  if not os.path.exists(dir_path):
    return None

  try:
    with os.scandir(dir_path) as entries:
      for entry in entries:
        if not entry.is_file():
          continue
        name = entry.name
        if name.startswith(".") or not name.endswith(".json"):
          continue
        try:
          step = int(name[:-5])
        except ValueError:
          continue
        if max_step is None or step > max_step:
          max_step = step
  except FileNotFoundError:
    return None

  return max_step

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

  latest_state = SimState.objects.filter(sim_code=sim_code).order_by('-step').first()
  latest_completed = (
    SimState.objects
    .filter(sim_code=sim_code, is_movement_ready=True)
    .order_by('-step')
    .first()
  )

  # Try to find the latest step that has completed movement data in the database
  if latest_completed:
    step = latest_completed.step
  else:
    # If no completed step is found, fall back to the absolute latest step in SimState
    if latest_state:
      step = latest_state.step
    else:
      # File-based fallback
      if check_if_file_exists(f_curr_step):
        with open(f_curr_step) as json_file:  
          step = json.load(json_file)["step"]
        os.remove(f_curr_step)
      else:
        env_dir = f"storage/{sim_code}/environment"
        move_dir = f"storage/{sim_code}/movement"
        file_count = _get_max_step_from_dir(env_dir)
        move_files = _get_max_step_from_dir(move_dir)

        if move_files is not None:
          step = move_files
        elif file_count is not None:
          step = file_count
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
  env_dir = f"storage/{sim_code}/environment"
  persona_init_pos_dict = None

  # Prefer the exact step we are about to render instead of scanning the whole
  # environment directory for the latest JSON on every first page load.
  try:
    sim_state_for_step = SimState.objects.get(sim_code=sim_code, step=step)
    if sim_state_for_step.environment and sim_state_for_step.environment != "{}":
      persona_init_pos_dict = json.loads(sim_state_for_step.environment)
  except SimState.DoesNotExist:
    pass

  if persona_init_pos_dict is None and latest_state and latest_state.environment and latest_state.environment != "{}":
    persona_init_pos_dict = json.loads(latest_state.environment)

  if persona_init_pos_dict is None:
    exact_env_json = f"storage/{sim_code}/environment/{step}.json"
    if os.path.exists(exact_env_json):
      curr_json = exact_env_json
    else:
      latest_env_step = _get_max_step_from_dir(env_dir)
      curr_json = f"storage/{sim_code}/environment/{latest_env_step}.json" if latest_env_step is not None else None

    if curr_json and os.path.exists(curr_json):
      with open(curr_json) as json_file:
        persona_init_pos_dict = json.load(json_file)

  if persona_init_pos_dict is None:
    context = {}
    template = "home/error_start_backend.html"
    return render(request, template, context)

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


def _load_json_if_exists(path):
  if path and os.path.exists(path):
    with open(path, "r", encoding="utf-8") as f:
      return json.load(f)
  return None


def _parse_log_timestamp(ts_str):
  if not ts_str:
    return None
  try:
    clean_ts = str(ts_str).split("+")[0].replace("Z", "")
    return datetime.datetime.fromisoformat(clean_ts)
  except Exception:
    return None


def _get_sim_log_start_time(sim_code):
  resolved_code = sim_code
  if not sim_code.startswith("sim_"):
    curr_sim_file = os.path.join(_project_root, "environment", "frontend_server", "temp_storage", "curr_sim_code.json")
    if os.path.exists(curr_sim_file):
      try:
        with open(curr_sim_file, "r") as f:
          data = json.load(f)
          active_code = data.get("sim_code", "")
          if active_code.startswith("sim_"):
            resolved_code = active_code
      except Exception:
        pass

  timing_file = os.path.join(_project_root, "logs", "step_timing.jsonl")
  if not os.path.exists(timing_file):
    return None
  try:
    with open(timing_file, "r", encoding="utf-8") as f:
      for line in f:
        if not line.strip():
          continue
        try:
          data = json.loads(line)
        except Exception:
          continue
        if data.get("sim_code") == resolved_code:
          dt = _parse_log_timestamp(data.get("ts"))
          if dt:
            return dt - datetime.timedelta(seconds=60)
  except Exception:
    return None
  return None


def _load_chat_transcript_records(sim_code, step=None, limit=12, channel=None):
  chat_files = [
    os.path.join(_project_root, "environment", "frontend_server", "storage", sim_code, "chat_transcript.jsonl"),
    os.path.join(_project_root, "logs", "chat_transcript.jsonl"),
  ]

  start_time = _get_sim_log_start_time(sim_code)
  records = []
  seen_dialogues = set()
  try:
    for chat_file in chat_files:
      if not os.path.exists(chat_file):
        continue
      with open(chat_file, "r", encoding="utf-8") as f:
        for line in f:
          if not line.strip():
            continue
          try:
            data = json.loads(line)
          except Exception:
            continue

          record_sim_code = str(data.get("sim_code", "") or "").strip()
          if record_sim_code and record_sim_code != sim_code:
            continue
          record_channel = str(data.get("channel", "") or "").strip()
          if channel and record_channel != channel:
            continue

          record_time = _parse_log_timestamp(data.get("ts"))
          if start_time and record_time and record_time < start_time:
            continue
          if step is not None:
            try:
              if int(data.get("step", -1)) > int(step):
                continue
            except Exception:
              pass

          dialogue_id = data.get("dialogue_id")
          if dialogue_id and dialogue_id in seen_dialogues:
            continue
          if dialogue_id:
            seen_dialogues.add(dialogue_id)

          conversation = []
          for turn in data.get("conversation", []) or []:
            if isinstance(turn, dict):
              speaker = turn.get("speaker", "")
              utterance = turn.get("utterance", "")
            elif isinstance(turn, (list, tuple)) and len(turn) >= 2:
              speaker = turn[0]
              utterance = turn[1]
            else:
              continue
            if speaker and utterance:
              conversation.append({"speaker": speaker, "utterance": utterance})

          if conversation:
            records.append({
              "dialogue_id": dialogue_id or "",
              "persona": data.get("persona", ""),
              "target": data.get("target", ""),
              "sim_time": data.get("sim_time", ""),
              "step": data.get("step"),
              "ts": data.get("ts", ""),
              "channel": record_channel,
              "conversation": conversation,
            })
  except Exception:
    return []

  records.sort(key=lambda item: item.get("ts") or "")
  return records[-limit:]


def _load_sim_meta(sim_code):
  candidate_paths = [
    os.path.join("storage", sim_code, "reverie", "meta.json"),
    os.path.join("compressed_storage", sim_code, "meta.json"),
    os.path.join("environment", "frontend_server", "storage", sim_code, "reverie", "meta.json"),
  ]
  for path in candidate_paths:
    data = _load_json_if_exists(path)
    if data:
      return data
  return {}


def _derive_sim_time(sim_code, step, scratch):
  meta = _load_sim_meta(sim_code)
  start_date = meta.get("start_date")
  sec_per_step = meta.get("sec_per_step")
  if start_date and sec_per_step is not None:
    try:
      curr_dt = datetime.datetime.strptime(
        start_date + " 00:00:00", "%B %d, %Y %H:%M:%S"
      ) + datetime.timedelta(seconds=int(step) * int(sec_per_step))
      return curr_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
      pass
  return scratch.get("curr_time", "")


def _load_persona_movement_snapshot(sim_code, step, persona_name):
  try:
    sim_state = (
      SimState.objects.filter(sim_code=sim_code, step__lte=step, is_movement_ready=True)
      .order_by("-step")
      .first()
    )
    if sim_state and sim_state.movement:
      movement = json.loads(sim_state.movement)
      if movement.get("persona", {}).get(persona_name):
        return movement["persona"][persona_name]
  except Exception:
    pass

  candidate_paths = [
    os.path.join("storage", sim_code, "movement", f"{step}.json"),
    os.path.join("compressed_storage", sim_code, "master_movement.json"),
  ]
  for path in candidate_paths:
    data = _load_json_if_exists(path)
    if not data:
      continue
    if path.endswith("master_movement.json"):
      step_key = str(step)
      if step_key in data and persona_name in data[step_key]:
        return data[step_key][persona_name]
    elif data.get("persona", {}).get(persona_name):
      return data["persona"][persona_name]
  return {}


def _build_environment_candidates(spatial):
  area_candidates = []
  flat_objects = []
  seen_objects = set()

  for world_name, sectors in (spatial or {}).items():
    if not isinstance(sectors, dict):
      continue
    for sector_name, arenas in sectors.items():
      if not isinstance(arenas, dict):
        continue
      for arena_name, objects in arenas.items():
        if not objects:
          continue
        clean_objects = [obj for obj in objects if obj]
        if not clean_objects:
          continue
        area_candidates.append(
          {
            "world": world_name,
            "sector": sector_name,
            "arena": arena_name,
            "objects": clean_objects,
          }
        )
        for obj in clean_objects:
          lowered = obj.strip().lower()
          if lowered not in seen_objects:
            seen_objects.add(lowered)
            flat_objects.append(obj)

  area_candidates.sort(key=lambda item: (item["sector"], item["arena"]))
  return area_candidates, flat_objects


def _build_decision_rules(status_values):
  satiety = float(status_values.get("satiety", 0.0) or 0.0)
  stamina = float(status_values.get("stamina", 0.0) or 0.0)
  inventory = status_values.get("inventory", {}) or {}
  rules = [
    "- Consuming food (Consume action) restores +40.0 Satiety and +5.0 Health, and consumes 1 food item from inventory.",
    "- Gathering food (Gather action) from resources (like apple tree, refrigerator, stove, and cafe counter) adds items to inventory.",
    "- Resting (Rest action) restores +40.0 Stamina.",
    "- Socializing (Socialize action) restores +30.0 Mood.",
    "- Survival Privilege: Daily plan requirements and lifestyle guidelines are non-binding recommendations.",
  ]

  has_food = False
  for item_name, count in inventory.items():
    if count and count > 0:
      has_food = True
      if satiety < 40.0:
        rules.insert(
          0,
          f"- AVAILABLE PHYSICAL RULE: You have food ({item_name}) in your inventory and can select 'Consume' targeting '{item_name}'.",
        )
      break

  if satiety < 40.0 and not has_food:
    rules.insert(
      0,
      "- AVAILABLE PHYSICAL RULE: Inventory is empty, so you must use Gather on a valid food source like refrigerator, stove, cafe counter, or apple tree before consuming.",
    )
  if stamina < 40.0:
    rules.insert(
      0,
      "- AVAILABLE PHYSICAL RULE: You can use Rest targeting bed or sofa to restore Stamina.",
    )
  if satiety < 30.0:
    if has_food:
      food_item = next((k for k, v in inventory.items() if v and v > 0), "food")
      rules.insert(
        0,
        f"- CRITICAL HOMEOPATHY RULE: Satiety is critically low, so you must immediately Consume targeting '{food_item}'.",
      )
    else:
      rules.insert(
        0,
        "- CRITICAL HOMEOPATHY RULE: Satiety is critically low, inventory is empty, so you must Gather from refrigerator, stove, cafe counter, or apple tree first.",
      )
  elif stamina < 30.0:
    rules.insert(
      0,
      "- CRITICAL HOMEOPATHY RULE: Stamina is critically low, so you must immediately Rest targeting bed or sofa.",
    )

  return rules


def _load_recent_decision_logs(persona_name, limit=8):
  logs_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs", "translation_verify.jsonl")
  )
  if not os.path.exists(logs_path):
    return []

  interesting = {"decision_snapshot", "target_resolution", "retarget_invalid_food_source"}
  matched = []
  with open(logs_path, "r", encoding="utf-8") as f:
    for line in f:
      line = line.strip()
      if not line:
        continue
      try:
        entry = json.loads(line)
      except Exception:
        continue
      if entry.get("persona") != persona_name:
        continue
      if entry.get("event") not in interesting:
        continue
      matched.append(entry)
  return matched[-limit:]


def _load_recent_decision_stability_logs(persona_name, limit=10):
  logs_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs", "decision_stability.jsonl")
  )
  if not os.path.exists(logs_path):
    return []

  interesting = {"switch_blocked", "switch_accepted", "action_completed"}
  matched = []
  with open(logs_path, "r", encoding="utf-8") as f:
    for line in f:
      line = line.strip()
      if not line:
        continue
      try:
        entry = json.loads(line)
      except Exception:
        continue
      if entry.get("persona") != persona_name:
        continue
      if entry.get("event") not in interesting:
        continue
      matched.append(entry)
  return matched[-limit:]


def _load_recent_motive_monitor_logs(persona_name, limit=12):
  logs_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs", "motive_monitor.jsonl")
  )
  if not os.path.exists(logs_path):
    return []

  matched = []
  with open(logs_path, "r", encoding="utf-8") as f:
    for line in f:
      line = line.strip()
      if not line:
        continue
      try:
        entry = json.loads(line)
      except Exception:
        continue
      if entry.get("persona") != persona_name:
        continue
      if entry.get("event") != "motive_delta":
        continue
      matched.append(entry)
  return matched[-limit:]


def _translate_inventory_items(inventory, translate_func=translate_to_chinese):
  translated = []
  for item_name, count in (inventory or {}).items():
    if count and count > 0:
      translated.append({
        "name": translate_func(item_name),
        "count": count,
      })
  return translated


def _translate_environment_candidates(area_candidates, translate_func=translate_to_chinese):
  translated = []
  for area in area_candidates:
    translated.append({
      "world": translate_func(area.get("world", "")),
      "sector": translate_func(area.get("sector", "")),
      "arena": translate_func(area.get("arena", "")),
      "objects": [translate_func(obj) for obj in area.get("objects", [])],
    })
  return translated


def _translate_retrieved_memories(memories, translate_func=translate_to_chinese):
  translated = []
  for mem in memories or []:
    translated.append({
      **mem,
      "description": translate_func(mem.get("description", "")),
    })
  return translated


def _translate_recent_decision_logs(logs, translate_func=translate_to_chinese):
  translated = []
  for log in logs or []:
    copied = dict(log)
    if copied.get("event") == "decision_snapshot":
      copied["intent_zh"] = translate_func(copied.get("intent", ""))
      llm_decision_text = copied.get("llm_decision_text") or {}
      copied["llm_decision_text_zh"] = {
        "thought": translate_func(str(llm_decision_text.get("thought", copied.get("intent", "")))),
        "reasoning": translate_func(str(llm_decision_text.get("reasoning", copied.get("decision_routed_reasoning", "")))),
      }
      decision = copied.get("decision")
      if isinstance(decision, dict):
        copied["decision_zh"] = {
          "action": translate_func(str(decision.get("action", ""))),
          "target": translate_func(str(decision.get("target", ""))),
          "detail": translate_func(str(decision.get("detail", ""))),
          "duration": decision.get("duration", ""),
          "reasoning": translate_func(str(decision.get("reasoning", ""))),
        }
      else:
        copied["decision_zh"] = translate_func(str(decision))
      motives = copied.get("motives")
      if isinstance(motives, dict):
        copied["motives_zh"] = {
          "dominant_motive": translate_func(str(motives.get("dominant_motive", ""))),
          "secondary_motive": translate_func(str(motives.get("secondary_motive", ""))),
          "guard_motive": translate_func(str(motives.get("guard_motive", ""))),
          "dominant_motive_text": translate_func(str(motives.get("dominant_motive_text", ""))),
          "secondary_motive_text": translate_func(str(motives.get("secondary_motive_text", ""))),
          "motive_sentence": translate_func(str(motives.get("motive_sentence", ""))),
          "top_scores": [
            {
              **score,
              "motive_zh": translate_func(str(score.get("motive", ""))),
              "reason_zh": translate_func(str(score.get("reason", ""))),
            }
            for score in motives.get("top_scores", [])
          ],
        }
    elif copied.get("event") == "target_resolution":
      copied["target_zh"] = translate_func(copied.get("target", ""))
      copied["new_address_zh"] = translate_func(copied.get("new_address", ""))
      copied["act_description_zh"] = translate_func(copied.get("act_description", ""))
    elif copied.get("event") == "retarget_invalid_food_source":
      copied["original_target_zh"] = translate_func(copied.get("original_target", ""))
      copied["fallback_target_zh"] = translate_func(copied.get("fallback_target", ""))
      copied["valid_sources_zh"] = [translate_func(str(x)) for x in copied.get("valid_sources", [])]
    translated.append(copied)
  return translated


def _translate_decision_signature(signature, translate_func=translate_to_chinese):
  if not isinstance(signature, dict):
    return translate_func(str(signature))
  return {
    "skill_id": translate_func(str(signature.get("skill_id", ""))),
    "target": translate_func(str(signature.get("target", ""))),
    "intent_family": translate_func(str(signature.get("intent_family", ""))),
  }


def _translate_recent_decision_stability_logs(logs, translate_func=translate_to_chinese):
  translated = []
  for log in logs or []:
    copied = dict(log)
    event = copied.get("event")
    if event in {"switch_blocked", "switch_accepted"}:
      copied["old_signature_zh"] = _translate_decision_signature(copied.get("old_signature"), translate_func=translate_func)
      copied["new_signature_zh"] = _translate_decision_signature(copied.get("new_signature"), translate_func=translate_func)
      copied["description_zh"] = translate_func(str(copied.get("description", "")))
      copied["source_zh"] = translate_func(str(copied.get("source", "")))
    elif event == "action_completed":
      copied["signature_zh"] = _translate_decision_signature(copied.get("signature"), translate_func=translate_func)
    translated.append(copied)
  return translated


def _translate_recent_motive_monitor_logs(logs, translate_func=translate_to_chinese):
  translated = []
  for log in logs or []:
    copied = dict(log)
    copied["source_zh"] = translate_func(str(copied.get("source", "")))
    copied["reason_zh"] = translate_func(str(copied.get("reason", "")))
    copied["dominant_motive_zh"] = translate_func(str(copied.get("dominant_motive", "")))
    copied["secondary_motive_zh"] = translate_func(str(copied.get("secondary_motive", "")))
    copied["guard_motive_zh"] = translate_func(str(copied.get("guard_motive", "")))
    copied["motive_sentence_zh"] = translate_func(str(copied.get("motive_sentence", "")))
    copied["changed_motives_zh"] = []
    for item in copied.get("changed_motives", []):
      copied["changed_motives_zh"].append(
        {
          **item,
          "motive_zh": translate_func(str(item.get("motive", ""))),
        }
      )
    copied["top_scores_zh"] = []
    for score in copied.get("top_scores", []):
      copied["top_scores_zh"].append(
        {
          **score,
          "motive_zh": translate_func(str(score.get("motive", ""))),
          "reason_zh": translate_func(str(score.get("reason", ""))),
        }
      )
    translated.append(copied)
  return translated


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
  
  movement_snapshot = _load_persona_movement_snapshot(sim_code, step, persona_name)
  area_candidates, flat_objects = _build_environment_candidates(spatial)
  live_inventory = movement_snapshot.get("inventory", scratch.get("inventory", {})) or {}
  live_status = {
    "satiety": movement_snapshot.get("satiety", scratch.get("satiety", 0.0)),
    "stamina": movement_snapshot.get("stamina", scratch.get("stamina", 0.0)),
    "health": movement_snapshot.get("health", scratch.get("health", 0.0)),
    "mood": movement_snapshot.get("mood", scratch.get("mood", 0.0)),
    "inventory": live_inventory,
  }
  raw_description = movement_snapshot.get("description", "")
  current_action = raw_description.split("@")[0].strip() if "@" in raw_description else raw_description
  current_address = raw_description.split("@", 1)[1].strip() if "@" in raw_description else scratch.get("act_address", "")
  valid_food_sources = [obj for obj in flat_objects if obj.lower() in {"refrigerator", "stove", "cafe counter", "behind the cafe counter", "apple tree"}]
  retrieved_memories = movement_snapshot.get("retrieved_memories", []) or []
  decision_rules = _build_decision_rules(live_status)
  recent_decision_logs = _load_recent_decision_logs(persona_name)
  recent_decision_stability_logs = _load_recent_decision_stability_logs(persona_name)
  recent_motive_monitor_logs = _load_recent_motive_monitor_logs(persona_name)
  derived_sim_time = _derive_sim_time(sim_code, step, scratch)
  state_translate = translate_to_chinese_with_deepseek
  translated_inventory_items = _translate_inventory_items(live_inventory, translate_func=state_translate)
  translated_environment_candidates = _translate_environment_candidates(area_candidates, translate_func=state_translate)
  translated_flat_objects = [state_translate(obj) for obj in flat_objects]
  translated_valid_food_sources = [state_translate(obj) for obj in valid_food_sources]
  translated_retrieved_memories = _translate_retrieved_memories(retrieved_memories, translate_func=state_translate)
  translated_decision_rules = [state_translate(rule) for rule in decision_rules]
  translated_recent_decision_logs = _translate_recent_decision_logs(recent_decision_logs, translate_func=state_translate)
  translated_recent_decision_stability_logs = _translate_recent_decision_stability_logs(recent_decision_stability_logs, translate_func=state_translate)
  translated_recent_motive_monitor_logs = _translate_recent_motive_monitor_logs(recent_motive_monitor_logs, translate_func=state_translate)
  translated_current_action = state_translate(current_action)
  translated_current_address = state_translate(current_address)
  translated_last_chat = state_translate(movement_snapshot.get("last_chat", ""))
  translated_scratch_currently = state_translate(scratch.get("currently", ""))
  translated_innate = state_translate(scratch.get("innate", ""))
  translated_learned = state_translate(scratch.get("learned", ""))
  translated_lifestyle = state_translate(scratch.get("lifestyle", ""))
  
  context = {"sim_code": sim_code,
             "step": step,
             "persona_name": persona_name, 
             "persona_name_underscore": persona_name_underscore, 
             "scratch": scratch,
             "spatial": spatial,
             "a_mem_event": a_mem_event,
             "a_mem_chat": a_mem_chat,
             "a_mem_thought": a_mem_thought,
             "live_status": live_status,
             "translated_inventory_items": translated_inventory_items,
             "derived_sim_time": derived_sim_time,
             "current_action": current_action,
             "translated_current_action": translated_current_action,
             "current_address": current_address,
             "translated_current_address": translated_current_address,
             "last_chat": movement_snapshot.get("last_chat", ""),
             "translated_last_chat": translated_last_chat,
             "retrieved_memories": retrieved_memories,
             "translated_retrieved_memories": translated_retrieved_memories,
             "decision_rules": decision_rules,
             "translated_decision_rules": translated_decision_rules,
             "environment_candidates": area_candidates,
             "translated_environment_candidates": translated_environment_candidates,
             "flat_objects": flat_objects,
             "translated_flat_objects": translated_flat_objects,
             "valid_food_sources": valid_food_sources,
             "translated_valid_food_sources": translated_valid_food_sources,
             "recent_decision_logs": recent_decision_logs,
             "translated_recent_decision_logs": translated_recent_decision_logs,
             "recent_decision_stability_logs": recent_decision_stability_logs,
             "translated_recent_decision_stability_logs": translated_recent_decision_stability_logs,
             "recent_motive_monitor_logs": recent_motive_monitor_logs,
             "translated_recent_motive_monitor_logs": translated_recent_motive_monitor_logs,
             "translated_scratch_currently": translated_scratch_currently,
             "translated_innate": translated_innate,
             "translated_learned": translated_learned,
             "translated_lifestyle": translated_lifestyle}
  template = "persona_state/persona_state.html"
  return render(request, template, context)


def path_tester(request):
  context = {}
  template = "path_tester/path_tester.html"
  return render(request, template, context)


QUERY_HINTS = ["什么", "如何", "为什么", "吗", "？", "?", "状态", "情况", "记得", "计划", "关系", "在哪", "做什么"]
NOTIFY_HINTS = ["通知", "提醒你", "告诉你", "FYI", "仅供参考", "记住这件事"]
INSTRUCTION_HINTS = ["先", "去", "请", "不要", "立刻", "马上", "停止", "执行", "帮我"]


def classify_creator_message(user_message):
  text = str(user_message or "").strip()
  if not text:
    return {"message_mode": "query"}
  if any(token in text for token in NOTIFY_HINTS):
    return {"message_mode": "notify"}
  if text.endswith(("?", "？")) or any(token in text for token in QUERY_HINTS):
    return {"message_mode": "query"}
  if any(token in text for token in INSTRUCTION_HINTS):
    return {"message_mode": "instruction"}
  return {"message_mode": "query"}


def _normalize_conversation_history(conversation_history):
  if isinstance(conversation_history, list):
    return conversation_history[:12]
  return []


def _resolve_pending_action_reply(action):
  status = str(getattr(action, "status", "") or "")
  response = getattr(action, "response", None)
  if status == "failed":
    cleaned = str(response or "").strip()
    return "__FAILED__", cleaned or "NPC chat processing failed"
  if status == "replied":
    cleaned = str(response or "").strip()
    return "reply", cleaned if cleaned else None
  return "pending", None


@csrf_exempt
def process_environment(request): 
  data = json.loads(request.body)
  step = data["step"]
  sim_code = data["sim_code"]
  environment = data["environment"]

  # Record that frontend is active (heartbeat) if not requested by backend
  is_backend = data.get("is_backend", False)
  if not is_backend:
    _mark_frontend_active(sim_code)

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
  translate_for_ui = _coerce_bool(data.get("translate"), default=False)

  # Record that frontend is active (heartbeat)
  _mark_frontend_active(sim_code)

  response_data = {"<step>": -1}
  
  # Try Database first
  try:
    sim_state = SimState.objects.get(sim_code=sim_code, step=step)
    if sim_state.is_movement_ready:
      response_data = json.loads(sim_state.movement)
      response_data["<step>"] = step
      if translate_for_ui:
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
      if translate_for_ui:
        response_data = translate_movements_in_place(response_data)

  return JsonResponse(response_data)


@csrf_exempt
def api_frontend_heartbeat(request):
  if request.method != "POST":
    return JsonResponse({"error": "POST required"}, status=400)

  try:
    data = json.loads(request.body)
    sim_code = data["sim_code"]
  except Exception as e:
    return JsonResponse({"error": f"invalid payload: {e}"}, status=400)

  _mark_frontend_active(sim_code)
  return JsonResponse({"status": "ok"})


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


def admin_console_with_persona(request):
    """
    Web API: 用户通过网页打开管理员控制台与角色通信。
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
        conversation_history = _normalize_conversation_history(data.get("conversation_history", []))
        classification = classify_creator_message(user_message)
        message_mode = data.get("message_mode") or classification["message_mode"]

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
                action_type="admin_console",
                message_mode=message_mode,
                content=user_message,
                conversation_history=json.dumps(conversation_history, ensure_ascii=False),
                status="queued"
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
                result_type, result_payload = _resolve_pending_action_reply(act)
                if result_type == "__FAILED__":
                    return JsonResponse({"error": result_payload}, status=502)
                if result_type == "reply":
                    reply = result_payload
                    break
            except Exception:
                break

        if reply is None:
            reply = "我暂时没组织好回答，请再问我一次。"

        # Strip deepseek thoughts if any
        import re
        reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL).strip()

        return JsonResponse({
            "reply": reply,
            "persona_name": persona_name,
            "message_mode": message_mode,
            "channel": "admin",
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


def chat_with_persona(request):
    return admin_console_with_persona(request)


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
def api_get_chat_transcript(request):
  sim_code = request.GET.get("sim_code", "").strip()
  if not sim_code:
    return JsonResponse({"error": "sim_code required"}, status=400)

  step = request.GET.get("step")
  limit = request.GET.get("limit", 12)
  channel = request.GET.get("channel", "").strip()
  try:
    step = int(step) if step not in (None, "") else None
  except Exception:
    step = None
  try:
    limit = max(1, min(int(limit), 50))
  except Exception:
    limit = 12

  dialogues = _load_chat_transcript_records(
    sim_code,
    step=step,
    limit=limit,
    channel=channel or None,
  )
  messages = []
  for dialogue in dialogues:
    dialogue_id = dialogue.get("dialogue_id", "")
    for index, turn in enumerate(dialogue.get("conversation", [])):
      messages.append({
        "key": f"{dialogue_id}:{index}" if dialogue_id else "",
        "dialogue_id": dialogue_id,
        "speaker": turn.get("speaker", ""),
        "utterance": turn.get("utterance", ""),
        "sim_time": dialogue.get("sim_time", ""),
        "step": dialogue.get("step"),
        "ts": dialogue.get("ts", ""),
        "channel": dialogue.get("channel", ""),
      })

  return JsonResponse({"dialogues": dialogues, "messages": messages})


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
    data = json.loads(request.body)
    processing_ids = data.get("processing_ids", [])
    processed_ids = data.get("processed_ids", [])
    failed_ids = data.get("failed_ids", [])
    if processing_ids:
      SimPendingAction.objects.filter(id__in=processing_ids).update(status="processing")
    if processed_ids:
      SimPendingAction.objects.filter(id__in=processed_ids).update(processed=True, status="replied")
    if failed_ids:
      SimPendingAction.objects.filter(id__in=failed_ids).update(processed=True, status="failed")
    return JsonResponse({"status": "acknowledged"})
    
  # GET request to retrieve actions
  sim_code = request.GET.get("sim_code")
  actions = SimPendingAction.objects.filter(sim_code=sim_code, processed=False, status="queued")
  actions_data = []
  for act in actions:
    actions_data.append({
      "id": act.id,
      "persona_name": act.persona_name,
      "action_type": act.action_type,
      "message_mode": act.message_mode,
      "content": act.content,
      "conversation_history": act.conversation_history,
      "status": act.status,
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
    message_mode="instruction",
    content=instruction,
    conversation_history="[]",
    status="queued"
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


@csrf_exempt
def api_get_persona_relationship(request):
  """
  获取指定小人的社会关系图谱，并翻译成中文返回给前端。
  """
  sim_code = request.GET.get("sim_code")
  persona_name = request.GET.get("persona_name").replace("_", " ")
  
  memory = f"storage/{sim_code}/personas/{persona_name}/bootstrap_memory"
  if not os.path.exists(memory): 
    memory = f"compressed_storage/{sim_code}/personas/{persona_name}/bootstrap_memory"
      
  if not os.path.exists(memory):
    return JsonResponse({"error": f"Persona '{persona_name}' not found"}, status=404)
      
  try:
    graph_path = os.path.join(memory, "associative_memory", "social_relationship_graph.json")
    if not os.path.exists(graph_path):
      return JsonResponse({"relations": {}})
      
    with open(graph_path, encoding="utf-8") as json_file:  
      graph_data = json.load(json_file)
    
    relations = graph_data.get("relations", {})
    translated_relations = {}
    
    # 关系翻译映射表
    rel_translation = {
      "friend": "朋友",
      "colleague": "同事",
      "acquaintance": "熟人",
      "enemy": "对手/敌人",
      "stranger": "陌生人",
      "best_friend": "至交好友",
      "family": "家人",
      "partner": "伴侣"
    }
    
    for name, info in relations.items():
      eng_rel = info.get("relationship", "acquaintance").lower()
      cn_rel = rel_translation.get(eng_rel, translate_to_chinese(eng_rel))
      
      # 翻译近期交互事件
      recent_events = info.get("recent_events", [])
      cn_events = [translate_to_chinese(evt) for evt in recent_events]
      
      translated_relations[name] = {
        "relationship": cn_rel,
        "trust": info.get("trust", 0.5),
        "recent_events": cn_events
      }
      
    return JsonResponse({
      "persona_name": persona_name,
      "relations": translated_relations
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




