"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: reverie.py
Description: This is the main program for running generative agent simulations
that defines the ReverieServer class. This class maintains and records all  
states related to the simulation. The primary mode of interaction for those  
running the simulation should be through the open_server function, which  
enables the simulator to input command-line prompts for running and saving  
the simulation, among other tasks.

Release note (June 14, 2023) -- Reverie implements the core simulation 
mechanism described in my paper entitled "Generative Agents: Interactive 
Simulacra of Human Behavior." If you are reading through these lines after 
having read the paper, you might notice that I use older terms to describe 
generative agents and their cognitive modules here. Most notably, I use the 
term "personas" to refer to generative agents, "associative memory" to refer 
to the memory stream, and "reverie" to refer to the overarching simulation 
framework.
"""
# python 3.10 compatibility monkey-patch for django 2.2
import collections
import collections.abc
collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping
collections.MutableMapping = collections.abc.MutableMapping
collections.Sequence = collections.abc.Sequence
collections.MutableSequence = collections.abc.MutableSequence

import json
import numpy
import datetime
import pickle
import time
import math
import os
import shutil
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from global_methods import *
from utils import *
from maze import *
from persona.persona import *
from persona.prompt_template.gpt_structure import save_cache_to_disk
import requests

##############################################################################
#                                  REVERIE                                   #
##############################################################################

class ReverieServer: 
  def __init__(self, 
               fork_sim_code,
               sim_code):
    # FORKING FROM A PRIOR SIMULATION:
    # <fork_sim_code> indicates the simulation we are forking from. 
    # Interestingly, all simulations must be forked from some initial 
    # simulation, where the first simulation is "hand-crafted".
    self.fork_sim_code = fork_sim_code
    fork_folder = f"{fs_storage}/{self.fork_sim_code}"

    # <sim_code> indicates our current simulation. The first step here is to 
    # copy everything that's in <fork_sim_code>, but edit its 
    # reverie/meta/json's fork variable. 
    self.sim_code = sim_code
    sim_folder = f"{fs_storage}/{self.sim_code}"
    if self.fork_sim_code != self.sim_code:
      copyanything(fork_folder, sim_folder)

    with open(f"{sim_folder}/reverie/meta.json") as json_file:  
      reverie_meta = json.load(json_file)

    with open(f"{sim_folder}/reverie/meta.json", "w") as outfile: 
      reverie_meta["fork_sim_code"] = fork_sim_code
      outfile.write(json.dumps(reverie_meta, indent=2))

    # LOADING REVERIE'S GLOBAL VARIABLES
    # The start datetime of the Reverie: 
    # <start_datetime> is the datetime instance for the start datetime of 
    # the Reverie instance. Once it is set, this is not really meant to 
    # change. It takes a string date in the following example form: 
    # "June 25, 2022"
    # e.g., ...strptime(June 25, 2022, "%B %d, %Y")
    self.start_time = datetime.datetime.strptime(
                        f"{reverie_meta['start_date']}, 00:00:00",  
                        "%B %d, %Y, %H:%M:%S")
    # <curr_time> is the datetime instance that indicates the game's current
    # time. This gets incremented by <sec_per_step> amount everytime the world
    # progresses (that is, everytime curr_env_file is recieved). 
    self.curr_time = datetime.datetime.strptime(reverie_meta['curr_time'], 
                                                "%B %d, %Y, %H:%M:%S")
    # <sec_per_step> denotes the number of seconds in game time that each 
    # step moves foward. 
    self.sec_per_step = reverie_meta['sec_per_step']
    
    # <maze> is the main Maze instance. Note that we pass in the maze_name
    # (e.g., "double_studio") to instantiate Maze. 
    # e.g., Maze("double_studio")
    self.maze = Maze(reverie_meta['maze_name'])
    
    # <step> denotes the number of steps that our game has taken. A step here
    # literally translates to the number of moves our personas made in terms
    # of the number of tiles. 
    self.step = reverie_meta['step']

    # SETTING UP PERSONAS IN REVERIE
    # <personas> is a dictionary that takes the persona's full name as its 
    # keys, and the actual persona instance as its values.
    # This dictionary is meant to keep track of all personas who are part of
    # the Reverie instance. 
    # e.g., ["Isabella Rodriguez"] = Persona("Isabella Rodriguezs")
    self.personas = dict()
    # <personas_tile> is a dictionary that contains the tile location of
    # the personas (!-> NOT px tile, but the actual tile coordinate).
    # The tile take the form of a set, (row, col). 
    # e.g., ["Isabella Rodriguez"] = (58, 39)
    self.personas_tile = dict()
    
    # # <persona_convo_match> is a dictionary that describes which of the two
    # # personas are talking to each other. It takes a key of a persona's full
    # # name, and value of another persona's full name who is talking to the 
    # # original persona. 
    # # e.g., dict["Isabella Rodriguez"] = ["Maria Lopez"]
    # self.persona_convo_match = dict()
    # # <persona_convo> contains the actual content of the conversations. It
    # # takes as keys, a pair of persona names, and val of a string convo. 
    # # Note that the key pairs are *ordered alphabetically*. 
    # # e.g., dict[("Adam Abraham", "Zane Xu")] = "Adam: baba \n Zane:..."
    # self.persona_convo = dict()

    # Loading in all personas. 
    init_env_file = f"{sim_folder}/environment/{str(self.step)}.json"
    init_env = json.load(open(init_env_file))
    for persona_name in reverie_meta['persona_names']: 
      persona_folder = f"{sim_folder}/personas/{persona_name}"
      p_x = init_env[persona_name]["x"]
      p_y = init_env[persona_name]["y"]
      curr_persona = Persona(persona_name, persona_folder)

      self.personas[persona_name] = curr_persona
      self.personas_tile[persona_name] = (p_x, p_y)
      self.maze.tiles[p_y][p_x]["events"].add(curr_persona.scratch
                                              .get_curr_event_and_desc())

    # REVERIE SETTINGS PARAMETERS:  
    # <server_sleep> denotes the amount of time that our while loop rests each
    # cycle; this is to not kill our machine. 
    self.server_sleep = 0.1

    # SIGNALING THE FRONTEND SERVER: 
    # curr_sim_code.json contains the current simulation code, and
    # curr_step.json contains the current step of the simulation. These are 
    # used to communicate the code and step information to the frontend. 
    # Note that step file is removed as soon as the frontend opens up the 
    # simulation. 
    try:
      requests.post("http://127.0.0.1:8000/api/init_sim/", json={
        "sim_code": self.sim_code,
        "step": self.step
      }, timeout=5)
    except Exception as e:
      print(f"Warning: Failed to initialize simulation on frontend API: {e}")

    curr_sim_code = dict()
    curr_sim_code["sim_code"] = self.sim_code
    with open(f"{fs_temp_storage}/curr_sim_code.json", "w") as outfile: 
      outfile.write(json.dumps(curr_sim_code, indent=2))
    
    curr_step = dict()
    curr_step["step"] = self.step
    with open(f"{fs_temp_storage}/curr_step.json", "w") as outfile: 
      outfile.write(json.dumps(curr_step, indent=2))


  def save(self): 
    """
    Save all Reverie progress -- this includes Reverie's global state as well
    as all the personas.  

    INPUT
      None
    OUTPUT 
      None
      * Saves all relevant data to the designated memory directory
    """
    # <sim_folder> points to the current simulation folder.
    sim_folder = f"{fs_storage}/{self.sim_code}"

    # Save Reverie meta information.
    reverie_meta = dict() 
    reverie_meta["fork_sim_code"] = self.fork_sim_code
    reverie_meta["start_date"] = self.start_time.strftime("%B %d, %Y")
    reverie_meta["curr_time"] = self.curr_time.strftime("%B %d, %Y, %H:%M:%S")
    reverie_meta["sec_per_step"] = self.sec_per_step
    reverie_meta["maze_name"] = self.maze.maze_name
    reverie_meta["persona_names"] = list(self.personas.keys())
    reverie_meta["step"] = self.step
    reverie_meta_f = f"{sim_folder}/reverie/meta.json"
    with open(reverie_meta_f, "w") as outfile: 
      outfile.write(json.dumps(reverie_meta, indent=2))

    # Save the personas.
    for persona_name, persona in self.personas.items(): 
      save_folder = f"{sim_folder}/personas/{persona_name}/bootstrap_memory"
      persona.save(save_folder)

    # [OPTIMIZATION] Flush LLM prompt cache to disk on save
    save_cache_to_disk()


  def start_path_tester_server(self): 
    """
    Starts the path tester server. This is for generating the spatial memory
    that we need for bootstrapping a persona's state. 

    To use this, you need to open server and enter the path tester mode, and
    open the front-end side of the browser. 

    INPUT 
      None
    OUTPUT 
      None
      * Saves the spatial memory of the test agent to the path_tester_env.json
        of the temp storage. 
    """
    def print_tree(tree): 
      def _print_tree(tree, depth):
        dash = " >" * depth

        if type(tree) == type(list()): 
          if tree:
            print (dash, tree)
          return 

        for key, val in tree.items(): 
          if key: 
            print (dash, key)
          _print_tree(val, depth+1)
      
      _print_tree(tree, 0)

    # <curr_vision> is the vision radius of the test agent. Recommend 8 as 
    # our default. 
    curr_vision = 8
    # <s_mem> is our test spatial memory. 
    s_mem = dict()

    # The main while loop for the test agent. 
    while (True): 
      try: 
        curr_dict = {}
        tester_file = fs_temp_storage + "/path_tester_env.json"
        if check_if_file_exists(tester_file): 
          with open(tester_file) as json_file: 
            curr_dict = json.load(json_file)
            os.remove(tester_file)
          
          # Current camera location
          curr_sts = self.maze.sq_tile_size
          curr_camera = (int(math.ceil(curr_dict["x"]/curr_sts)), 
                         int(math.ceil(curr_dict["y"]/curr_sts))+1)
          curr_tile_det = self.maze.access_tile(curr_camera)

          # Initiating the s_mem
          world = curr_tile_det["world"]
          if curr_tile_det["world"] not in s_mem: 
            s_mem[world] = dict()

          # Iterating throughn the nearby tiles.
          nearby_tiles = self.maze.get_nearby_tiles(curr_camera, curr_vision)
          for i in nearby_tiles: 
            i_det = self.maze.access_tile(i)
            if (curr_tile_det["sector"] == i_det["sector"] 
                and curr_tile_det["arena"] == i_det["arena"]): 
              if i_det["sector"] != "": 
                if i_det["sector"] not in s_mem[world]: 
                  s_mem[world][i_det["sector"]] = dict()
              if i_det["arena"] != "": 
                if i_det["arena"] not in s_mem[world][i_det["sector"]]: 
                  s_mem[world][i_det["sector"]][i_det["arena"]] = list()
              if i_det["game_object"] != "": 
                if (i_det["game_object"] 
                    not in s_mem[world][i_det["sector"]][i_det["arena"]]):
                  s_mem[world][i_det["sector"]][i_det["arena"]] += [
                                                         i_det["game_object"]]

        # Incrementally outputting the s_mem and saving the json file. 
        print ("= " * 15)
        out_file = fs_temp_storage + "/path_tester_out.json"
        with open(out_file, "w") as outfile: 
          outfile.write(json.dumps(s_mem, indent=2))
        print_tree(s_mem)

      except:
        pass

      time.sleep(self.server_sleep * 10)


  def start_server(self, int_counter): 
    """
    The main backend server of Reverie. 
    This function retrieves the environment file from the frontend to 
    understand the state of the world, calls on each personas to make 
    decisions based on the world state, and saves their moves at certain step
    intervals. 
    INPUT
      int_counter: Integer value for the number of steps left for us to take
                   in this iteration. 
    OUTPUT 
      None
    """
    # <sim_folder> points to the current simulation folder.
    sim_folder = f"{fs_storage}/{self.sim_code}"

    # When a persona arrives at a game object, we give a unique event
    # to that object. 
    # e.g., ('double studio[...]:bed', 'is', 'unmade', 'unmade')
    # Later on, before this cycle ends, we need to return that to its 
    # initial state, like this: 
    # e.g., ('double studio[...]:bed', None, None, None)
    # So we need to keep track of which event we added. 
    # <game_obj_cleanup> is used for that. 
    game_obj_cleanup = dict()

    # The main while loop of Reverie. 
    while (True): 
      # Done with this iteration if <int_counter> reaches 0. 
      if int_counter == 0: 
        break

      step_start_time = time.time()

      # Chat active pause mechanism removed.

      env_retrieved = False
      # We check the environment state via Django HTTP API (Option 3 API Gateway)
      try:
        response = requests.get(f"http://127.0.0.1:8000/api/get_environment/?sim_code={self.sim_code}&step={self.step}", timeout=5)
        if response.status_code == 200:
          new_env = response.json()
          env_retrieved = True
      except Exception as e:
        pass

      # Heartbeat lock step sync: check if frontend browser is active
      frontend_active = False
      frontend_active_file = f"{fs_temp_storage}/frontend_active_{self.sim_code}.json"
      if os.path.exists(frontend_active_file):
        try:
          with open(frontend_active_file, "r") as f:
            status = json.load(f)
            if time.time() - status.get("last_active", 0) < 10.0:
              frontend_active = True
        except Exception:
          pass

      # If frontend is active and we don't have the environment yet, wait for the frontend to post it
      if frontend_active and not env_retrieved:
        print(f"[Backend] Frontend is active. Waiting for frontend to advance to step {self.step}...")
        while not env_retrieved:
          # Chat active pause mechanism removed.
          
          # Check if frontend heartbeat expired (closed or stopped)
          try:
            with open(frontend_active_file, "r") as f:
              status = json.load(f)
              if time.time() - status.get("last_active", 0) >= 10.0:
                print(f"[Backend] Frontend heartbeat expired (inactive) during step wait. Fallback to independent run.")
                break
          except Exception:
            pass

          try:
            response = requests.get(f"http://127.0.0.1:8000/api/get_environment/?sim_code={self.sim_code}&step={self.step}", timeout=5)
            if response.status_code == 200:
              new_env = response.json()
              env_retrieved = True
              print(f"[Backend] Received environment for step {self.step} from frontend.")
              break
          except Exception:
            pass

          time.sleep(0.5)

      if not env_retrieved:
        # Fallback to local files for backward compatibility
        curr_env_file = f"{sim_folder}/environment/{self.step}.json"
        if check_if_file_exists(curr_env_file):
          try: 
            with open(curr_env_file) as json_file:
              new_env = json.load(json_file)
              env_retrieved = True
          except: 
            pass

      if not env_retrieved:
        # Decouple: If no environment is found (browser is closed/refreshing),
        # backend runs independently by using its own tracked persona tiles.
        new_env = {}
        for p_name, p_tile in self.personas_tile.items():
          new_env[p_name] = {"x": p_tile[0], "y": p_tile[1]}
        env_retrieved = True
        
        # Notify Django of this environment state so the database is updated
        try:
          requests.post("http://127.0.0.1:8000/process_environment/", json={
            "sim_code": self.sim_code,
            "step": self.step,
            "environment": new_env
          }, timeout=2)
        except Exception as post_err:
          pass
      
      if env_retrieved: 
          # Retrieve and inject user pending actions (chats/instructions)
          processed_ids = []
          try:
            response = requests.get(f"http://127.0.0.1:8000/api/get_pending_actions/?sim_code={self.sim_code}", timeout=5)
            if response.status_code == 200:
              pending_actions = response.json()
              if pending_actions:
                for action in pending_actions:
                  p_name = action["persona_name"]
                  a_type = action["action_type"]
                  content = action["content"]
                  action_id = action["id"]
                  
                  if p_name in self.personas:
                    p = self.personas[p_name]
                    print(f"=== [造物主沟通指令注入] {p.name} 接收到指令: {content} (类型: {a_type}) ===")
                    
                    target_str = json.dumps({
                      "id": action_id,
                      "action_type": a_type,
                      "content": content
                    })
                    
                    p.scratch.add_new_action(
                      f"<creator> {target_str}",
                      1,
                      "communicating with the Creator",
                      "👁️",
                      (p.name, "creator_comm", "creator"),
                      None,
                      None,
                      {},
                      None,
                      None,
                      None,
                      (None, None, None),
                      p.scratch.curr_time
                    )
                    # Reset pathing to take effect immediately
                    p.scratch.planned_path = []
                    p.scratch.act_path_set = False
                    processed_ids.append(action_id)
                  
                if processed_ids:
                  requests.post("http://127.0.0.1:8000/api/get_pending_actions/", json={"processed_ids": processed_ids}, timeout=5)
          except Exception as e:
            print(f"Warning: Failed to fetch/process pending actions: {e}")

          # This is where we go through <game_obj_cleanup> to clean up all 
          # object actions that were used in this cylce. 
          for key, val in game_obj_cleanup.items(): 
            # We turn all object actions to their blank form (with None). 
            self.maze.turn_event_from_tile_idle(key, val)
          # Then we initialize game_obj_cleanup for this cycle. 
          game_obj_cleanup = dict()

          # We first move our personas in the backend environment to match 
          # the frontend environment. 
          for persona_name, persona in self.personas.items(): 
            # <curr_tile> is the tile that the persona was at previously. 
            curr_tile = self.personas_tile[persona_name]
            # <new_tile> is the tile that the persona will move to right now,
            # during this cycle. 
            new_tile = (new_env[persona_name]["x"], 
                        new_env[persona_name]["y"])

            # We actually move the persona on the backend tile map here. 
            self.personas_tile[persona_name] = new_tile
            self.maze.remove_subject_events_from_tile(persona.name, curr_tile)
            self.maze.add_event_from_tile(persona.scratch
                                         .get_curr_event_and_desc(), new_tile)

            # Now, the persona will travel to get to their destination. *Once*
            # the persona gets there, we activate the object action.
            if not persona.scratch.planned_path: 
              # We add that new object action event to the backend tile map. 
              # At its creation, it is stored in the persona's backend. 
              game_obj_cleanup[persona.scratch
                               .get_curr_obj_event_and_desc()] = new_tile
              self.maze.add_event_from_tile(persona.scratch
                                     .get_curr_obj_event_and_desc(), new_tile)
              # We also need to remove the temporary blank action for the 
              # object that is currently taking the action. 
              blank = (persona.scratch.get_curr_obj_event_and_desc()[0], 
                       None, None, None)
              self.maze.remove_event_from_tile(blank, new_tile)

          # Apply metabolic decay and recovery for each persona per step
          for persona_name, persona in self.personas.items():
            # If already dead, freeze all values to 0.0 and bypass decay calculations
            if persona.scratch.health <= 0.0:
              persona.scratch.satiety = 0.0
              persona.scratch.stamina = 0.0
              persona.scratch.health = 0.0
              persona.scratch.mood = 0.0
              continue

            act_desc = persona.scratch.act_description.lower() if persona.scratch.act_description else ""
            
            # 1. 饱食度（Satiety）代谢
            if "sleeping" in act_desc or "sleep" in act_desc:
              persona.scratch.satiety = max(0.0, persona.scratch.satiety - 0.04)
            else:
              persona.scratch.satiety = max(0.0, persona.scratch.satiety - 0.08)
              
            # 2. 精力（Stamina）消耗与恢复
            if "sleeping" in act_desc or "sleep" in act_desc:
              persona.scratch.stamina = min(100.0, persona.scratch.stamina + 0.15)
            elif "resting" in act_desc or "rest" in act_desc:
              persona.scratch.stamina = min(100.0, persona.scratch.stamina + 0.08)
            else:
              decay_stamina = 0.07 if persona.scratch.planned_path else 0.04
              persona.scratch.stamina = max(0.0, persona.scratch.stamina - decay_stamina)

            # 3. 情绪/幸福度（Mood）状态更新
            # A. 基础更新：社交增加，独处自然衰减
            if persona.scratch.chatting_with and persona.scratch.chatting_with not in ["", "<creator>"]:
              persona.scratch.last_social_time = self.curr_time
              persona.scratch.mood = min(100.0, persona.scratch.mood + 0.30)
            else:
              persona.scratch.mood = max(0.0, persona.scratch.mood - 0.06)
            
            # B. 生理指标联动：饱腹与充足精力提供额外情绪增益/惩罚
            if persona.scratch.satiety >= 80.0:
              persona.scratch.mood = min(100.0, persona.scratch.mood + 0.02)  # 饱食的幸福增益
            elif persona.scratch.satiety < 20.0:
              persona.scratch.mood = max(0.0, persona.scratch.mood - 0.08)  # 饥饿的抑郁惩罚
              
            if persona.scratch.stamina >= 80.0:
              persona.scratch.mood = min(100.0, persona.scratch.mood + 0.02)  # 精力充沛增益
            elif persona.scratch.stamina < 20.0:
              persona.scratch.mood = max(0.0, persona.scratch.mood - 0.06)  # 疲惫抑郁惩罚

            # 4. 健康度（Health）状态扣减与恢复
            # A. 饥饿扣血惩罚
            if persona.scratch.satiety <= 0.0:
              persona.scratch.health = max(0.0, persona.scratch.health - 0.05)
            # B. 精力枯竭扣血惩罚
            if persona.scratch.stamina <= 0.0:
              persona.scratch.health = max(0.0, persona.scratch.health - 0.02)
            # C. 极度沮丧躯体化扣血惩罚
            if persona.scratch.mood < 20.0:
              persona.scratch.health = max(0.0, persona.scratch.health - 0.02)
            # D. 自然康复：饱食度、精力和幸福度均在良好状态（>50.0），生命值缓慢康复
            if persona.scratch.satiety > 50.0 and persona.scratch.stamina > 50.0 and persona.scratch.mood > 50.0:
              persona.scratch.health = min(100.0, persona.scratch.health + 0.01)

          # Then we need to actually have each of the personas perceive and
          # move. The movement for each of the personas comes in the form of
          # x y coordinates where the persona will move towards. e.g., (50, 34)
          # This is where the core brains of the personas are invoked. 
          movements = {"persona": dict(), 
                       "meta": dict()}

          # [OPTIMIZATION] Phase 2: Run persona.move() in parallel threads
          # Each persona's cognitive pipeline is independent per step, so we
          # can safely parallelize across personas.
          def _move_persona(persona_name, persona):
            return persona_name, persona.move(
              self.maze, self.personas, self.personas_tile[persona_name], 
              self.curr_time, self.step)

          with ThreadPoolExecutor(max_workers=len(self.personas)) as executor:
            futures = []
            for persona_name, persona in self.personas.items():
              futures.append(executor.submit(_move_persona, persona_name, persona))
            
            for future in as_completed(futures):
              persona_name, (next_tile, pronunciatio, description) = future.result()
              self.personas_tile[persona_name] = next_tile
              movements["persona"][persona_name] = {}
              movements["persona"][persona_name]["movement"] = next_tile
              movements["persona"][persona_name]["pronunciatio"] = pronunciatio
              
              movements["persona"][persona_name]["description"] = description
              
              p_inst = self.personas[persona_name]
              movements["persona"][persona_name]["chat"] = p_inst.scratch.chat
              last_chat_val = "None at the moment"
              if getattr(p_inst.scratch, 'last_chat', None):
                last_chat_val = f"{p_inst.name}: {p_inst.scratch.last_chat}"
              movements["persona"][persona_name]["last_chat"] = last_chat_val

              # Include physiological values in movements payload for the frontend/replay
              movements["persona"][persona_name]["satiety"] = p_inst.scratch.satiety
              movements["persona"][persona_name]["stamina"] = p_inst.scratch.stamina
              movements["persona"][persona_name]["health"] = p_inst.scratch.health
              movements["persona"][persona_name]["mood"] = p_inst.scratch.mood
              movements["persona"][persona_name]["inventory"] = p_inst.scratch.inventory

              # Calculate next action
              if p_inst.scratch.health <= 0.0:
                next_action = "已死"
              else:
                curr_index = p_inst.scratch.get_f_daily_schedule_index()
                next_action = "None"
                if curr_index + 1 < len(p_inst.scratch.f_daily_schedule):
                  next_action = p_inst.scratch.f_daily_schedule[curr_index + 1][0]
              movements["persona"][persona_name]["next_action"] = next_action
              
              # Helper to format datetime safely
              def format_dt(dt):
                if not dt:
                  return ""
                if isinstance(dt, str):
                  return dt
                try:
                  return dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                  return str(dt)

              # Serialize retrieved memories (deduplicated & capped to top 20 to prevent MemoryError)
              retrieved_mems = []
              seen_mems = set()
              if hasattr(p_inst.scratch, "last_retrieved_memories") and p_inst.scratch.last_retrieved_memories:
                for event_desc, details in p_inst.scratch.last_retrieved_memories.items():
                  # Perceived event
                  curr_ev = details.get("curr_event")
                  if curr_ev and curr_ev.description not in seen_mems:
                    seen_mems.add(curr_ev.description)
                    retrieved_mems.append({
                      "type": "perceived_event",
                      "description": curr_ev.description,
                      "created": format_dt(curr_ev.created)
                    })
                  # Retrieved events
                  for e in details.get("events", []):
                    if e.description not in seen_mems:
                      seen_mems.add(e.description)
                      retrieved_mems.append({
                        "type": "retrieved_event",
                        "description": e.description,
                        "created": format_dt(e.created),
                        "poignancy": e.poignancy if hasattr(e, "poignancy") else 1
                      })
                  # Retrieved thoughts
                  for t in details.get("thoughts", []):
                    if t.description not in seen_mems:
                      seen_mems.add(t.description)
                      retrieved_mems.append({
                        "type": "retrieved_thought",
                        "description": t.description,
                        "created": format_dt(t.created),
                        "poignancy": t.poignancy if hasattr(t, "poignancy") else 1
                      })
              
              # Sort non-perceived memories by poignancy (higher is more important)
              perceived_list = [m for m in retrieved_mems if m["type"] == "perceived_event"]
              other_list = [m for m in retrieved_mems if m["type"] != "perceived_event"]
              other_list.sort(key=lambda x: x.get("poignancy", 1), reverse=True)
              
              movements["persona"][persona_name]["retrieved_memories"] = (perceived_list + other_list)[:20]

          # Include the meta information about the current stage in the 
          # movements dictionary. 
          movements["meta"]["curr_time"] = (self.curr_time 
                                             .strftime("%B %d, %Y, %H:%M:%S"))

          # We then write the personas' movements to a file that will be sent 
          # to the frontend server. 
          # Example json output: 
          # {"persona": {"Maria Lopez": {"movement": [58, 9]}},
          #  "persona": {"Klaus Mueller": {"movement": [38, 12]}}, 
          #  "meta": {curr_time: <datetime>}}
          # POST movements to Django API (Option 3 API Gateway)
          # Fire-and-forget: use a background thread so we never block the sim loop
          import threading
          def _post_movement(sim_code, step, movements):
            try:
              requests.post("http://127.0.0.1:8000/api/post_movement/", json={
                "sim_code": sim_code,
                "step": step,
                "movements": movements
              }, timeout=15)
            except Exception as e:
              print(f"Warning: Failed to post movement to Django API: {e}")
          threading.Thread(target=_post_movement, args=(self.sim_code, self.step, movements), daemon=True).start()

          curr_move_file = f"{sim_folder}/movement/{self.step}.json"
          os.makedirs(os.path.dirname(curr_move_file), exist_ok=True)
          with open(curr_move_file, "w") as outfile: 
            outfile.write(json.dumps(movements, indent=2))

          # After this cycle, the world takes one step forward, and the 
          # current time moves by <sec_per_step> amount. 
          self.step += 1
          self.curr_time += datetime.timedelta(seconds=self.sec_per_step)
          print(f"[{self.sim_code}] 步数: {self.step} | 游戏时间: {self.curr_time.strftime('%Y-%m-%d %H:%M:%S')} | 实际计算耗时: {time.time() - step_start_time:.2f}秒")

          # Periodically save the simulation state to disk (every 10 steps)
          if self.step % 10 == 0:
            print(f"[{self.sim_code}] 第 {self.step} 步: 正在自动保存模拟状态...")
            try:
              self.save()
            except Exception as save_err:
              print(f"警告: 自动保存失败: {save_err}")

          int_counter -= 1
          
      # Sleep so we don't burn our machines. 
      time.sleep(self.server_sleep)


  def open_server(self): 
    """
    Open up an interactive terminal prompt that lets you run the simulation 
    step by step and probe agent state. 

    INPUT 
      None
    OUTPUT
      None
    """
    print ("Note: The agents in this simulation package are computational")
    print ("constructs powered by generative agents architecture and LLM. We")
    print ("clarify that these agents lack human-like agency, consciousness,")
    print ("and independent decision-making.\n---")

    # <sim_folder> points to the current simulation folder.
    sim_folder = f"{fs_storage}/{self.sim_code}"

    while True: 
      sim_command = input("Enter option: ")
      sim_command = sim_command.strip()
      ret_str = ""

      try: 
        if sim_command.lower() in ["f", "fin", "finish", "save and finish"]: 
          # Finishes the simulation environment and saves the progress. 
          # Example: fin
          self.save()
          break

        elif sim_command.lower() == "start path tester mode": 
          # Starts the path tester and removes the currently forked sim files.
          # Note that once you start this mode, you need to exit out of the
          # session and restart in case you want to run something else. 
          shutil.rmtree(sim_folder) 
          self.start_path_tester_server()

        elif sim_command.lower() == "exit": 
          # Finishes the simulation environment but does not save the progress
          # and erases all saved data from current simulation. 
          # Example: exit 
          shutil.rmtree(sim_folder) 
          break 

        elif sim_command.lower() == "save": 
          # Saves the current simulation progress. 
          # Example: save
          self.save()

        elif sim_command[:3].lower() == "run": 
          # Runs the number of steps specified in the prompt.
          # Example: run 1000
          int_count = int(sim_command.split()[-1])
          rs.start_server(int_count)

        elif ("print persona schedule" 
              in sim_command[:22].lower()): 
          # Print the decomposed schedule of the persona specified in the 
          # prompt.
          # Example: print persona schedule Isabella Rodriguez
          ret_str += (self.personas[" ".join(sim_command.split()[-2:])]
                      .scratch.get_str_daily_schedule_summary())

        elif ("print all persona schedule" 
              in sim_command[:26].lower()): 
          # Print the decomposed schedule of all personas in the world. 
          # Example: print all persona schedule
          for persona_name, persona in self.personas.items(): 
            ret_str += f"{persona_name}\n"
            ret_str += f"{persona.scratch.get_str_daily_schedule_summary()}\n"
            ret_str += f"---\n"

        elif ("print hourly org persona schedule" 
              in sim_command.lower()): 
          # Print the hourly schedule of the persona specified in the prompt.
          # This one shows the original, non-decomposed version of the 
          # schedule.
          # Ex: print persona schedule Isabella Rodriguez
          ret_str += (self.personas[" ".join(sim_command.split()[-2:])]
                      .scratch.get_str_daily_schedule_hourly_org_summary())

        elif ("print persona current tile" 
              in sim_command[:26].lower()): 
          # Print the x y tile coordinate of the persona specified in the 
          # prompt. 
          # Ex: print persona current tile Isabella Rodriguez
          ret_str += str(self.personas[" ".join(sim_command.split()[-2:])]
                      .scratch.curr_tile)

        elif ("print persona chatting with buffer" 
              in sim_command.lower()): 
          # Print the chatting with buffer of the persona specified in the 
          # prompt.
          # Ex: print persona chatting with buffer Isabella Rodriguez
          curr_persona = self.personas[" ".join(sim_command.split()[-2:])]
          for p_n, count in curr_persona.scratch.chatting_with_buffer.items(): 
            ret_str += f"{p_n}: {count}"

        elif ("print persona associative memory (event)" 
              in sim_command.lower()):
          # Print the associative memory (event) of the persona specified in
          # the prompt
          # Ex: print persona associative memory (event) Isabella Rodriguez
          ret_str += f'{self.personas[" ".join(sim_command.split()[-2:])]}\n'
          ret_str += (self.personas[" ".join(sim_command.split()[-2:])]
                                       .a_mem.get_str_seq_events())

        elif ("print persona associative memory (thought)" 
              in sim_command.lower()): 
          # Print the associative memory (thought) of the persona specified in
          # the prompt
          # Ex: print persona associative memory (thought) Isabella Rodriguez
          ret_str += f'{self.personas[" ".join(sim_command.split()[-2:])]}\n'
          ret_str += (self.personas[" ".join(sim_command.split()[-2:])]
                                       .a_mem.get_str_seq_thoughts())

        elif ("print persona associative memory (chat)" 
              in sim_command.lower()): 
          # Print the associative memory (chat) of the persona specified in
          # the prompt
          # Ex: print persona associative memory (chat) Isabella Rodriguez
          ret_str += f'{self.personas[" ".join(sim_command.split()[-2:])]}\n'
          ret_str += (self.personas[" ".join(sim_command.split()[-2:])]
                                       .a_mem.get_str_seq_chats())

        elif ("print persona spatial memory" 
              in sim_command.lower()): 
          # Print the spatial memory of the persona specified in the prompt
          # Ex: print persona spatial memory Isabella Rodriguez
          self.personas[" ".join(sim_command.split()[-2:])].s_mem.print_tree()

        elif ("print current time" 
              in sim_command[:18].lower()): 
          # Print the current time of the world. 
          # Ex: print current time
          ret_str += f'{self.curr_time.strftime("%B %d, %Y, %H:%M:%S")}\n'
          ret_str += f'steps: {self.step}'

        elif ("print tile event" 
              in sim_command[:16].lower()): 
          # Print the tile events in the tile specified in the prompt 
          # Ex: print tile event 50, 30
          cooordinate = [int(i.strip()) for i in sim_command[16:].split(",")]
          for i in self.maze.access_tile(cooordinate)["events"]: 
            ret_str += f"{i}\n"

        elif ("print tile details" 
              in sim_command.lower()): 
          # Print the tile details of the tile specified in the prompt 
          # Ex: print tile event 50, 30
          cooordinate = [int(i.strip()) for i in sim_command[18:].split(",")]
          for key, val in self.maze.access_tile(cooordinate).items(): 
            ret_str += f"{key}: {val}\n"

        elif ("call -- analysis" 
              in sim_command.lower()): 
          # Starts a stateless chat session with the agent. It does not save 
          # anything to the agent's memory. 
          # Ex: call -- analysis Isabella Rodriguez
          persona_name = sim_command[len("call -- analysis"):].strip() 
          self.personas[persona_name].open_convo_session("analysis")

        elif ("call -- load history" 
              in sim_command.lower()): 
          curr_file = maze_assets_loc + "/" + sim_command[len("call -- load history"):].strip() 
          # call -- load history the_ville/agent_history_init_n3.csv

          rows = read_file_to_list(curr_file, header=True, strip_trail=True)[1]
          clean_whispers = []
          for row in rows: 
            agent_name = row[0].strip() 
            whispers = row[1].split(";")
            whispers = [whisper.strip() for whisper in whispers]
            for whisper in whispers: 
              clean_whispers += [[agent_name, whisper]]

          load_history_via_whisper(self.personas, clean_whispers)

        print (ret_str)

      except:
        traceback.print_exc()
        print ("Error.")
        pass


if __name__ == '__main__':
  import sys

  def setup_logging(target):
    import os
    logs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs"))
    os.makedirs(logs_dir, exist_ok=True)
    log_file_path = os.path.join(logs_dir, f"{target}.log")
    
    class Tee(object):
      def __init__(self, *files):
        self.files = files
      def write(self, obj):
        for f in self.files:
          f.write(obj)
          f.flush()
      def flush(self):
        for f in self.files:
          f.flush()
          
    try:
      log_file = open(log_file_path, "a", encoding="utf-8")
      sys.stdout = Tee(sys.stdout, log_file)
      sys.stderr = Tee(sys.stderr, log_file)
    except Exception as e:
      print(f"Warning: Failed to set up file logging: {e}")

  # Check for command line arguments: python reverie.py <fork_name> <new_name> [auto_run_steps]
  if len(sys.argv) >= 3:
    origin = sys.argv[1].strip()
    target = sys.argv[2].strip()
    setup_logging(target)
    
    auto_run_steps = None
    if len(sys.argv) >= 4:
      try:
        auto_run_steps = int(sys.argv[3].strip())
      except ValueError:
        pass
        
    print(f"正在复制/创建模拟副本: {origin} -> {target}")
    rs = ReverieServer(origin, target)
    
    if auto_run_steps is not None:
      print(f"正在自动运行模拟，共计 {auto_run_steps} 步...")
      rs.start_server(auto_run_steps)
      print("正在保存模拟状态...")
      rs.save()
      print("模拟已保存并成功完成！")
    else:
      rs.open_server()
  else:
    origin = input("Enter the name of the forked simulation: ").strip()
    target = input("Enter the name of the new simulation: ").strip()
    setup_logging(target)

    rs = ReverieServer(origin, target)
    rs.open_server()




















































