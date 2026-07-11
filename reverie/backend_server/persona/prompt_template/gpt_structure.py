"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: gpt_structure.py
Description: Wrapper functions for calling OpenAI APIs.
"""
import json
import random
import openai
import time
import hashlib
import os
import threading
import inspect

from utils import *
from persona.cognitive_modules.debug_log import append_debug_log
openai.api_key = openai_api_key
if openai_api_base:
  openai.api_base = openai_api_base

# ============================================================================
# #################### [PROMPT CACHE INFRASTRUCTURE] #########################
# ============================================================================
_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".prompt_cache")
os.makedirs(_cache_dir, exist_ok=True)
_cache_file = os.path.join(_cache_dir, "llm_cache.json")
_cache_lock = threading.Lock()
_cache = {}
_cache_hits = 0
_cache_misses = 0
_openai_config_lock = threading.Lock()
_cache_sim_scope = None

def _load_cache():
  global _cache
  try:
    if os.path.exists(_cache_file):
      with open(_cache_file, "r", encoding="utf-8") as f:
        _cache = json.load(f)
      print(f"[缓存] 已成功加载 {len(_cache)} 条响应缓存。")
  except Exception as e:
    print(f"[缓存] 加载缓存失败: {e}")
    _cache = {}

def _save_cache():
  try:
    with open(_cache_file, "w", encoding="utf-8") as f:
      json.dump(_cache, f, ensure_ascii=False)
  except Exception as e:
    print(f"[缓存] 保存缓存失败: {e}")

def _cache_key(prompt, extra=""):
  raw = prompt + str(extra)
  return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def set_cache_sim_scope(sim_code):
  """Bind prompt cache lookups to a single simulation run."""
  global _cache_sim_scope
  normalized = str(sim_code or "").strip()
  _cache_sim_scope = normalized or None


def get_cache_sim_scope():
  return _cache_sim_scope


def _short_hash(text):
  try:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:12]
  except Exception:
    return "unhashable"


def _truncate_text(value, limit=160):
  text = str(value or "")
  if len(text) <= limit:
    return text
  return text[:limit] + "...(truncated)"


def _ns_to_ms(value):
  if value in (None, "", 0):
    return 0.0
  try:
    return round(float(value) / 1_000_000.0, 3)
  except Exception:
    return 0.0


def _response_to_dict(response):
  if isinstance(response, dict):
    return response
  for attr in ("to_dict_recursive", "to_dict", "model_dump"):
    method = getattr(response, attr, None)
    if callable(method):
      try:
        data = method()
        if isinstance(data, dict):
          return data
      except Exception:
        pass
  return {}


def _extract_ollama_metrics(response):
  payload = _response_to_dict(response)
  return {
    "total_ms": _ns_to_ms(payload.get("total_duration")),
    "load_ms": _ns_to_ms(payload.get("load_duration")),
    "prompt_eval_ms": _ns_to_ms(payload.get("prompt_eval_duration")),
    "eval_ms": _ns_to_ms(payload.get("eval_duration")),
    "prompt_eval_count": int(payload.get("prompt_eval_count") or 0),
    "eval_count": int(payload.get("eval_count") or 0),
  }


def _caller_label(default_label="unknown"):
  try:
    for frame_info in inspect.stack()[2:8]:
      module = inspect.getmodule(frame_info.frame)
      module_name = getattr(module, "__name__", "")
      if module_name.endswith("gpt_structure"):
        continue
      if module_name:
        return f"{module_name}.{frame_info.function}"
      if frame_info.function:
        return frame_info.function
  except Exception:
    pass
  return default_label


def _log_llm_event(event, payload):
  try:
    record = dict(payload or {})
    record.setdefault("event", event)
    if _cache_sim_scope and "sim_code" not in record:
      record["sim_code"] = _cache_sim_scope
    append_debug_log("llm_request_events.jsonl", record)
  except Exception:
    # Logging must never interrupt the simulation path.
    return None


def _llm_error_summary(prompt_kind, resolved_config, metadata=None, error=None):
  metadata = dict(metadata or {})
  route = metadata.get("llm_route") or metadata.get("route_name") or "unknown"
  model = resolved_config.get("model") or "unknown"
  api_base = resolved_config.get("api_base") or "unknown"
  error_text = _truncate_text(error, 200) if error is not None else "unknown"
  return (
    f"ChatGPT ERROR [prompt_kind={prompt_kind} route={route} "
    f"model={model} api_base={api_base}] {error_text}"
  )


def _resolve_request_config(request_config=None):
  if request_config:
    return dict(request_config)
  try:
    from llm_api_config import get_default_cloud_chat_request_config
    return get_default_cloud_chat_request_config()
  except Exception:
    return {
      "api_key": openai_api_key,
      "api_base": openai_api_base,
      "model": gpt35_model,
    }


def _cache_scope(label, request_config=None):
  cfg = _resolve_request_config(request_config)
  return json.dumps(
    {
      "label": label,
      "api_base": cfg.get("api_base"),
      "model": cfg.get("model"),
      "sim_code": _cache_sim_scope,
    },
    ensure_ascii=False,
    sort_keys=True,
  )


def _chat_completion_create(messages, request_config=None, **kwargs):
  cfg = _resolve_request_config(request_config)
  with _openai_config_lock:
    prev_api_key = getattr(openai, "api_key", None)
    prev_api_base = getattr(openai, "api_base", None)
    try:
      openai.api_key = cfg["api_key"]
      if cfg["api_base"]:
        openai.api_base = cfg["api_base"]
      return openai.ChatCompletion.create(
        model=cfg["model"],
        messages=messages,
        **kwargs
      )
    finally:
      openai.api_key = prev_api_key
      openai.api_base = prev_api_base

def _get_cached(key):
  global _cache_hits
  with _cache_lock:
    val = _cache.get(key)
    if val is not None:
      _cache_hits += 1
      if _cache_hits % 50 == 0:
        print(f"[缓存统计] 命中次数: {_cache_hits} / 未命中次数: {_cache_misses}")
    return val

def _set_cached(key, value):
  global _cache_misses
  with _cache_lock:
    _cache_misses += 1
    _cache[key] = value
    # Periodic save every 20 new entries
    if _cache_misses % 20 == 0:
      _save_cache()

# Load cache on module import
_load_cache()

def save_cache_to_disk():
  """Call this to flush cache to disk (e.g., on simulation save/exit)."""
  with _cache_lock:
    _save_cache()
    print(f"[缓存] 已保存 {len(_cache)} 条缓存。当前统计 - 命中次数: {_cache_hits}, 未命中次数: {_cache_misses}")

# ============================================================================

def temp_sleep(seconds=0.1):
  time.sleep(seconds)

def ChatGPT_single_request(prompt): 
  return ChatGPT_request(prompt, prompt_kind="single_request")


# ============================================================================
# # ####################[SECTION 1: CHATGPT-3 STRUCTURE] ######################
# ============================================================================

def GPT4_request(prompt): 
  """
  Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
  server and returns the response. 
  ARGS:
    prompt: a str prompt
    gpt_parameter: a python dictionary with the keys indicating the names of  
                   the parameter and the values indicating the parameter 
                   values.   
  RETURNS: 
    a str of GPT-3's response. 
  """
  return ChatGPT_request(prompt, prompt_kind="gpt4_request")


def ChatGPT_request(prompt, prompt_kind="generic", metadata=None, request_config=None, skip_cache=False): 
  """
  Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
  server and returns the response. 
  ARGS:
    prompt: a str prompt
    gpt_parameter: a python dictionary with the keys indicating the names of  
                   the parameter and the values indicating the parameter 
                   values.   
  RETURNS: 
    a str of GPT-3's response. 
  """
  # Check cache first
  metadata = dict(metadata or {})
  decision_id = metadata.get("decision_id")
  resolved_config = _resolve_request_config(request_config)
  key = _cache_key(prompt, _cache_scope("chatgpt", resolved_config))
  prompt_hash = _short_hash(prompt)
  caller = _caller_label("ChatGPT_request")
  if not skip_cache:
    cached = _get_cached(key)
    if cached is not None:
      _log_llm_event(
        "chatgpt_request",
        {
          "caller": caller,
          "prompt_kind": prompt_kind,
          "cache_hit": True,
          "prompt_hash": prompt_hash,
          "prompt_chars": len(prompt),
          "response_chars": len(str(cached)),
          "duration_ms": 0.0,
          "metadata": metadata,
          "decision_id": decision_id,
          "retry_count": 0,
          "api_base": resolved_config.get("api_base"),
          "model": resolved_config.get("model"),
          "total_ms": 0.0,
          "load_ms": 0.0,
          "prompt_eval_ms": 0.0,
          "eval_ms": 0.0,
          "prompt_eval_count": 0,
          "eval_count": 0,
        }
      )
      return cached

  # temp_sleep()
  started_at = time.perf_counter()
  try: 
    completion = _chat_completion_create(
      [
        {"role": "system", "content": "You are a precise text completion engine. When given a prompt that ends in a sentence fragment, complete it directly without any introduction or conversational text. Do not repeat the prompt. Output ONLY the text that completes the sentence fragment. If the prompt asks for a JSON object, output only the JSON object."},
        {"role": "user", "content": prompt}
      ],
      request_config=resolved_config,
    )
    metrics = _extract_ollama_metrics(completion)
    result = completion["choices"][0]["message"]["content"]
    if not skip_cache:
      _set_cached(key, result)
    _log_llm_event(
      "chatgpt_request",
      {
        "caller": caller,
        "prompt_kind": prompt_kind,
        "cache_hit": False,
        "prompt_hash": prompt_hash,
        "prompt_chars": len(prompt),
        "response_chars": len(str(result)),
        "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 3),
        "status": "ok",
        "metadata": metadata,
        "decision_id": decision_id,
        "retry_count": 0,
        "api_base": resolved_config.get("api_base"),
        "model": resolved_config.get("model"),
        **metrics,
      }
    )
    return result
  
  except Exception as e: 
    _log_llm_event(
      "chatgpt_request",
      {
        "caller": caller,
        "prompt_kind": prompt_kind,
        "cache_hit": False,
        "prompt_hash": prompt_hash,
        "prompt_chars": len(prompt),
        "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 3),
        "status": "error",
        "error": _truncate_text(e, 240),
        "metadata": metadata,
        "decision_id": decision_id,
        "retry_count": 0,
        "api_base": resolved_config.get("api_base"),
        "model": resolved_config.get("model"),
        "total_ms": 0.0,
        "load_ms": 0.0,
        "prompt_eval_ms": 0.0,
        "eval_ms": 0.0,
        "prompt_eval_count": 0,
        "eval_count": 0,
      }
    )
    print(_llm_error_summary(prompt_kind, resolved_config, metadata=metadata, error=e))
    return "ChatGPT ERROR"


def clean_json_str(raw_str):
  s = raw_str.strip()
  # Remove markdown block symbols if present
  if s.startswith("```json"):
    s = s[7:]
  elif s.startswith("```"):
    s = s[3:]
  if s.endswith("```"):
    s = s[:-3]
  s = s.strip()
  return s


def GPT4_safe_generate_response(prompt, 
                                   example_output,
                                   special_instruction,
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False): 
  prompt = 'GPT-3 Prompt:\n"""\n' + prompt + '\n"""\n'
  prompt += f"Output the response to the prompt above in json. {special_instruction}\n"
  prompt += "Example output json:\n"
  prompt += '{"output": "' + str(example_output) + '"}'

  if verbose: 
    print ("CHAT GPT PROMPT")
    print (prompt)

  for i in range(repeat): 

    try: 
      raw_resp = GPT4_request(prompt)
      cleaned_resp = clean_json_str(raw_resp)
      end_index = cleaned_resp.rfind('}') + 1
      curr_gpt_response = cleaned_resp[:end_index]
      curr_gpt_response = json.loads(curr_gpt_response)["output"]
      
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      
      if verbose: 
        print ("---- repeat count: \n", i, curr_gpt_response)
        print (curr_gpt_response)
        print ("~~~~")

    except: 
      pass

  return fail_safe_response



def ChatGPT_safe_generate_response(prompt, 
                                   example_output,
                                   special_instruction,
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False,
                                   prompt_kind="generic",
                                   metadata=None,
                                   request_config=None,
                                   skip_cache=False): 
  # prompt = 'GPT-3 Prompt:\n"""\n' + prompt + '\n"""\n'
  metadata = dict(metadata or {})
  prompt = '"""\n' + prompt + '\n"""\n'
  prompt += f"Output the response to the prompt above in json. {special_instruction}\n"
  prompt += "Example output json:\n"
  prompt += '{"output": "' + str(example_output) + '"}'

  if verbose: 
    print ("CHAT GPT PROMPT")
    print (prompt)

  caller = _caller_label("ChatGPT_safe_generate_response")
  prompt_hash = _short_hash(prompt)
  decision_id = metadata.get("decision_id")
  resolved_config = _resolve_request_config(request_config)
  safe_started_at = time.perf_counter()
  for i in range(repeat): 
    raw_response = ""
    attempt_started_at = time.perf_counter()
    try: 
      raw_response = ChatGPT_request(
        prompt,
        prompt_kind=prompt_kind,
        metadata=dict(metadata, safe_repeat=repeat, safe_attempt=i + 1),
        request_config=resolved_config,
        skip_cache=skip_cache,
      )
      cleaned_resp = clean_json_str(raw_response)
      end_index = cleaned_resp.rfind('}') + 1
      curr_gpt_response = cleaned_resp[:end_index]
      try:
        data = json.loads(curr_gpt_response)
      except json.JSONDecodeError:
        # Handle nested JSON where inner braces are not escaped,
        # e.g. {"output": "{"utterance": "...", ...}"}
        inner_start = curr_gpt_response.find('{', 1)
        inner_end = curr_gpt_response.rfind('}', 0, len(curr_gpt_response) - 1)
        if inner_start != -1 and inner_end != -1 and inner_end > inner_start:
          data = json.loads(curr_gpt_response[inner_start:inner_end + 1])
        else:
          raise
      if isinstance(data, dict) and "output" in data:
        output_val = data["output"]
        # The output value itself may be a JSON string that needs parsing
        if isinstance(output_val, str):
          try:
            curr_gpt_response = json.loads(output_val)
          except (json.JSONDecodeError, ValueError):
            curr_gpt_response = output_val
        else:
          curr_gpt_response = output_val
      else:
        curr_gpt_response = data
      
      is_valid = func_validate(curr_gpt_response, prompt=prompt)
      _log_llm_event(
        "chatgpt_safe_attempt",
        {
          "caller": caller,
          "prompt_kind": prompt_kind,
          "prompt_hash": prompt_hash,
          "attempt": i + 1,
          "repeat": repeat,
          "valid": bool(is_valid),
          "raw_response_chars": len(str(raw_response)),
          "duration_ms": round((time.perf_counter() - attempt_started_at) * 1000.0, 3),
          "status": "ok",
          "metadata": metadata,
          "decision_id": decision_id,
          "api_base": resolved_config.get("api_base"),
          "model": resolved_config.get("model"),
        }
      )
      if is_valid: 
        _log_llm_event(
          "chatgpt_safe_summary",
          {
            "caller": caller,
            "prompt_kind": prompt_kind,
            "prompt_hash": prompt_hash,
            "repeat": repeat,
            "attempts_used": i + 1,
            "status": "ok",
            "duration_ms": round((time.perf_counter() - safe_started_at) * 1000.0, 3),
            "metadata": metadata,
            "decision_id": decision_id,
            "api_base": resolved_config.get("api_base"),
            "model": resolved_config.get("model"),
          }
        )
        return func_clean_up(curr_gpt_response, prompt=prompt)
      
      if verbose: 
        print ("---- repeat count (validation failed): \n", i, curr_gpt_response)
        print (curr_gpt_response)
        print ("~~~~")

    except Exception as e: 
      _log_llm_event(
        "chatgpt_safe_attempt",
        {
          "caller": caller,
          "prompt_kind": prompt_kind,
          "prompt_hash": prompt_hash,
          "attempt": i + 1,
          "repeat": repeat,
          "valid": False,
          "raw_response_chars": len(str(raw_response)),
          "duration_ms": round((time.perf_counter() - attempt_started_at) * 1000.0, 3),
          "status": "exception",
          "error": _truncate_text(e, 240),
          "metadata": metadata,
          "decision_id": decision_id,
          "api_base": resolved_config.get("api_base"),
          "model": resolved_config.get("model"),
        }
      )
      if verbose:
        print(f"--- ChatGPT_safe_generate_response Exception on attempt {i}: {e}")
        print(f"Raw response: {raw_response!r}")
      pass
  _log_llm_event(
    "chatgpt_safe_summary",
    {
      "caller": caller,
      "prompt_kind": prompt_kind,
      "prompt_hash": prompt_hash,
      "repeat": repeat,
      "attempts_used": repeat,
      "status": "fail_safe",
      "duration_ms": round((time.perf_counter() - safe_started_at) * 1000.0, 3),
      "metadata": metadata,
      "decision_id": decision_id,
      "api_base": resolved_config.get("api_base"),
      "model": resolved_config.get("model"),
    }
  )

  return fail_safe_response


def ChatGPT_safe_generate_response_OLD(prompt, 
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False): 
  if verbose: 
    print ("CHAT GPT PROMPT")
    print (prompt)

  for i in range(repeat): 
    try: 
      curr_gpt_response = ChatGPT_request(prompt).strip()
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      if verbose: 
        print (f"---- repeat count: {i}")
        print (curr_gpt_response)
        print ("~~~~")

    except: 
      pass
  print ("FAIL SAFE TRIGGERED") 
  return fail_safe_response


# ============================================================================
# ###################[SECTION 2: ORIGINAL GPT-3 STRUCTURE] ###################
# ============================================================================

def GPT_request(prompt, gpt_parameter): 
  """
  Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
  server and returns the response. 
  ARGS:
    prompt: a str prompt
    gpt_parameter: a python dictionary with the keys indicating the names of  
                   the parameter and the values indicating the parameter 
                   values.   
  RETURNS: 
    a str of GPT-3's response. 
  """
  # Cache only deterministic requests (temperature == 0)
  use_cache = gpt_parameter.get("temperature", 0.0) == 0
  resolved_config = _resolve_request_config()
  if use_cache:
    key = _cache_key(prompt, _cache_scope("gpt_request", resolved_config))
    cached = _get_cached(key)
    if cached is not None:
      return cached

  temp_sleep()
  try: 
    stop_sequence = gpt_parameter.get("stop", None)
    response = _chat_completion_create(
                [
                  {"role": "system", "content": "You are a precise text completion engine. When given a prompt that ends in a sentence fragment, complete it directly without any introduction or conversational text. Do not repeat the prompt. Output ONLY the text that completes the sentence fragment. If the prompt asks for a JSON object, output only the JSON object."},
                  {"role": "user", "content": prompt}
                ],
                request_config=resolved_config,
                temperature=gpt_parameter.get("temperature", 0.0),
                max_tokens=gpt_parameter.get("max_tokens", 100),
                top_p=gpt_parameter.get("top_p", 1.0),
                frequency_penalty=gpt_parameter.get("frequency_penalty", 0.0),
                presence_penalty=gpt_parameter.get("presence_penalty", 0.0),
                stop=stop_sequence)
    result = response.choices[0].message.content
    if use_cache:
      _set_cached(key, result)
    return result
  except Exception as e: 
    if debug:
      print(f"GPT_request error: {e}")
    print ("TOKEN LIMIT EXCEEDED")
    return "TOKEN LIMIT EXCEEDED"


def generate_prompt(curr_input, prompt_lib_file): 
  """
  Takes in the current input (e.g. comment that you want to classifiy) and 
  the path to a prompt file. The prompt file contains the raw str prompt that
  will be used, which contains the following substr: !<INPUT>! -- this 
  function replaces this substr with the actual curr_input to produce the 
  final promopt that will be sent to the GPT3 server. 
  ARGS:
    curr_input: the input we want to feed in (IF THERE ARE MORE THAN ONE
                INPUT, THIS CAN BE A LIST.)
    prompt_lib_file: the path to the promopt file. 
  RETURNS: 
    a str prompt that will be sent to OpenAI's GPT server.  
  """
  if type(curr_input) == type("string"): 
    curr_input = [curr_input]
  curr_input = [str(i) for i in curr_input]

  f = open(prompt_lib_file, "r", encoding="utf-8")
  prompt = f.read()
  f.close()
  for count, i in enumerate(curr_input):   
    prompt = prompt.replace(f"!<INPUT {count}>!", i)
  if "<commentblockmarker>###</commentblockmarker>" in prompt: 
    # Drop the template legend/header and keep the actual prompt body.
    prompt = prompt.split("<commentblockmarker>###</commentblockmarker>", 1)[1]
  return prompt.strip()


def safe_generate_response(prompt, 
                           gpt_parameter,
                           repeat=5,
                           fail_safe_response="error",
                           func_validate=None,
                           func_clean_up=None,
                           verbose=False): 
  if verbose: 
    print (prompt)

  for i in range(repeat): 
    curr_gpt_response = GPT_request(prompt, gpt_parameter)
    if func_validate(curr_gpt_response, prompt=prompt): 
      return func_clean_up(curr_gpt_response, prompt=prompt)
    if verbose: 
      print ("---- repeat count: ", i, curr_gpt_response)
      print (curr_gpt_response)
      print ("~~~~")
  return fail_safe_response


# Embedding cache (in-memory, embeddings are deterministic)
_embedding_cache = {}

def get_embedding(text, model=embedding_model):
  text = text.replace("\n", " ")
  if not text: 
    text = "this is blank"
  
  # Check embedding cache
  if text in _embedding_cache:
    return _embedding_cache[text]
  
  # Call local Ollama for embedding
  response = openai.Embedding.create(
          input=[text], 
          model=model, 
          api_base=ollama_api_base, 
          api_key="ollama"
  )
  embedding = response['data'][0]['embedding']
  
  # Pad or truncate the embedding to match the 1536-dimensional database
  if len(embedding) < 1536:
    embedding = embedding + [0.0] * (1536 - len(embedding))
  elif len(embedding) > 1536:
    embedding = embedding[:1536]
  
  _embedding_cache[text] = embedding
  return embedding


def get_embeddings_batch(texts, model=embedding_model):
  """Batch-fetch embeddings for multiple texts in a single API call."""
  cleaned = []
  indices_to_fetch = []  # indices in the original list that need API calls
  results = [None] * len(texts)
  
  for i, t in enumerate(texts):
    t = t.replace("\n", " ")
    if not t:
      t = "this is blank"
    # Check cache first
    if t in _embedding_cache:
      results[i] = _embedding_cache[t]
    else:
      cleaned.append(t)
      indices_to_fetch.append(i)
  
  if cleaned:
    response = openai.Embedding.create(
      input=cleaned,
      model=model,
      api_base=ollama_api_base,
      api_key="ollama"
    )
    for j, item in enumerate(response['data']):
      emb = item['embedding']
      if len(emb) < 1536:
        emb = emb + [0.0] * (1536 - len(emb))
      elif len(emb) > 1536:
        emb = emb[:1536]
      orig_idx = indices_to_fetch[j]
      results[orig_idx] = emb
      _embedding_cache[cleaned[j]] = emb
  
  return results


if __name__ == '__main__':
  gpt_parameter = {"engine": "text-davinci-003", "max_tokens": 50, 
                   "temperature": 0, "top_p": 1, "stream": False,
                   "frequency_penalty": 0, "presence_penalty": 0, 
                   "stop": ['"']}
  curr_input = ["driving to a friend's house"]
  prompt_lib_file = "prompt_template/test_prompt_July5.txt"
  prompt = generate_prompt(curr_input, prompt_lib_file)

  def __func_validate(gpt_response): 
    if len(gpt_response.strip()) <= 1:
      return False
    if len(gpt_response.strip().split(" ")) > 1: 
      return False
    return True
  def __func_clean_up(gpt_response):
    cleaned_response = gpt_response.strip()
    return cleaned_response

  output = safe_generate_response(prompt, 
                                 gpt_parameter,
                                 5,
                                 "rest",
                                 __func_validate,
                                 __func_clean_up,
                                 True)

  print (output)










