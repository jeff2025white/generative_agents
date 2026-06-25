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

from utils import *

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

def _load_cache():
  global _cache
  try:
    if os.path.exists(_cache_file):
      with open(_cache_file, "r", encoding="utf-8") as f:
        _cache = json.load(f)
      print(f"[Cache] Loaded {len(_cache)} cached responses.")
  except Exception as e:
    print(f"[Cache] Failed to load cache: {e}")
    _cache = {}

def _save_cache():
  try:
    with open(_cache_file, "w", encoding="utf-8") as f:
      json.dump(_cache, f, ensure_ascii=False)
  except Exception as e:
    print(f"[Cache] Failed to save cache: {e}")

def _cache_key(prompt, extra=""):
  raw = prompt + str(extra)
  return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _get_cached(key):
  global _cache_hits
  with _cache_lock:
    val = _cache.get(key)
    if val is not None:
      _cache_hits += 1
      if _cache_hits % 50 == 0:
        print(f"[Cache] Stats: {_cache_hits} hits / {_cache_misses} misses")
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
    print(f"[Cache] Saved {len(_cache)} entries. Hits: {_cache_hits}, Misses: {_cache_misses}")

# ============================================================================

def temp_sleep(seconds=0.1):
  time.sleep(seconds)

def ChatGPT_single_request(prompt): 
  # Check cache first
  key = _cache_key(prompt, "single")
  cached = _get_cached(key)
  if cached is not None:
    return cached

  temp_sleep()

  completion = openai.ChatCompletion.create(
    model=gpt35_model, 
    messages=[
      {"role": "system", "content": "You are a precise text completion engine. When given a prompt that ends in a sentence fragment, complete it directly without any introduction or conversational text. Do not repeat the prompt. Output ONLY the text that completes the sentence fragment. If the prompt asks for a JSON object, output only the JSON object."},
      {"role": "user", "content": prompt}
    ]
  )
  result = completion["choices"][0]["message"]["content"]
  _set_cached(key, result)
  return result


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
  # Check cache first
  key = _cache_key(prompt, "gpt4")
  cached = _get_cached(key)
  if cached is not None:
    return cached

  temp_sleep()

  try: 
    completion = openai.ChatCompletion.create(
    model=gpt4_model, 
    messages=[
      {"role": "system", "content": "You are a precise text completion engine. When given a prompt that ends in a sentence fragment, complete it directly without any introduction or conversational text. Do not repeat the prompt. Output ONLY the text that completes the sentence fragment. If the prompt asks for a JSON object, output only the JSON object."},
      {"role": "user", "content": prompt}
    ]
    )
    result = completion["choices"][0]["message"]["content"]
    _set_cached(key, result)
    return result
  
  except: 
    print ("ChatGPT ERROR")
    return "ChatGPT ERROR"


def ChatGPT_request(prompt): 
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
  key = _cache_key(prompt, "chatgpt")
  cached = _get_cached(key)
  if cached is not None:
    return cached

  # temp_sleep()
  try: 
    completion = openai.ChatCompletion.create(
    model=gpt35_model, 
    messages=[
      {"role": "system", "content": "You are a precise text completion engine. When given a prompt that ends in a sentence fragment, complete it directly without any introduction or conversational text. Do not repeat the prompt. Output ONLY the text that completes the sentence fragment. If the prompt asks for a JSON object, output only the JSON object."},
      {"role": "user", "content": prompt}
    ]
    )
    result = completion["choices"][0]["message"]["content"]
    _set_cached(key, result)
    return result
  
  except: 
    print ("ChatGPT ERROR")
    return "ChatGPT ERROR"


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
      curr_gpt_response = GPT4_request(prompt).strip()
      end_index = curr_gpt_response.rfind('}') + 1
      curr_gpt_response = curr_gpt_response[:end_index]
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
                                   verbose=False): 
  # prompt = 'GPT-3 Prompt:\n"""\n' + prompt + '\n"""\n'
  prompt = '"""\n' + prompt + '\n"""\n'
  prompt += f"Output the response to the prompt above in json. {special_instruction}\n"
  prompt += "Example output json:\n"
  prompt += '{"output": "' + str(example_output) + '"}'

  if verbose: 
    print ("CHAT GPT PROMPT")
    print (prompt)

  for i in range(repeat): 
    raw_response = ""
    try: 
      raw_response = ChatGPT_request(prompt)
      curr_gpt_response = raw_response.strip()
      end_index = curr_gpt_response.rfind('}') + 1
      curr_gpt_response = curr_gpt_response[:end_index]
      curr_gpt_response = json.loads(curr_gpt_response)["output"]
      
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      
      if verbose: 
        print ("---- repeat count (validation failed): \n", i, curr_gpt_response)
        print (curr_gpt_response)
        print ("~~~~")

    except Exception as e: 
      if verbose:
        print(f"--- ChatGPT_safe_generate_response Exception on attempt {i}: {e}")
        print(f"Raw response: {raw_response!r}")
      pass

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
  if use_cache:
    key = _cache_key(prompt, str(sorted(gpt_parameter.items())))
    cached = _get_cached(key)
    if cached is not None:
      return cached

  temp_sleep()
  try: 
    stop_sequence = gpt_parameter.get("stop", None)
    response = openai.ChatCompletion.create(
                model=gpt35_model,
                messages=[
                  {"role": "system", "content": "You are a precise text completion engine. When given a prompt that ends in a sentence fragment, complete it directly without any introduction or conversational text. Do not repeat the prompt. Output ONLY the text that completes the sentence fragment. If the prompt asks for a JSON object, output only the JSON object."},
                  {"role": "user", "content": prompt}
                ],
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

  f = open(prompt_lib_file, "r")
  prompt = f.read()
  f.close()
  for count, i in enumerate(curr_input):   
    prompt = prompt.replace(f"!<INPUT {count}>!", i)
  if "<commentblockmarker>###</commentblockmarker>" in prompt: 
    prompt = prompt.split("<commentblockmarker>###</commentblockmarker>")[1]
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




















