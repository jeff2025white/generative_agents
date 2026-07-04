"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: persona.py
Description: Defines the Persona class that powers the agents in Reverie. 

Note (May 1, 2023) -- this is effectively GenerativeAgent class. Persona was
the term we used internally back in 2022, taking from our Social Simulacra 
paper.
"""
import math
import sys
import datetime
import random
import time
sys.path.append('../')

from global_methods import *

from persona.memory_structures.spatial_memory import *
from persona.memory_structures.associative_memory import *
from persona.memory_structures.scratch import *

from persona.cognitive_modules.perceive import *
from persona.cognitive_modules.retrieve import *
from persona.cognitive_modules.plan import *
from persona.cognitive_modules.reflect import *
from persona.cognitive_modules.execute import *
from persona.cognitive_modules.converse import *
from persona.cognitive_modules.debug_log import append_debug_log
from persona.cognitive_modules.social_dialogue_log import clear_social_dialogue_state, log_social_dialogue
from persona.cognitive_modules.social_trigger import should_run_periodic_social_scan

class Persona: 
  def __init__(self, name, folder_mem_saved=False):
    # PERSONA BASE STATE 
    # <name> is the full name of the persona. This is a unique identifier for
    # the persona within Reverie. 
    self.name = name
    self.world_resource_state = None

    # PERSONA MEMORY 
    # If there is already memory in folder_mem_saved, we load that. Otherwise,
    # we create new memory instances. 
    # <s_mem> is the persona's spatial memory. 
    f_s_mem_saved = f"{folder_mem_saved}/bootstrap_memory/spatial_memory.json"
    self.s_mem = MemoryTree(f_s_mem_saved)
    # <s_mem> is the persona's associative memory. 
    f_a_mem_saved = f"{folder_mem_saved}/bootstrap_memory/associative_memory"
    self.a_mem = AssociativeMemory(f_a_mem_saved)
    # <scratch> is the persona's scratch (short term memory) space. 
    scratch_saved = f"{folder_mem_saved}/bootstrap_memory/scratch.json"
    self.scratch = Scratch(scratch_saved)


  def save(self,
           save_folder,
           save_spatial_memory=True,
           save_associative_memory=True,
           save_scratch=True): 
    """
    Save persona's current state (i.e., memory). 

    INPUT: 
      save_folder: The folder where we wil be saving our persona's state. 
    OUTPUT: 
      None
    """
    # Spatial memory contains a tree in a json format. 
    # e.g., {"double studio": 
    #         {"double studio": 
    #           {"bedroom 2": 
    #             ["painting", "easel", "closet", "bed"]}}}
    if save_spatial_memory:
      f_s_mem = f"{save_folder}/spatial_memory.json"
      self.s_mem.save(f_s_mem)
    
    # Associative memory contains a csv with the following rows: 
    # [event.type, event.created, event.expiration, s, p, o]
    # e.g., event,2022-10-23 00:00:00,,Isabella Rodriguez,is,idle
    if save_associative_memory:
      f_a_mem = f"{save_folder}/associative_memory"
      self.a_mem.save(f_a_mem)

    # Scratch contains non-permanent data associated with the persona. When 
    # it is saved, it takes a json form. When we load it, we move the values
    # to Python variables. 
    if save_scratch:
      f_scratch = f"{save_folder}/scratch.json"
      self.scratch.save(f_scratch)


  def get_step_debug_snapshot(self):
    """
    Return a compact, JSON-serializable snapshot for step timing logs.
    """
    active_signature = self.scratch.get_active_decision_signature()
    planned_path = self.scratch.planned_path or []
    return {
      "satiety": round(float(self.scratch.satiety), 3),
      "stamina": round(float(self.scratch.stamina), 3),
      "active_signature": active_signature,
      "planned_path_len": len(planned_path),
    }


  def perceive(self, maze):
    """
    This function takes the current maze, and returns events that are 
    happening around the persona. Importantly, perceive is guided by 
    two key hyper-parameter for the  persona: 1) att_bandwidth, and 
    2) retention. 

    First, <att_bandwidth> determines the number of nearby events that the 
    persona can perceive. Say there are 10 events that are within the vision
    radius for the persona -- perceiving all 10 might be too much. So, the 
    persona perceives the closest att_bandwidth number of events in case there
    are too many events. 

    Second, the persona does not want to perceive and think about the same 
    event at each time step. That's where <retention> comes in -- there is 
    temporal order to what the persona remembers. So if the persona's memory
    contains the current surrounding events that happened within the most 
    recent retention, there is no need to perceive that again. xx

    INPUT: 
      maze: Current <Maze> instance of the world. 
    OUTPUT: 
      a list of <ConceptNode> that are perceived and new. 
        See associative_memory.py -- but to get you a sense of what it 
        receives as its input: "s, p, o, desc, persona.scratch.curr_time"
    """
    return perceive(self, maze)


  def retrieve(self, perceived):
    """
    This function takes the events that are perceived by the persona as input
    and returns a set of related events and thoughts that the persona would 
    need to consider as context when planning. 

    INPUT: 
      perceive: a list of <ConceptNode> that are perceived and new.  
    OUTPUT: 
      retrieved: dictionary of dictionary. The first layer specifies an event,
                 while the latter layer specifies the "curr_event", "events", 
                 and "thoughts" that are relevant.
    """
    return retrieve(self, perceived)


  def plan(self, maze, personas, new_day, retrieved):
    """
    Main cognitive function of the chain. It takes the retrieved memory and 
    perception, as well as the maze and the first day state to conduct both 
    the long term and short term planning for the persona. 

    INPUT: 
      maze: Current <Maze> instance of the world. 
      personas: A dictionary that contains all persona names as keys, and the 
                Persona instance as values. 
      new_day: This can take one of the three values. 
        1) <Boolean> False -- It is not a "new day" cycle (if it is, we would
           need to call the long term planning sequence for the persona). 
        2) <String> "First day" -- It is literally the start of a simulation,
           so not only is it a new day, but also it is the first day. 
        2) <String> "New day" -- It is a new day. 
      retrieved: dictionary of dictionary. The first layer specifies an event,
                 while the latter layer specifies the "curr_event", "events", 
                 and "thoughts" that are relevant.
    OUTPUT 
      The target action address of the persona (persona.scratch.act_address).
    """
    return plan(self, maze, personas, new_day, retrieved)


  def execute(self, maze, personas, plan):
    """
    This function takes the agent's current plan and outputs a concrete 
    execution (what object to use, and what tile to travel to). 

    INPUT: 
      maze: Current <Maze> instance of the world. 
      personas: A dictionary that contains all persona names as keys, and the 
                Persona instance as values. 
      plan: The target action address of the persona  
            (persona.scratch.act_address).
    OUTPUT: 
      execution: A triple set that contains the following components: 
        <next_tile> is a x,y coordinate. e.g., (58, 9)
        <pronunciatio> is an emoji.
        <description> is a string description of the movement. e.g., 
        writing her next novel (editing her novel) 
        @ double studio:double studio:common room:sofa
    """
    return execute(self, maze, personas, plan)


  def reflect(self):
    """
    Reviews the persona's memory and create new thoughts based on it. 

    INPUT: 
      None
    OUTPUT: 
      None
    """
    reflect(self)


  def move(self, maze, personas, curr_tile, curr_time, step=None):
    """
    This is the main cognitive function where our main sequence is called. 

    INPUT: 
      maze: The Maze class of the current world. 
      personas: A dictionary that contains all persona names as keys, and the 
                Persona instance as values. 
      curr_tile: A tuple that designates the persona's current tile location 
                 in (row, col) form. e.g., (58, 39)
      curr_time: datetime instance that indicates the game's current time. 
      step: Current simulation step number.
    OUTPUT: 
      execution: A triple set that contains the following components: 
        <next_tile> is a x,y coordinate. e.g., (58, 9)
        <pronunciatio> is an emoji.
        <description> is a string description of the movement. e.g., 
        writing her next novel (editing her novel) 
        @ double studio:double studio:common room:sofa
    """
    # Updating persona's scratch memory with <curr_tile>. 
    move_started_at = time.perf_counter()
    timings_ms = {}
    self.scratch.curr_tile = curr_tile
    self.scratch.curr_step = step

    # 死亡拦截器：如果生命值归零，则角色“已死”，原地冻结且不参与任何认知计算（ReAct / step 运算）
    if self.scratch.health <= 0.0:
      addr = self.scratch.act_address if self.scratch.act_address else self.scratch.living_area
      self.scratch.act_description = "已死"
      self.scratch.planned_path = []
      self.scratch.act_path_set = False
      self.scratch.chat = None
      self.scratch.chatting_with = None
      step_info = {
        "mode": "dead",
        "total_ms": round((time.perf_counter() - move_started_at) * 1000.0, 3),
        "timings_ms": {},
        "destination": None,
        "remaining_path_len": 0,
      }
      return curr_tile, "💀", f"已死 @ {addr}", step_info

    # We figure out whether the persona started a new day, and if it is a new
    # day, whether it is the very first day of the simulation. This is 
    # important because we set up the persona's long term plan at the start of
    # a new day. 
    new_day = False
    if not self.scratch.curr_time: 
      new_day = "First day"
    elif (self.scratch.curr_time.strftime('%A %B %d')
          != curr_time.strftime('%A %B %d')):
      new_day = "New day"
    self.scratch.curr_time = curr_time

    # [OPTIMIZATION] Fast path: if the persona is mid-walk on a planned path
    # and it's not a new day, continue the existing plan unless a hard
    # physiological interrupt says the current plan is no longer acceptable.
    if self.scratch.planned_path and not new_day:
      if not self.scratch.should_interrupt_for_physiological_crisis():
        fast_path_scan_started_at = time.perf_counter()
        if should_run_periodic_social_scan(self):
          perceived = self.perceive(maze)
          retrieved = self.retrieve(perceived)
          self.scratch.last_retrieved_memories = retrieved
          plan_social_reaction(self, maze, personas, retrieved)
        timings_ms["fast_path_social_scan"] = round((time.perf_counter() - fast_path_scan_started_at) * 1000.0, 3)
        execute_started_at = time.perf_counter()
        result = self.execute(maze, personas, None)
        timings_ms["execute"] = round((time.perf_counter() - execute_started_at) * 1000.0, 3)
        total_ms = round((time.perf_counter() - move_started_at) * 1000.0, 3)
        step_info = {
          "mode": "fast_path",
          "total_ms": total_ms,
          "timings_ms": timings_ms,
          "destination": self.scratch.act_address,
          "remaining_path_len": len(self.scratch.planned_path),
        }
        append_debug_log(
          "step_timing.jsonl",
          {
            "event": "persona_move_timing",
            "persona": self.name,
            "curr_step": self.scratch.curr_step,
            "mode": "fast_path",
            "total_ms": total_ms,
            "timings_ms": timings_ms,
            "state": self.get_step_debug_snapshot(),
          }
        )
        ret_tile, ret_pron, ret_desc = result
        return ret_tile, ret_pron, ret_desc, step_info

    if self.scratch.should_interrupt_for_physiological_crisis() and self.scratch.has_active_plan():
      print(f"[{self.name}] 生理危机打断！(饱食度: {self.scratch.satiety:.1f}, 精力: {self.scratch.stamina:.1f}). 清理当前路径与动作，紧急求生。")
      if getattr(self.scratch, "social_dialogue_id", None):
        log_social_dialogue(
          self,
          "failure",
          "dialogue_aborted",
          payload={
            "reason": "physiological_interrupt",
            "satiety": self.scratch.satiety,
            "stamina": self.scratch.stamina,
            "act_description": self.scratch.act_description,
          },
        )
      self.scratch.suspend_current_action("physiological_crisis", source="move")
      self.scratch.last_action_desc = f"{self.scratch.act_description} (Interrupted due to physiological crisis)"
      self.scratch.clear_current_action()
      clear_social_dialogue_state(self)

    # Main cognitive sequence begins here. 
    perceive_started_at = time.perf_counter()
    perceived = self.perceive(maze)
    timings_ms["perceive"] = round((time.perf_counter() - perceive_started_at) * 1000.0, 3)
    retrieve_started_at = time.perf_counter()
    retrieved = self.retrieve(perceived)
    timings_ms["retrieve"] = round((time.perf_counter() - retrieve_started_at) * 1000.0, 3)
    self.scratch.last_retrieved_memories = retrieved
    plan_started_at = time.perf_counter()
    plan = self.plan(maze, personas, new_day, retrieved)
    timings_ms["plan"] = round((time.perf_counter() - plan_started_at) * 1000.0, 3)
    reflect_started_at = time.perf_counter()
    self.reflect()
    timings_ms["reflect"] = round((time.perf_counter() - reflect_started_at) * 1000.0, 3)

    # <execution> is a triple set that contains the following components: 
    # <next_tile> is a x,y coordinate. e.g., (58, 9)
    # <pronunciatio> is an emoji. e.g., "\ud83d\udca4"
    # <description> is a string description of the movement. e.g., 
    #   writing her next novel (editing her novel) 
    #   @ double studio:double studio:common room:sofa
    execute_started_at = time.perf_counter()
    result = self.execute(maze, personas, plan)
    timings_ms["execute"] = round((time.perf_counter() - execute_started_at) * 1000.0, 3)
    total_ms = round((time.perf_counter() - move_started_at) * 1000.0, 3)
    step_info = {
      "mode": "full_pipeline",
      "total_ms": total_ms,
      "timings_ms": timings_ms,
      "destination": self.scratch.act_address,
      "remaining_path_len": len(self.scratch.planned_path) if self.scratch.planned_path else 0,
    }
    append_debug_log(
      "step_timing.jsonl",
      {
        "event": "persona_move_timing",
        "persona": self.name,
        "curr_step": self.scratch.curr_step,
        "mode": "full_pipeline",
        "total_ms": total_ms,
        "timings_ms": timings_ms,
        "state": self.get_step_debug_snapshot(),
      }
    )
    ret_tile, ret_pron, ret_desc = result
    return ret_tile, ret_pron, ret_desc, step_info


  def open_convo_session(self, convo_mode): 
    open_convo_session(self, convo_mode)
    




























