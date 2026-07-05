"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: scratch.py
Description: Defines the short-term memory module for generative agents.
"""
import datetime
import json
import sys
sys.path.append('../../')

from global_methods import *
from persona.cognitive_modules.action_command_utils import (
  build_decision_signature,
  infer_action_command_from_event,
)
from persona.cognitive_modules.debug_log import append_debug_log


def _normalize_event_tuple(raw_event, fallback):
  if isinstance(raw_event, list):
    return tuple(raw_event)
  if isinstance(raw_event, tuple):
    return raw_event
  if raw_event is None:
    return fallback
  return raw_event


def _normalize_action_address(raw_address):
  if isinstance(raw_address, str):
    raw_address = raw_address.strip()
    return raw_address or None
  return raw_address

class Scratch: 
  def __init__(self, f_saved): 
    # PERSONA HYPERPARAMETERS
    # <vision_r> denotes the number of tiles that the persona can see around 
    # them. 
    self.vision_r = 4
    # <att_bandwidth> TODO 
    self.att_bandwidth = 3
    # <retention> TODO 
    self.retention = 5

    # WORLD INFORMATION
    # Perceived world time. 
    self.curr_time = None
    # Current simulation step number.
    self.curr_step = None
    # Current x,y tile coordinate of the persona. 
    self.curr_tile = None
    # Perceived world daily requirement. 
    self.daily_plan_req = None
    
    # THE CORE IDENTITY OF THE PERSONA 
    # Base information about the persona.
    self.name = None
    self.first_name = None
    self.last_name = None
    self.age = None
    # L0 permanent core traits.  
    self.innate = None
    # L1 stable traits.
    self.learned = None
    # L2 external implementation. 
    self.currently = None
    self.lifestyle = None
    self.living_area = None

    # Physiological metabolic states
    self.satiety = 40.0
    self.stamina = 100.0
    self.health = 100.0
    # Psychological and switching state
    self.mood = 50.0
    self.last_social_time = None
    self.last_action_switch_time = None
    self.decision_commit_until_step = None
    self.last_decision_signature = None
    self.last_decision_reason = None
    self.recent_completed_action_signature = None
    self.recent_completed_action_step = None
    self.suspended_action = None
    self.suspended_action_step = None
    self.pending_interrupt = None
    self.navigation_failure = None
    self.last_action_observation = None
    self.active_execution_state = None
    # Inventory state
    self.inventory = {}
    # Skills system
    self.skills = {
      "farming": {"level": 1, "xp": 0},
      "cooking": {"level": 1, "xp": 0},
      "gathering": {"level": 1, "xp": 0},
      "singing": {"level": 1, "xp": 0}
    }
    # Personal knowledge base
    self.personal_knowledge = {}

    # REFLECTION VARIABLES
    self.concept_forget = 100
    self.daily_reflection_time = 60 * 3
    self.daily_reflection_size = 5
    self.overlap_reflect_th = 2
    self.kw_strg_event_reflect_th = 4
    self.kw_strg_thought_reflect_th = 4

    # New reflection variables
    self.recency_w = 1
    self.relevance_w = 1
    self.importance_w = 1
    self.recency_decay = 0.99
    self.importance_trigger_max = 150
    self.importance_trigger_curr = self.importance_trigger_max
    self.importance_ele_n = 0 
    self.thought_count = 5

    # PERSONA PLANNING 
    # <daily_req> is a list of various goals the persona is aiming to achieve
    # today. 
    # e.g., ['Work on her paintings for her upcoming show', 
    #        'Take a break to watch some TV', 
    #        'Make lunch for herself', 
    #        'Work on her paintings some more', 
    #        'Go to bed early']
    # They have to be renewed at the end of the day, which is why we are
    # keeping track of when they were first generated. 
    self.daily_req = []
    # <f_daily_schedule> denotes a form of long term planning. This lays out 
    # the persona's daily plan. 
    # Note that we take the long term planning and short term decomposition 
    # appoach, which is to say that we first layout hourly schedules and 
    # gradually decompose as we go. 
    # Three things to note in the example below: 
    # 1) See how "sleeping" was not decomposed -- some of the common events 
    #    really, just mainly sleeping, are hard coded to be not decomposable.
    # 2) Some of the elements are starting to be decomposed... More of the 
    #    things will be decomposed as the day goes on (when they are 
    #    decomposed, they leave behind the original hourly action description
    #    in tact).
    # 3) The latter elements are not decomposed. When an event occurs, the
    #    non-decomposed elements go out the window.  
    # e.g., [['sleeping', 360], 
    #         ['wakes up and ... (wakes up and stretches ...)', 5], 
    #         ['wakes up and starts her morning routine (out of bed )', 10],
    #         ...
    #         ['having lunch', 60], 
    #         ['working on her painting', 180], ...]
    self.f_daily_schedule = []
    # <f_daily_schedule_hourly_org> is a replica of f_daily_schedule
    # initially, but retains the original non-decomposed version of the hourly
    # schedule. 
    # e.g., [['sleeping', 360], 
    #        ['wakes up and starts her morning routine', 120],
    #        ['working on her painting', 240], ... ['going to bed', 60]]
    self.f_daily_schedule_hourly_org = []
    
    # CURR ACTION 
    # <address> is literally the string address of where the action is taking 
    # place.  It comes in the form of 
    # "{world}:{sector}:{arena}:{game_objects}". It is important that you 
    # access this without doing negative indexing (e.g., [-1]) because the 
    # latter address elements may not be present in some cases. 
    # e.g., "dolores double studio:double studio:bedroom 1:bed"
    self.act_address = None
    # <start_time> is a python datetime instance that indicates when the 
    # action has started. 
    self.act_start_time = None
    # <duration> is the integer value that indicates the number of minutes an
    # action is meant to last. 
    self.act_duration = None
    # <description> is a string description of the action. 
    self.act_description = None
    # <pronunciatio> is the descriptive expression of the self.description. 
    # Currently, it is implemented as emojis. 
    self.act_pronunciatio = None
    # <event_form> represents the event triple that the persona is currently 
    # engaged in. 
    self.act_event = (self.name, None, None)
    self.act_command = infer_action_command_from_event(self.act_event, source="init")

    # <obj_description> is a string description of the object action. 
    self.act_obj_description = None
    # <obj_pronunciatio> is the descriptive expression of the object action. 
    # Currently, it is implemented as emojis. 
    self.act_obj_pronunciatio = None
    # <obj_event_form> represents the event triple that the action object is  
    # currently engaged in. 
    self.act_obj_event = (self.name, None, None)

    # <chatting_with> is the string name of the persona that the current 
    # persona is chatting with. None if it does not exist. 
    self.chatting_with = None
    # <chat> is a list of list that saves a conversation between two personas.
    # It comes in the form of: [["Dolores Murphy", "Hi"], 
    #                           ["Maeve Jenson", "Hi"] ...]
    self.chat = None
    self.last_chat = None
    # <chatting_with_buffer>  
    # e.g., ["Dolores Murphy"] = self.vision_r
    self.chatting_with_buffer = dict()
    self.chatting_end_time = None
    self.social_dialogue_id = None
    self.social_dialogue_partner = None
    self.social_dialogue_role = None
    self.social_dialogue_started_step = None

    # <path_set> is True if we've already calculated the path the persona will
    # take to execute this action. That path is stored in the persona's 
    # scratch.planned_path.
    self.act_path_set = False
    # <planned_path> is a list of x y coordinate tuples (tiles) that describe
    # the path the persona is to take to execute the <curr_action>. 
    # The list does not include the persona's current tile, and includes the 
    # destination tile. 
    # e.g., [(50, 10), (49, 10), (48, 10), ...]
    self.planned_path = []
    self.last_retrieved_memories = {}

    if check_if_file_exists(f_saved): 
      # If we have a bootstrap file, load that here. 
      with open(f_saved, encoding="utf-8") as scratch_file:
        scratch_load = json.load(scratch_file)

      self.vision_r = scratch_load["vision_r"]
      self.att_bandwidth = scratch_load["att_bandwidth"]
      self.retention = scratch_load["retention"]

      if scratch_load["curr_time"]: 
        self.curr_time = datetime.datetime.strptime(scratch_load["curr_time"],
                                                  "%B %d, %Y, %H:%M:%S")
      else: 
        self.curr_time = None
      self.curr_tile = scratch_load["curr_tile"]
      self.daily_plan_req = scratch_load["daily_plan_req"]

      self.name = scratch_load["name"]
      self.first_name = scratch_load["first_name"]
      self.last_name = scratch_load["last_name"]
      self.age = scratch_load["age"]
      self.innate = scratch_load["innate"]
      self.learned = scratch_load["learned"]
      self.currently = scratch_load["currently"]
      self.lifestyle = scratch_load["lifestyle"]
      self.living_area = scratch_load["living_area"]

      # Load physiological and skill parameters
      self.satiety = scratch_load.get("satiety", 40.0)
      self.stamina = scratch_load.get("stamina", 100.0)
      self.health = scratch_load.get("health", 100.0)
      self.mood = scratch_load.get("mood", 50.0)
      
      lst_str = scratch_load.get("last_social_time", None)
      self.last_social_time = datetime.datetime.strptime(lst_str, "%B %d, %Y, %H:%M:%S") if lst_str else None
      
      last_switch_str = scratch_load.get("last_action_switch_time", None)
      self.last_action_switch_time = datetime.datetime.strptime(last_switch_str, "%B %d, %Y, %H:%M:%S") if last_switch_str else None
      self.decision_commit_until_step = scratch_load.get("decision_commit_until_step", None)
      self.last_decision_signature = scratch_load.get("last_decision_signature", None)
      self.last_decision_reason = scratch_load.get("last_decision_reason", None)
      self.recent_completed_action_signature = scratch_load.get("recent_completed_action_signature", None)
      self.recent_completed_action_step = scratch_load.get("recent_completed_action_step", None)
      self.suspended_action = scratch_load.get("suspended_action", None)
      self.suspended_action_step = scratch_load.get("suspended_action_step", None)
      self.pending_interrupt = scratch_load.get("pending_interrupt", None)
      self.navigation_failure = scratch_load.get("navigation_failure", None)
      self.last_action_observation = scratch_load.get("last_action_observation", None)
      self.active_execution_state = scratch_load.get("active_execution_state", None)

      self.inventory = scratch_load.get("inventory", {})
      self.skills = scratch_load.get("skills", {
        "farming": {"level": 1, "xp": 0},
        "cooking": {"level": 1, "xp": 0},
        "gathering": {"level": 1, "xp": 0},
        "singing": {"level": 1, "xp": 0}
      })
      if "singing" not in self.skills:
        self.skills["singing"] = {"level": 1, "xp": 0}
      self.personal_knowledge = scratch_load.get("personal_knowledge", {})

      self.concept_forget = scratch_load["concept_forget"]
      self.daily_reflection_time = scratch_load["daily_reflection_time"]
      self.daily_reflection_size = scratch_load["daily_reflection_size"]
      self.overlap_reflect_th = scratch_load["overlap_reflect_th"]
      self.kw_strg_event_reflect_th = scratch_load["kw_strg_event_reflect_th"]
      self.kw_strg_thought_reflect_th = scratch_load["kw_strg_thought_reflect_th"]

      self.recency_w = scratch_load["recency_w"]
      self.relevance_w = scratch_load["relevance_w"]
      self.importance_w = scratch_load["importance_w"]
      self.recency_decay = scratch_load["recency_decay"]
      self.importance_trigger_max = scratch_load["importance_trigger_max"]
      self.importance_trigger_curr = scratch_load["importance_trigger_curr"]
      self.importance_ele_n = scratch_load["importance_ele_n"]
      self.thought_count = scratch_load["thought_count"]

      self.daily_req = scratch_load["daily_req"]
      self.f_daily_schedule = scratch_load["f_daily_schedule"]
      self.f_daily_schedule_hourly_org = scratch_load["f_daily_schedule_hourly_org"]

      self.act_address = _normalize_action_address(scratch_load["act_address"])
      if scratch_load["act_start_time"]: 
        self.act_start_time = datetime.datetime.strptime(
                                              scratch_load["act_start_time"],
                                              "%B %d, %Y, %H:%M:%S")
      else: 
        self.curr_time = None
      self.act_duration = scratch_load["act_duration"]
      self.act_description = scratch_load["act_description"]
      self.act_pronunciatio = scratch_load["act_pronunciatio"]
      self.act_event = _normalize_event_tuple(
        scratch_load.get("act_event"),
        (self.name, None, None),
      )
      self.act_command = scratch_load.get("act_command", infer_action_command_from_event(self.act_event, source="load"))

      self.act_obj_description = scratch_load["act_obj_description"]
      self.act_obj_pronunciatio = scratch_load["act_obj_pronunciatio"]
      self.act_obj_event = _normalize_event_tuple(
        scratch_load.get("act_obj_event"),
        (None, None, None),
      )

      self.chatting_with = scratch_load.get("chatting_with")
      self.chat = scratch_load.get("chat")
      self.last_chat = scratch_load.get("last_chat", None)
      self.chatting_with_buffer = scratch_load.get("chatting_with_buffer", {})
      chatting_end_time = scratch_load.get("chatting_end_time")
      if chatting_end_time: 
        self.chatting_end_time = datetime.datetime.strptime(
                                            chatting_end_time,
                                            "%B %d, %Y, %H:%M:%S")
      else:
        self.chatting_end_time = None
      self.social_dialogue_id = scratch_load.get("social_dialogue_id", None)
      self.social_dialogue_partner = scratch_load.get("social_dialogue_partner", None)
      self.social_dialogue_role = scratch_load.get("social_dialogue_role", None)
      self.social_dialogue_started_step = scratch_load.get("social_dialogue_started_step", None)

      self.act_path_set = scratch_load["act_path_set"]
      self.planned_path = scratch_load["planned_path"]


  def save(self, out_json):
    """
    Save persona's scratch. 

    INPUT: 
      out_json: The file where we wil be saving our persona's state. 
    OUTPUT: 
      None
    """
    scratch = dict() 
    scratch["vision_r"] = self.vision_r
    scratch["att_bandwidth"] = self.att_bandwidth
    scratch["retention"] = self.retention

    scratch["curr_time"] = self.curr_time.strftime("%B %d, %Y, %H:%M:%S")
    scratch["curr_tile"] = self.curr_tile
    scratch["daily_plan_req"] = self.daily_plan_req

    scratch["name"] = self.name
    scratch["first_name"] = self.first_name
    scratch["last_name"] = self.last_name
    scratch["age"] = self.age
    scratch["innate"] = self.innate
    scratch["learned"] = self.learned
    scratch["currently"] = self.currently
    scratch["lifestyle"] = self.lifestyle
    scratch["living_area"] = self.living_area

    # Save physiological and skill parameters
    scratch["satiety"] = self.satiety
    scratch["stamina"] = self.stamina
    scratch["health"] = self.health
    scratch["mood"] = self.mood
    scratch["last_social_time"] = self.last_social_time.strftime("%B %d, %Y, %H:%M:%S") if self.last_social_time else None
    scratch["last_action_switch_time"] = self.last_action_switch_time.strftime("%B %d, %Y, %H:%M:%S") if self.last_action_switch_time else None
    scratch["decision_commit_until_step"] = self.decision_commit_until_step
    scratch["last_decision_signature"] = self.last_decision_signature
    scratch["last_decision_reason"] = self.last_decision_reason
    scratch["recent_completed_action_signature"] = self.recent_completed_action_signature
    scratch["recent_completed_action_step"] = self.recent_completed_action_step
    scratch["suspended_action"] = self.suspended_action
    scratch["suspended_action_step"] = self.suspended_action_step
    scratch["pending_interrupt"] = self.pending_interrupt
    scratch["navigation_failure"] = self.navigation_failure
    scratch["last_action_observation"] = self.last_action_observation
    scratch["active_execution_state"] = self.active_execution_state
    scratch["inventory"] = self.inventory
    scratch["skills"] = self.skills
    scratch["personal_knowledge"] = self.personal_knowledge

    scratch["concept_forget"] = self.concept_forget
    scratch["daily_reflection_time"] = self.daily_reflection_time
    scratch["daily_reflection_size"] = self.daily_reflection_size
    scratch["overlap_reflect_th"] = self.overlap_reflect_th
    scratch["kw_strg_event_reflect_th"] = self.kw_strg_event_reflect_th
    scratch["kw_strg_thought_reflect_th"] = self.kw_strg_thought_reflect_th

    scratch["recency_w"] = self.recency_w
    scratch["relevance_w"] = self.relevance_w
    scratch["importance_w"] = self.importance_w
    scratch["recency_decay"] = self.recency_decay
    scratch["importance_trigger_max"] = self.importance_trigger_max
    scratch["importance_trigger_curr"] = self.importance_trigger_curr
    scratch["importance_ele_n"] = self.importance_ele_n
    scratch["thought_count"] = self.thought_count

    scratch["daily_req"] = self.daily_req
    scratch["f_daily_schedule"] = self.f_daily_schedule
    scratch["f_daily_schedule_hourly_org"] = self.f_daily_schedule_hourly_org

    scratch["act_address"] = _normalize_action_address(self.act_address)
    scratch["act_start_time"] = (self.act_start_time
                                     .strftime("%B %d, %Y, %H:%M:%S"))
    scratch["act_duration"] = self.act_duration
    scratch["act_description"] = self.act_description
    scratch["act_pronunciatio"] = self.act_pronunciatio
    scratch["act_event"] = self.act_event
    scratch["act_command"] = self.act_command

    scratch["act_obj_description"] = self.act_obj_description
    scratch["act_obj_pronunciatio"] = self.act_obj_pronunciatio
    scratch["act_obj_event"] = self.act_obj_event

    scratch["act_path_set"] = self.act_path_set
    scratch["planned_path"] = self.planned_path

    with open(out_json, "w") as outfile:
      json.dump(scratch, outfile, indent=2) 


  def get_f_daily_schedule_index(self, advance=0):
    """
    We get the current index of self.f_daily_schedule. 

    Recall that self.f_daily_schedule stores the decomposed action sequences 
    up until now, and the hourly sequences of the future action for the rest
    of today. Given that self.f_daily_schedule is a list of list where the 
    inner list is composed of [task, duration], we continue to add up the 
    duration until we reach "if elapsed > today_min_elapsed" condition. The
    index where we stop is the index we will return. 

    INPUT
      advance: Integer value of the number minutes we want to look into the 
               future. This allows us to get the index of a future timeframe.
    OUTPUT 
      an integer value for the current index of f_daily_schedule.
    """
    # We first calculate teh number of minutes elapsed today. 
    today_min_elapsed = 0
    today_min_elapsed += self.curr_time.hour * 60
    today_min_elapsed += self.curr_time.minute
    today_min_elapsed += advance

    x = 0
    for task, duration in self.f_daily_schedule: 
      x += duration
    x = 0
    for task, duration in self.f_daily_schedule_hourly_org: 
      x += duration

    # We then calculate the current index based on that. 
    curr_index = 0
    elapsed = 0
    for task, duration in self.f_daily_schedule: 
      elapsed += duration
      if elapsed > today_min_elapsed: 
        return curr_index
      curr_index += 1

    return curr_index


  def get_f_daily_schedule_hourly_org_index(self, advance=0):
    """
    We get the current index of self.f_daily_schedule_hourly_org. 
    It is otherwise the same as get_f_daily_schedule_index. 

    INPUT
      advance: Integer value of the number minutes we want to look into the 
               future. This allows us to get the index of a future timeframe.
    OUTPUT 
      an integer value for the current index of f_daily_schedule.
    """
    # We first calculate teh number of minutes elapsed today. 
    today_min_elapsed = 0
    today_min_elapsed += self.curr_time.hour * 60
    today_min_elapsed += self.curr_time.minute
    today_min_elapsed += advance
    # We then calculate the current index based on that. 
    curr_index = 0
    elapsed = 0
    for task, duration in self.f_daily_schedule_hourly_org: 
      elapsed += duration
      if elapsed > today_min_elapsed: 
        return curr_index
      curr_index += 1
    return curr_index


  def get_str_iss(self): 
    """
    ISS stands for "identity stable set." This describes the commonset summary
    of this persona -- basically, the bare minimum description of the persona
    that gets used in almost all prompts that need to call on the persona. 

    INPUT
      None
    OUTPUT
      the identity stable set summary of the persona in a string form.
    EXAMPLE STR OUTPUT
      "Name: Dolores Heitmiller
       Age: 28
       Innate traits: hard-edged, independent, loyal
       Learned traits: Dolores is a painter who wants live quietly and paint 
         while enjoying her everyday life.
       Currently: Dolores is preparing for her first solo show. She mostly 
         works from home.
       Lifestyle: Dolores goes to bed around 11pm, sleeps for 7 hours, eats 
         dinner around 6pm.
       Daily plan requirement: Dolores is planning to stay at home all day and 
         never go out."
    """
    commonset = ""
    commonset += f"Name: {self.name}\n"
    commonset += f"Age: {self.age}\n"
    commonset += f"Innate traits: {self.innate}\n"
    commonset += f"Learned traits: {self.learned}\n"
    commonset += f"Currently: {self.currently}\n"
    commonset += f"Lifestyle: {self.lifestyle}\n"
    commonset += f"Daily plan requirement: {self.daily_plan_req}\n"
    commonset += f"Current Date: {self.curr_time.strftime('%A %B %d')}\n"
    return commonset


  def get_str_name(self): 
    return self.name


  def get_str_firstname(self): 
    return self.first_name


  def get_str_lastname(self): 
    return self.last_name


  def get_str_age(self): 
    return str(self.age)


  def get_str_innate(self): 
    return self.innate


  def get_str_learned(self): 
    return self.learned


  def get_str_currently(self): 
    return self.currently


  def get_str_lifestyle(self): 
    return self.lifestyle


  def get_str_daily_plan_req(self): 
    return self.daily_plan_req


  def get_str_curr_date_str(self): 
    return self.curr_time.strftime("%A %B %d")


  def get_curr_event(self):
    if not self.act_address: 
      return (self.name, None, None)
    else: 
      return self.act_event


  def get_curr_event_and_desc(self): 
    if not self.act_address: 
      return (self.name, None, None, None)
    else: 
      return (self.act_event[0], 
              self.act_event[1], 
              self.act_event[2],
              self.act_description)


  def get_curr_obj_event_and_desc(self): 
    if not self.act_address: 
      return ("", None, None, None)
    else: 
      return (self.act_address, 
              self.act_obj_event[1], 
              self.act_obj_event[2],
              self.act_obj_description)


  def add_new_action(self, 
                     action_address,
                     action_duration,
                     action_description,
                     action_pronunciatio, 
                     action_event,
                     action_command,
                     chatting_with, 
                     chat, 
                     chatting_with_buffer,
                     chatting_end_time,
                     act_obj_description, 
                     act_obj_pronunciatio, 
                     act_obj_event, 
                     act_start_time=None): 
    action_address = _normalize_action_address(action_address)
    resolved_action_command = action_command or infer_action_command_from_event(action_event, source="add_new_action")
    next_signature = build_decision_signature(
      resolved_action_command,
      action_event=action_event,
      action_description=action_description,
      action_address=action_address,
    )
    if not self.should_accept_action_switch(next_signature, resolved_action_command, action_description):
      return False

    previous_signature = self.last_decision_signature
    if previous_signature != next_signature:
      self.last_action_switch_time = self.curr_time
      append_debug_log(
        "decision_stability.jsonl",
        {
          "persona": self.name,
          "event": "switch_accepted",
          "curr_step": self.curr_step,
          "old_signature": previous_signature,
          "new_signature": next_signature,
          "source": resolved_action_command.get("source") if isinstance(resolved_action_command, dict) else None,
          "description": action_description,
        }
      )
    self.last_decision_signature = dict(next_signature)
    self.last_decision_reason = action_description
    self.decision_commit_until_step = self._next_commit_window_step(next_signature)

    self.act_address = action_address
    self.act_duration = action_duration
    self.act_description = action_description
    self.act_pronunciatio = action_pronunciatio
    self.act_event = action_event
    self.act_command = resolved_action_command

    self.chatting_with = chatting_with
    self.chat = chat 
    if chatting_with_buffer: 
      self.chatting_with_buffer.update(chatting_with_buffer)
    self.chatting_end_time = chatting_end_time
    predicate = None
    if action_event and len(action_event) > 1:
      predicate = action_event[1]
    if predicate != "chat with":
      self.social_dialogue_id = None
      self.social_dialogue_partner = None
      self.social_dialogue_role = None
      self.social_dialogue_started_step = None

    self.act_obj_description = act_obj_description
    self.act_obj_pronunciatio = act_obj_pronunciatio
    self.act_obj_event = act_obj_event
    
    self.act_start_time = self.curr_time
    
    self.act_path_set = False
    self.serving_memory_written = False
    self.drinking_memory_written = False
    self.begin_execution_state(phase="planned")
    return True


  def _next_commit_window_step(self, action_signature):
    curr_step = self.curr_step if self.curr_step is not None else None
    if curr_step is None:
      return None
    family = (action_signature or {}).get("intent_family")
    if family in {"restore_satiety", "restore_stamina"}:
      return curr_step + 2
    if family == "communication":
      return curr_step + 1
    return curr_step + 3


  def _same_decision_family(self, old_signature, new_signature):
    if not old_signature or not new_signature:
      return False
    if old_signature == new_signature:
      return True
    if old_signature.get("skill_id") == new_signature.get("skill_id") and old_signature.get("target") == new_signature.get("target"):
      return True
    if old_signature.get("intent_family") == new_signature.get("intent_family") and old_signature.get("intent_family") in {"restore_satiety", "restore_stamina", "communication"}:
      return True
    return False


  def _is_internal_family_oscillation(self, old_signature, new_signature):
    if not old_signature or not new_signature:
      return False
    if old_signature.get("intent_family") != new_signature.get("intent_family"):
      return False
    if old_signature.get("target") != new_signature.get("target"):
      return False
    family = old_signature.get("intent_family")
    if family not in {"restore_satiety", "restore_stamina"}:
      return False
    old_skill = old_signature.get("skill_id")
    new_skill = new_signature.get("skill_id")
    if not old_skill or not new_skill or old_skill == new_skill:
      return False
    return True


  def get_active_decision_signature(self):
    if not (self.act_command or self.act_event or self.act_address):
      return None
    return build_decision_signature(
      self.act_command,
      action_event=self.act_event,
      action_description=self.act_description,
      action_address=self.act_address,
    )


  def _is_forced_switch_source(self, action_command):
    if not isinstance(action_command, dict):
      return False
    return action_command.get("source") in {
      "survival_direct",
      "creator_injection",
      "chat_followup",
      "post_gather_followup",
    }


  def _is_critical_survival_switch(self, action_signature):
    if not action_signature:
      return False
    family = action_signature.get("intent_family")
    if family == "restore_satiety":
      return self.satiety < 30.0
    if family == "restore_stamina":
      return self.stamina < 30.0
    return False


  def should_accept_action_switch(self, action_signature, action_command=None, action_description=None):
    if not action_signature or not action_signature.get("skill_id"):
      return True
    if not self.last_decision_signature:
      return True
    if self._is_forced_switch_source(action_command) or self._is_critical_survival_switch(action_signature):
      return True

    commit_until = self.decision_commit_until_step
    if self._is_internal_family_oscillation(self.last_decision_signature, action_signature):
      if commit_until is not None and self.curr_step is not None and self.curr_step < commit_until:
        append_debug_log(
          "decision_stability.jsonl",
          {
            "persona": self.name,
            "event": "switch_blocked",
            "curr_step": self.curr_step,
            "commit_until_step": commit_until,
            "old_signature": self.last_decision_signature,
            "new_signature": action_signature,
            "source": action_command.get("source") if isinstance(action_command, dict) else None,
            "description": action_description,
            "block_reason": "same_family_internal_oscillation",
          }
        )
        return False

    if self._same_decision_family(self.last_decision_signature, action_signature):
      return True
    commit_until = self.decision_commit_until_step
    if commit_until is None or self.curr_step is None or self.curr_step >= commit_until:
      return True

    append_debug_log(
      "decision_stability.jsonl",
      {
        "persona": self.name,
        "event": "switch_blocked",
        "curr_step": self.curr_step,
        "commit_until_step": commit_until,
        "old_signature": self.last_decision_signature,
        "new_signature": action_signature,
        "source": action_command.get("source") if isinstance(action_command, dict) else None,
        "description": action_description,
        "block_reason": "commit_window",
      }
    )
    return False


  def is_recent_duplicate_action(self, action_signature, within_steps=2):
    if not action_signature or not self.recent_completed_action_signature:
      return False
    if self.curr_step is None or self.recent_completed_action_step is None:
      return False
    if self.curr_step - self.recent_completed_action_step > within_steps:
      return False
    return self.recent_completed_action_signature == action_signature


  def compute_switch_cost(self, action_signature):
    if not action_signature or not action_signature.get("skill_id"):
      return 0.0
    current_signature = self.get_active_decision_signature()
    if not current_signature:
      return 0.0
    if self._is_internal_family_oscillation(current_signature, action_signature):
      penalty = 0.18
      if self.curr_step is not None and self.decision_commit_until_step is not None and self.curr_step < self.decision_commit_until_step:
        penalty += 0.1
      return min(0.36, penalty)
    if self._same_decision_family(current_signature, action_signature):
      return 0.0

    penalty = 0.06
    current_family = current_signature.get("intent_family")
    new_family = action_signature.get("intent_family")
    if self.curr_step is not None and self.decision_commit_until_step is not None and self.curr_step < self.decision_commit_until_step:
      penalty += 0.12
    if current_family in {"work", "study", "leisure", "acquire_resource"}:
      penalty += 0.05
    if current_family in {"restore_satiety", "restore_stamina"}:
      penalty += 0.12
    if new_family == "communication" and current_family not in {"communication", "leisure"}:
      penalty += 0.04
    return min(0.32, max(0.0, penalty))


  def should_hold_after_recent_consume(self, within_steps=2, satiety_floor=40.0):
    signature = self.recent_completed_action_signature or {}
    if signature.get("intent_family") != "restore_satiety":
      return False
    if signature.get("skill_id") != "consume":
      return False
    if self.curr_step is None or self.recent_completed_action_step is None:
      return False
    if self.curr_step - self.recent_completed_action_step > within_steps:
      return False
    return self.satiety >= satiety_floor


  def has_active_plan(self):
    return bool(self.act_address or self.act_command or self.planned_path)


  def is_moving_to_action(self):
    return bool(self.planned_path)


  def is_resolving_physiological_need(self, need_family):
    signature = self.get_active_decision_signature() or {}
    current_family = signature.get("intent_family")
    if need_family == "restore_satiety":
      return current_family in {"restore_satiety", "acquire_resource"}
    if need_family == "restore_stamina":
      return current_family == "restore_stamina"
    return current_family == need_family


  def should_defer_social_interrupts(self):
    if not self.is_moving_to_action():
      return False
    signature = self.get_active_decision_signature() or {}
    family = signature.get("intent_family")
    if family not in {"restore_satiety", "restore_stamina"}:
      return False
    if self.curr_step is None or self.decision_commit_until_step is None:
      return True
    return self.curr_step < self.decision_commit_until_step


  def should_interrupt_for_physiological_crisis(self):
    needs_satiety = self.satiety < 30.0
    needs_stamina = self.stamina < 30.0
    if not (needs_satiety or needs_stamina):
      return False

    if needs_satiety and needs_stamina:
      return not (
        self.is_resolving_physiological_need("restore_satiety")
        or self.is_resolving_physiological_need("restore_stamina")
      )
    if needs_satiety:
      return not self.is_resolving_physiological_need("restore_satiety")
    if needs_stamina:
      return not self.is_resolving_physiological_need("restore_stamina")
    return False


  def remember_pending_interrupt(self, reason, source="system", payload=None):
    self.pending_interrupt = {
      "reason": reason,
      "source": source,
      "payload": payload or {},
      "curr_step": self.curr_step,
      "active_signature": self.get_active_decision_signature(),
    }
    append_debug_log(
      "decision_stability.jsonl",
      {
        "persona": self.name,
        "event": "interrupt_pending",
        "curr_step": self.curr_step,
        "reason": reason,
        "source": source,
        "payload": payload or {},
        "active_signature": self.get_active_decision_signature(),
      }
    )


  def _snapshot_current_action(self):
    signature = self.get_active_decision_signature()
    if not (signature and self.has_active_plan()):
      return None
    return {
      "act_address": _normalize_action_address(self.act_address),
      "act_duration": self.act_duration,
      "act_description": self.act_description,
      "act_pronunciatio": self.act_pronunciatio,
      "act_event": list(self.act_event) if isinstance(self.act_event, tuple) else self.act_event,
      "act_command": self.act_command,
      "act_obj_description": self.act_obj_description,
      "act_obj_pronunciatio": self.act_obj_pronunciatio,
      "act_obj_event": list(self.act_obj_event) if isinstance(self.act_obj_event, tuple) else self.act_obj_event,
      "chatting_with": self.chatting_with,
      "chat": self.chat,
      "chatting_with_buffer": self.chatting_with_buffer,
      "chatting_end_time": (
        self.chatting_end_time.strftime("%B %d, %Y, %H:%M:%S")
        if self.chatting_end_time else None
      ),
      "signature": signature,
      "planned_path": self.planned_path,
    }


  def clear_current_action(self, keep_last_desc=False):
    if keep_last_desc and self.act_description:
      self.last_action_desc = self.act_description
    self.release_execution_state(phase="cleared")


  def _snapshot_execution_payload(self, phase=None, failure=None):
    signature = self.get_active_decision_signature()
    existing = self.active_execution_state or {}
    state_id = existing.get("id")
    if not state_id:
      skill = (signature or {}).get("skill_id") or "unknown"
      target = (signature or {}).get("target") or "none"
      state_id = f"{self.name}-{self.curr_step}-{skill}-{target}"
    started_step = existing.get("started_step")
    if started_step is None:
      started_step = self.curr_step
    return {
      "id": state_id,
      "phase": phase or existing.get("phase") or "planned",
      "address": _normalize_action_address(self.act_address),
      "command": self.act_command,
      "description": self.act_description,
      "event": list(self.act_event) if isinstance(self.act_event, tuple) else self.act_event,
      "path": list(self.planned_path or []),
      "path_set": bool(self.act_path_set),
      "signature": signature,
      "started_step": started_step,
      "updated_step": self.curr_step,
      "failure": failure,
    }


  def begin_execution_state(self, phase="planned"):
    self.active_execution_state = None
    self.active_execution_state = self._snapshot_execution_payload(phase=phase)
    append_debug_log(
      "decision_stability.jsonl",
      {
        "persona": self.name,
        "event": "execution_state_begin",
        "curr_step": self.curr_step,
        "state": self.active_execution_state,
      }
    )
    return self.active_execution_state


  def update_execution_state(self, phase=None, failure=None):
    if not self.active_execution_state and not self.has_active_plan():
      return None
    self.active_execution_state = self._snapshot_execution_payload(phase=phase, failure=failure)
    append_debug_log(
      "decision_stability.jsonl",
      {
        "persona": self.name,
        "event": "execution_state_update",
        "curr_step": self.curr_step,
        "state": self.active_execution_state,
      }
    )
    return self.active_execution_state


  def release_execution_state(self, phase="completed", failure=None):
    if self.has_active_plan() or self.active_execution_state:
      self.active_execution_state = self._snapshot_execution_payload(phase=phase, failure=failure)
      append_debug_log(
        "decision_stability.jsonl",
        {
          "persona": self.name,
          "event": "execution_state_release",
          "curr_step": self.curr_step,
          "state": self.active_execution_state,
        }
      )
    self.planned_path = []
    self.act_path_set = False
    self.chatting_with = None
    self.chat = None
    self.chatting_end_time = None
    self.act_address = None
    self.act_description = None
    self.act_command = None
    self.act_event = None
    self.act_obj_description = None
    self.act_obj_pronunciatio = None
    self.act_obj_event = (None, None, None)


  def complete_execution(self):
    self.release_execution_state(phase="completed")


  def fail_execution(self, reason, payload=None):
    self.release_execution_state(
      phase="failed",
      failure={
        "reason": reason,
        "payload": payload or {},
      },
    )


  def interrupt_execution(self, reason, payload=None):
    self.release_execution_state(
      phase="interrupted",
      failure={
        "reason": reason,
        "payload": payload or {},
      },
    )


  def note_navigation_failure(self, target=None, target_address=None, reason="path_not_found", payload=None):
    self.navigation_failure = {
      "target": target,
      "target_address": target_address,
      "reason": reason,
      "payload": payload or {},
      "curr_tile": list(self.curr_tile) if isinstance(self.curr_tile, (list, tuple)) else self.curr_tile,
      "curr_step": self.curr_step,
    }
    self.last_action_observation = {
      "kind": "execution_result",
      "result": "failed",
      "target": target,
      "target_address": target_address,
      "reason": reason,
      "payload": payload or {},
      "curr_tile": list(self.curr_tile) if isinstance(self.curr_tile, (list, tuple)) else self.curr_tile,
      "curr_step": self.curr_step,
    }


  def get_recent_navigation_failure(self, max_age_steps=6):
    failure = self.navigation_failure or {}
    if not failure:
      return None
    failed_step = failure.get("curr_step")
    if self.curr_step is None or failed_step is None:
      return failure
    if self.curr_step - failed_step > max_age_steps:
      return None
    return failure


  def get_recent_invalid_targets(self, max_age_steps=6):
    """Return recently failed targets that are forbidden for the next step."""
    failure = self.get_recent_navigation_failure(max_age_steps=max_age_steps)
    if not failure:
      return []
    target = str(failure.get("target") or "").strip()
    if not target:
      return []
    return [target]


  def clear_navigation_failure(self):
    self.navigation_failure = None


  def get_recent_action_observation(self, max_age_steps=6):
    observation = self.last_action_observation or {}
    if not observation:
      return None
    observed_step = observation.get("curr_step")
    if self.curr_step is None or observed_step is None:
      return observation
    if self.curr_step - observed_step > max_age_steps:
      return None
    return observation


  def suspend_current_action(self, reason, source="system"):
    snapshot = self._snapshot_current_action()
    if not snapshot:
      return False
    self.suspended_action = snapshot
    self.suspended_action_step = self.curr_step
    append_debug_log(
      "decision_stability.jsonl",
      {
        "persona": self.name,
        "event": "plan_suspended",
        "curr_step": self.curr_step,
        "reason": reason,
        "source": source,
        "signature": snapshot.get("signature"),
        "act_description": snapshot.get("act_description"),
      }
    )
    return True


  def should_resume_suspended_action(self, max_age_steps=12):
    snapshot = self.suspended_action or {}
    signature = snapshot.get("signature") or {}
    if not signature:
      return False
    if self.has_active_plan():
      return False
    if self.curr_step is not None and self.suspended_action_step is not None:
      if self.curr_step - self.suspended_action_step > max_age_steps:
        return False
    if self.satiety < 30.0 and signature.get("intent_family") not in {"restore_satiety", "acquire_resource"}:
      return False
    if self.stamina < 30.0 and signature.get("intent_family") != "restore_stamina":
      return False
    return True


  def resume_suspended_action(self):
    snapshot = self.suspended_action or {}
    if not snapshot:
      return False
    self.act_address = _normalize_action_address(snapshot.get("act_address"))
    self.act_duration = snapshot.get("act_duration")
    self.act_description = snapshot.get("act_description")
    self.act_pronunciatio = snapshot.get("act_pronunciatio")
    act_event = snapshot.get("act_event")
    self.act_event = tuple(act_event) if isinstance(act_event, list) else act_event
    self.act_command = snapshot.get("act_command")
    self.act_obj_description = snapshot.get("act_obj_description")
    self.act_obj_pronunciatio = snapshot.get("act_obj_pronunciatio")
    act_obj_event = snapshot.get("act_obj_event")
    self.act_obj_event = tuple(act_obj_event) if isinstance(act_obj_event, list) else act_obj_event
    self.chatting_with = snapshot.get("chatting_with")
    self.chat = snapshot.get("chat")
    self.chatting_with_buffer = snapshot.get("chatting_with_buffer") or {}
    chatting_end_time = snapshot.get("chatting_end_time")
    self.chatting_end_time = (
      datetime.datetime.strptime(chatting_end_time, "%B %d, %Y, %H:%M:%S")
      if chatting_end_time else None
    )
    # Always force path recalculation from the current tile instead of trusting a stale path.
    self.planned_path = []
    self.act_path_set = False
    self.act_start_time = self.curr_time
    self.last_decision_signature = snapshot.get("signature")
    self.last_decision_reason = self.act_description
    self.decision_commit_until_step = self._next_commit_window_step(snapshot.get("signature"))
    append_debug_log(
      "decision_stability.jsonl",
      {
        "persona": self.name,
        "event": "plan_resumed",
        "curr_step": self.curr_step,
        "signature": snapshot.get("signature"),
        "act_description": self.act_description,
      }
    )
    self.suspended_action = None
    self.suspended_action_step = None
    self.pending_interrupt = None
    self.navigation_failure = None
    return True


  def mark_action_completed(self, action_command=None, action_event=None, action_description=None, action_address=None):
    signature = build_decision_signature(
      action_command or self.act_command,
      action_event=action_event or self.act_event,
      action_description=action_description or self.act_description,
      action_address=action_address or self.act_address,
    )
    self.recent_completed_action_signature = signature
    self.recent_completed_action_step = self.curr_step
    self.last_action_observation = {
      "kind": "execution_result",
      "result": "completed",
      "target": signature.get("target"),
      "target_address": action_address or self.act_address,
      "skill_id": signature.get("skill_id"),
      "action_description": action_description or self.act_description,
      "curr_step": self.curr_step,
    }
    append_debug_log(
      "decision_stability.jsonl",
      {
        "persona": self.name,
        "event": "action_completed",
        "curr_step": self.curr_step,
        "signature": signature,
      }
    )


  def act_time_str(self): 
    """
    Returns a string output of the current time. 

    INPUT
      None
    OUTPUT 
      A string output of the current time.
    EXAMPLE STR OUTPUT
      "14:05 P.M."
    """
    return self.act_start_time.strftime("%H:%M %p")


  def act_check_finished(self): 
    """
    Checks whether the self.Action instance has finished.  

    INPUT
      curr_datetime: Current time. If current time is later than the action's
                     start time + its duration, then the action has finished. 
    OUTPUT 
      Boolean [True]: Action has finished.
      Boolean [False]: Action has not finished and is still ongoing.
    """
    if not self.act_address: 
      return True
    if self.curr_time is None:
      return False
      
    if self.chatting_with and self.chatting_with != "<creator>": 
      end_time = self.chatting_end_time
    else: 
      x = self.act_start_time
      if x is None:
        return False
      if x.second != 0: 
        x = x.replace(second=0)
        x = (x + datetime.timedelta(minutes=1))
      end_time = (x + datetime.timedelta(minutes=self.act_duration))
    if end_time is None:
      return False

    return self.curr_time >= end_time


  def act_summarize(self):
    """
    Summarize the current action as a dictionary. 

    INPUT
      None
    OUTPUT 
      ret: A human readable summary of the action.
    """
    exp = dict()
    exp["persona"] = self.name
    exp["address"] = self.act_address
    exp["start_datetime"] = self.act_start_time
    exp["duration"] = self.act_duration
    exp["description"] = self.act_description
    exp["pronunciatio"] = self.act_pronunciatio
    return exp


  def act_summary_str(self):
    """
    Returns a string summary of the current action. Meant to be 
    human-readable.

    INPUT
      None
    OUTPUT 
      ret: A human readable summary of the action.
    """
    start_datetime_str = self.act_start_time.strftime("%A %B %d -- %H:%M %p")
    ret = f"[{start_datetime_str}]\n"
    ret += f"Activity: {self.name} is {self.act_description}\n"
    ret += f"Address: {self.act_address}\n"
    ret += f"Duration in minutes (e.g., x min): {str(self.act_duration)} min\n"
    return ret


  def get_str_daily_schedule_summary(self): 
    ret = ""
    curr_min_sum = 0
    for row in self.f_daily_schedule: 
      curr_min_sum += row[1]
      hour = int(curr_min_sum/60)
      minute = curr_min_sum%60
      ret += f"{hour:02}:{minute:02} || {row[0]}\n"
    return ret


  def get_str_daily_schedule_hourly_org_summary(self): 
    ret = ""
    curr_min_sum = 0
    for row in self.f_daily_schedule_hourly_org: 
      curr_min_sum += row[1]
      hour = int(curr_min_sum/60)
      minute = curr_min_sum%60
      ret += f"{hour:02}:{minute:02} || {row[0]}\n"
    return ret
