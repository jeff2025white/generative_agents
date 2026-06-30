"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: plan.py
Description: This defines the "Plan" module for generative agents. 
"""
import datetime
import math
import random 
import sys
import time
sys.path.append('../../')

from global_methods import *
from persona.prompt_template.run_gpt_prompt import *
from persona.cognitive_modules.retrieve import *
from persona.cognitive_modules.converse import *

##############################################################################
# CHAPTER 2: Generate
##############################################################################

def generate_wake_up_hour(persona):
  """
  Generates the time when the persona wakes up. This becomes an integral part
  of our process for generating the persona's daily plan.
  
  Persona state: identity stable set, lifestyle, first_name

  INPUT: 
    persona: The Persona class instance 
  OUTPUT: 
    an integer signifying the persona's wake up hour
  EXAMPLE OUTPUT: 
    8
  """
  if debug: print ("GNS FUNCTION: <generate_wake_up_hour>")
  return int(run_gpt_prompt_wake_up_hour(persona)[0])


def generate_first_daily_plan(persona, wake_up_hour): 
  """
  Generates the daily plan for the persona. 
  Basically the long term planning that spans a day. Returns a list of actions
  that the persona will take today. Usually comes in the following form: 
  'wake up and complete the morning routine at 6:00 am', 
  'eat breakfast at 7:00 am',.. 
  Note that the actions come without a period. 

  Persona state: identity stable set, lifestyle, cur_data_str, first_name

  INPUT: 
    persona: The Persona class instance 
    wake_up_hour: an integer that indicates when the hour the persona wakes up 
                  (e.g., 8)
  OUTPUT: 
    a list of daily actions in broad strokes.
  EXAMPLE OUTPUT: 
    ['wake up and complete the morning routine at 6:00 am', 
     'have breakfast and brush teeth at 6:30 am',
     'work on painting project from 8:00 am to 12:00 pm', 
     'have lunch at 12:00 pm', 
     'take a break and watch TV from 2:00 pm to 4:00 pm', 
     'work on painting project from 4:00 pm to 6:00 pm', 
     'have dinner at 6:00 pm', 'watch TV from 7:00 pm to 8:00 pm']
  """
  if debug: print ("GNS FUNCTION: <generate_first_daily_plan>")
  return run_gpt_prompt_daily_plan(persona, wake_up_hour)[0]


def generate_hourly_schedule(persona, wake_up_hour): 
  """
  Based on the daily req, creates an hourly schedule -- one hour at a time. 
  The form of the action for each of the hour is something like below: 
  "sleeping in her bed"
  
  The output is basically meant to finish the phrase, "x is..."

  Persona state: identity stable set, daily_plan

  INPUT: 
    persona: The Persona class instance 
    persona: Integer form of the wake up hour for the persona.  
  OUTPUT: 
    a list of activities and their duration in minutes: 
  EXAMPLE OUTPUT: 
    [['sleeping', 360], ['waking up and starting her morning routine', 60], 
     ['eating breakfast', 60],..
  """
  if debug: print ("GNS FUNCTION: <generate_hourly_schedule>")

  hour_str = ["00:00 AM", "01:00 AM", "02:00 AM", "03:00 AM", "04:00 AM", 
              "05:00 AM", "06:00 AM", "07:00 AM", "08:00 AM", "09:00 AM", 
              "10:00 AM", "11:00 AM", "12:00 PM", "01:00 PM", "02:00 PM", 
              "03:00 PM", "04:00 PM", "05:00 PM", "06:00 PM", "07:00 PM",
              "08:00 PM", "09:00 PM", "10:00 PM", "11:00 PM"]
  n_m1_activity = []
  diversity_repeat_count = 3
  for i in range(diversity_repeat_count): 
    n_m1_activity_set = set(n_m1_activity)
    if len(n_m1_activity_set) < 5: 
      n_m1_activity = []
      for count, curr_hour_str in enumerate(hour_str): 
        if wake_up_hour > 0: 
          n_m1_activity += ["sleeping"]
          wake_up_hour -= 1
        else: 
          n_m1_activity += [run_gpt_prompt_generate_hourly_schedule(
                          persona, curr_hour_str, n_m1_activity, hour_str)[0]]
  
  # Step 1. Compressing the hourly schedule to the following format: 
  # The integer indicates the number of hours. They should add up to 24. 
  # [['sleeping', 6], ['waking up and starting her morning routine', 1], 
  # ['eating breakfast', 1], ['getting ready for the day', 1], 
  # ['working on her painting', 2], ['taking a break', 1], 
  # ['having lunch', 1], ['working on her painting', 3], 
  # ['taking a break', 2], ['working on her painting', 2], 
  # ['relaxing and watching TV', 1], ['going to bed', 1], ['sleeping', 2]]
  _n_m1_hourly_compressed = []
  prev = None 
  prev_count = 0
  for i in n_m1_activity: 
    if i != prev:
      prev_count = 1 
      _n_m1_hourly_compressed += [[i, prev_count]]
      prev = i
    else: 
      if _n_m1_hourly_compressed: 
        _n_m1_hourly_compressed[-1][1] += 1

  # Step 2. Expand to min scale (from hour scale)
  # [['sleeping', 360], ['waking up and starting her morning routine', 60], 
  # ['eating breakfast', 60],..
  n_m1_hourly_compressed = []
  for task, duration in _n_m1_hourly_compressed: 
    n_m1_hourly_compressed += [[task, duration*60]]

  return n_m1_hourly_compressed


def generate_task_decomp(persona, task, duration): 
  """
  A few shot decomposition of a task given the task description 

  Persona state: identity stable set, curr_date_str, first_name

  INPUT: 
    persona: The Persona class instance 
    task: the description of the task at hand in str form
          (e.g., "waking up and starting her morning routine")
    duration: an integer that indicates the number of minutes this task is 
              meant to last (e.g., 60)
  OUTPUT: 
    a list of list where the inner list contains the decomposed task 
    description and the number of minutes the task is supposed to last. 
  EXAMPLE OUTPUT: 
    [['going to the bathroom', 5], ['getting dressed', 5], 
     ['eating breakfast', 15], ['checking her email', 5], 
     ['getting her supplies ready for the day', 15], 
     ['starting to work on her painting', 15]] 

  """
  if debug: print ("GNS FUNCTION: <generate_task_decomp>")
  return run_gpt_prompt_task_decomp(persona, task, duration)[0]


def generate_action_sector(act_desp, persona, maze): 
  """TODO 
  Given the persona and the task description, choose the action_sector. 

  Persona state: identity stable set, n-1 day schedule, daily plan

  INPUT: 
    act_desp: description of the new action (e.g., "sleeping")
    persona: The Persona class instance 
  OUTPUT: 
    action_arena (e.g., "bedroom 2")
  EXAMPLE OUTPUT: 
    "bedroom 2"
  """
  if debug: print ("GNS FUNCTION: <generate_action_sector>")
  return run_gpt_prompt_action_sector(act_desp, persona, maze)[0]


def generate_action_arena(act_desp, persona, maze, act_world, act_sector): 
  """TODO 
  Given the persona and the task description, choose the action_arena. 

  Persona state: identity stable set, n-1 day schedule, daily plan

  INPUT: 
    act_desp: description of the new action (e.g., "sleeping")
    persona: The Persona class instance 
  OUTPUT: 
    action_arena (e.g., "bedroom 2")
  EXAMPLE OUTPUT: 
    "bedroom 2"
  """
  if debug: print ("GNS FUNCTION: <generate_action_arena>")
  return run_gpt_prompt_action_arena(act_desp, persona, maze, act_world, act_sector)[0]


def generate_action_game_object(act_desp, act_address, persona, maze):
  """TODO
  Given the action description and the act address (the address where
  we expect the action to task place), choose one of the game objects. 

  Persona state: identity stable set, n-1 day schedule, daily plan

  INPUT: 
    act_desp: the description of the action (e.g., "sleeping")
    act_address: the arena where the action will take place: 
               (e.g., "dolores double studio:double studio:bedroom 2")
    persona: The Persona class instance 
  OUTPUT: 
    act_game_object: 
  EXAMPLE OUTPUT: 
    "bed"
  """
  if debug: print ("GNS FUNCTION: <generate_action_game_object>")
  if not persona.s_mem.get_str_accessible_arena_game_objects(act_address): 
    return "<random>"
  return run_gpt_prompt_action_game_object(act_desp, persona, maze, act_address)[0]


def generate_action_pronunciatio(act_desp, persona): 
  """TODO 
  Given an action description, creates an emoji string description via a few
  shot prompt. 

  Does not really need any information from persona. 

  INPUT: 
    act_desp: the description of the action (e.g., "sleeping")
    persona: The Persona class instance
  OUTPUT: 
    a string of emoji that translates action description.
  EXAMPLE OUTPUT: 
    "🧈🍞"
  """
  if debug: print ("GNS FUNCTION: <generate_action_pronunciatio>")
  try: 
    x = run_gpt_prompt_pronunciatio(act_desp, persona)[0]
  except: 
    x = "🙂"

  if not x: 
    return "🙂"
  return x


def generate_action_event_triple(act_desp, persona): 
  """TODO 

  INPUT: 
    act_desp: the description of the action (e.g., "sleeping")
    persona: The Persona class instance
  OUTPUT: 
    a string of emoji that translates action description.
  EXAMPLE OUTPUT: 
    "🧈🍞"
  """
  if debug: print ("GNS FUNCTION: <generate_action_event_triple>")
  return run_gpt_prompt_event_triple(act_desp, persona)[0]


def generate_act_obj_desc(act_game_object, act_desp, persona): 
  if debug: print ("GNS FUNCTION: <generate_act_obj_desc>")
  return run_gpt_prompt_act_obj_desc(act_game_object, act_desp, persona)[0]


def generate_act_obj_event_triple(act_game_object, act_obj_desc, persona): 
  if debug: print ("GNS FUNCTION: <generate_act_obj_event_triple>")
  return run_gpt_prompt_act_obj_event_triple(act_game_object, act_obj_desc, persona)[0]


def generate_convo(maze, init_persona, target_persona): 
  curr_loc = maze.access_tile(init_persona.scratch.curr_tile)

  # convo = run_gpt_prompt_create_conversation(init_persona, target_persona, curr_loc)[0]
  # convo = agent_chat_v1(maze, init_persona, target_persona)
  convo = agent_chat_v2(maze, init_persona, target_persona)
  all_utt = ""

  for row in convo: 
    speaker = row[0]
    utt = row[1]
    all_utt += f"{speaker}: {utt}\n"

  convo_length = math.ceil(int(len(all_utt)/8) / 30)

  if debug: print ("GNS FUNCTION: <generate_convo>")
  return convo, convo_length


def generate_convo_summary(persona, convo): 
  convo_summary = run_gpt_prompt_summarize_conversation(persona, convo)[0]
  return convo_summary


def generate_decide_to_talk(init_persona, target_persona, retrieved): 
  x =run_gpt_prompt_decide_to_talk(init_persona, target_persona, retrieved)[0]
  if debug: print ("GNS FUNCTION: <generate_decide_to_talk>")

  if x == "yes": 
    return True
  else: 
    return False


def generate_decide_to_react(init_persona, target_persona, retrieved): 
  if debug: print ("GNS FUNCTION: <generate_decide_to_react>")
  return run_gpt_prompt_decide_to_react(init_persona, target_persona, retrieved)[0]


def generate_new_decomp_schedule(persona, inserted_act, inserted_act_dur,  start_hour, end_hour): 
  # Step 1: Setting up the core variables for the function. 
  # <p> is the persona whose schedule we are editing right now. 
  p = persona
  # <today_min_pass> indicates the number of minutes that have passed today. 
  today_min_pass = (int(p.scratch.curr_time.hour) * 60 
                    + int(p.scratch.curr_time.minute) + 1)
  
  # Step 2: We need to create <main_act_dur> and <truncated_act_dur>. 
  # These are basically a sub-component of <f_daily_schedule> of the persona,
  # but focusing on the current decomposition. 
  # Here is an example for <main_act_dur>: 
  # ['wakes up and completes her morning routine (wakes up at 6am)', 5]
  # ['wakes up and completes her morning routine (wakes up at 6am)', 5]
  # ['wakes up and completes her morning routine (uses the restroom)', 5]
  # ['wakes up and completes her morning routine (washes her ...)', 10]
  # ['wakes up and completes her morning routine (makes her bed)', 5]
  # ['wakes up and completes her morning routine (eats breakfast)', 15]
  # ['wakes up and completes her morning routine (gets dressed)', 10]
  # ['wakes up and completes her morning routine (leaves her ...)', 5]
  # ['wakes up and completes her morning routine (starts her ...)', 5]
  # ['preparing for her day (waking up at 6am)', 5]
  # ['preparing for her day (making her bed)', 5]
  # ['preparing for her day (taking a shower)', 15]
  # ['preparing for her day (getting dressed)', 5]
  # ['preparing for her day (eating breakfast)', 10]
  # ['preparing for her day (brushing her teeth)', 5]
  # ['preparing for her day (making coffee)', 5]
  # ['preparing for her day (checking her email)', 5]
  # ['preparing for her day (starting to work on her painting)', 5]
  # 
  # And <truncated_act_dur> concerns only until where an event happens. 
  # ['wakes up and completes her morning routine (wakes up at 6am)', 5]
  # ['wakes up and completes her morning routine (wakes up at 6am)', 2]
  main_act_dur = []
  truncated_act_dur = []
  dur_sum = 0 # duration sum
  count = 0 # enumerate count
  truncated_fin = False 

  print ("DEBUG::: ", persona.scratch.name)
  for act, dur in p.scratch.f_daily_schedule: 
    if (dur_sum >= start_hour * 60) and (dur_sum < end_hour * 60): 
      main_act_dur += [[act, dur]]
      if dur_sum <= today_min_pass:
        truncated_act_dur += [[act, dur]]
      elif dur_sum > today_min_pass and not truncated_fin: 
        # We need to insert that last act, duration list like this one: 
        # e.g., ['wakes up and completes her morning routine (wakes up...)', 2]
        truncated_act_dur += [[p.scratch.f_daily_schedule[count][0], 
                               dur_sum - today_min_pass]] 
        truncated_act_dur[-1][-1] -= (dur_sum - today_min_pass) ######## DEC 7 DEBUG;.. is the +1 the right thing to do??? 
        # truncated_act_dur[-1][-1] -= (dur_sum - today_min_pass + 1) ######## DEC 7 DEBUG;.. is the +1 the right thing to do??? 
        print ("DEBUG::: ", truncated_act_dur)

        # truncated_act_dur[-1][-1] -= (dur_sum - today_min_pass) ######## DEC 7 DEBUG;.. is the +1 the right thing to do??? 
        truncated_fin = True
    dur_sum += dur
    count += 1

  persona_name = persona.name 
  main_act_dur = main_act_dur

  x = truncated_act_dur[-1][0].split("(")[0].strip() + " (on the way to " + truncated_act_dur[-1][0].split("(")[-1][:-1] + ")"
  truncated_act_dur[-1][0] = x 

  if "(" in truncated_act_dur[-1][0]: 
    inserted_act = truncated_act_dur[-1][0].split("(")[0].strip() + " (" + inserted_act + ")"

  # To do inserted_act_dur+1 below is an important decision but I'm not sure
  # if I understand the full extent of its implications. Might want to 
  # revisit. 
  truncated_act_dur += [[inserted_act, inserted_act_dur]]
  start_time_hour = (datetime.datetime(2022, 10, 31, 0, 0) 
                   + datetime.timedelta(hours=start_hour))
  end_time_hour = (datetime.datetime(2022, 10, 31, 0, 0) 
                   + datetime.timedelta(hours=end_hour))

  if debug: print ("GNS FUNCTION: <generate_new_decomp_schedule>")
  return run_gpt_prompt_new_decomp_schedule(persona, 
                                            main_act_dur, 
                                            truncated_act_dur, 
                                            start_time_hour,
                                            end_time_hour,
                                            inserted_act,
                                            inserted_act_dur)[0]


##############################################################################
# CHAPTER 3: Plan
##############################################################################

def revise_identity(persona): 
  p_name = persona.scratch.name

  focal_points = [f"{p_name}'s plan for {persona.scratch.get_str_curr_date_str()}.",
                  f"Important recent events for {p_name}'s life."]
  retrieved = new_retrieve(persona, focal_points)

  statements = "[Statements]\n"
  for key, val in retrieved.items():
    for i in val: 
      statements += f"{i.created.strftime('%A %B %d -- %H:%M %p')}: {i.embedding_key}\n"

  # print (";adjhfno;asdjao;idfjo;af", p_name)
  plan_prompt = statements + "\n"
  plan_prompt += f"Given the statements above, is there anything that {p_name} should remember as they plan for"
  plan_prompt += f" *{persona.scratch.curr_time.strftime('%A %B %d')}*? "
  plan_prompt += f"If there is any scheduling information, be as specific as possible (include date, time, and location if stated in the statement)\n\n"
  plan_prompt += f"Write the response from {p_name}'s perspective."
  plan_note = ChatGPT_single_request(plan_prompt)
  # print (plan_note)

  thought_prompt = statements + "\n"
  thought_prompt += f"Given the statements above, how might we summarize {p_name}'s feelings about their days up to now?\n\n"
  thought_prompt += f"Write the response from {p_name}'s perspective."
  thought_note = ChatGPT_single_request(thought_prompt)
  # print (thought_note)

  currently_prompt = f"{p_name}'s status from {(persona.scratch.curr_time - datetime.timedelta(days=1)).strftime('%A %B %d')}:\n"
  currently_prompt += f"{persona.scratch.currently}\n\n"
  currently_prompt += f"{p_name}'s thoughts at the end of {(persona.scratch.curr_time - datetime.timedelta(days=1)).strftime('%A %B %d')}:\n" 
  currently_prompt += (plan_note + thought_note).replace('\n', '') + "\n\n"
  currently_prompt += f"It is now {persona.scratch.curr_time.strftime('%A %B %d')}. Given the above, write {p_name}'s status for {persona.scratch.curr_time.strftime('%A %B %d')} that reflects {p_name}'s thoughts at the end of {(persona.scratch.curr_time - datetime.timedelta(days=1)).strftime('%A %B %d')}. Write this in third-person talking about {p_name}."
  currently_prompt += f"If there is any scheduling information, be as specific as possible (include date, time, and location if stated in the statement).\n\n"
  currently_prompt += "Follow this format below:\nStatus: <new status>"
  # print ("DEBUG ;adjhfno;asdjao;asdfsidfjo;af", p_name)
  # print (currently_prompt)
  new_currently = ChatGPT_single_request(currently_prompt)
  # print (new_currently)
  # print (new_currently[10:])

  persona.scratch.currently = new_currently

  daily_req_prompt = persona.scratch.get_str_iss() + "\n"
  daily_req_prompt += f"Today is {persona.scratch.curr_time.strftime('%A %B %d')}. Here is {persona.scratch.name}'s plan today in broad-strokes (with the time of the day. e.g., have a lunch at 12:00 pm, watch TV from 7 to 8 pm).\n\n"
  daily_req_prompt += f"Follow this format (the list should have 4~6 items but no more):\n"
  daily_req_prompt += f"1. wake up and complete the morning routine at <time>, 2. ..."

  new_daily_req = ChatGPT_single_request(daily_req_prompt)
  new_daily_req = new_daily_req.replace('\n', ' ')
  print ("WE ARE HERE!!!", new_daily_req)
  persona.scratch.daily_plan_req = new_daily_req


def _long_term_planning(persona, new_day): 
  """
  Formulates the persona's daily long-term plan if it is the start of a new 
  day. This basically has two components: first, we create the wake-up hour, 
  and second, we create the hourly schedule based on it. 
  INPUT
    new_day: Indicates whether the current time signals a "First day",
             "New day", or False (for neither). This is important because we
             create the personas' long term planning on the new day. 
  """
  # We start by creating the wake up hour for the persona. 
  wake_up_hour = generate_wake_up_hour(persona)

  # When it is a new day, we start by creating the daily_req of the persona.
  # Note that the daily_req is a list of strings that describe the persona's
  # day in broad strokes.
  if new_day == "First day": 
    # Bootstrapping the daily plan for the start of then generation:
    # if this is the start of generation (so there is no previous day's 
    # daily requirement, or if we are on a new day, we want to create a new
    # set of daily requirements.
    persona.scratch.daily_req = generate_first_daily_plan(persona, 
                                                          wake_up_hour)
  elif new_day == "New day":
    revise_identity(persona)
    persona.scratch.daily_req = generate_first_daily_plan(persona, wake_up_hour)

  # Hard constraints to enforce realistic daily requirements and avoid LLM plan loss
  if persona.name == "Isabella Rodriguez":
    print(f"=== [日程约束修正] Isabella Rodriguez 日程强制绑定为咖啡店值守 ===")
    persona.scratch.daily_req = [
      "wake up and complete the morning routine at 6:00 am",
      "eat breakfast at 7:00 am",
      "open Hobbs Cafe and work at the counter from 8:00 am to 12:00 pm",
      "have lunch at 12:00 pm",
      "work at the counter of Hobbs Cafe from 1:00 pm to 5:00 pm",
      "work at the counter of Hobbs Cafe from 5:00 pm to 8:00 pm",
      "relax and watch TV from 8:00 pm to 11:00 pm",
      "go to bed at 11:00 pm"
    ]
  elif persona.name == "Klaus Mueller":
    print(f"=== [日程约束修正] Klaus Mueller 日程强制绑定为前往图书馆和在咖啡厅就餐 ===")
    persona.scratch.daily_req = [
      "wake up and complete the morning routine at 7:00 am",
      "eat breakfast at 8:00 am",
      "go to the library at Oak Hill College and write his research paper from 9:00 am to 12:00 pm",
      "have lunch at Hobbs Cafe from 12:00 pm to 1:00 pm",
      "continue writing his research paper at Oak Hill College library from 1:00 pm to 5:00 pm",
      "have dinner at Hobbs Cafe from 5:00 pm to 6:00 pm",
      "relax in his dorm room from 6:00 pm to 11:00 pm",
      "go to bed at 11:00 pm"
    ]

  # Based on the daily_req, we create an hourly schedule for the persona, 
  # which is a list of todo items with a time duration (in minutes) that 
  # add up to 24 hours.
  persona.scratch.f_daily_schedule = generate_hourly_schedule(persona, 
                                                              wake_up_hour)
  persona.scratch.f_daily_schedule_hourly_org = (persona.scratch
                                                   .f_daily_schedule[:])


  # Added March 4 -- adding plan to the memory.
  thought = f"This is {persona.scratch.name}'s plan for {persona.scratch.curr_time.strftime('%A %B %d')}:"
  for i in persona.scratch.daily_req: 
    thought += f" {i},"
  thought = thought[:-1] + "."
  created = persona.scratch.curr_time
  expiration = persona.scratch.curr_time + datetime.timedelta(days=30)
  s, p, o = (persona.scratch.name, "plan", persona.scratch.curr_time.strftime('%A %B %d'))
  keywords = set(["plan"])
  thought_poignancy = 5
  thought_embedding_pair = (thought, get_embedding(thought))
  persona.a_mem.add_thought(created, expiration, s, p, o, 
                            thought, keywords, thought_poignancy, 
                            thought_embedding_pair, None)

  # print("Sleeping for 20 seconds...")
  # time.sleep(10)
  # print("Done sleeping!")



def _determine_action(persona, maze): 
  """
  Creates the next action sequence for the persona. 
  The main goal of this function is to run "add_new_action" on the persona's 
  scratch space, which sets up all the action related variables for the next 
  action. 
  As a part of this, the persona may need to decompose its hourly schedule as 
  needed.   
  INPUT
    persona: Current <Persona> instance whose action we are determining. 
    maze: Current <Maze> instance. 
  """
  def determine_decomp(act_desp, act_dura):
    """
    Given an action description and its duration, we determine whether we need
    to decompose it. If the action is about the agent sleeping, we generally
    do not want to decompose it, so that's what we catch here. 

    INPUT: 
      act_desp: the description of the action (e.g., "sleeping")
      act_dura: the duration of the action in minutes. 
    OUTPUT: 
      a boolean. True if we need to decompose, False otherwise. 
    """
    if "sleep" not in act_desp and "bed" not in act_desp: 
      return True
    elif "sleeping" in act_desp or "asleep" in act_desp or "in bed" in act_desp:
      return False
    elif "sleep" in act_desp or "bed" in act_desp: 
      if act_dura > 60: 
        return False
    return True

  # The goal of this function is to get us the action associated with 
  # <curr_index>. As a part of this, we may need to decompose some large 
  # chunk actions. 
  # Importantly, we try to decompose at least two hours worth of schedule at
  # any given point. 
  curr_index = persona.scratch.get_f_daily_schedule_index()
  curr_index_60 = persona.scratch.get_f_daily_schedule_index(advance=60)

  # * Decompose * 
  # During the first hour of the day, we need to decompose two hours 
  # sequence. We do that here. 
  if curr_index == 0:
    # This portion is invoked if it is the first hour of the day. 
    act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index]
    if act_dura >= 60: 
      # We decompose if the next action is longer than an hour, and fits the
      # criteria described in determine_decomp.
      if determine_decomp(act_desp, act_dura): 
        persona.scratch.f_daily_schedule[curr_index:curr_index+1] = (
                            generate_task_decomp(persona, act_desp, act_dura))
    if curr_index_60 + 1 < len(persona.scratch.f_daily_schedule):
      act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index_60+1]
      if act_dura >= 60: 
        if determine_decomp(act_desp, act_dura): 
          persona.scratch.f_daily_schedule[curr_index_60+1:curr_index_60+2] = (
                            generate_task_decomp(persona, act_desp, act_dura))

  if curr_index_60 < len(persona.scratch.f_daily_schedule):
    # If it is not the first hour of the day, this is always invoked (it is
    # also invoked during the first hour of the day -- to double up so we can
    # decompose two hours in one go). Of course, we need to have something to
    # decompose as well, so we check for that too. 
    if persona.scratch.curr_time.hour < 23:
      # And we don't want to decompose after 11 pm. 
      act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index_60]
      if act_dura >= 60: 
        if determine_decomp(act_desp, act_dura): 
          persona.scratch.f_daily_schedule[curr_index_60:curr_index_60+1] = (
                              generate_task_decomp(persona, act_desp, act_dura))
  # * End of Decompose * 

  # Generate an <Action> instance from the action description and duration. By
  # this point, we assume that all the relevant actions are decomposed and 
  # ready in f_daily_schedule. 
  print ("DEBUG LJSDLFSKJF")
  for i in persona.scratch.f_daily_schedule: print (i)
  print (curr_index)
  print (len(persona.scratch.f_daily_schedule))
  print (persona.scratch.name)
  print ("------")

  # 1440
  x_emergency = 0
  for i in persona.scratch.f_daily_schedule: 
    x_emergency += i[1]
  # print ("x_emergency", x_emergency)

  if 1440 - x_emergency > 0: 
    print ("x_emergency__AAA", x_emergency)
  persona.scratch.f_daily_schedule += [["sleeping", 1440 - x_emergency]]
  



  act_desp, act_dura = persona.scratch.f_daily_schedule[curr_index] 

  # Bug fix: adjust duration of the action if we started mid-action (e.g. at start of simulation)
  task_start_min = sum([d for t, d in persona.scratch.f_daily_schedule[:curr_index]])
  today_min_elapsed = persona.scratch.curr_time.hour * 60 + persona.scratch.curr_time.minute
  corrected_act_dura = (task_start_min + act_dura) - today_min_elapsed
  if corrected_act_dura > 0:
    print(f"[修正首个动作时长] 智能体: {persona.scratch.name}, 动作: {act_desp}, 原始计划时长: {act_dura}分钟, 当天已流逝时间: {today_min_elapsed}分钟, 修正后实际执行剩余时长: {corrected_act_dura}分钟")
    act_dura = corrected_act_dura



  # Finding the target location of the action and creating action-related
  # variables.
  act_world = maze.access_tile(persona.scratch.curr_tile)["world"]
  # act_sector = maze.access_tile(persona.scratch.curr_tile)["sector"]
  
  is_coffee_flow = False
  if "serving coffee" in act_desp.lower():
    is_coffee_flow = True
    act_sector = "Hobbs Cafe"
    act_arena = "cafe"
    act_game_object = "cafe customer seating"
    new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
    act_pron = "💁"
    act_event = (persona.name, "serve", "coffee to Klaus")
    act_obj_desp = "served with coffee"
    act_obj_pron = "☕"
    act_obj_event = ("cafe customer seating", "has", "served coffee")
  elif "brewing coffee" in act_desp.lower():
    is_coffee_flow = True
    act_sector = "Hobbs Cafe"
    act_arena = "cafe"
    act_game_object = "coffee maker"
    new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
    act_pron = "☕"
    act_event = (persona.name, "brew", "coffee")
    act_obj_desp = "brewing coffee"
    act_obj_pron = "♨️"
    act_obj_event = ("coffee maker", "is", "brewing coffee")
  elif "waiting for coffee" in act_desp.lower():
    is_coffee_flow = True
    act_sector = "Hobbs Cafe"
    act_arena = "cafe"
    act_game_object = "cafe customer seating"
    new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
    act_pron = "⌛"
    act_event = (persona.name, "waiting for", "coffee")
    act_obj_desp = "empty"
    act_obj_pron = "🍽️"
    act_obj_event = ("cafe customer seating", "is", "empty")
  elif "drinking coffee" in act_desp.lower():
    is_coffee_flow = True
    act_sector = "Hobbs Cafe"
    act_arena = "cafe"
    act_game_object = "cafe customer seating"
    new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
    act_pron = "☕"
    act_event = (persona.name, "drink", "coffee")
    act_obj_desp = "empty"
    act_obj_pron = "🍽️"
    act_obj_event = ("cafe customer seating", "is", "empty")

  if not is_coffee_flow:
    act_sector = generate_action_sector(act_desp, persona, maze)
    act_arena = generate_action_arena(act_desp, persona, maze, act_world, act_sector)
    act_address = f"{act_world}:{act_sector}:{act_arena}"
    act_game_object = generate_action_game_object(act_desp, act_address,
                                                  persona, maze)
    new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"
    act_pron = generate_action_pronunciatio(act_desp, persona)
    act_event = generate_action_event_triple(act_desp, persona)
    # Persona's actions also influence the object states. We set those up here. 
    act_obj_desp = generate_act_obj_desc(act_game_object, act_desp, persona)
    act_obj_pron = generate_action_pronunciatio(act_obj_desp, persona)
    act_obj_event = generate_act_obj_event_triple(act_game_object, 
                                                  act_obj_desp, persona)

  # Adding the action to persona's queue. 
  persona.scratch.add_new_action(new_address, 
                                 int(act_dura), 
                                 act_desp, 
                                 act_pron, 
                                 act_event,
                                 None,
                                 None,
                                 None,
                                 None,
                                 act_obj_desp, 
                                 act_obj_pron, 
                                 act_obj_event)


def _choose_retrieved(persona, retrieved): 
  """
  Retrieved elements have multiple core "curr_events". We need to choose one
  event to which we are going to react to. We pick that event here. 
  INPUT
    persona: Current <Persona> instance whose action we are determining. 
    retrieved: A dictionary of <ConceptNode> that were retrieved from the 
               the persona's associative memory. This dictionary takes the
               following form: 
               dictionary[event.description] = 
                 {["curr_event"] = <ConceptNode>, 
                  ["events"] = [<ConceptNode>, ...], 
                  ["thoughts"] = [<ConceptNode>, ...] }
  """
  # Once we are done with the reflection, we might want to build a more  
  # complex structure here.
  
  # We do not want to take self events... for now 
  copy_retrieved = retrieved.copy()
  for event_desc, rel_ctx in copy_retrieved.items(): 
    curr_event = rel_ctx["curr_event"]
    if curr_event.subject == persona.name: 
      del retrieved[event_desc]

  # Always choose persona first.
  priority = []
  for event_desc, rel_ctx in retrieved.items(): 
    curr_event = rel_ctx["curr_event"]
    if (":" not in curr_event.subject 
        and curr_event.subject != persona.name): 
      priority += [rel_ctx]
  if priority: 
    return random.choice(priority)

  # Skip idle. 
  for event_desc, rel_ctx in retrieved.items(): 
    curr_event = rel_ctx["curr_event"]
    if "is idle" not in event_desc: 
      priority += [rel_ctx]
  if priority: 
    return random.choice(priority)
  return None


def _should_react(persona, retrieved, personas): 
  """
  Determines what form of reaction the persona should exihibit given the 
  retrieved values. 
  INPUT
    persona: Current <Persona> instance whose action we are determining. 
    retrieved: A dictionary of <ConceptNode> that were retrieved from the 
               the persona's associative memory. This dictionary takes the
               following form: 
               dictionary[event.description] = 
                 {["curr_event"] = <ConceptNode>, 
                  ["events"] = [<ConceptNode>, ...], 
                  ["thoughts"] = [<ConceptNode>, ...] }
    personas: A dictionary that contains all persona names as keys, and the 
              <Persona> instance as values. 
  """
  def lets_talk(init_persona, target_persona, retrieved):
    if (not target_persona.scratch.act_address 
        or not target_persona.scratch.act_description
        or not init_persona.scratch.act_address
        or not init_persona.scratch.act_description): 
      return False

    if ("sleeping" in target_persona.scratch.act_description 
        or "sleeping" in init_persona.scratch.act_description): 
      return False

    if init_persona.scratch.curr_time.hour == 23: 
      return False

    if "<waiting>" in target_persona.scratch.act_address: 
      return False

    if (target_persona.scratch.chatting_with 
      or init_persona.scratch.chatting_with): 
      return False

    if (target_persona.name in init_persona.scratch.chatting_with_buffer): 
      if init_persona.scratch.chatting_with_buffer[target_persona.name] > 0: 
        return False

    if generate_decide_to_talk(init_persona, target_persona, retrieved): 

      return True

    return False

  def lets_react(init_persona, target_persona, retrieved): 
    if (not target_persona.scratch.act_address 
        or not target_persona.scratch.act_description
        or not init_persona.scratch.act_address
        or not init_persona.scratch.act_description): 
      return False

    if ("sleeping" in target_persona.scratch.act_description 
        or "sleeping" in init_persona.scratch.act_description): 
      return False

    # return False
    if init_persona.scratch.curr_time.hour == 23: 
      return False

    if "waiting" in target_persona.scratch.act_description: 
      return False
    if init_persona.scratch.planned_path == []:
      return False

    if (init_persona.scratch.act_address 
        != target_persona.scratch.act_address): 
      return False

    react_mode = generate_decide_to_react(init_persona, 
                                          target_persona, retrieved)

    if react_mode == "1": 
      wait_until = ((target_persona.scratch.act_start_time 
        + datetime.timedelta(minutes=target_persona.scratch.act_duration - 1))
        .strftime("%B %d, %Y, %H:%M:%S"))
      return f"wait: {wait_until}"
    elif react_mode == "2":
      return False
      return "do other things"
    else:
      return False #"keep" 

  # If the persona is chatting right now, default to no reaction 
  if persona.scratch.chatting_with: 
    return False
  if "<waiting>" in persona.scratch.act_address: 
    return False

  # Recall that retrieved takes the following form: 
  # dictionary {["curr_event"] = <ConceptNode>, 
  #             ["events"] = [<ConceptNode>, ...], 
  #             ["thoughts"] = [<ConceptNode>, ...]}
  curr_event = retrieved["curr_event"]

  if ":" not in curr_event.subject: 
    # this is a persona event. 
    if lets_talk(persona, personas[curr_event.subject], retrieved):
      return f"chat with {curr_event.subject}"
    react_mode = lets_react(persona, personas[curr_event.subject], 
                            retrieved)
    return react_mode
  return False


def _create_react(persona, inserted_act, inserted_act_dur,
                  act_address, act_event, chatting_with, chat, chatting_with_buffer,
                  chatting_end_time, 
                  act_pronunciatio, act_obj_description, act_obj_pronunciatio, 
                  act_obj_event, act_start_time=None): 
  p = persona 

  min_sum = 0
  for i in range (p.scratch.get_f_daily_schedule_hourly_org_index()): 
    min_sum += p.scratch.f_daily_schedule_hourly_org[i][1]
  start_hour = int (min_sum/60)

  if (p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()][1] >= 120):
    end_hour = start_hour + p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()][1]/60

  elif (p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()][1] + 
      p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()+1][1]): 
    end_hour = start_hour + ((p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()][1] + 
              p.scratch.f_daily_schedule_hourly_org[p.scratch.get_f_daily_schedule_hourly_org_index()+1][1])/60)

  else: 
    end_hour = start_hour + 2
  end_hour = int(end_hour)

  dur_sum = 0
  count = 0 
  start_index = None
  end_index = None
  for act, dur in p.scratch.f_daily_schedule: 
    if dur_sum >= start_hour * 60 and start_index == None:
      start_index = count
    if dur_sum >= end_hour * 60 and end_index == None: 
      end_index = count
    dur_sum += dur
    count += 1

  ret = generate_new_decomp_schedule(p, inserted_act, inserted_act_dur, 
                                       start_hour, end_hour)
  p.scratch.f_daily_schedule[start_index:end_index] = ret
  p.scratch.add_new_action(act_address,
                           inserted_act_dur,
                           inserted_act,
                           act_pronunciatio,
                           act_event,
                           chatting_with,
                           chat,
                           chatting_with_buffer,
                           chatting_end_time,
                           act_obj_description,
                           act_obj_pronunciatio,
                           act_obj_event,
                           act_start_time)


def inject_coffee_flow(p, role, chatting_end_time):
  # 1. Calculate the minute of the day when the chat ends
  chat_end_min = chatting_end_time.hour * 60 + chatting_end_time.minute
  
  # 2. Rebuild f_daily_schedule
  new_schedule = []
  elapsed = 0
  rest_schedule = []
  
  for task, dur in p.scratch.f_daily_schedule:
    if elapsed + dur <= chat_end_min:
      new_schedule.append([task, dur])
      elapsed += dur
    elif elapsed < chat_end_min and elapsed + dur > chat_end_min:
      past_dur = chat_end_min - elapsed
      new_schedule.append([task, past_dur])
      
      future_dur = (elapsed + dur) - chat_end_min
      rest_schedule.append([task, future_dur])
      elapsed += dur
    else:
      rest_schedule.append([task, dur])
      elapsed += dur
      
  # 3. Define the custom workflow blocks
  workflow_blocks = []
  if role == "barista":
    workflow_blocks = [
      ["brewing coffee at the coffee maker", 5],
      ["serving coffee to Klaus", 2]
    ]
  elif role == "customer":
    workflow_blocks = [
      ["waiting for coffee to be served", 7],
      ["drinking coffee", 15]
    ]
    
  workflow_duration = sum(b[1] for b in workflow_blocks)
  new_schedule.extend(workflow_blocks)
  
  # 4. Append the rest of the schedule, adjusting durations
  remaining_to_subtract = workflow_duration
  for task, dur in rest_schedule:
    if remaining_to_subtract > 0:
      if dur > remaining_to_subtract:
        new_schedule.append([task, dur - remaining_to_subtract])
        remaining_to_subtract = 0
      else:
        remaining_to_subtract -= dur
    else:
      new_schedule.append([task, dur])
      
  total_sum = sum(b[1] for b in new_schedule)
  if total_sum < 1440:
    new_schedule.append(["sleeping", 1440 - total_sum])
  elif total_sum > 1440:
    new_schedule[-1][1] -= (total_sum - 1440)
    
  p.scratch.f_daily_schedule = new_schedule
  print(f"[注入成功] {p.name} 的日程表已成功注入咖啡协同动作，新日程总时长: {sum(b[1] for b in p.scratch.f_daily_schedule)} 分钟")


def _chat_react(maze, persona, focused_event, reaction_mode, personas):
  # There are two personas -- the persona who is initiating the conversation
  # and the persona who is the target. We get the persona instances here. 
  init_persona = persona
  target_persona = personas[reaction_mode[9:].strip()]
  curr_personas = [init_persona, target_persona]

  # In the refactored Chat Skill Pack architecture, we perform lazy execution.
  # We do not generate dialogue at the planning stage. Instead, we use a placeholder action
  # and a default duration (10 minutes). The dialogue is generated dynamically upon arrival.
  inserted_act = f"having a conversation with {target_persona.name}"
  inserted_act_dur = 10

  act_start_time = target_persona.scratch.act_start_time

  curr_time = target_persona.scratch.curr_time
  if curr_time.second != 0: 
    temp_curr_time = curr_time + datetime.timedelta(seconds=60 - curr_time.second)
    chatting_end_time = temp_curr_time + datetime.timedelta(minutes=inserted_act_dur)
  else: 
    chatting_end_time = curr_time + datetime.timedelta(minutes=inserted_act_dur)

  for role, p in [("init", init_persona), ("target", target_persona)]: 
    if role == "init": 
      act_address = f"<persona> {target_persona.name}"
      act_event = (p.name, "chat with", target_persona.name)
      chatting_with = target_persona.name
      chatting_with_buffer = {}
      chatting_with_buffer[target_persona.name] = 800
    elif role == "target": 
      act_address = f"<persona> {init_persona.name}"
      act_event = (p.name, "chat with", init_persona.name)
      chatting_with = init_persona.name
      chatting_with_buffer = {}
      chatting_with_buffer[init_persona.name] = 800

    act_pronunciatio = "💬" 
    act_obj_description = None
    act_obj_pronunciatio = None
    act_obj_event = (None, None, None)

    _create_react(p, inserted_act, inserted_act_dur,
      act_address, act_event, chatting_with, None, chatting_with_buffer, chatting_end_time,
      act_pronunciatio, act_obj_description, act_obj_pronunciatio, 
      act_obj_event, act_start_time)


def _wait_react(persona, reaction_mode): 
  p = persona

  inserted_act = f'waiting to start {p.scratch.act_description.split("(")[-1][:-1]}'
  end_time = datetime.datetime.strptime(reaction_mode[6:].strip(), "%B %d, %Y, %H:%M:%S")
  inserted_act_dur = (end_time.minute + end_time.hour * 60) - (p.scratch.curr_time.minute + p.scratch.curr_time.hour * 60) + 1

  act_address = f"<waiting> {p.scratch.curr_tile[0]} {p.scratch.curr_tile[1]}"
  act_event = (p.name, "waiting to start", p.scratch.act_description.split("(")[-1][:-1])
  chatting_with = None
  chat = None
  chatting_with_buffer = None
  chatting_end_time = None

  act_pronunciatio = "⌛" 
  act_obj_description = None
  act_obj_pronunciatio = None
  act_obj_event = (None, None, None)

  _create_react(p, inserted_act, inserted_act_dur,
    act_address, act_event, chatting_with, chat, chatting_with_buffer, chatting_end_time,
    act_pronunciatio, act_obj_description, act_obj_pronunciatio, act_obj_event)


def decide_survival_action(persona, maze):
  import json
  # Get all objects the persona knows about
  objs = set()
  for w in persona.s_mem.tree:
    for s in persona.s_mem.tree[w]:
      for a in persona.s_mem.tree[w][s]:
        for obj in persona.s_mem.tree[w][s][a]:
          objs.add(obj)
  objs_list = list(objs)

  # Query environment micro-states and cooperative details
  object_states = []
  cooperative_events = []
  
  for obj in objs_list:
    address = persona.s_mem.find_nearest_object(obj)
    if address and address in maze.address_tiles:
      tiles = list(maze.address_tiles[address])
      events_on_obj = []
      for tile in tiles:
        tile_details = maze.access_tile(tile)
        if tile_details and tile_details["events"]:
          for ev in tile_details["events"]:
            ev_str = str(ev)
            events_on_obj.append(ev_str)
            if any(kw in ev_str.lower() for kw in ["waiting", "serve", "served"]):
              cooperative_events.append(f"{ev_str} (at {obj})")
      if events_on_obj:
        object_states.append(f"{obj} (current state: {', '.join(events_on_obj)})")
      else:
        object_states.append(f"{obj} (idle/normal)")
    else:
      object_states.append(f"{obj} (normal)")

  # Compile Temporal Context
  curr_time_str = persona.scratch.curr_time.strftime("%A %B %d, %Y, %I:%M %p") if persona.scratch.curr_time else "Unknown"
  act_desc = persona.scratch.act_description if persona.scratch.act_description else "None"
  act_dur = persona.scratch.act_duration if persona.scratch.act_duration else 0
  temporal_context = f"- Current Time: {curr_time_str}\n- Active Scheduled Action: '{act_desc}' (Planned duration remaining: {act_dur} minutes)"

  # Compile Physiological Rules
  physiological_rules = (
      "- Consuming food (Consume action) restores +40.0 Satiety and +5.0 Health, and consumes 1 food item from inventory.\n"
      "- Gathering food (Gather action) from resources (like apple_tree, refrigerator, cafe counter) adds items to inventory.\n"
      "- Resting (Rest action) restores +40.0 Stamina.\n"
      "- Normal activities decay Satiety by -0.008 per step, and walking decays Satiety by -0.015 per step.\n"
      "- If Satiety reaches 0.0, Health decays by -2.0 per step."
  )

  # Compile Cooperative Context
  cooperative_context = ""
  if cooperative_events:
    cooperative_context += "Active cooperative/social events nearby:\n" + "\n".join([f"- {ev}" for ev in cooperative_events])
  else:
    cooperative_context += "No special cooperative tasks or wait states are active nearby."

  curr_sector = maze.get_tile_path(persona.scratch.curr_tile, "sector").lower() if (persona.scratch.curr_tile and maze.get_tile_path(persona.scratch.curr_tile, "sector")) else ""
  is_worker = any(job in persona.scratch.learned.lower() for job in ["owner", "barista", "employee", "worker", "staff"]) and curr_sector in persona.scratch.learned.lower()
  if is_worker:
    cooperative_context += f"\n- NOTE: You are a staff/owner of the current area ({curr_sector}). You do not need to wait for others to serve you food/drink; you have direct access to resources and can gather or prepare food yourself."

  # Call GPT to decide survival action
  decision = run_gpt_prompt_survival_decision(
      persona, 
      object_states, 
      temporal_context=temporal_context, 
      physiological_rules=physiological_rules, 
      cooperative_context=cooperative_context
  )
  action = decision.get("action", "Idle")
  target = decision.get("target", "none")
  reasoning = decision.get("reasoning", "")

  print(f"[{persona.name}] 经过LLM生存分析做出决策: Action={action}, Target={target}, 原因={reasoning}")

  if action == "Idle" or target == "none":
    # Idle action
    persona.scratch.act_address = f"{persona.scratch.living_area}"
    persona.scratch.act_description = "idling to conserve energy"
    persona.scratch.act_duration = 10
    persona.scratch.act_start_time = persona.scratch.curr_time
    persona.scratch.act_pronunciatio = "💤"
    persona.scratch.act_event = (persona.name, "idle", "none")
    persona.scratch.act_path_set = False
    return persona.scratch.act_address

  # Resolve object address
  address = persona.s_mem.find_nearest_object(target)
  if not address:
    # Fallback to living area
    address = f"{persona.scratch.living_area}"

  if action == "Consume":
    # Check if target is in inventory (case-insensitive)
    item_key = target.strip().lower()
    in_inv = False
    for k in persona.scratch.inventory:
      if k.strip().lower() == item_key and persona.scratch.inventory[k] > 0:
        in_inv = True
        break
    
    if not in_inv:
      print(f"[{persona.name}] 背包中没有 {target}！修改动作为 Gather 从环境获取。")
      action = "Gather"
      # Prioritize cafe customer seating or behind the cafe counter
      if "cafe customer seating" in objs_list:
        target = "cafe customer seating"
      elif "behind the cafe counter" in objs_list:
        target = "behind the cafe counter"
      else:
        target = "refrigerator" if "refrigerator" in objs_list else "apple_tree"
      address = persona.s_mem.find_nearest_object(target) or address


  if action == "Gather":
    persona.scratch.act_address = address
    persona.scratch.act_description = f"gathering from {target}"
    persona.scratch.act_duration = 15
    persona.scratch.act_start_time = persona.scratch.curr_time
    persona.scratch.act_pronunciatio = "🍎"
    persona.scratch.act_event = (persona.name, "gather", target)
    persona.scratch.act_obj_description = f"being harvested by {persona.scratch.first_name}"
    persona.scratch.act_obj_pronunciatio = "🍎"
    persona.scratch.act_obj_event = (target, "harvested_by", persona.name)
    persona.scratch.act_path_set = False

  elif action == "Consume":
    persona.scratch.act_address = address
    persona.scratch.act_description = f"consuming {target}"
    persona.scratch.act_duration = 5
    persona.scratch.act_start_time = persona.scratch.curr_time
    persona.scratch.act_pronunciatio = "🍴"
    persona.scratch.act_event = (persona.name, "consume", target)
    persona.scratch.act_obj_description = f"being eaten by {persona.scratch.first_name}"
    persona.scratch.act_obj_pronunciatio = "🍴"
    persona.scratch.act_obj_event = (target, "consumed_by", persona.name)
    persona.scratch.act_path_set = False

  elif action == "Rest":
    persona.scratch.act_address = address
    persona.scratch.act_description = f"resting at {target}"
    persona.scratch.act_duration = 30
    persona.scratch.act_start_time = persona.scratch.curr_time
    persona.scratch.act_pronunciatio = "🛌"
    persona.scratch.act_event = (persona.name, "rest", target)
    persona.scratch.act_obj_description = f"being rested on by {persona.scratch.first_name}"
    persona.scratch.act_obj_pronunciatio = "🛌"
    persona.scratch.act_obj_event = (target, "rested_on_by", persona.name)
    persona.scratch.act_path_set = False

  return persona.scratch.act_address


def decide_demand_action(persona, maze):
  import json
  # Get all objects the persona knows about
  objs = set()
  for w in persona.s_mem.tree:
    for s in persona.s_mem.tree[w]:
      for a in persona.s_mem.tree[w][s]:
        for obj in persona.s_mem.tree[w][s][a]:
          objs.add(obj)
  objs_list = list(objs)

  # Query environment micro-states and cooperative details
  object_states = []
  cooperative_events = []
  
  for obj in objs_list:
    address = persona.s_mem.find_nearest_object(obj)
    if address and address in maze.address_tiles:
      tiles = list(maze.address_tiles[address])
      events_on_obj = []
      for tile in tiles:
        tile_details = maze.access_tile(tile)
        if tile_details and tile_details["events"]:
          for ev in tile_details["events"]:
            ev_str = str(ev)
            events_on_obj.append(ev_str)
            if any(kw in ev_str.lower() for kw in ["waiting", "serve", "served"]):
              cooperative_events.append(f"{ev_str} (at {obj})")
      if events_on_obj:
        object_states.append(f"{obj} (current state: {', '.join(events_on_obj)})")
      else:
        object_states.append(f"{obj} (idle/normal)")
    else:
      object_states.append(f"{obj} (normal)")

  # Compile Temporal Context
  curr_time_str = persona.scratch.curr_time.strftime("%A %B %d, %Y, %I:%M %p") if persona.scratch.curr_time else "Unknown"
  temporal_context = f"- Current Time: {curr_time_str}"

  # Compile Homeostasis & World Rules
  physiological_rules = (
      "- Consuming food (Consume action) restores +40.0 Satiety and +5.0 Health, and consumes 1 food item from inventory.\n"
      "- Gathering food (Gather action) from resources (like apple_tree, refrigerator, cafe counter) adds items to inventory.\n"
      "- Resting (Rest action) restores +40.0 Stamina.\n"
      "- Socializing (Socialize action) restores +30.0 Mood.\n"
      "- Normal activities decay Satiety by -0.015 per step, sleeping decays Satiety by -0.008 per step.\n"
      "- Normal activities decay Stamina by -0.015 per step, walking decays Stamina by -0.022 per step.\n"
      "- Sleeping restores Stamina by +0.05 per step, resting restores Stamina by +0.03 per step.\n"
      "- Switch Cost: Changing tasks/actions in under 15 minutes consumes a high penalty of -5.0 Stamina.\n"
      "- If Satiety reaches 0.0, Health decays by -0.05 per step."
  )

  # Compile Cooperative Context
  cooperative_context = ""
  if cooperative_events:
    cooperative_context += "Active cooperative/social events nearby:\n" + "\n".join([f"- {ev}" for ev in cooperative_events])
  else:
    cooperative_context += "No special cooperative tasks or wait states are active nearby."

  curr_sector = maze.get_tile_path(persona.scratch.curr_tile, "sector").lower() if (persona.scratch.curr_tile and maze.get_tile_path(persona.scratch.curr_tile, "sector")) else ""
  is_worker = any(job in persona.scratch.learned.lower() for job in ["owner", "barista", "employee", "worker", "staff"]) and curr_sector in persona.scratch.learned.lower()
  if is_worker:
    cooperative_context += f"\n- NOTE: You are a staff/owner of the current area ({curr_sector}). You do not need to wait for others to serve you food/drink; you have direct access to resources and can gather or prepare food yourself."

  # Call GPT to decide dynamic action
  decision = run_gpt_prompt_demand_decision(
      persona, 
      object_states, 
      temporal_context=temporal_context, 
      rules=physiological_rules, 
      cooperative_context=cooperative_context
  )
  action = decision.get("action", "Idle")
  target = decision.get("target", "none")
  act_desp = decision.get("detail", "idling")
  act_dura = decision.get("duration", 10)
  reasoning = decision.get("reasoning", "")

  print(f"[{persona.name}] 需求驱动实时决策: Action={action}, Target={target}, Duration={act_dura} min, Detail='{act_desp}', 原因={reasoning}")

  # Fallback check
  if not act_desp:
    act_desp = "idling to conserve energy"
    act_dura = 10

  # Resolve sector, arena, object
  act_world = maze.access_tile(persona.scratch.curr_tile)["world"]
  
  # Check if target is a known object with a specific address
  address = persona.s_mem.find_nearest_object(target)
  if address:
    new_address = address
  else:
    # Use standard prompt resolvers
    act_sector = generate_action_sector(act_desp, persona, maze)
    act_arena = generate_action_arena(act_desp, persona, maze, act_world, act_sector)
    act_address = f"{act_world}:{act_sector}:{act_arena}"
    act_game_object = generate_action_game_object(act_desp, act_address, persona, maze)
    new_address = f"{act_world}:{act_sector}:{act_arena}:{act_game_object}"

  act_pron = generate_action_pronunciatio(act_desp, persona)
  act_event = generate_action_event_triple(act_desp, persona)
  
  # Persona's actions also influence the object states. We set those up here. 
  try:
    act_game_object = new_address.split(":")[-1]
  except:
    act_game_object = "none"
  act_obj_desp = generate_act_obj_desc(act_game_object, act_desp, persona)
  act_obj_pron = generate_action_pronunciatio(act_obj_desp, persona)
  act_obj_event = generate_act_obj_event_triple(act_game_object, act_obj_desp, persona)

  # Adding the action to persona's queue. 
  persona.scratch.add_new_action(new_address, 
                                 int(act_dura), 
                                 act_desp, 
                                 act_pron, 
                                 act_event,
                                 None,
                                 None,
                                 None,
                                 None,
                                 act_obj_desp, 
                                 act_obj_pron, 
                                 act_obj_event)
  return persona.scratch.act_address


def plan(persona, maze, personas, new_day, retrieved): 
  """
  Main cognitive function of the chain. It takes the retrieved memory and 
  perception, as well as the maze and the first day state to conduct both 
  the long term and short term planning for the persona. 
  """ 
  # If it is a new day, revise identity, but do NOT generate a rigid hourly schedule
  if new_day == "New day":
    revise_identity(persona)

  # Unify scheduling and survival intercepts into one real-time demand-driven decision engine
  act_desc = persona.scratch.act_description if persona.scratch.act_description else ""
  if persona.scratch.act_check_finished() or not act_desc:
    decide_demand_action(persona, maze)

  # PART 3: If you perceived an event that needs to be responded to (saw 
  # another persona), and retrieved relevant information. 
  # Step 1: Retrieved may have multiple events represented in it. The first 
  #         job here is to determine which of the events we want to focus 
  #         on for the persona. 
  #         <focused_event> takes the form of a dictionary like this: 
  #         dictionary {["curr_event"] = <ConceptNode>, 
  #                     ["events"] = [<ConceptNode>, ...], 
  #                     ["thoughts"] = [<ConceptNode>, ...]}
  focused_event = False
  if retrieved.keys(): 
    focused_event = _choose_retrieved(persona, retrieved)
  
  # Step 2: Once we choose an event, we need to determine whether the
  #         persona will take any actions for the perceived event. There are
  #         three possible modes of reaction returned by _should_react. 
  #         a) "chat with {target_persona.name}"
  #         b) "react"
  #         c) False
  if focused_event: 
    reaction_mode = _should_react(persona, focused_event, personas)
    if reaction_mode: 
      # If we do want to chat, then we generate conversation 
      if reaction_mode[:9] == "chat with":
        _chat_react(maze, persona, focused_event, reaction_mode, personas)
      elif reaction_mode[:4] == "wait": 
        _wait_react(persona, reaction_mode)
      # elif reaction_mode == "do other things": 
      #   _chat_react(persona, focused_event, reaction_mode, personas)

  # Step 3: Chat-related state clean up. 
  # If the persona is not chatting with anyone, we clean up any of the 
  # chat-related states here. 
  if persona.scratch.act_event[1] not in ["chat with", "creator_comm"]:
    persona.scratch.chatting_with = None
    persona.scratch.chat = None
    persona.scratch.chatting_end_time = None
  # We want to make sure that the persona does not keep conversing with each
  # other in an infinite loop. So, chatting_with_buffer maintains a form of 
  # buffer that makes the persona wait from talking to the same target 
  # immediately after chatting once. We keep track of the buffer value here. 
  curr_persona_chat_buffer = persona.scratch.chatting_with_buffer
  for persona_name, buffer_count in curr_persona_chat_buffer.items():
    if persona_name != persona.scratch.chatting_with: 
      persona.scratch.chatting_with_buffer[persona_name] -= 1

  return persona.scratch.act_address













































 
