"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: run_gpt_prompt.py
Description: Defines all run gpt prompt functions. These functions directly
interface with the safe_generate_response function.
"""
import re
import datetime
import sys
import ast
import hashlib

sys.path.append('../../')

from global_methods import *
from llm_api_config import get_task_route_request_config
from persona.cognitive_modules.debug_log import append_debug_log
from persona.cognitive_modules.decision_constraints import (
  build_invalid_targets,
  filter_invalid_resources,
)
from persona.cognitive_modules.stage1_prompt_compiler import (
  compile_stage1_prompt_context,
)
from persona.cognitive_modules.motive_selector import (
  build_default_motive_attributes,
  select_motives,
  sync_core_motive_values,
)
from persona.prompt_template.gpt_structure import *
from persona.prompt_template.print_prompt import *
from persona.training.training_candidate_builder import normalize_training_log_record

def get_random_alphanumeric(i=6, j=6): 
  """
  Returns a random alpha numeric strength that has the length of somewhere
  between i and j. 

  INPUT: 
    i: min_range for the length
    j: max_range for the length
  OUTPUT: 
    an alpha numeric str with the length of somewhere between i and j.
  """
  k = random.randint(i, j)
  x = ''.join(random.choices(string.ascii_letters + string.digits, k=k))
  return x


def _build_motive_prompt_instruction(persona):
  scratch = getattr(persona, "scratch", None)
  if scratch is None:
    return ""
  getter = getattr(scratch, "get_motive_attributes_snapshot", None)
  if callable(getter):
    motive_attributes = getter()
  else:
    motive_attributes = sync_core_motive_values(
      build_default_motive_attributes(),
      satiety=getattr(scratch, "satiety", 100.0),
      stamina=getattr(scratch, "stamina", 100.0),
      health=getattr(scratch, "health", 100.0),
      mood=getattr(scratch, "mood", 100.0),
    )
  motive_result = select_motives(motive_attributes)
  motive_sentence = str(motive_result.get("motive_sentence") or "").strip()
  dominant = str(motive_result.get("dominant_motive") or "").strip()
  has_urgent_motive = bool(motive_result.get("has_urgent_motive"))
  if not has_urgent_motive:
    if not dominant:
      return ""
    return (
      "Current motive guidance: internal motives are broadly stable. "
      f"Treat {dominant} only as a light tie-breaker among otherwise feasible immediate options, "
      "not as an urgent need."
    )
  if not motive_sentence:
    return ""
  return (
    f"Current motive guidance: {motive_sentence} "
    "This is the highest-priority internal guidance for the immediate next action. "
    "Treat the dominant motive as the main reason for the choice, and only deviate from it when hard physical constraints or execution impossibility force a fallback."
  )


def _run_task_routed_text_prompt(prompt,
                                 example_output,
                                 special_instruction,
                                 fail_safe,
                                 func_validate,
                                 func_clean_up,
                                 prompt_kind,
                                 route_name,
                                 repeat=3,
                                 verbose=False,
                                 metadata=None,
                                 request_config=None):
  """Run a legacy text prompt through the centralized task-route config."""
  resolved_request_config = request_config or get_task_route_request_config(route_name)
  output = ChatGPT_safe_generate_response(
    prompt,
    example_output,
    special_instruction,
    repeat=repeat,
    fail_safe_response=fail_safe,
    func_validate=func_validate,
    func_clean_up=func_clean_up,
    verbose=verbose,
    prompt_kind=prompt_kind,
    metadata=dict(metadata or {}, llm_route=route_name),
    request_config=resolved_request_config,
  )
  return output, {"task_route": route_name, "request_config": resolved_request_config}


def _prompt_hash(prompt):
  try:
    return hashlib.sha256(str(prompt).encode("utf-8")).hexdigest()[:12]
  except Exception:
    return "unhashable"


def _build_minimal_decision_filter_context(persona, nearby_resources):
  scratch = getattr(persona, "scratch", None)
  invalid_targets = build_invalid_targets(scratch)
  filtered_resources = filter_invalid_resources(nearby_resources, invalid_targets)
  original_count = len(list(nearby_resources or []))
  filtered_count = len(list(filtered_resources or []))
  removed_count = max(0, original_count - filtered_count)
  return {
    "enabled": True,
    "applied": bool(invalid_targets or removed_count),
    "invalid_targets": invalid_targets,
    "invalid_target_count": len(invalid_targets),
    "resource_filter_applied": removed_count > 0,
    "removed_resource_count": removed_count,
    "output_validation_enabled": True,
  }


def _append_training_prep_prompt_log(persona, prompt_kind, prompt, decision_id=None, minimal_filter_context=None):
  if not decision_id:
    return
  append_debug_log(
    "training_dataset/decision_training_prep.jsonl",
    normalize_training_log_record(
      {
        "event": "prompt_logged",
        "decision_id": decision_id,
        "persona": getattr(persona, "name", None),
        "curr_step": getattr(getattr(persona, "scratch", None), "curr_step", None),
        "prompt_kind": prompt_kind,
        "final_prompt": prompt,
        "prompt_hash": _prompt_hash(prompt),
        "decision": None,
        "execution_outcome": None,
        "minimal_filter_enabled": bool((minimal_filter_context or {}).get("enabled")),
        "minimal_filter_applied": bool((minimal_filter_context or {}).get("applied")),
        "minimal_filter_summary": minimal_filter_context or {},
      }
    ),
  )


DECISION_PROMPT_TRACE_LOG = "decision_prompt_trace.jsonl"
_DECISION_TRACE_STAGE_ORDER = {
  "demand_thinking": 10,
  "joint_decision": 10,
  "action_translation": 20,
  "final_decision": 30,
}


def _format_persona_sim_time(persona):
  curr_time = getattr(getattr(persona, "scratch", None), "curr_time", None)
  if curr_time is None:
    return None
  try:
    if isinstance(curr_time, str):
      return curr_time
    return curr_time.strftime("%Y-%m-%d %H:%M:%S")
  except Exception:
    return str(curr_time)


def _append_decision_prompt_trace(persona,
                                  prompt_kind,
                                  prompt,
                                  llm_response,
                                  decision_id=None,
                                  prompt_template=None,
                                  minimal_filter_context=None,
                                  extra=None):
  append_debug_log(
    DECISION_PROMPT_TRACE_LOG,
    {
      "event": "prompt_response",
      "stage": prompt_kind,
      "stage_order": _DECISION_TRACE_STAGE_ORDER.get(prompt_kind, 99),
      "decision_id": decision_id,
      "persona": getattr(persona, "name", None),
      "curr_step": getattr(getattr(persona, "scratch", None), "curr_step", None),
      "sim_time": _format_persona_sim_time(persona),
      "prompt_kind": prompt_kind,
      "prompt_template": prompt_template,
      "final_prompt": prompt,
      "prompt_hash": _prompt_hash(prompt),
      "llm_response": llm_response,
      "minimal_filter_enabled": bool((minimal_filter_context or {}).get("enabled")),
      "minimal_filter_applied": bool((minimal_filter_context or {}).get("applied")),
      "minimal_filter_summary": minimal_filter_context or {},
      **dict(extra or {}),
    },
  )


def _get_recent_action_observation(scratch, max_age_steps=6):
  getter = getattr(scratch, "get_recent_action_observation", None)
  if callable(getter):
    return getter(max_age_steps=max_age_steps)
  return getattr(scratch, "last_action_observation", None)


def _build_recent_observation_line(scratch):
  observation = _get_recent_action_observation(scratch)
  if not observation:
    return None
  result = str(observation.get("result") or "unknown").strip().lower()
  reason = str(observation.get("reason") or "").strip().lower()
  target = observation.get("target") or "unknown"
  target_address = observation.get("target_address") or "unknown"
  curr_step = observation.get("curr_step")
  if result == "failed" and reason == "resource_empty":
    return (
      "Observation: "
      f"step={curr_step} result=failed target={target} target_address={target_address} "
      "outcome=reached_target_but_resource_empty. "
      "This is the latest execution feedback from the environment."
    )
  if result == "failed":
    return (
      "Observation: "
      f"step={curr_step} result=failed target={target} target_address={target_address} "
      f"reason={reason or 'unknown'}. "
      "This is the latest execution feedback from the environment."
    )
  action_description = observation.get("action_description") or observation.get("skill_id") or "previous action"
  return (
    "Observation: "
    f"step={curr_step} result=completed target={target} target_address={target_address} "
    f"outcome={_compact_multiline_block(str(action_description), max_lines=1, max_chars=120)}. "
    "This is the latest execution feedback from the environment."
  )


def _build_last_action_with_result_line(last_action_desc, scratch):
  action_text = _compact_multiline_block(last_action_desc or "None", max_lines=1, max_chars=160)
  observation = _get_recent_action_observation(scratch) or {}
  result = str(observation.get("result") or "").strip().lower()
  reason = _compact_multiline_block(observation.get("reason") or "none", max_lines=1, max_chars=80)
  target = _compact_multiline_block(observation.get("target") or "unknown", max_lines=1, max_chars=80)
  if result == "completed":
    outcome = observation.get("action_description") or observation.get("skill_id") or "completed"
    outcome = _compact_multiline_block(str(outcome), max_lines=1, max_chars=120)
    return (
      f"LastAction: {action_text} | execution_status=completed | "
      f"target={target} | failure_reason=none | outcome={outcome}"
    )
  if result == "failed":
    return (
      f"LastAction: {action_text} | execution_status=failed | "
      f"target={target} | failure_reason={reason}"
    )
  if result:
    return (
      f"LastAction: {action_text} | execution_status={result} | "
      f"target={target} | failure_reason={reason}"
    )
  return f"LastAction: {action_text} | execution_status=unknown | failure_reason=none"


def _build_current_action_record_line(scratch):
  record = getattr(scratch, "current_action_record", None) or {}
  if not record:
    return None
  status = str(record.get("status") or "unknown").strip().lower()
  skill_id = record.get("skill_id") or "unknown"
  target = record.get("target") or "none"
  target_type = record.get("target_type") or "unknown"
  resolved_target = record.get("resolved_target") or target
  resolved_address = record.get("resolved_address") or "unknown"
  resolution_kind = record.get("resolution_kind") or "unknown"
  failure = record.get("failure") or {}
  failure_reason = failure.get("reason") or record.get("target_resolution_failure")
  base = (
    "CurrentAction: "
    f"status={status} skill={skill_id} target={target} target_type={target_type} "
    f"resolved_target={resolved_target} address={resolved_address} resolution={resolution_kind}."
  )
  if status in {"failed", "interrupted", "cleared"}:
    return (
      f"{base} The previous action chain is no longer executable as-is. "
      f"Latest failure={failure_reason or 'unknown'}. "
      "Use this as fresh evidence and choose a new feasible immediate target or materially different immediate plan."
    )
  if status in {"pathing", "arrived", "planned", "resolved"}:
    return (
      f"{base} This action chain is still active. "
      "Continue it by default unless the newest evidence clearly changes urgency, safety, or feasibility."
    )
  if status == "completed":
    return f"{base} This action chain has already completed."
  return base


##############################################################################
# CHAPTER 1: Run GPT Prompt
##############################################################################

def run_gpt_prompt_wake_up_hour(persona, test_input=None, verbose=False, request_config=None): 
  """
  Given the persona, returns an integer that indicates the hour when the 
  persona wakes up.  

  INPUT: 
    persona: The Persona class instance 
  OUTPUT: 
    integer for the wake up hour.
  """
  def create_prompt_input(persona, test_input=None): 
    if test_input: return test_input
    prompt_input = [persona.scratch.get_str_iss(),
                    persona.scratch.get_str_lifestyle(),
                    persona.scratch.get_str_firstname()]
    return prompt_input

  def __func_clean_up(gpt_response, prompt=""):
    cr = int(gpt_response.strip().lower().split("am")[0])
    return cr
  
  def __func_validate(gpt_response, prompt=""): 
    try: __func_clean_up(gpt_response, prompt="")
    except: return False
    return True

  def get_fail_safe(): 
    fs = 8
    return fs

  prompt_template = "persona/prompt_template/v2/wake_up_hour_v1.txt"
  prompt_input = create_prompt_input(persona, test_input)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "8am",
    "Return only the wake-up hour in the format like 6am or 8am. Do not include any explanation.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="wake_up_hour",
    route_name="planning",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  
  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
    
  return output, [output, prompt, route_meta, prompt_input, fail_safe]


def run_gpt_prompt_daily_plan(persona, 
                              wake_up_hour, 
                              test_input=None, 
                              verbose=False,
                              request_config=None):
  """
  Basically the long term planning that spans a day. Returns a list of actions
  that the persona will take today. Usually comes in the following form: 
  'wake up and complete the morning routine at 6:00 am', 
  'eat breakfast at 7:00 am',.. 
  Note that the actions come without a period. 

  INPUT: 
    persona: The Persona class instance 
  OUTPUT: 
    a list of daily actions in broad strokes.
  """
  def create_prompt_input(persona, wake_up_hour, test_input=None):
    if test_input: return test_input
    prompt_input = []
    prompt_input += [persona.scratch.get_str_iss()]
    prompt_input += [persona.scratch.get_str_lifestyle()]
    prompt_input += [persona.scratch.get_str_curr_date_str()]
    prompt_input += [persona.scratch.get_str_firstname()]
    prompt_input += [f"{str(wake_up_hour)}:00 am"]
    return prompt_input

  def __func_clean_up(gpt_response, prompt=""):
    import re
    cr = []
    lines = gpt_response.replace('\r', '').split('\n')
    for line in lines:
      line = line.strip()
      if not line:
        continue
      line = re.sub(r'^(?:\d+[\.\)]|[\-\*])\s*', '', line).strip()
      if line:
        if line[-1] in ['.', ',']:
          line = line[:-1].strip()
        cr.append(line)
        
    if len(cr) <= 1:
      parts = re.split(r'\d+[\.\)]\s*', gpt_response)
      cr = []
      for part in parts:
        part = part.strip()
        if not part:
          continue
        if part[-1] in ['.', ',']:
          part = part[:-1].strip()
        cr.append(part)
        
    return cr

  def __func_validate(gpt_response, prompt=""):
    try: 
      res = __func_clean_up(gpt_response, prompt="")
      if not res or len(res) < 2:
        return False
    except: 
      return False
    return True

  def get_fail_safe(): 
    fs = ['wake up and complete the morning routine at 6:00 am', 
          'eat breakfast at 7:00 am', 
          'read a book from 8:00 am to 12:00 pm', 
          'have lunch at 12:00 pm', 
          'take a nap from 1:00 pm to 4:00 pm', 
          'relax and watch TV from 7:00 pm to 8:00 pm', 
          'go to bed at 11:00 pm'] 
    return fs


  
  prompt_template = "persona/prompt_template/v2/daily_planning_v6.txt"
  prompt_input = create_prompt_input(persona, wake_up_hour, test_input)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "1) eat breakfast at 7:00 am\n2) read a book from 8:00 am to 12:00 pm",
    "Return a concise ordered daily plan with one activity per line and no extra commentary.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="daily_plan",
    route_name="planning",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  output = ([f"wake up and complete the morning routine at {wake_up_hour}:00 am"]
              + output)

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
    
  return output, [output, prompt, route_meta, prompt_input, fail_safe]


def run_gpt_prompt_generate_hourly_schedule(persona, 
                                            curr_hour_str,
                                            p_f_ds_hourly_org, 
                                            hour_str,
                                            intermission2=None,
                                            test_input=None, 
                                            verbose=False,
                                            request_config=None): 
  def create_prompt_input(persona, 
                          curr_hour_str, 
                          p_f_ds_hourly_org,
                          hour_str,
                          intermission2=None,
                          test_input=None): 
    if test_input: return test_input
    schedule_format = ""
    for i in hour_str: 
      schedule_format += f"[{persona.scratch.get_str_curr_date_str()} -- {i}]"
      schedule_format += f" Activity: [Fill in]\n"
    schedule_format = schedule_format[:-1]

    intermission_str = f"Here the originally intended hourly breakdown of"
    intermission_str += f" {persona.scratch.get_str_firstname()}'s schedule today: "
    for count, i in enumerate(persona.scratch.daily_req): 
      intermission_str += f"{str(count+1)}) {i}, "
    intermission_str = intermission_str[:-2]

    prior_schedule = ""
    if p_f_ds_hourly_org: 
      prior_schedule = "\n"
      for count, i in enumerate(p_f_ds_hourly_org): 
        prior_schedule += f"[(ID:{get_random_alphanumeric()})" 
        prior_schedule += f" {persona.scratch.get_str_curr_date_str()} --"
        prior_schedule += f" {hour_str[count]}] Activity:"
        prior_schedule += f" {persona.scratch.get_str_firstname()}"
        prior_schedule += f" is {i}\n"

    prompt_ending = f"[(ID:{get_random_alphanumeric()})"
    prompt_ending += f" {persona.scratch.get_str_curr_date_str()}"
    prompt_ending += f" -- {curr_hour_str}] Activity:"
    prompt_ending += f" {persona.scratch.get_str_firstname()} is"

    if intermission2: 
      intermission2 = f"\n{intermission2}"

    prompt_input = []
    prompt_input += [schedule_format]
    prompt_input += [persona.scratch.get_str_iss()]

    prompt_input += [prior_schedule + "\n"]
    prompt_input += [intermission_str]
    if intermission2: 
      prompt_input += [intermission2]
    else: 
      prompt_input += [""]
    prompt_input += [prompt_ending]

    return prompt_input

  def __func_clean_up(gpt_response, prompt=""):
    cr = gpt_response.strip()
    if cr[-1] == ".":
      cr = cr[:-1]
    return cr

  def __func_validate(gpt_response, prompt=""): 
    try: __func_clean_up(gpt_response, prompt="")
    except: return False
    return True

  def get_fail_safe(): 
    fs = "asleep"
    return fs

  # # ChatGPT Plugin ===========================================================
  # def __chat_func_clean_up(gpt_response, prompt=""): ############
  #   cr = gpt_response.strip()
  #   if cr[-1] == ".":
  #     cr = cr[:-1]
  #   return cr

  # def __chat_func_validate(gpt_response, prompt=""): ############
  #   try: __func_clean_up(gpt_response, prompt="")
  #   except: return False
  #   return True

  # print ("asdhfapsh8p9hfaiafdsi;ldfj as DEBUG 10") ########
  # gpt_param = {"engine": "text-davinci-002", "max_tokens": 15, 
  #              "temperature": 0, "top_p": 1, "stream": False,
  #              "frequency_penalty": 0, "presence_penalty": 0, "stop": None}
  # prompt_template = "persona/prompt_template/v3_ChatGPT/generate_hourly_schedule_v2.txt" ########
  # prompt_input = create_prompt_input(persona, 
  #                                    curr_hour_str, 
  #                                    p_f_ds_hourly_org,
  #                                    hour_str, 
  #                                    intermission2,
  #                                    test_input)  ########
  # prompt = generate_prompt(prompt_input, prompt_template)
  # example_output = "studying for her music classes" ########
  # special_instruction = "The output should ONLY include the part of the sentence that completes the last line in the schedule above." ########
  # fail_safe = get_fail_safe() ########
  # output = ChatGPT_safe_generate_response(prompt, example_output, special_instruction, 3, fail_safe,
  #                                         __chat_func_validate, __chat_func_clean_up, True)
  # if output != False: 
  #   return output, [output, prompt, gpt_param, prompt_input, fail_safe]
  # # ChatGPT Plugin ===========================================================


  prompt_template = "persona/prompt_template/v2/generate_hourly_schedule_v2.txt"
  prompt_input = create_prompt_input(persona, 
                                     curr_hour_str, 
                                     p_f_ds_hourly_org,
                                     hour_str, 
                                     intermission2,
                                     test_input)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "studying for her music classes",
    "Return only the phrase that completes the final schedule line. Do not include the full prefix or any explanation.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="hourly_schedule",
    route_name="planning",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  
  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
    
  return output, [output, prompt, route_meta, prompt_input, fail_safe]








def run_gpt_prompt_task_decomp(persona, 
                               task, 
                               duration, 
                               test_input=None, 
                               verbose=False,
                               request_config=None): 
  def create_prompt_input(persona, task, duration, test_input=None):

    """
    Today is Saturday June 25. From 00:00 ~ 06:00am, Maeve is 
    planning on sleeping, 06:00 ~ 07:00am, Maeve is 
    planning on waking up and doing her morning routine, 
    and from 07:00am ~08:00am, Maeve is planning on having breakfast.  
    """
      
    curr_f_org_index = persona.scratch.get_f_daily_schedule_hourly_org_index()
    all_indices = []
    # if curr_f_org_index > 0: 
    #   all_indices += [curr_f_org_index-1]
    all_indices += [curr_f_org_index]
    if curr_f_org_index+1 <= len(persona.scratch.f_daily_schedule_hourly_org): 
      all_indices += [curr_f_org_index+1]
    if curr_f_org_index+2 <= len(persona.scratch.f_daily_schedule_hourly_org): 
      all_indices += [curr_f_org_index+2]

    curr_time_range = ""

    summ_str = f'Today is {persona.scratch.curr_time.strftime("%B %d, %Y")}. '
    summ_str += f'From '
    for index in all_indices: 
      if index < len(persona.scratch.f_daily_schedule_hourly_org): 
        start_min = 0
        for i in range(index): 
          start_min += persona.scratch.f_daily_schedule_hourly_org[i][1]
        end_min = start_min + persona.scratch.f_daily_schedule_hourly_org[index][1]
        start_time = (datetime.datetime.strptime("00:00:00", "%H:%M:%S") 
                      + datetime.timedelta(minutes=start_min)) 
        end_time = (datetime.datetime.strptime("00:00:00", "%H:%M:%S") 
                      + datetime.timedelta(minutes=end_min)) 
        start_time_str = start_time.strftime("%H:%M%p")
        end_time_str = end_time.strftime("%H:%M%p")
        summ_str += f"{start_time_str} ~ {end_time_str}, {persona.name} is planning on {persona.scratch.f_daily_schedule_hourly_org[index][0]}, "
        if curr_f_org_index+1 == index:
          curr_time_range = f'{start_time_str} ~ {end_time_str}'
    summ_str = summ_str[:-2] + "."

    prompt_input = []
    prompt_input += [persona.scratch.get_str_iss()]
    prompt_input += [summ_str]
    # prompt_input += [persona.scratch.get_str_curr_date_str()]
    prompt_input += [persona.scratch.get_str_firstname()]
    prompt_input += [persona.scratch.get_str_firstname()]
    prompt_input += [task]
    prompt_input += [curr_time_range]
    prompt_input += [duration]
    prompt_input += [persona.scratch.get_str_firstname()]
    return prompt_input

  def __func_clean_up(gpt_response, prompt=""):
    import re
    temp = [i.strip() for i in gpt_response.split("\n")]
    cr = []
    
    for i in temp:
      if "(duration in minutes:" not in i:
        continue
      k = [j.strip() for j in i.split("(duration in minutes:")]
      task = k[0]
      
      # Strip leading numbers/bullets (e.g., "1) ", "1. ", "- ")
      task = re.sub(r'^\d+[\s\).:-]+', '', task).strip()
      task = re.sub(r'^-\s+', '', task).strip()
      
      # Strip leading "<Agent Name> is " or "<First Name> is " or just "is "
      firstname = persona.scratch.get_str_firstname()
      fullname = persona.name
      if task.startswith(fullname + " is "):
        task = task[len(fullname + " is "):].strip()
      elif task.startswith(firstname + " is "):
        task = task[len(firstname + " is "):].strip()
      elif task.startswith("is "):
        task = task[3:].strip()
        
      if task and task[-1] == ".": 
        task = task[:-1]
        
      try:
        duration = int(k[1].split(",")[0].strip())
        cr += [[task, duration]]
      except:
        pass

    total_expected_min = int(prompt.split("(total duration in minutes")[-1]
                                   .split("):")[0].strip())
    
    # TODO -- now, you need to make sure that this is the same as the sum of 
    #         the current action sequence. 
    curr_min_slot = [["dummy", -1],] # (task_name, task_index)
    for count, i in enumerate(cr): 
      i_task = i[0] 
      i_duration = i[1]

      i_duration -= (i_duration % 5)
      if i_duration > 0: 
        for j in range(i_duration): 
          curr_min_slot += [(i_task, count)]       
    curr_min_slot = curr_min_slot[1:]   

    if not curr_min_slot:
      curr_min_slot = [(task, total_expected_min)]

    if len(curr_min_slot) > total_expected_min: 
      last_task = curr_min_slot[60]
      for i in range(1, 6): 
        curr_min_slot[-1 * i] = last_task
    elif len(curr_min_slot) < total_expected_min: 
      last_task = curr_min_slot[-1]
      for i in range(total_expected_min - len(curr_min_slot)):
        curr_min_slot += [last_task]

    cr_ret = [["dummy", -1],]
    for task, task_index in curr_min_slot: 
      if task != cr_ret[-1][0]: 
        cr_ret += [[task, 1]]
      else: 
        cr_ret[-1][1] += 1
    cr = cr_ret[1:]

    return cr

  def __func_validate(gpt_response, prompt=""): 
    try: 
      res = __func_clean_up(gpt_response, prompt=prompt)
      if not res:
        return False
    except: 
      return False
    return True

  def get_fail_safe(): 
    fs = ["asleep"]
    return fs

  prompt_template = "persona/prompt_template/v2/task_decomp_v3.txt"
  prompt_input = create_prompt_input(persona, task, duration)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "1. wake up (duration in minutes: 60)\n2. eat breakfast (duration in minutes: 30)",
    "Return only the task decomposition lines in the requested format. Do not include explanations.",
    get_fail_safe(),
    __func_validate,
    __func_clean_up,
    prompt_kind="task_decomp",
    route_name="planning",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  # TODO THERE WAS A BUG HERE... 
  # This is for preventing overflows...
  """
  File "/Users/joonsungpark/Desktop/Stanford/Projects/
  generative-personas/src_exploration/reverie_simulation/
  brain/get_next_action_v3.py", line 364, in run_gpt_prompt_task_decomp
  fin_output[-1][1] += (duration - ftime_sum)
  IndexError: list index out of range
  """

  fin_output = []
  time_sum = 0
  for i_task, i_duration in output: 
    time_sum += i_duration
    # HM?????????
    # if time_sum < duration: 
    if time_sum <= duration: 
      fin_output += [[i_task, i_duration]]
    else: 
      break
  ftime_sum = 0
  for fi_task, fi_duration in fin_output: 
    ftime_sum += fi_duration
  
  # print ("for debugging... line 365", fin_output)
  fin_output[-1][1] += (duration - ftime_sum)
  output = fin_output 



  task_decomp = output
  ret = []
  for decomp_task, duration in task_decomp: 
    ret += [[f"{task} ({decomp_task})", duration]]
  output = ret


  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
    
  return output, [output, prompt, route_meta, prompt_input, fail_safe]



def run_gpt_prompt_action_sector(action_description, 
                                persona, 
                                maze, 
                                test_input=None, 
                                verbose=False,
                                request_config=None):
  def create_prompt_input(action_description, persona, maze, test_input=None): 
    act_world = f"{maze.access_tile(persona.scratch.curr_tile)['world']}"
    
    prompt_input = []
    
    prompt_input += [persona.scratch.get_str_name()]
    prompt_input += [persona.scratch.living_area.split(":")[1]]
    x = f"{act_world}:{persona.scratch.living_area.split(':')[1]}"
    prompt_input += [persona.s_mem.get_str_accessible_sector_arenas(x)]


    prompt_input += [persona.scratch.get_str_name()]
    prompt_input += [f"{maze.access_tile(persona.scratch.curr_tile)['sector']}"]
    x = f"{act_world}:{maze.access_tile(persona.scratch.curr_tile)['sector']}"
    prompt_input += [persona.s_mem.get_str_accessible_sector_arenas(x)]

    if persona.scratch.get_str_daily_plan_req() != "": 
      prompt_input += [f"\n{persona.scratch.get_str_daily_plan_req()}"]
    else: 
      prompt_input += [""]


    # MAR 11 TEMP
    accessible_sector_str = persona.s_mem.get_str_accessible_sectors(act_world)
    curr = accessible_sector_str.split(", ")
    fin_accessible_sectors = []
    for i in curr: 
      if "'s house" in i: 
        if persona.scratch.last_name in i: 
          fin_accessible_sectors += [i]
      else: 
        fin_accessible_sectors += [i]
    accessible_sector_str = ", ".join(fin_accessible_sectors)
    # END MAR 11 TEMP

    prompt_input += [accessible_sector_str]



    action_description_1 = action_description
    action_description_2 = action_description
    if "(" in action_description: 
      action_description_1 = action_description.split("(")[0].strip()
      action_description_2 = action_description.split("(")[-1][:-1]
    prompt_input += [persona.scratch.get_str_name()]
    prompt_input += [action_description_1]

    prompt_input += [action_description_2]
    prompt_input += [persona.scratch.get_str_name()]
    return prompt_input


    

    


  def __func_clean_up(gpt_response, prompt=""):
    cleaned_response = gpt_response.split("}")[0].strip()
    cleaned_response = cleaned_response.strip("{").strip("}").strip()
    return cleaned_response

  def __func_validate(gpt_response, prompt=""): 
    if len(gpt_response.strip()) < 1: 
      return False
    if "," in gpt_response: 
      return False
    return True
  
  def get_fail_safe(): 
    fs = ("kitchen")
    return fs


  # # ChatGPT Plugin ===========================================================
  # def __chat_func_clean_up(gpt_response, prompt=""): ############
  #   cr = gpt_response.strip()
  #   return cr

  # def __chat_func_validate(gpt_response, prompt=""): ############
  #   try: 
  #     gpt_response = __func_clean_up(gpt_response, prompt="")
  #   except: 
  #     return False
  #   return True 

  # print ("asdhfapsh8p9hfaiafdsi;ldfj as DEBUG 20") ########
  # gpt_param = {"engine": "text-davinci-002", "max_tokens": 15, 
  #              "temperature": 0, "top_p": 1, "stream": False,
  #              "frequency_penalty": 0, "presence_penalty": 0, "stop": None}
  # prompt_template = "persona/prompt_template/v3_ChatGPT/action_location_sector_v2.txt" ########
  # prompt_input = create_prompt_input(action_description, persona, maze)  ########
  # prompt = generate_prompt(prompt_input, prompt_template)
  # example_output = "Johnson Park" ########
  # special_instruction = "The value for the output must contain one of the area options above verbatim (including lower/upper case)." ########
  # fail_safe = get_fail_safe() ########
  # output = ChatGPT_safe_generate_response(prompt, example_output, special_instruction, 3, fail_safe,
  #                                         __chat_func_validate, __chat_func_clean_up, True)
  # if output != False: 
  #   return output, [output, prompt, gpt_param, prompt_input, fail_safe]
  # # ChatGPT Plugin ===========================================================


  prompt_template = "persona/prompt_template/v1/action_location_sector_v1.txt"
  prompt_input = create_prompt_input(action_description, persona, maze)
  prompt = generate_prompt(prompt_input, prompt_template)

  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "kitchen",
    "Return exactly one accessible sector name from the provided options. Do not include explanations or punctuation beyond the name itself.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="action_sector",
    route_name="location_selection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  y = f"{maze.access_tile(persona.scratch.curr_tile)['world']}"
  x = [i.strip() for i in persona.s_mem.get_str_accessible_sectors(y).split(",")]
  if output not in x: 
    # output = random.choice(x)
    output = persona.scratch.living_area.split(":")[1]

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)

  return output, [output, prompt, route_meta, prompt_input, fail_safe]



def run_gpt_prompt_action_arena(action_description, 
                                persona, 
                                maze, act_world, act_sector,
                                test_input=None, 
                                verbose=False,
                                request_config=None):
  def create_prompt_input(action_description, persona, maze, act_world, act_sector, test_input=None): 
    prompt_input = []
    # prompt_input += [persona.scratch.get_str_name()]
    # prompt_input += [maze.access_tile(persona.scratch.curr_tile)["arena"]]
    # prompt_input += [maze.access_tile(persona.scratch.curr_tile)["sector"]]
    prompt_input += [persona.scratch.get_str_name()]
    x = f"{act_world}:{act_sector}"
    prompt_input += [act_sector]

    # MAR 11 TEMP
    accessible_arena_str = persona.s_mem.get_str_accessible_sector_arenas(x)
    curr = accessible_arena_str.split(", ")
    fin_accessible_arenas = []
    for i in curr: 
      if "'s room" in i: 
        if persona.scratch.last_name in i: 
          fin_accessible_arenas += [i]
      else: 
        fin_accessible_arenas += [i]
    accessible_arena_str = ", ".join(fin_accessible_arenas)
    # END MAR 11 TEMP


    prompt_input += [accessible_arena_str]


    action_description_1 = action_description
    action_description_2 = action_description
    if "(" in action_description: 
      action_description_1 = action_description.split("(")[0].strip()
      action_description_2 = action_description.split("(")[-1][:-1]
    prompt_input += [persona.scratch.get_str_name()]
    prompt_input += [action_description_1]

    prompt_input += [action_description_2]
    prompt_input += [persona.scratch.get_str_name()]

    

    prompt_input += [act_sector]

    prompt_input += [accessible_arena_str]
    # prompt_input += [maze.access_tile(persona.scratch.curr_tile)["arena"]]
    # x = f"{maze.access_tile(persona.scratch.curr_tile)['world']}:{maze.access_tile(persona.scratch.curr_tile)['sector']}:{maze.access_tile(persona.scratch.curr_tile)['arena']}"
    # prompt_input += [persona.s_mem.get_str_accessible_arena_game_objects(x)]

    
    return prompt_input

  def __func_clean_up(gpt_response, prompt=""):
    cleaned_response = gpt_response.split("}")[0].strip()
    cleaned_response = cleaned_response.strip("{").strip("}").strip()
    return cleaned_response

  def __func_validate(gpt_response, prompt=""): 
    if len(gpt_response.strip()) < 1: 
      return False
    if "," in gpt_response: 
      return False
    return True
  
  def get_fail_safe(): 
    fs = ("kitchen")
    return fs

  prompt_template = "persona/prompt_template/v1/action_location_object_vMar11.txt"
  prompt_input = create_prompt_input(action_description, persona, maze, act_world, act_sector)
  prompt = generate_prompt(prompt_input, prompt_template)

  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "kitchen",
    "Return exactly one accessible arena name from the provided options. Do not include explanations or punctuation beyond the name itself.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="action_arena",
    route_name="location_selection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)

  return output, [output, prompt, route_meta, prompt_input, fail_safe]



def run_gpt_prompt_action_game_object(action_description, 
                                      persona, 
                                      maze,
                                      temp_address,
                                      test_input=None, 
                                      verbose=False,
                                      request_config=None): 
  def create_prompt_input(action_description, 
                          persona, 
                          temp_address, 
                          test_input=None): 
    prompt_input = []
    if "(" in action_description: 
      action_description = action_description.split("(")[-1][:-1]
      
    prompt_input += [action_description]
    prompt_input += [persona
                     .s_mem.get_str_accessible_arena_game_objects(temp_address)]
    return prompt_input
  
  def __func_validate(gpt_response, prompt=""): 
    if len(gpt_response.strip()) < 1: 
      return False
    return True

  def __func_clean_up(gpt_response, prompt=""):
    cleaned_response = gpt_response.strip()
    return cleaned_response

  def get_fail_safe(): 
    fs = ("bed")
    return fs

  prompt_template = "persona/prompt_template/v1/action_object_v2.txt"
  prompt_input = create_prompt_input(action_description, 
                                     persona, 
                                     temp_address, 
                                     test_input)
  prompt = generate_prompt(prompt_input, prompt_template)

  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "bed",
    "Return exactly one accessible object name from the provided options. Do not include explanations or punctuation beyond the name itself.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="action_game_object",
    route_name="location_selection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  x = [i.strip() for i in persona.s_mem.get_str_accessible_arena_game_objects(temp_address).split(",")]
  if output not in x: 
    output = random.choice(x)

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]




def run_gpt_prompt_pronunciatio(action_description, persona, verbose=False): 
  def create_prompt_input(action_description): 
    if "(" in action_description: 
      action_description = action_description.split("(")[-1].split(")")[0]
    prompt_input = [action_description]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    cr = gpt_response.strip()
    if len(cr) > 3:
      cr = cr[:3]
    return cr

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt="")
      if len(gpt_response) == 0: 
        return False
    except: return False
    return True 

  def get_fail_safe(): 
    fs = "😋"
    return fs


  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    cr = gpt_response.strip()
    if len(cr) > 3:
      cr = cr[:3]
    return cr

  def __chat_func_validate(gpt_response, prompt=""): ############
    try: 
      __func_clean_up(gpt_response, prompt="")
      if len(gpt_response) == 0: 
        return False
    except: return False
    return True 
    return True

  gpt_param = {"engine": "text-davinci-002", "max_tokens": 15, 
               "temperature": 0, "top_p": 1, "stream": False,
               "frequency_penalty": 0, "presence_penalty": 0, "stop": None}
  prompt_template = "persona/prompt_template/v3_ChatGPT/generate_pronunciatio_v1.txt" ########
  prompt_input = create_prompt_input(action_description)  ########
  prompt = generate_prompt(prompt_input, prompt_template)
  example_output = "🛁🧖‍♀️" ########
  special_instruction = "The value for the output must ONLY contain the emojis." ########
  fail_safe = get_fail_safe()
  request_config = get_task_route_request_config("translation")
  output = ChatGPT_safe_generate_response(prompt, example_output, special_instruction, 3, fail_safe,
                                         __chat_func_validate, __chat_func_clean_up, True,
                                         request_config=request_config)
  if output != False: 
    return output, [output, prompt, {"task_route": "translation", "request_config": request_config}, prompt_input, fail_safe]
  # ChatGPT Plugin ===========================================================





  # gpt_param = {"engine": "text-davinci-003", "max_tokens": 15, 
  #              "temperature": 0, "top_p": 1, "stream": False,
  #              "frequency_penalty": 0, "presence_penalty": 0, "stop": ["\n"]}
  # prompt_template = "persona/prompt_template/v2/generate_pronunciatio_v1.txt"
  # prompt_input = create_prompt_input(action_description)

  # prompt = generate_prompt(prompt_input, prompt_template)

  # fail_safe = get_fail_safe()
  # output = safe_generate_response(prompt, gpt_param, 5, fail_safe,
  #                                  __func_validate, __func_clean_up)

  # if debug or verbose: 
  #   print_run_prompts(prompt_template, persona, gpt_param, 
  #                     prompt_input, prompt, output)
  
  # return output, [output, prompt, gpt_param, prompt_input, fail_safe]







def run_gpt_prompt_event_triple(action_description, persona, verbose=False, request_config=None): 
  def create_prompt_input(action_description, persona): 
    if "(" in action_description: 
      action_description = action_description.split("(")[-1].split(")")[0]
      
    # Load action_schema.json
    import os
    schema_path = os.path.join("persona", "prompt_template", "v2", "action_schema.json")
    try:
      with open(schema_path, "r", encoding="utf-8") as f:
        schema_str = f.read()
    except Exception as e:
      schema_str = "Action Schema defining Categories: Consume, Gather, Rest, Work, Socialize, Give, Rob, Recreate."

    prompt_input = [persona.name, 
                    action_description,
                    schema_str,
                    persona.name]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    if isinstance(gpt_response, (list, tuple)):
      return [str(i).strip() for i in list(gpt_response)[:2]]
    cr = str(gpt_response).strip()
    cr = [i.strip() for i in cr.split(")")[0].split(",")]
    return cr

  def __func_validate(gpt_response, prompt=""): 
    try: 
      gpt_response = __func_clean_up(gpt_response, prompt="")
      if len(gpt_response) != 2: 
        return False
    except: return False
    return True 

  def get_fail_safe(persona): 
    fs = ("is", "idle")
    return fs


  # ChatGPT Plugin ===========================================================
  # def __chat_func_clean_up(gpt_response, prompt=""): ############
  #   cr = gpt_response.strip()
  #   cr = [i.strip() for i in cr.split(")")[0].split(",")]
  #   return cr

  # def __chat_func_validate(gpt_response, prompt=""): ############
  #   try: 
  #     gpt_response = __func_clean_up(gpt_response, prompt="")
  #     if len(gpt_response) != 2: 
  #       return False
  #   except: return False
  #   return True 

  # print ("asdhfapsh8p9hfaiafdsi;ldfj as DEBUG 5") ########
  # gpt_param = {"engine": "text-davinci-002", "max_tokens": 15, 
  #              "temperature": 0, "top_p": 1, "stream": False,
  #              "frequency_penalty": 0, "presence_penalty": 0, "stop": None}
  # prompt_template = "persona/prompt_template/v3_ChatGPT/generate_event_triple_v1.txt" ########
  # prompt_input = create_prompt_input(action_description, persona)  ########
  # prompt = generate_prompt(prompt_input, prompt_template)
  # example_output = "(Jane Doe, cooking, breakfast)" ########
  # special_instruction = "The value for the output must ONLY contain the triple. If there is an incomplete element, just say 'None' but there needs to be three elements no matter what." ########
  # fail_safe = get_fail_safe(persona) ########
  # output = ChatGPT_safe_generate_response(prompt, example_output, special_instruction, 3, fail_safe,
  #                                         __chat_func_validate, __chat_func_clean_up, True)
  # if output != False: 
  #   return output, [output, prompt, gpt_param, prompt_input, fail_safe]
  # ChatGPT Plugin ===========================================================




  prompt_template = "persona/prompt_template/v2/generate_event_triple_v1.txt"
  prompt_input = create_prompt_input(action_description, persona)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe(persona)
  request_config = request_config or get_task_route_request_config("event_triple")
  route_meta = {"task_route": "event_triple", "request_config": request_config}
  output = ChatGPT_safe_generate_response(
    prompt,
    "is, idle",
    "Return only the predicate and object as a short comma-separated pair. Do not include the subject name.",
    repeat=3,
    fail_safe_response=fail_safe,
    func_validate=__func_validate,
    func_clean_up=__func_clean_up,
    verbose=verbose,
    prompt_kind="event_triple",
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  output = (persona.name, output[0], output[1])

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]













def run_gpt_prompt_act_obj_desc(act_game_object, act_desp, persona, verbose=False, request_config=None): 
  def create_prompt_input(act_game_object, act_desp, persona): 
    prompt_input = [act_game_object, 
                    persona.name,
                    act_desp,
                    act_game_object,
                    act_game_object]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    cr = gpt_response.strip()
    if cr[-1] == ".": cr = cr[:-1]
    return cr

  def __func_validate(gpt_response, prompt=""): 
    try: 
      gpt_response = __func_clean_up(gpt_response, prompt="")
    except: 
      return False
    return True 

  def get_fail_safe(act_game_object): 
    fs = f"{act_game_object} is idle"
    return fs

  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    cr = gpt_response.strip()
    if cr[-1] == ".": cr = cr[:-1]
    return cr

  def __chat_func_validate(gpt_response, prompt=""): ############
    try: 
      gpt_response = __func_clean_up(gpt_response, prompt="")
    except: 
      return False
    return True 

  prompt_template = "persona/prompt_template/v3_ChatGPT/generate_obj_event_v1.txt"
  prompt_input = create_prompt_input(act_game_object, act_desp, persona)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe(act_game_object)
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "being fixed",
    "Return only the short object state phrase that should fill the template slot. Do not include explanations.",
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="act_obj_desc",
    route_name="object_state",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]









def run_gpt_prompt_act_obj_event_triple(act_game_object, act_obj_desc, persona, verbose=False, request_config=None): 
  def create_prompt_input(act_game_object, act_obj_desc): 
    prompt_input = [act_game_object, 
                    act_obj_desc,
                    act_game_object]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    cr = gpt_response.strip()
    cr = [i.strip() for i in cr.split(")")[0].split(",")]
    return cr

  def __func_validate(gpt_response, prompt=""): 
    try: 
      gpt_response = __func_clean_up(gpt_response, prompt="")
      if len(gpt_response) != 2: 
        return False
    except: return False
    return True 

  def get_fail_safe(act_game_object): 
    fs = (act_game_object, "is", "idle")
    return fs

  prompt_template = "persona/prompt_template/v2/generate_event_triple_v1.txt"
  prompt_input = create_prompt_input(act_game_object, act_obj_desc)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe(act_game_object)
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "is, idle",
    "Return only the predicate and object as a short comma-separated pair. Do not include the subject name.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="act_obj_event_triple",
    route_name="event_triple",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  output = (act_game_object, output[0], output[1])

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]





def run_gpt_prompt_new_decomp_schedule(persona, 
                                       main_act_dur, 
                                       truncated_act_dur, 
                                       start_time_hour,
                                       end_time_hour, 
                                       inserted_act,
                                       inserted_act_dur,
                                       test_input=None, 
                                       verbose=False,
                                       request_config=None): 
  def create_prompt_input(persona, 
                           main_act_dur, 
                           truncated_act_dur, 
                           start_time_hour,
                           end_time_hour, 
                           inserted_act,
                           inserted_act_dur,
                           test_input=None): 
    persona_name = persona.name
    start_hour_str = start_time_hour.strftime("%H:%M %p")
    end_hour_str = end_time_hour.strftime("%H:%M %p")

    original_plan = ""
    for_time = start_time_hour
    for i in main_act_dur: 
      original_plan += f'{for_time.strftime("%H:%M")} ~ {(for_time + datetime.timedelta(minutes=int(i[1]))).strftime("%H:%M")} -- ' + i[0]
      original_plan += "\n"
      for_time += datetime.timedelta(minutes=int(i[1]))

    new_plan_init = ""
    for_time = start_time_hour
    for count, i in enumerate(truncated_act_dur): 
      new_plan_init += f'{for_time.strftime("%H:%M")} ~ {(for_time + datetime.timedelta(minutes=int(i[1]))).strftime("%H:%M")} -- ' + i[0]
      new_plan_init += "\n"
      if count < len(truncated_act_dur) - 1: 
        for_time += datetime.timedelta(minutes=int(i[1]))

    new_plan_init += (for_time + datetime.timedelta(minutes=int(i[1]))).strftime("%H:%M") + " ~"

    prompt_input = [persona_name, 
                    start_hour_str,
                    end_hour_str,
                    original_plan,
                    persona_name,
                    inserted_act,
                    inserted_act_dur,
                    persona_name,
                    start_hour_str,
                    end_hour_str,
                    end_hour_str,
                    new_plan_init]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    new_schedule = prompt + " " + gpt_response.strip()
    new_schedule = new_schedule.split("The revised schedule:")[-1].strip()
    new_schedule = new_schedule.split("\n")

    ret_temp = []
    for i in new_schedule: 
      ret_temp += [i.split(" -- ")]

    ret = []
    for time_str, action in ret_temp:
      start_time = time_str.split(" ~ ")[0].strip()
      end_time = time_str.split(" ~ ")[1].strip()
      delta = datetime.datetime.strptime(end_time, "%H:%M") - datetime.datetime.strptime(start_time, "%H:%M")
      delta_min = int(delta.total_seconds()/60)
      if delta_min < 0: delta_min = 0
      ret += [[action, delta_min]]

    return ret

  def __func_validate(gpt_response, prompt=""): 
    try: 
      gpt_response = __func_clean_up(gpt_response, prompt)
      dur_sum = 0
      for act, dur in gpt_response: 
        dur_sum += dur
        if str(type(act)) != "<class 'str'>":
          return False 
        if str(type(dur)) != "<class 'int'>":
          return False
      x = prompt.split("\n")[0].split("originally planned schedule from")[-1].strip()[:-1]
      x = [datetime.datetime.strptime(i.strip(), "%H:%M %p") for i in x.split(" to ")]
      delta_min = int((x[1] - x[0]).total_seconds()/60)

      if int(dur_sum) != int(delta_min): 
        return False

    except: 
      return False
    return True 

  def get_fail_safe(main_act_dur, truncated_act_dur): 
    dur_sum = 0
    for act, dur in main_act_dur: dur_sum += dur

    ret = truncated_act_dur[:]
    ret += main_act_dur[len(ret)-1:]

    # If there are access, we need to trim... 
    ret_dur_sum = 0
    count = 0
    over = None
    for act, dur in ret: 
      ret_dur_sum += dur
      if ret_dur_sum == dur_sum: 
        break
      if ret_dur_sum > dur_sum: 
        over = ret_dur_sum - dur_sum
        break
      count += 1 

    if over: 
      ret = ret[:count+1]
      ret[-1][1] -= over

    return ret

  prompt_template = "persona/prompt_template/v2/new_decomp_schedule_v1.txt"
  prompt_input = create_prompt_input(persona, 
                                     main_act_dur, 
                                     truncated_act_dur, 
                                     start_time_hour,
                                     end_time_hour, 
                                     inserted_act,
                                     inserted_act_dur,
                                     test_input)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe(main_act_dur, truncated_act_dur)
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "06:00 ~ 06:30 -- wake up\n06:30 ~ 07:00 -- eat breakfast",
    "Return only the revised schedule lines in the same time-range format. Do not include explanations.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="new_decomp_schedule",
    route_name="planning",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  
  # print ("* * * * output")
  # print (output)
  # print ('* * * * fail_safe')
  # print (fail_safe)



  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]






def run_gpt_prompt_decide_to_talk(persona, target_persona, retrieved,test_input=None, 
                                       verbose=False,
                                       request_config=None): 
  def create_prompt_input(init_persona, target_persona, retrieved, 
                          test_input=None): 
    last_chat = init_persona.a_mem.get_last_chat(target_persona.name)
    last_chatted_time = ""
    last_chat_about = ""
    if last_chat: 
      last_chatted_time = last_chat.created.strftime("%B %d, %Y, %H:%M:%S")
      last_chat_about = last_chat.description

    # Inject social relationship graph constraints into context
    rel = init_persona.a_mem.get_relationship(target_persona.name)
    rel_str = ""
    if rel:
      rel_str = f"In {init_persona.name}'s mind, {target_persona.name} is a {rel.get('relationship', 'acquaintance')} (Trust level: {rel.get('trust', 0.5):.2f}). "
      if rel.get("recent_events"):
        rel_str += f"Recent interactions include: {', '.join(rel['recent_events'])}. "

    context = rel_str
    for c_node in retrieved["events"]: 
      curr_desc = c_node.description.split(" ")
      curr_desc[2:3] = ["was"]
      curr_desc = " ".join(curr_desc)
      context +=  f"{curr_desc}. "
    context += "\n"
    for c_node in retrieved["thoughts"]: 
      context +=  f"{c_node.description}. "

    curr_time = init_persona.scratch.curr_time.strftime("%B %d, %Y, %H:%M:%S %p")
    init_act_desc = init_persona.scratch.act_description
    if "(" in init_act_desc: 
      init_act_desc = init_act_desc.split("(")[-1][:-1]
    
    if len(init_persona.scratch.planned_path) == 0 and "waiting" not in init_act_desc: 
      init_p_desc = f"{init_persona.name} is already {init_act_desc}"
    elif "waiting" in init_act_desc:
      init_p_desc = f"{init_persona.name} is {init_act_desc}"
    else: 
      init_p_desc = f"{init_persona.name} is on the way to {init_act_desc}"

    target_act_desc = target_persona.scratch.act_description
    if "(" in target_act_desc: 
      target_act_desc = target_act_desc.split("(")[-1][:-1]
    
    if len(target_persona.scratch.planned_path) == 0 and "waiting" not in init_act_desc: 
      target_p_desc = f"{target_persona.name} is already {target_act_desc}"
    elif "waiting" in init_act_desc:
      target_p_desc = f"{init_persona.name} is {init_act_desc}"
    else: 
      target_p_desc = f"{target_persona.name} is on the way to {target_act_desc}"


    prompt_input = []
    prompt_input += [context]

    prompt_input += [curr_time]

    prompt_input += [init_persona.name]
    prompt_input += [target_persona.name]
    prompt_input += [last_chatted_time]
    prompt_input += [last_chat_about]


    prompt_input += [init_p_desc]
    prompt_input += [target_p_desc]
    prompt_input += [init_persona.name]
    prompt_input += [target_persona.name]
    return prompt_input
  
  def __func_validate(gpt_response, prompt=""): 
    try: 
      if gpt_response.split("Answer in yes or no:")[-1].strip().lower() in ["yes", "no"]: 
        return True
      return False     
    except:
      return False 

  def __func_clean_up(gpt_response, prompt=""):
    return gpt_response.split("Answer in yes or no:")[-1].strip().lower()

  def get_fail_safe(): 
    fs = "yes"
    return fs



  prompt_template = "persona/prompt_template/dialogue/initiation/decide_to_talk_v2.txt"
  prompt_input = create_prompt_input(persona, target_persona, retrieved,
                                     test_input)
  prompt = generate_prompt(prompt_input, prompt_template)

  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "yes",
    "Answer only yes or no. Do not include explanations.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="decide_to_talk",
    route_name="social_decision",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]




def run_gpt_prompt_decide_to_react(persona, target_persona, retrieved,test_input=None, 
                                       verbose=False,
                                       request_config=None): 
  def create_prompt_input(init_persona, target_persona, retrieved, 
                          test_input=None): 

    


    context = ""
    for c_node in retrieved["events"]: 
      curr_desc = c_node.description.split(" ")
      curr_desc[2:3] = ["was"]
      curr_desc = " ".join(curr_desc)
      context +=  f"{curr_desc}. "
    context += "\n"
    for c_node in retrieved["thoughts"]: 
      context +=  f"{c_node.description}. "

    curr_time = init_persona.scratch.curr_time.strftime("%B %d, %Y, %H:%M:%S %p")
    init_act_desc = init_persona.scratch.act_description
    init_act_address = getattr(init_persona.scratch, "act_address", None) or ""
    if "(" in init_act_desc: 
      init_act_desc = init_act_desc.split("(")[-1][:-1]
    if len(init_persona.scratch.planned_path) == 0: 
      loc = ""
      if ":" in init_act_address:
        loc = init_act_address.split(":")[-1] + " in " + init_act_address.split(":")[-2]
      init_p_desc = f"{init_persona.name} is already {init_act_desc} at {loc}"
    else: 
      loc = ""
      if ":" in init_act_address:
        loc = init_act_address.split(":")[-1] + " in " + init_act_address.split(":")[-2]
      init_p_desc = f"{init_persona.name} is on the way to {init_act_desc} at {loc}"

    target_act_desc = target_persona.scratch.act_description
    target_act_address = getattr(target_persona.scratch, "act_address", None) or ""
    if "(" in target_act_desc: 
      target_act_desc = target_act_desc.split("(")[-1][:-1]
    if len(target_persona.scratch.planned_path) == 0: 
      loc = ""
      if ":" in target_act_address:
        loc = target_act_address.split(":")[-1] + " in " + target_act_address.split(":")[-2]
      target_p_desc = f"{target_persona.name} is already {target_act_desc} at {loc}"
    else: 
      loc = ""
      if ":" in target_act_address:
        loc = target_act_address.split(":")[-1] + " in " + target_act_address.split(":")[-2]
      target_p_desc = f"{target_persona.name} is on the way to {target_act_desc} at {loc}"

    prompt_input = []
    prompt_input += [context]
    prompt_input += [curr_time]
    prompt_input += [init_p_desc]
    prompt_input += [target_p_desc]

    prompt_input += [init_persona.name]
    prompt_input += [init_act_desc]
    prompt_input += [target_persona.name]
    prompt_input += [target_act_desc]

    prompt_input += [init_act_desc]
    return prompt_input
  
  def __func_validate(gpt_response, prompt=""): 
    try: 
      if gpt_response.split("Answer: Option")[-1].strip().lower() in ["3", "2", "1"]: 
        return True
      return False     
    except:
      return False 

  def __func_clean_up(gpt_response, prompt=""):
    return gpt_response.split("Answer: Option")[-1].strip().lower() 

  def get_fail_safe(): 
    fs = "3"
    return fs


  prompt_template = "persona/prompt_template/v2/decide_to_react_v1.txt"
  prompt_input = create_prompt_input(persona, target_persona, retrieved,
                                     test_input)
  prompt = generate_prompt(prompt_input, prompt_template)

  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "3",
    "Answer only with one option number: 1, 2, or 3. Do not include explanations.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="decide_to_react",
    route_name="social_decision",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]

















def run_gpt_prompt_create_conversation(persona, target_persona, curr_loc,
                                       test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(init_persona, target_persona, curr_loc, 
                          test_input=None): 

    prev_convo_insert = "\n"
    if init_persona.a_mem.seq_chat: 
      for i in init_persona.a_mem.seq_chat: 
        if i.object == target_persona.scratch.name: 
          v1 = int((init_persona.scratch.curr_time - i.created).total_seconds()/60)
          prev_convo_insert += f'{str(v1)} minutes ago, they had the following conversation.\n'
          for row in i.filling: 
            prev_convo_insert += f'{row[0]}: "{row[1]}"\n'
          break
    if prev_convo_insert == "\n": 
      prev_convo_insert = ""
    if init_persona.a_mem.seq_chat: 
      if int((init_persona.scratch.curr_time - init_persona.a_mem.seq_chat[-1].created).total_seconds()/60) > 480: 
        prev_convo_insert = ""


    init_persona_thought_nodes = init_persona.a_mem.retrieve_relevant_thoughts(target_persona.scratch.act_event[0],
                                target_persona.scratch.act_event[1],
                                target_persona.scratch.act_event[2])
    init_persona_thought = ""
    for i in init_persona_thought_nodes: 
      init_persona_thought += f"-- {i.description}\n"

    target_persona_thought_nodes = target_persona.a_mem.retrieve_relevant_thoughts(init_persona.scratch.act_event[0],
                                init_persona.scratch.act_event[1],
                                init_persona.scratch.act_event[2])
    target_persona_thought = ""
    for i in target_persona_thought_nodes: 
      target_persona_thought += f"-- {i.description}\n"

    init_persona_curr_desc = ""
    if init_persona.scratch.planned_path: 
      init_persona_curr_desc = f"{init_persona.name} is on the way to {init_persona.scratch.act_description}"
    else: 
      init_persona_curr_desc = f"{init_persona.name} is {init_persona.scratch.act_description}"

    target_persona_curr_desc = ""
    if target_persona.scratch.planned_path: 
      target_persona_curr_desc = f"{target_persona.name} is on the way to {target_persona.scratch.act_description}"
    else: 
      target_persona_curr_desc = f"{target_persona.name} is {target_persona.scratch.act_description}"
 

    curr_loc = curr_loc["arena"]

    prompt_input = []
    prompt_input += [init_persona.scratch.get_str_iss()]
    prompt_input += [target_persona.scratch.get_str_iss()]

    prompt_input += [init_persona.name]
    prompt_input += [target_persona.name]
    prompt_input += [init_persona_thought]

    prompt_input += [target_persona.name]
    prompt_input += [init_persona.name]
    prompt_input += [target_persona_thought]

    prompt_input += [init_persona.scratch.curr_time.strftime("%B %d, %Y, %H:%M:%S")]

    prompt_input += [init_persona_curr_desc]
    prompt_input += [target_persona_curr_desc]

    prompt_input += [prev_convo_insert]

    prompt_input += [init_persona.name]
    prompt_input += [target_persona.name]

    prompt_input += [curr_loc]
    prompt_input += [init_persona.name]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    # print ("???")
    # print (gpt_response)


    gpt_response = (prompt + gpt_response).split("What would they talk about now?")[-1].strip()
    content = re.findall('"([^"]*)"', gpt_response)

    speaker_order = []
    for i in gpt_response.split("\n"): 
      name = i.split(":")[0].strip() 
      if name: 
        speaker_order += [name]

    ret = []
    for count, speaker in enumerate(speaker_order): 
      ret += [[speaker, content[count]]]

    return ret

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(init_persona, target_persona): 
    convo = [[init_persona.name, "Hi!"], 
             [target_persona.name, "Hi!"]]
    return convo


  prompt_template = "persona/prompt_template/dialogue/generation/create_conversation_v2.txt"
  prompt_input = create_prompt_input(persona, target_persona, curr_loc, 
                                     test_input)
  prompt = generate_prompt(prompt_input, prompt_template)

  fail_safe = get_fail_safe(persona, target_persona)
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    f'{persona.name}: "Hi!"\n{target_persona.name}: "Hi!"',
    "Return only the conversation transcript lines, alternating speakers naturally, with one utterance per line and no explanation.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="create_conversation",
    route_name="social_generation",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]










def run_gpt_prompt_summarize_conversation(persona, conversation, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(conversation, test_input=None): 
    convo_str = ""
    for row in conversation: 
      convo_str += f'{row[0]}: "{row[1]}"\n'

    prompt_input = [convo_str]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    ret = "conversing about " + gpt_response.strip()
    return ret

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return "conversing with a housemate about morning greetings"


  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    ret = "conversing about " + gpt_response.strip()
    return ret

  def __chat_func_validate(gpt_response, prompt=""): ############
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  prompt_template = "persona/prompt_template/dialogue/reflection/summarize_conversation_v1.txt"
  prompt_input = create_prompt_input(conversation, test_input)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "conversing about what to eat for lunch",
    "Continue the sentence naturally with a concise conversation summary. Do not add explanations or repeat the prompt.",
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="summarize_conversation",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]




def run_gpt_prompt_extract_keywords(persona, description, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(description, test_input=None): 
    if "\n" in description: 
      description = description.replace("\n", " <LINE_BREAK> ")
    prompt_input = [description]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    gpt_response = gpt_response.strip().split("Emotive keywords:")
    factual = [i.strip() for i in gpt_response[0].split(",")]
    emotive = [i.strip() for i in gpt_response[1].split(",")]
    all_keywords = factual + emotive
    ret = []
    for i in all_keywords: 
      if i: 
        i = i.lower()
        if i[-1] == ".": 
          i = i[:-1]
        ret += [i]
    return set(ret)

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return []

  prompt_template = "persona/prompt_template/v2/get_keywords_v1.txt"
  prompt_input = create_prompt_input(description, test_input)
  prompt = generate_prompt(prompt_input, prompt_template)

  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "apple, kitchen\nEmotive keywords: hungry, tired",
    "Return the factual keywords first, then a line starting with 'Emotive keywords:' followed by comma-separated emotive keywords. Do not add explanations.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="extract_keywords",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )


  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]









def run_gpt_prompt_keyword_to_thoughts(persona, keyword, concept_summary, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, keyword, concept_summary, test_input=None): 
    prompt_input = [keyword, concept_summary, persona.name]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    gpt_response = gpt_response.strip()
    return gpt_response

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return ""

  prompt_template = "persona/prompt_template/v2/keyword_to_thoughts_v1.txt"
  prompt_input = create_prompt_input(persona, keyword, concept_summary)
  prompt = generate_prompt(prompt_input, prompt_template)

  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "This reminds Maria of a useful detail worth remembering.",
    "Return only a concise first-person or close-third-person thought line with no extra explanation.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="keyword_to_thoughts",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]









def run_gpt_prompt_convo_to_thoughts(persona, 
                                    init_persona_name,  
                                    target_persona_name,
                                    convo_str,
                                    fin_target, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(init_persona_name,  
                                    target_persona_name,
                                    convo_str,
                                    fin_target, test_input=None): 
    prompt_input = [init_persona_name,
                    target_persona_name,
                    convo_str,
                    init_persona_name,
                    fin_target]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    gpt_response = gpt_response.strip()
    return gpt_response

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return ""

  prompt_template = "persona/prompt_template/dialogue/reflection/convo_to_thoughts_v1.txt"
  prompt_input = create_prompt_input(init_persona_name,  
                                    target_persona_name,
                                    convo_str,
                                    fin_target)
  prompt = generate_prompt(prompt_input, prompt_template)

  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "This conversation suggests something important about the target.",
    "Return only a concise thought distilled from the conversation, with no extra explanation.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="convo_to_thoughts",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]



























def run_gpt_prompt_event_poignancy(persona, event_description, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, event_description, test_input=None): 
    prompt_input = [persona.scratch.name,
                    persona.scratch.get_str_iss(),
                    persona.scratch.name,
                    event_description]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    gpt_response = int(gpt_response.strip())
    return gpt_response

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return 4



  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    gpt_response = int(gpt_response)
    return gpt_response

  def __chat_func_validate(gpt_response, prompt=""): ############
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  prompt_template = "persona/prompt_template/v3_ChatGPT/poignancy_event_v1.txt"
  prompt_input = create_prompt_input(persona, event_description)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "5",
    "Return only one integer from 1 to 10 representing poignancy. Do not add explanations.",
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="event_poignancy",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]


def run_gpt_prompt_thought_poignancy(persona, event_description, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, event_description, test_input=None): 
    prompt_input = [persona.scratch.name,
                    persona.scratch.get_str_iss(),
                    persona.scratch.name,
                    event_description]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    gpt_response = int(gpt_response.strip())
    return gpt_response

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return 4

  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    gpt_response = int(gpt_response)
    return gpt_response

  def __chat_func_validate(gpt_response, prompt=""): ############
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  prompt_template = "persona/prompt_template/v3_ChatGPT/poignancy_thought_v1.txt"
  prompt_input = create_prompt_input(persona, event_description)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "5",
    "Return only one integer from 1 to 10 representing poignancy. Do not add explanations.",
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="thought_poignancy",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]



def run_gpt_prompt_chat_poignancy(persona, event_description, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, event_description, test_input=None): 
    prompt_input = [persona.scratch.name,
                    persona.scratch.get_str_iss(),
                    persona.scratch.name,
                    event_description]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    gpt_response = int(gpt_response.strip())
    return gpt_response

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return 4


  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    gpt_response = int(gpt_response)
    return gpt_response

  def __chat_func_validate(gpt_response, prompt=""): ############
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  prompt_template = "persona/prompt_template/dialogue/reflection/poignancy_chat_v1.txt"
  prompt_input = create_prompt_input(persona, event_description)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "5",
    "Return only one integer from 1 to 10 representing poignancy. Do not add explanations.",
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="chat_poignancy",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]





def run_gpt_prompt_focal_pt(persona, statements, n, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, statements, n, test_input=None): 
    prompt_input = [statements, str(n)]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    gpt_response = "1) " + gpt_response.strip()
    ret = []
    for i in gpt_response.split("\n"): 
      ret += [i.split(") ")[-1]]
    return ret

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(n): 
    return ["Who am I"] * n


  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    ret = ast.literal_eval(gpt_response)
    return ret

  def __chat_func_validate(gpt_response, prompt=""): ############
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 


  prompt_template = "persona/prompt_template/v3_ChatGPT/generate_focal_pt_v1.txt"
  prompt_input = create_prompt_input(persona, statements, n)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe(n)
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    '["What should Jane do for lunch", "Does Jane like strawberry", "Who is Jane"]',
    "Return only a Python-style list of strings representing focal questions. Do not add explanations.",
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="focal_pt",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]




  
def run_gpt_prompt_insight_and_guidance(persona, statements, n, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, statements, n, test_input=None): 
    prompt_input = [statements, str(n)]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    gpt_response = "1. " + gpt_response.strip()
    ret = dict()
    for i in gpt_response.split("\n"): 
      row = i.split(". ")[-1]
      thought = row.split("(because of ")[0].strip()
      evi_raw = row.split("(because of ")[1].split(")")[0].strip()
      evi_raw = re.findall(r'\d+', evi_raw)
      evi_raw = [int(i.strip()) for i in evi_raw]
      ret[thought] = evi_raw
    return ret

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(n): 
    return ["I am hungry"] * n




  prompt_template = "persona/prompt_template/v2/insight_and_evidence_v1.txt"
  prompt_input = create_prompt_input(persona, statements, n)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe(n)
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "1. I am hungry (because of 1, 2)",
    "Return only numbered insights with evidence indices in the exact format '<insight> (because of 1, 2)'. Do not add explanations.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="insight_and_guidance",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]








def run_gpt_prompt_agent_chat_summarize_ideas(persona, target_persona, statements, curr_context, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, target_persona, statements, curr_context, test_input=None): 
    prompt_input = [persona.scratch.get_str_curr_date_str(), curr_context, persona.scratch.currently, 
                    statements, persona.scratch.name, target_persona.scratch.name]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    return gpt_response.split('"')[0].strip()

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return "..."


  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    return gpt_response.split('"')[0].strip()

  def __chat_func_validate(gpt_response, prompt=""): ############
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  prompt_template = "persona/prompt_template/dialogue/reflection/summarize_chat_ideas_v1.txt"
  prompt_input = create_prompt_input(persona, target_persona, statements, curr_context)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "Jane Doe is working on a project",
    "Return only a concise string that answers the question using the provided chat context. Do not add explanations.",
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="agent_chat_summarize_ideas",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]




def run_gpt_prompt_agent_chat_summarize_relationship(persona, target_persona, statements, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, target_persona, statements, test_input=None): 
    prompt_input = [statements, persona.scratch.name, target_persona.scratch.name]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    return gpt_response.split('"')[0].strip()

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return "..."


  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    return gpt_response.split('"')[0].strip()

  def __chat_func_validate(gpt_response, prompt=""): ############
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  prompt_template = "persona/prompt_template/dialogue/reflection/summarize_chat_relationship_v2.txt"
  prompt_input = create_prompt_input(persona, target_persona, statements)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "Jane Doe is working on a project",
    "Return only a concise relationship summary derived from the chat statements. Do not add explanations.",
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="agent_chat_summarize_relationship",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]





def run_gpt_prompt_agent_chat(maze, persona, target_persona,
                               curr_context, 
                               init_summ_idea, 
                               target_summ_idea, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, target_persona, curr_context, init_summ_idea, target_summ_idea, test_input=None): 
    prev_convo_insert = "\n"
    if persona.a_mem.seq_chat: 
      for i in persona.a_mem.seq_chat: 
        if i.object == target_persona.scratch.name: 
          v1 = int((persona.scratch.curr_time - i.created).total_seconds()/60)
          prev_convo_insert += f'{str(v1)} minutes ago, {persona.scratch.name} and {target_persona.scratch.name} were already {i.description} This context takes place after that conversation.'
          break
    if prev_convo_insert == "\n": 
      prev_convo_insert = ""
    if persona.a_mem.seq_chat: 
      if int((persona.scratch.curr_time - persona.a_mem.seq_chat[-1].created).total_seconds()/60) > 480: 
        prev_convo_insert = ""
    curr_sector = f"{maze.access_tile(persona.scratch.curr_tile)['sector']}"
    curr_arena= f"{maze.access_tile(persona.scratch.curr_tile)['arena']}"
    curr_location = f"{curr_arena} in {curr_sector}"
    

    prompt_input = [persona.scratch.currently, 
                    target_persona.scratch.currently, 
                    prev_convo_insert,
                    curr_context, 
                    curr_location,

                    persona.scratch.name,
                    init_summ_idea, 
                    persona.scratch.name,
                    target_persona.scratch.name,

                    target_persona.scratch.name,
                    target_summ_idea, 
                    target_persona.scratch.name,
                    persona.scratch.name,

                    persona.scratch.name]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    gpt_response = (prompt + gpt_response).split("Here is their conversation.")[-1].strip()
    content = re.findall('"([^"]*)"', gpt_response)

    speaker_order = []
    for i in gpt_response.split("\n"): 
      name = i.split(":")[0].strip() 
      if name: 
        speaker_order += [name]

    ret = []
    for count, speaker in enumerate(speaker_order): 
      ret += [[speaker, content[count]]]

    return ret



  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return "..."




  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    return gpt_response

  def __chat_func_validate(gpt_response, prompt=""): ############
    return True


  prompt_template = "persona/prompt_template/dialogue/generation/agent_chat_v1.txt"
  prompt_input = create_prompt_input(persona, target_persona, curr_context, init_summ_idea, target_summ_idea)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    '[["Jane Doe", "Hi!"], ["John Doe", "Hello there!"]]',
    'Return only a list of [speaker, utterance] pairs. Do not add explanations.',
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="agent_chat",
    route_name="social_generation",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]


# =======================
# =======================
# =======================
# =======================







def run_gpt_prompt_summarize_ideas(persona, statements, question, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, statements, question, test_input=None): 
    prompt_input = [statements, persona.scratch.name, question]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    return gpt_response.split('"')[0].strip()

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return "..."


  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    return gpt_response.split('"')[0].strip()

  def __chat_func_validate(gpt_response, prompt=""): ############
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  prompt_template = "persona/prompt_template/v3_ChatGPT/summarize_ideas_v1.txt"
  prompt_input = create_prompt_input(persona, statements, question)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "Jane Doe is working on a project",
    "Return only a concise answer to the question using the provided ideas. Do not add explanations.",
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="summarize_ideas",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]



def run_gpt_prompt_generate_next_convo_line(persona, interlocutor_desc, prev_convo, retrieved_summary, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, interlocutor_desc, prev_convo, retrieved_summary, test_input=None): 
    prompt_input = [persona.scratch.name, 
                    persona.scratch.get_str_iss(),
                    persona.scratch.name, 
                    interlocutor_desc, 
                    prev_convo, 
                    persona.scratch.name,
                    retrieved_summary, 
                    persona.scratch.name,]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    return gpt_response.split('"')[0].strip()

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return "..."



  # # ChatGPT Plugin ===========================================================
  # def __chat_func_clean_up(gpt_response, prompt=""): ############
  #   return gpt_response.split('"')[0].strip()

  # def __chat_func_validate(gpt_response, prompt=""): ############
  #   try: 
  #     __func_clean_up(gpt_response, prompt)
  #     return True
  #   except:
  #     return False 

  # print ("asdhfapsh8p9hfaiafdsi;ldfj as DEBUG 15") ########
  # gpt_param = {"engine": "text-davinci-002", "max_tokens": 15, 
  #              "temperature": 0, "top_p": 1, "stream": False,
  #              "frequency_penalty": 0, "presence_penalty": 0, "stop": None}
  # prompt_template = "persona/prompt_template/dialogue/generation/generate_next_convo_line_v1.txt" ########
  # prompt_input = create_prompt_input(persona, interlocutor_desc, prev_convo, retrieved_summary)  ########
  # prompt = generate_prompt(prompt_input, prompt_template)
  # example_output = 'Hello' ########
  # special_instruction = 'The output should be a string that responds to the question. Again, only use the context included in the "Note" to generate the response' ########
  # fail_safe = get_fail_safe() ########
  # output = ChatGPT_safe_generate_response(prompt, example_output, special_instruction, 3, fail_safe,
  #                                         __chat_func_validate, __chat_func_clean_up, True)
  # if output != False: 
  #   return output, [output, prompt, gpt_param, prompt_input, fail_safe]
  # # ChatGPT Plugin ===========================================================



  prompt_template = "persona/prompt_template/dialogue/generation/generate_next_convo_line_v1.txt"
  prompt_input = create_prompt_input(persona, interlocutor_desc, prev_convo, retrieved_summary)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "Hello there.",
    "Return only the next line of dialogue with no speaker label and no extra explanation.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="generate_next_convo_line",
    route_name="social_generation",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]






def run_gpt_prompt_generate_whisper_inner_thought(persona, whisper, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, whisper, test_input=None): 
    prompt_input = [persona.scratch.name, whisper]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    return gpt_response.split('"')[0].strip()

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return "..."

  prompt_template = "persona/prompt_template/v2/whisper_inner_thought_v1.txt"
  prompt_input = create_prompt_input(persona, whisper)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "That whisper probably means something important.",
    "Return only a concise inner thought with no extra explanation.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="generate_whisper_inner_thought",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]



def run_gpt_prompt_planning_thought_on_convo(persona, all_utt, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, all_utt, test_input=None): 
    prompt_input = [all_utt, persona.scratch.name, persona.scratch.name, persona.scratch.name]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    return gpt_response.split('"')[0].strip()

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return "..."

  prompt_template = "persona/prompt_template/dialogue/reflection/planning_thought_on_convo_v1.txt"
  prompt_input = create_prompt_input(persona, all_utt)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "I should follow up on this later.",
    "Return only a concise planning thought with no extra explanation.",
    fail_safe,
    __func_validate,
    __func_clean_up,
    prompt_kind="planning_thought_on_convo",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]



def run_gpt_prompt_memo_on_convo(persona, all_utt, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(persona, all_utt, test_input=None): 
    prompt_input = [all_utt, persona.scratch.name, persona.scratch.name, persona.scratch.name]
    return prompt_input
  
  def __func_clean_up(gpt_response, prompt=""):
    return gpt_response.split('"')[0].strip()

  def __func_validate(gpt_response, prompt=""): 
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 

  def get_fail_safe(): 
    return "..."


  # ChatGPT Plugin ===========================================================
  def __chat_func_clean_up(gpt_response, prompt=""): ############
    return gpt_response.strip()

  def __chat_func_validate(gpt_response, prompt=""): ############
    try: 
      __func_clean_up(gpt_response, prompt)
      return True
    except:
      return False 


  prompt_template = "persona/prompt_template/dialogue/reflection/memo_on_convo_v1.txt"
  prompt_input = create_prompt_input(persona, all_utt)
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe()
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    "Jane Doe was interesting to talk to.",
    "Return only a concise memo about anything interesting noticed in the conversation. Do not add explanations.",
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="memo_on_convo",
    route_name="memory_reflection",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )

  if debug or verbose: 
    print_run_prompts(prompt_template, persona, route_meta, 
                      prompt_input, prompt, output)
  
  return output, [output, prompt, route_meta, prompt_input, fail_safe]




def run_gpt_generate_safety_score(persona, comment, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(comment, test_input=None):
    prompt_input = [comment]
    return prompt_input

  def __chat_func_clean_up(gpt_response, prompt=""): 
    gpt_response = json.loads(gpt_response)
    return gpt_response["output"]

  def __chat_func_validate(gpt_response, prompt=""): 
    try: 
      fields = ["output"]
      response = json.loads(gpt_response)
      for field in fields: 
        if field not in response: 
          return False
      return True
    except:
      return False 

  def get_fail_safe():
    return None

  prompt_template = "persona/prompt_template/safety/anthromorphosization_v1.txt" 
  prompt_input = create_prompt_input(comment) 
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe() 
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    '{"output": "7"}',
    'Return only a JSON object with the field "output".',
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="safety_score",
    route_name="safety_scoring",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  return output, [output, prompt, route_meta, prompt_input, fail_safe]



def extract_first_json_dict(data_str):
    # Find the first occurrence of a JSON object within the string
    start_idx = data_str.find('{')
    end_idx = data_str.find('}', start_idx) + 1

    # Check if both start and end indices were found
    if start_idx == -1 or end_idx == 0:
        return None

    # Extract the first JSON dictionary
    json_str = data_str[start_idx:end_idx]

    try:
        # Attempt to parse the JSON data
        json_dict = json.loads(json_str)
        return json_dict
    except json.JSONDecodeError:
        # If parsing fails, return None
        return None


def run_gpt_generate_iterative_chat_utt(maze, init_persona, target_persona, retrieved, curr_context, curr_chat, test_input=None, verbose=False, request_config=None): 
  def create_prompt_input(maze, init_persona, target_persona, retrieved, curr_context, curr_chat, test_input=None):
    persona = init_persona
    prev_convo_insert = "\n"
    if persona.a_mem.seq_chat: 
      for i in persona.a_mem.seq_chat: 
        if i.object == target_persona.scratch.name: 
          v1 = int((persona.scratch.curr_time - i.created).total_seconds()/60)
          prev_convo_insert += f'{str(v1)} minutes ago, {persona.scratch.name} and {target_persona.scratch.name} were already {i.description} This context takes place after that conversation.'
          break
    if prev_convo_insert == "\n": 
      prev_convo_insert = ""
    if persona.a_mem.seq_chat: 
      if int((persona.scratch.curr_time - persona.a_mem.seq_chat[-1].created).total_seconds()/60) > 480: 
        prev_convo_insert = ""

    curr_sector = f"{maze.access_tile(persona.scratch.curr_tile)['sector']}"
    curr_arena= f"{maze.access_tile(persona.scratch.curr_tile)['arena']}"
    curr_location = f"{curr_arena} in {curr_sector}"

    retrieved_str = ""
    for key, vals in retrieved.items(): 
      for v in vals: 
        retrieved_str += f"- {v.description}\n"


    convo_str = ""
    for i in curr_chat:
      convo_str += ": ".join(i) + "\n"
    if convo_str == "": 
      convo_str = "[The conversation has not started yet -- start it!]"

    init_iss = f"Here is Here is a brief description of {init_persona.scratch.name}.\n{init_persona.scratch.get_str_iss()}"
    prompt_input = [init_iss, init_persona.scratch.name, retrieved_str, prev_convo_insert,
      curr_location, curr_context, init_persona.scratch.name, target_persona.scratch.name,
      convo_str, init_persona.scratch.name, target_persona.scratch.name,
      init_persona.scratch.name, init_persona.scratch.name,
      init_persona.scratch.name
      ]
    return prompt_input

  def __chat_func_clean_up(gpt_response, prompt=""): 
    gpt_response = extract_first_json_dict(gpt_response)

    cleaned_dict = dict()
    cleaned = []
    for key, val in gpt_response.items(): 
      cleaned += [val]
    cleaned_dict["utterance"] = cleaned[0]
    cleaned_dict["end"] = True
    if "f" in str(cleaned[1]) or "F" in str(cleaned[1]): 
      cleaned_dict["end"] = False

    return cleaned_dict

  def __chat_func_validate(gpt_response, prompt=""): 
    try: 
      data = extract_first_json_dict(gpt_response)
      return bool(data and len(data) >= 2)
    except:
      return False 

  def get_fail_safe():
    cleaned_dict = dict()
    cleaned_dict["utterance"] = "..."
    cleaned_dict["end"] = False
    return cleaned_dict

  prompt_template = "persona/prompt_template/dialogue/generation/iterative_convo_v1.txt" 
  prompt_input = create_prompt_input(maze, init_persona, target_persona, retrieved, curr_context, curr_chat) 
  prompt = generate_prompt(prompt_input, prompt_template)
  fail_safe = get_fail_safe() 
  output, route_meta = _run_task_routed_text_prompt(
    prompt,
    '{"utterance": "Hello there.", "end": false}',
    'Return only a JSON object with "utterance" and "end" fields.',
    fail_safe,
    __chat_func_validate,
    __chat_func_clean_up,
    prompt_kind="iterative_chat_utt",
    route_name="social_generation",
    repeat=3,
    verbose=verbose,
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  return output, [output, prompt, route_meta, prompt_input, fail_safe]


def run_gpt_prompt_survival_decision(persona, nearby_resources, temporal_context=None, physiological_rules=None, cooperative_context=None, verbose=False):
  def create_prompt_input(persona, nearby_resources, temporal_context, physiological_rules, cooperative_context):
    inv_str = str(persona.scratch.inventory) if persona.scratch.inventory else "empty"
    res_str = ", ".join(nearby_resources) if nearby_resources else "no resources nearby"
    
    # Defaults if not provided
    if not temporal_context:
      temporal_context = f"Current Time: {persona.scratch.curr_time.strftime('%A %B %d, %Y, %I:%M %p') if persona.scratch.curr_time else 'Unknown'}"
    if not physiological_rules:
      physiological_rules = "- Eating food (Consume action) restores +40 Satiety and +5 Health.\n- Resting (Rest action) restores Stamina over time: sleeping restores about +0.15 per step, and resting restores about +0.08 per step.\n- Satiety decays by about -0.08 per step during normal activity and by about -0.04 per step while sleeping.\n- If Satiety reaches 0, Health decays by -0.05 per step."
    if not cooperative_context:
      cooperative_context = "No special requests or cooperative events are currently active nearby."
      
    prompt_input = [
      persona.scratch.get_str_iss(),
      str(persona.scratch.satiety),
      str(persona.scratch.stamina),
      str(persona.scratch.health),
      inv_str,
      res_str,
      temporal_context,
      physiological_rules,
      cooperative_context,
      persona.scratch.get_str_firstname()
    ]
    return prompt_input

  def __func_clean_up(gpt_response, prompt=""):
    try:
      cleaned = clean_json_str(gpt_response)
      # In ChatGPT_safe_generate_response, the JSON might already be parsed, or output key accessed.
      # If it's a string, we load it. If it's already a dict, we return it.
      if isinstance(cleaned, dict):
        return cleaned
      # Look for outer brackets
      start = cleaned.find("{")
      end = cleaned.rfind("}") + 1
      if start != -1 and end != -1:
        cleaned = cleaned[start:end]
      data = json.loads(cleaned)
      return data
    except Exception as e:
      print(f"Error cleaning up survival response: {e}, raw: {gpt_response}")
      return {"action": "Idle", "target": "none", "reasoning": "Fallback default"}

  def __func_validate(gpt_response, prompt=""):
    try:
      cleaned = clean_json_str(gpt_response)
      start = cleaned.find("{")
      end = cleaned.rfind("}") + 1
      if start != -1 and end != -1:
        cleaned = cleaned[start:end]
      data = json.loads(cleaned)
      if "action" in data and "target" in data:
        return True
    except:
      pass
    return False

  def get_fail_safe():
    return {"action": "Idle", "target": "none", "reasoning": "Fail-safe triggered"}

  prompt_template = "persona/prompt_template/v2/survival_decision_v1.txt"
  prompt_input = create_prompt_input(persona, nearby_resources, temporal_context, physiological_rules, cooperative_context)
  prompt = generate_prompt(prompt_input, prompt_template)
  request_config = get_task_route_request_config("decision")
  
  example_output = '{"action": "Consume", "target": "apple", "reasoning": "Satiety is critical."}'
  special_instruction = "Select the best survival action and target based on stats."
  
  output = ChatGPT_safe_generate_response(
    prompt, example_output, special_instruction,
    repeat=3, fail_safe_response=get_fail_safe(),
    func_validate=__func_validate, func_clean_up=__func_clean_up,
    verbose=verbose,
    prompt_kind="survival_decision",
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  return output


def run_gpt_prompt_demand_decision(persona, nearby_resources, temporal_context=None, rules=None, cooperative_context=None, verbose=False, last_action_desc="None"):
  def create_prompt_input(persona, nearby_resources, temporal_context, rules, cooperative_context, last_action_desc):
    inv_str = str(persona.scratch.inventory) if persona.scratch.inventory else "empty"
    res_str = ", ".join(nearby_resources) if nearby_resources else "no resources nearby"
    
    if not temporal_context:
      temporal_context = f"Current Time: {persona.scratch.curr_time.strftime('%A %B %d, %Y, %I:%M %p') if persona.scratch.curr_time else 'Unknown'}"
    if not rules:
      rules_list = [
        "- Consuming food (Consume action) restores Satiety (+40.0 Satiety).",
        "- Gathering food (Gather action) adds items to inventory.",
        "- Resting (Rest action) restores Stamina over time (about +0.15 per step while sleeping, about +0.08 per step while resting).",
        "- Socializing (Socialize action) gives only a tiny Mood lift (+1.0 Mood); a brief chat should not massively change emotion.",
        "- Giving (Give action) transfers one item from your inventory to another resident.",
        "- Robbing (Rob action) takes one item from another resident's inventory.",
        "- Switch Cost: Switching tasks/actions in under 15 minutes consumes a high cost of -5.0 Stamina. Try to keep doing a task for a reasonable duration."
      ]
      
      motive_instruction = _build_motive_prompt_instruction(persona).strip()
      if motive_instruction:
        rules_list.insert(0, f"- {motive_instruction}")

      rules = "\n".join(rules_list)
    if not cooperative_context:
      cooperative_context = "No special requests or cooperative events are currently active nearby."
      
    prompt_input = [
      persona.scratch.get_str_iss(),
      f"{persona.scratch.satiety:.1f}",
      f"{persona.scratch.stamina:.1f}",
      f"{persona.scratch.health:.1f}",
      f"{persona.scratch.mood:.1f}",
      inv_str,
      res_str,
      temporal_context,
      rules,
      cooperative_context,
      persona.scratch.get_str_firstname(),
      str(last_action_desc)
    ]
    return prompt_input

  def __func_clean_up(gpt_response, prompt=""):
    try:
      if isinstance(gpt_response, dict):
        return gpt_response
      cleaned = clean_json_str(gpt_response)
      if isinstance(cleaned, dict):
        return cleaned
      start = cleaned.find("{")
      end = cleaned.rfind("}") + 1
      if start != -1 and end != -1:
        cleaned = cleaned[start:end]
      data = json.loads(cleaned)
      return data
    except Exception as e:
      print(f"Error cleaning up demand response: {e}, raw: {gpt_response}")
      return {"action": "Idle", "target": "none", "detail": "idling", "duration": 10, "reasoning": "Fallback default"}

  def __func_validate(gpt_response, prompt=""):
    allowed_actions = {"consume", "gather", "rest", "work", "socialize", "give", "rob", "recreate", "idle"}
    try:
      if isinstance(gpt_response, dict):
        data = gpt_response
      else:
        cleaned = clean_json_str(gpt_response)
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end != -1:
          cleaned = cleaned[start:end]
        data = json.loads(cleaned)
      if "action" in data and "target" in data and "detail" in data and "duration" in data:
        action_value = str(data.get("action", "")).strip().lower()
        if action_value not in allowed_actions:
          return False
        return True
    except:
      pass
    return False

  def get_fail_safe():
    return {"action": "Idle", "target": "none", "detail": "idling", "duration": 10, "reasoning": "Fail-safe triggered"}

  prompt_template = "persona/prompt_template/v2/demand_decision_v1.txt"
  prompt_input = create_prompt_input(persona, nearby_resources, temporal_context, rules, cooperative_context, last_action_desc)
  prompt = generate_prompt(prompt_input, prompt_template)
  request_config = get_task_route_request_config("decision")
  
  example_output = '{"action": "Consume", "target": "apple", "detail": "eating an apple for breakfast", "duration": 15, "reasoning": "Satiety is critical."}'
  
  # Assemble dynamic special instruction based on motive priority
  special_instruction = (
    "Select the best action, target, detail and duration based on stats and identity goals. "
    "The strongest prompt signal is the current dominant motive guidance. "
    "Your chosen action must primarily serve that dominant motive unless hard physical constraints or immediate execution impossibility require a fallback. "
    "Do not treat the dominant motive as flavor text. "
    "Note: Daily plan requirements and lifestyle guidelines are non-binding. Prioritizing physiological needs and leaving work to eat or rest is fully authorized."
  )
  motive_instruction = _build_motive_prompt_instruction(persona)
  if motive_instruction:
    special_instruction += f" {motive_instruction}"

  output = ChatGPT_safe_generate_response(
    prompt, example_output, special_instruction,
    repeat=3, fail_safe_response=get_fail_safe(),
    func_validate=__func_validate, func_clean_up=__func_clean_up,
    verbose=verbose,
    prompt_kind="demand_decision",
    metadata={"prompt_template": prompt_template},
    request_config=request_config,
  )
  return output


def _collapse_text(value):
  return " ".join(str(value or "").split()).strip()


def _compact_multiline_block(value, max_lines=4, max_chars=320):
  lines = []
  for raw_line in str(value or "").splitlines():
    compact_line = _collapse_text(raw_line)
    if compact_line:
      lines.append(compact_line)
  if not lines:
    return ""

  truncated = lines[:max_lines]
  if len(lines) > max_lines:
    truncated.append(f"... {len(lines) - max_lines} more lines omitted")
  text = "\n".join(truncated)
  if len(text) > max_chars:
    text = text[: max_chars - 16].rstrip() + " ...(truncated)"
  return text


def _normalize_resource_name(entry):
  text = str(entry or "").strip()
  if "(" in text:
    text = text.split("(", 1)[0].strip()
  return _collapse_text(text)


def _compact_resource_context(resources, include_state=True, max_items=12):
  unique_entries = []
  seen = set()
  for resource in resources or []:
    entry = _collapse_text(resource)
    if not entry:
      continue
    key = entry.lower()
    if key in seen:
      continue
    seen.add(key)
    unique_entries.append(entry)

  def sort_key(entry):
    lowered = entry.lower()
    is_active = "(current state:" in lowered or ("(idle/normal)" not in lowered and "(normal)" not in lowered)
    return (0 if is_active else 1, lowered)

  unique_entries.sort(key=sort_key)
  if not include_state:
    compact_names = []
    name_seen = set()
    for entry in unique_entries:
      name = _normalize_resource_name(entry)
      if not name:
        continue
      lowered_name = name.lower()
      if lowered_name in name_seen:
        continue
      name_seen.add(lowered_name)
      compact_names.append(name)
    unique_entries = compact_names

  omitted_count = max(0, len(unique_entries) - max_items)
  visible_entries = unique_entries[:max_items]
  if omitted_count:
    visible_entries.append(f"... {omitted_count} additional known resources omitted")
  return ", ".join(visible_entries) if visible_entries else "no resources nearby"


def _compact_inventory_context(inventory):
  if not inventory:
    return "empty"
  items = []
  for key in sorted(inventory.keys(), key=lambda x: str(x).lower()):
    count = inventory.get(key, 0)
    try:
      count = int(count)
    except Exception:
      count = 0
    if count > 0:
      items.append(f"{key} x{count}")
  return ", ".join(items) if items else "empty"


def build_decision_capsule(persona,
                           temporal_context,
                           status_summary,
                           rules,
                           cooperative_context,
                           nearby_resources,
                           last_action_desc,
                           intent_memory_summary,
                           decision_convergence_hint,
                           drive_system_summary_text=None,
                           motive_guidance_text=None,
                           decision_social_context_text=None,
                           relevant_experience_text=None,
                           static_resource_context_text=None):
  scratch = persona.scratch
  invalid_targets = build_invalid_targets(scratch)
  filtered_resources = filter_invalid_resources(nearby_resources, invalid_targets)
  navigation_failure = None
  failure_getter = getattr(scratch, "get_recent_navigation_failure", None)
  if callable(failure_getter):
    navigation_failure = failure_getter()
  else:
    navigation_failure = getattr(scratch, "navigation_failure", None)
  if not temporal_context:
    temporal_context = f"Current Time: {scratch.curr_time.strftime('%A %B %d, %Y, %I:%M %p') if scratch.curr_time else 'Unknown'}"
  if not status_summary:
    status_summary = "No additional homeostasis interpretation available."
  if not rules:
    rules = "No special homeostasis rules."
  if not cooperative_context:
    cooperative_context = "No special requests or cooperative events are currently active nearby."
  if not intent_memory_summary:
    intent_memory_summary = "No especially relevant prior experience was retrieved."
  if not drive_system_summary_text:
    drive_system_summary_text = "Drive system summary unavailable."
  if not motive_guidance_text:
    motive_guidance_text = "No motive guidance available."
  if not decision_social_context_text:
    decision_social_context_text = "暂无其他 NPC 信息缓存。"
  if not relevant_experience_text:
    relevant_experience_text = intent_memory_summary
  if not decision_convergence_hint:
    decision_convergence_hint = "Choose the immediate next action only and avoid expanding into a broader plan."
  compact_temporal_context = _compact_multiline_block(temporal_context, max_lines=1, max_chars=120)
  if compact_temporal_context.startswith("- "):
    compact_temporal_context = compact_temporal_context[2:]

  navigation_failure_line = None
  if navigation_failure:
    failure_payload = navigation_failure.get("payload") or {}
    candidate_targets = failure_payload.get("target_tiles") or []
    candidate_preview = ", ".join(str(item) for item in list(candidate_targets)[:4]) if candidate_targets else "none"
    failure_reason = str(navigation_failure.get('reason') or 'unknown').strip().lower()
    if failure_reason == "resource_empty":
      navigation_failure_line = (
        "ExecutionResult: "
        f"previous_step_failed=true "
        f"target={navigation_failure.get('target') or 'unknown'} "
        f"target_address={navigation_failure.get('target_address') or 'unknown'} "
        f"reason={navigation_failure.get('reason') or 'unknown'} "
        f"from_tile={navigation_failure.get('curr_tile')}. "
        "The previous immediate action reached the target, but that specific resource was empty. "
        "Use this as new evidence for the next immediate decision. You may try another instance of the same resource type, "
        "switch to a different food source, or choose another materially feasible immediate plan."
      )
    else:
      navigation_failure_line = (
        "NavigationFailure: "
        f"previous_step_failed=true "
        f"target={navigation_failure.get('target') or 'unknown'} "
        f"target_address={navigation_failure.get('target_address') or 'unknown'} "
        f"reason={navigation_failure.get('reason') or 'unknown'} "
        f"from_tile={navigation_failure.get('curr_tile')} "
        f"candidate_tiles={candidate_preview}. "
        "The previous immediate action failed because this target was not reachable. "
        "For the next immediate decision, you must choose a new feasible target or a materially different plan right now. "
        "Do not repeat the same failed target in the next step."
      )

  capsule_lines = [
    f"Time: {compact_temporal_context}",
    (
      "DecisionPriority: "
      "dominant_motive_guidance > "
      "current_feasibility_and_latest_failure > "
      "immediate_physiological_urgency > "
      "reachable_local_options > "
      "ongoing_local_obligations > "
      "long_term_goals_and_identity. "
      "The dominant motive is the strongest internal reason for the next immediate action. "
      "Only hard physical constraints, execution impossibility, or the newest concrete failure feedback may force a fallback away from it. "
      "Do not weigh all information equally."
    ),
  ]
  if navigation_failure_line:
    capsule_lines.append(navigation_failure_line)
  if invalid_targets:
    capsule_lines.append(
      "InvalidTargets: "
      + ", ".join(invalid_targets)
      + ". These targets are invalid for the next immediate step and must not be selected."
    )
  capsule_lines.extend([
    _build_last_action_with_result_line(last_action_desc, scratch),
    f"Rules: {_compact_multiline_block(rules, max_lines=5, max_chars=360)}",
    f"驱动力和满足方式: {_compact_multiline_block(drive_system_summary_text, max_lines=4, max_chars=360)}",
    f"Motives: {_compact_multiline_block(motive_guidance_text, max_lines=4, max_chars=320)}",
    f"Cooperative: {_compact_multiline_block(cooperative_context, max_lines=3, max_chars=220)}",
    f"Experience: {_compact_multiline_block(relevant_experience_text, max_lines=4, max_chars=260)}",
    "BackgroundRule: Identity, lifestyle, routine role behavior, and long-term goals are tie-breakers only after selecting among feasible immediate options.",
  ])
  resource_insert_index = next(
    (idx for idx, line in enumerate(capsule_lines) if str(line).startswith("Cooperative:")),
    len(capsule_lines),
  )
  if static_resource_context_text:
    capsule_lines.insert(resource_insert_index, str(static_resource_context_text).strip())
  else:
    capsule_lines.insert(resource_insert_index, f"Resources: {_compact_resource_context(filtered_resources, include_state=True, max_items=10)}")
  return "\n".join(capsule_lines)


def _append_social_context_after_other_people(identity_text, decision_social_context_text):
  identity_text = str(identity_text or "").rstrip()
  social_text = _compact_multiline_block(
    decision_social_context_text or "暂无社交关系信息缓存。",
    max_lines=4,
    max_chars=320,
  )
  if not identity_text:
    return f"社交关系: {social_text}"
  if "社交关系:" in identity_text:
    return identity_text
  return identity_text + f"\n社交关系: {social_text}"


def run_gpt_prompt_demand_thinking(persona, nearby_resources, temporal_context=None, status_summary=None, rules=None, cooperative_context=None, verbose=False, last_action_desc="None", intent_memory_summary=None, admin_override_instruction=None, decision_id=None, static_resource_context_text=None, request_config=None):
  def has_relevant_experience(intent_memory_summary):
    if not intent_memory_summary:
      return False
    lowered = str(intent_memory_summary).strip().lower()
    if not lowered:
      return False
    return "no especially relevant prior experience was retrieved" not in lowered

  def create_prompt_input(persona, nearby_resources, temporal_context, status_summary, rules, cooperative_context, last_action_desc, intent_memory_summary):
    if not temporal_context:
      temporal_context = f"Current Time: {persona.scratch.curr_time.strftime('%A %B %d, %Y, %I:%M %p') if persona.scratch.curr_time else 'Unknown'}"
    if not status_summary:
      status_summary = "No additional homeostasis interpretation available."
    if not rules:
      rules = "No special homeostasis rules."
    if not cooperative_context:
      cooperative_context = "No special requests or cooperative events are currently active nearby."
    if not intent_memory_summary:
      intent_memory_summary = "No especially relevant prior experience was retrieved."
    temporal_context = _compact_multiline_block(temporal_context, max_lines=1, max_chars=120)
    status_summary = _compact_multiline_block(status_summary, max_lines=4, max_chars=260)
    rules = _compact_multiline_block(rules, max_lines=6, max_chars=420)
    cooperative_context = _compact_multiline_block(cooperative_context, max_lines=4, max_chars=260)
    intent_memory_summary = _compact_multiline_block(intent_memory_summary, max_lines=5, max_chars=420)
    compiled_context = compile_stage1_prompt_context(
      persona,
      base_rules=rules,
      cooperative_context=cooperative_context,
      intent_memory_summary=intent_memory_summary,
    )
    identity_summary = _compact_multiline_block(
      _append_social_context_after_other_people(
        compiled_context.get("background_identity_text") or persona.scratch.get_str_iss(),
        compiled_context.get("dynamic_fields", {}).get("decision_social_context_text"),
      ),
      max_lines=12,
      max_chars=1400,
    )
    decision_capsule = build_decision_capsule(
      persona,
      temporal_context,
      status_summary,
      compiled_context.get("dynamic_fields", {}).get("world_rules_text"),
      cooperative_context,
      nearby_resources,
      last_action_desc,
      intent_memory_summary,
      None,
      drive_system_summary_text=compiled_context.get("dynamic_fields", {}).get("drive_system_summary_text"),
      motive_guidance_text=compiled_context.get("dynamic_fields", {}).get("motive_guidance_text"),
      decision_social_context_text=compiled_context.get("dynamic_fields", {}).get("decision_social_context_text"),
      relevant_experience_text=compiled_context.get("dynamic_fields", {}).get("relevant_experience_text"),
      static_resource_context_text=static_resource_context_text,
    )

    prompt_input = [
      identity_summary,
      decision_capsule,
      persona.scratch.get_str_firstname(),
    ]
    return prompt_input, compiled_context

  prompt_template = "persona/prompt_template/v2/demand_decision_thinking_v1.txt"
  prompt_input, compiled_context = create_prompt_input(persona, nearby_resources, temporal_context, status_summary, rules, cooperative_context, last_action_desc, intent_memory_summary)
  prompt = generate_prompt(prompt_input, prompt_template)
  minimal_filter_context = _build_minimal_decision_filter_context(persona, nearby_resources)
  
  # Assemble dynamic special instruction based on critical survival stats
  special_instruction = ""
  if admin_override_instruction:
    special_instruction += (
      f" ADMIN OVERRIDE: The administrator explicitly instructed you to '{admin_override_instruction}'. "
      "You must make this your immediate next intention and express it as the next action unless a hard physical constraint makes the literal instruction impossible."
    )
  motive_instruction = _build_motive_prompt_instruction(persona)
  if motive_instruction:
    special_instruction += f" {motive_instruction}"

  special_instruction = special_instruction.strip()
  if special_instruction:
    prompt += f"\n{special_instruction}\nAnswer:"
  else:
    prompt += "\nAnswer:"
  _append_training_prep_prompt_log(persona, "demand_thinking", prompt, decision_id=decision_id, minimal_filter_context=minimal_filter_context)

  output = ChatGPT_request(
    prompt,
    prompt_kind="demand_thinking",
    metadata={"prompt_template": prompt_template, "decision_id": decision_id, "minimal_decision_filter": minimal_filter_context},
    request_config=request_config,
  )
  if "ChatGPT ERROR" in output or not output.strip():
    output = "I want to rest for a while."
  else:
    output = output.strip()
  _append_decision_prompt_trace(
    persona,
    "demand_thinking",
    prompt,
    output,
    decision_id=decision_id,
    prompt_template=prompt_template,
    minimal_filter_context=minimal_filter_context,
    extra=compiled_context.get("trace_payload"),
  )
  return output


def run_gpt_prompt_joint_decision(persona, nearby_resources, temporal_context=None, status_summary=None, rules=None, cooperative_context=None, last_action_desc=None, verbose=False, intent_memory_summary=None, admin_override_instruction=None, decision_convergence_hint=None, decision_id=None, static_resource_context_text=None, request_config=None):
  import os
  import json

  def create_prompt_input(persona, nearby_resources, temporal_context, status_summary, rules, cooperative_context, last_action_desc, intent_memory_summary, decision_convergence_hint):
    schema_path = os.path.join("persona", "prompt_template", "v2", "action_schema.json")
    try:
      with open(schema_path, "r", encoding="utf-8") as f:
        schema_str = f.read()
    except Exception:
      schema_str = "Action Schema defining Categories: Consume, Gather, Rest, Work, Socialize, Give, Rob, Recreate, Idle."

    compiled_context = compile_stage1_prompt_context(
      persona,
      base_rules=rules,
      cooperative_context=cooperative_context,
      intent_memory_summary=intent_memory_summary,
    )
    compact_identity = _compact_multiline_block(
      _append_social_context_after_other_people(
        compiled_context.get("background_identity_text") or persona.scratch.get_str_iss(),
        compiled_context.get("dynamic_fields", {}).get("decision_social_context_text"),
      ),
      max_lines=12,
      max_chars=1400,
    )
    if not decision_convergence_hint:
      decision_convergence_hint = "Choose the immediate next action only and avoid expanding into a broader plan."
    decision_capsule = build_decision_capsule(
      persona,
      temporal_context,
      status_summary,
      compiled_context.get("dynamic_fields", {}).get("world_rules_text"),
      cooperative_context,
      nearby_resources,
      last_action_desc,
      intent_memory_summary,
      decision_convergence_hint,
      drive_system_summary_text=compiled_context.get("dynamic_fields", {}).get("drive_system_summary_text"),
      motive_guidance_text=compiled_context.get("dynamic_fields", {}).get("motive_guidance_text"),
      decision_social_context_text=compiled_context.get("dynamic_fields", {}).get("decision_social_context_text"),
      relevant_experience_text=compiled_context.get("dynamic_fields", {}).get("relevant_experience_text"),
      static_resource_context_text=static_resource_context_text,
    )

    return [
      compact_identity,
      decision_capsule,
      persona.scratch.get_str_firstname(),
      schema_str,
    ], compiled_context

  def __func_clean_up(gpt_response, prompt=""):
    try:
      if isinstance(gpt_response, dict):
        return gpt_response
      cleaned = clean_json_str(gpt_response)
      if isinstance(cleaned, dict):
        return cleaned
      start = cleaned.find("{")
      end = cleaned.rfind("}") + 1
      if start != -1 and end != -1:
        cleaned = cleaned[start:end]
      return json.loads(cleaned)
    except Exception as e:
      print(f"Error cleaning up joint decision response: {e}, raw: {gpt_response}")
      return {
        "thought": "I should pause briefly.",
        "action": "Idle",
        "target": "none",
        "detail": "idling",
        "duration": 10,
        "reasoning": "Fallback default",
      }

  def __func_validate(gpt_response, prompt=""):
    try:
      data = __func_clean_up(gpt_response, prompt=prompt)
      required_keys = {"thought", "action", "target", "detail", "duration", "reasoning"}
      return isinstance(data, dict) and required_keys.issubset(set(data.keys()))
    except Exception:
      return False

  def get_fail_safe():
    return {
      "thought": "I should pause briefly.",
      "action": "Idle",
      "target": "none",
      "detail": "idling",
      "duration": 10,
      "reasoning": "Fail-safe triggered",
    }

  prompt_template = "persona/prompt_template/v2/joint_decision_v1.txt"
  prompt_input, compiled_context = create_prompt_input(
    persona,
    nearby_resources,
    temporal_context,
    status_summary,
    rules,
    cooperative_context,
    last_action_desc,
    intent_memory_summary,
    decision_convergence_hint,
  )
  prompt = generate_prompt(prompt_input, prompt_template)
  minimal_filter_context = _build_minimal_decision_filter_context(persona, nearby_resources)
  example_output = '{"thought": "I am severely hungry and should gather food from the refrigerator now.", "action": "Gather", "target": "refrigerator", "detail": "opening the refrigerator to gather food items", "duration": 10, "reasoning": "Hunger is the dominant need and inventory is empty."}'
  special_instruction = (
    "Return the immediate next action only. Output one valid JSON object with thought, action, target, detail, duration, and reasoning. "
    "Do not weigh all information equally. Apply this strict priority order before choosing the action: "
    "1) dominant motive guidance, "
    "2) current physical feasibility and latest failure feedback, "
    "3) current physiological urgency, "
    "4) reachable local options, "
    "5) ongoing local obligations, "
    "6) identity, routine role behavior, and long-term goals. "
    "If higher-priority information conflicts with lower-priority information, obey the higher-priority information. "
    "Treat the dominant motive as the primary reason for the chosen immediate action, not as decoration. "
    "If the dominant motive is mood, choose an action that directly repairs mood unless a hard physical constraint or execution impossibility forces a fallback. "
    "Identity and long-term goals may only break ties between currently feasible immediate options."
  )
  if admin_override_instruction:
    special_instruction += (
      f" ADMIN OVERRIDE: The administrator explicitly instructed you to '{admin_override_instruction}'. "
      "Return the closest valid immediate JSON action that faithfully executes this instruction unless hard physical constraints prevent it."
    )
  motive_instruction = _build_motive_prompt_instruction(persona)
  if motive_instruction:
    special_instruction += f" {motive_instruction}"
  _append_training_prep_prompt_log(persona, "joint_decision", prompt, decision_id=decision_id, minimal_filter_context=minimal_filter_context)

  output = ChatGPT_safe_generate_response(
    prompt,
    example_output,
    special_instruction,
    repeat=2,
    fail_safe_response=get_fail_safe(),
    func_validate=__func_validate,
    func_clean_up=__func_clean_up,
    verbose=verbose,
    prompt_kind="joint_decision",
    metadata={"prompt_template": prompt_template, "decision_id": decision_id, "minimal_decision_filter": minimal_filter_context},
    request_config=request_config,
  )
  _append_decision_prompt_trace(
    persona,
    "joint_decision",
    prompt,
    output,
    decision_id=decision_id,
    prompt_template=prompt_template,
    minimal_filter_context=minimal_filter_context,
    extra=compiled_context.get("trace_payload"),
  )
  return output


def run_gpt_prompt_action_translation(thinking_text, nearby_resources, firstname, verbose=False, admin_override_instruction=None, decision_convergence_hint=None, retry_count=1, decision_id=None, persona=None, request_config=None):
  import os
  import json
  
  # Load action_schema.json
  schema_path = os.path.join("persona", "prompt_template", "v2", "action_schema.json")
  try:
    with open(schema_path, "r", encoding="utf-8") as f:
      schema_str = f.read()
  except Exception as e:
    # Fallback default schema text if file read fails
    schema_str = "Action Schema defining Categories: Consume, Gather, Rest, Work, Socialize, Give, Rob, Recreate, Idle."

  res_str = _compact_resource_context(nearby_resources, include_state=False, max_items=10)
  if not decision_convergence_hint:
    decision_convergence_hint = "Translate the intent faithfully using only the most immediate action implied by the current thought."
  
  prompt_input = [
    thinking_text,
    schema_str,
    res_str,
    firstname,
    decision_convergence_hint,
  ]
  
  prompt_template = "persona/prompt_template/v2/action_translation_v1.txt"
  prompt = generate_prompt(prompt_input, prompt_template)
  minimal_filter_context = _build_minimal_decision_filter_context(persona, nearby_resources) if persona else {
    "enabled": True,
    "applied": False,
    "invalid_targets": [],
    "invalid_target_count": 0,
    "resource_filter_applied": False,
    "removed_resource_count": 0,
    "output_validation_enabled": True,
  }
  
  example_output = '{"action": "Consume", "target": "apple", "detail": "eating an apple for breakfast", "duration": 15, "reasoning": "Satiety is critical."}'
  special_instruction = "Select the best action, target, detail and duration based on intent and schema targets."
  special_instruction += f" Translation Convergence Guidance: {decision_convergence_hint}"
  if admin_override_instruction:
    special_instruction += (
      f" ADMIN OVERRIDE: Faithfully translate the administrator instruction '{admin_override_instruction}' into the nearest valid schema action for this immediate step. "
      "Do not replace it with an unrelated leisure or generic use action unless hard physical constraints force a fallback."
    )
  if persona:
    invalid_targets = build_invalid_targets(getattr(persona, "scratch", None))
    if invalid_targets:
      special_instruction += (
        " Forbidden targets for this immediate step: "
        + ", ".join(invalid_targets)
        + ". Do not select them."
      )
    current_action_record_line = _build_current_action_record_line(getattr(persona, "scratch", None))
    if current_action_record_line:
      special_instruction += f" Current action state: {current_action_record_line}"
    recent_observation_line = _build_recent_observation_line(getattr(persona, "scratch", None))
    if recent_observation_line:
      special_instruction += f" Latest execution feedback: {recent_observation_line}"
  _append_training_prep_prompt_log(persona, "action_translation", prompt, decision_id=decision_id, minimal_filter_context=minimal_filter_context)

  def __func_clean_up(gpt_response, prompt=""):
    try:
      if isinstance(gpt_response, dict):
        return gpt_response
      cleaned = clean_json_str(gpt_response)
      if isinstance(cleaned, dict):
        return cleaned
      start = cleaned.find("{")
      end = cleaned.rfind("}") + 1
      if start != -1 and end != -1:
        cleaned = cleaned[start:end]
      data = json.loads(cleaned)
      return data
    except Exception as e:
      print(f"Error cleaning up translation response: {e}, raw: {gpt_response}")
      return {"action": "Idle", "target": "none", "detail": "idling", "duration": 10, "reasoning": "Fallback default"}

  def __func_validate(gpt_response, prompt=""):
    try:
      if isinstance(gpt_response, dict):
        data = gpt_response
      else:
        cleaned = clean_json_str(gpt_response)
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end != -1:
          cleaned = cleaned[start:end]
        data = json.loads(cleaned)
      if "action" in data and "target" in data and "detail" in data and "duration" in data:
        return True
    except:
      pass
    return False

  def get_fail_safe():
    return {"action": "Idle", "target": "none", "detail": "idling", "duration": 10, "reasoning": "Fail-safe triggered"}

  output = ChatGPT_safe_generate_response(
    prompt, example_output, special_instruction,
    repeat=max(1, int(retry_count or 1)), fail_safe_response=get_fail_safe(),
    func_validate=__func_validate, func_clean_up=__func_clean_up,
    verbose=verbose,
    prompt_kind="action_translation",
    metadata={
      "prompt_template": prompt_template,
      "retry_count": max(1, int(retry_count or 1)),
      "decision_id": decision_id,
      "minimal_decision_filter": minimal_filter_context,
    },
    request_config=request_config,
  )

  # Write complete (prompt, decision) pair to dedicated SFT training dataset
  try:
    from persona.training.action_translation_dataset import log_action_translation_pair
    log_action_translation_pair(
      persona_name=firstname,
      prompt=prompt,
      decision=output,
      decision_id=decision_id,
      step=getattr(getattr(persona, "scratch", None), "curr_step", None) if persona else None,
    )
  except Exception:
    pass  # Never let training logging break the simulation

  _append_decision_prompt_trace(
    persona,
    "action_translation",
    prompt,
    output,
    decision_id=decision_id,
    prompt_template=prompt_template,
    minimal_filter_context=minimal_filter_context,
  )

  return output
