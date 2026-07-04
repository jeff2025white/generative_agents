"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: execute.py
Description: This defines the "Act" module for generative agents. 
"""
import sys
import random
sys.path.append('../../')

from global_methods import *
from path_finder import *
from utils import *
from persona.cognitive_modules.action_command_utils import infer_action_command_from_event
from persona.prompt_template.gpt_structure import get_embedding
from persona.cognitive_modules.debug_log import append_debug_log, safe_json_dumps
from persona.cognitive_modules.social_dialogue_log import clear_social_dialogue_state, log_social_dialogue
from persona.cognitive_modules.skill_packs import SKILL_REGISTRY


def _is_valid_navigation_path(curr_tile, target_tile, path):
  if not path:
    return False
  normalized_curr = tuple(curr_tile) if isinstance(curr_tile, (list, tuple)) else curr_tile
  normalized_target = tuple(target_tile) if isinstance(target_tile, (list, tuple)) else target_tile
  normalized_path = [
    tuple(tile) if isinstance(tile, (list, tuple)) else tile
    for tile in path
  ]
  if normalized_path[0] != normalized_curr:
    return False
  if normalized_path[-1] != normalized_target:
    return False
  if len(normalized_path) == 1 and normalized_curr != normalized_target:
    return False
  return True

def execute(persona, maze, personas, plan): 
  """
  Given a plan (action's string address), we execute the plan (actually 
  outputs the tile coordinate path and the next coordinate for the 
  persona). 

  INPUT:
    persona: Current <Persona> instance.  
    maze: An instance of current <Maze>.
    personas: A dictionary of all personas in the world. 
    plan: This is a string address of the action we need to execute. 
       It comes in the form of "{world}:{sector}:{arena}:{game_objects}". 
       It is important that you access this without doing negative 
       indexing (e.g., [-1]) because the latter address elements may not be 
       present in some cases. 
       e.g., "dolores double studio:double studio:bedroom 1:bed"
    
  OUTPUT: 
    execution
  """
  if not plan:
    plan = ""

  # PHYSICAL DEPENDENCY INTERCEPTOR removed: behaviors are now dynamically decided by the LLM cognitive layer.

  if "<random>" in plan and persona.scratch.planned_path == []: 
    persona.scratch.act_path_set = False

  # <act_path_set> is set to True if the path is set for the current action. 
  # It is False otherwise, and means we need to construct a new path. 
  if not persona.scratch.act_path_set: 
    # Reset survival effect applied status on new path generation
    persona.scratch.survival_applied = False
    # <target_tiles> is a list of tile coordinates where the persona may go 
    # to execute the current action. The goal is to pick one of them.
    target_tiles = None



    if "<persona>" in plan: 
      # Executing persona-persona interaction.
      target_p_tile = (personas[plan.split("<persona>")[-1].strip()]
                       .scratch.curr_tile)
      potential_path = path_finder(maze.collision_maze, 
                                   persona.scratch.curr_tile, 
                                   target_p_tile, 
                                   collision_block_id)
      if not potential_path:
        target_tiles = [target_p_tile]
      elif len(potential_path) <= 2: 
        target_tiles = [potential_path[0]]
      else: 
        potential_1 = path_finder(maze.collision_maze, 
                                persona.scratch.curr_tile, 
                                potential_path[int(len(potential_path)/2)], 
                                collision_block_id)
        potential_2 = path_finder(maze.collision_maze, 
                                persona.scratch.curr_tile, 
                                potential_path[int(len(potential_path)/2)+1], 
                                collision_block_id)
        if len(potential_1) <= len(potential_2): 
          target_tiles = [potential_path[int(len(potential_path)/2)]]
        else: 
          target_tiles = [potential_path[int(len(potential_path)/2+1)]]
    elif "<waiting>" in plan: 
      # Executing interaction where the persona has decided to wait before 
      # executing their action.
      x = int(plan.split()[1])
      y = int(plan.split()[2])
      target_tiles = [[x, y]]

    elif "<creator>" in plan:
      # Creator/Observer communication happens in-place
      target_tiles = [persona.scratch.curr_tile]

    elif "<random>" in plan: 
      # Executing a random location action.
      plan = ":".join(plan.split(":")[:-1]).strip()
      if plan in maze.address_tiles:
        target_tiles = maze.address_tiles[plan]
      else:
        matched_plan = None
        for k in maze.address_tiles:
          if k.lower() == plan.lower():
            matched_plan = k
            break
        if matched_plan:
          target_tiles = maze.address_tiles[matched_plan]
        else:
          target_tiles = [persona.scratch.curr_tile]
      target_tiles = random.sample(list(target_tiles), 1)

    else: 
      # This is our default execution. We simply take the persona to the
      # location where the current action is taking place. 
      # Retrieve the target addresses. Again, plan is an action address in its
      # string form. <maze.address_tiles> takes this and returns candidate 
      # coordinates. 
      plan = plan.strip()
      if plan in maze.address_tiles:
        target_tiles = maze.address_tiles[plan]
      else:
        matched_plan = None
        for k in maze.address_tiles:
          if k.lower() == plan.lower():
            matched_plan = k
            break
        if matched_plan:
          target_tiles = maze.address_tiles[matched_plan]
        else:
          # Try checking with/without "the Ville:" prefix
          alternative_plans = []
          if not plan.lower().startswith("the ville:"):
            alternative_plans.append("the Ville:" + plan)
          else:
            alternative_plans.append(plan[len("the Ville:"):])
          
          found_alternative = False
          for alt in alternative_plans:
            for k in maze.address_tiles:
              if k.lower() == alt.lower():
                target_tiles = maze.address_tiles[k]
                found_alternative = True
                break
            if found_alternative:
              break
          
          if not found_alternative:
            print(f"=== WARNING: plan address '{plan}' not found in maze.address_tiles! ===")
            target_tiles = [persona.scratch.curr_tile]

    # There are sometimes more than one tile returned from this (e.g., a tabe
    # may stretch many coordinates). So, we sample a few here. And from that 
    # random sample, we will take the closest ones. 
    if len(target_tiles) < 4: 
      target_tiles = random.sample(list(target_tiles), len(target_tiles))
    else:
      target_tiles = random.sample(list(target_tiles), 4)
    # If possible, we want personas to occupy different tiles when they are 
    # headed to the same location on the maze. It is ok if they end up on the 
    # same time, but we try to lower that probability. 
    # We take care of that overlap here.  
    persona_name_set = set(personas.keys())
    new_target_tiles = []
    for i in target_tiles: 
      curr_event_set = maze.access_tile(i)["events"]
      pass_curr_tile = False
      for j in curr_event_set: 
        if j[0] in persona_name_set: 
          pass_curr_tile = True
      if not pass_curr_tile: 
        new_target_tiles += [i]
    if len(new_target_tiles) == 0: 
      new_target_tiles = target_tiles
    target_tiles = new_target_tiles

    # Now that we've identified the target tile, we find the shortest path to
    # one of the target tiles. 
    curr_tile = persona.scratch.curr_tile
    collision_maze = maze.collision_maze
    closest_target_tile = None
    path = None
    for i in target_tiles: 
      # path_finder takes a collision_mze and the curr_tile coordinate as 
      # an input, and returns a list of coordinate tuples that becomes the
      # path. 
      # e.g., [(0, 1), (1, 1), (1, 2), (1, 3), (1, 4)...]
      curr_path = path_finder(maze.collision_maze, 
                              curr_tile, 
                              i, 
                              collision_block_id)
      if not _is_valid_navigation_path(curr_tile, i, curr_path):
        continue
      if not closest_target_tile: 
        closest_target_tile = i
        path = curr_path
      elif len(curr_path) < len(path): 
        closest_target_tile = i
        path = curr_path

    # Actually setting the <planned_path> and <act_path_set>. We cut the 
    # first element in the planned_path because it includes the curr_tile. 
    if not path:
      target_label = None
      if getattr(persona.scratch, "act_command", None):
        target_label = persona.scratch.act_command.get("target")
      if hasattr(persona.scratch, "note_navigation_failure"):
        persona.scratch.note_navigation_failure(
          target=target_label,
          target_address=plan,
          reason="path_not_found",
          payload={
            "target_tiles": target_tiles,
            "act_event": persona.scratch.act_event,
          },
        )
      append_debug_log(
        "action_execution_debug.jsonl",
        {
          "persona": persona.name,
          "event": "path_not_found",
          "plan": plan,
          "curr_tile": persona.scratch.curr_tile,
          "target_tiles": target_tiles,
          "act_event": persona.scratch.act_event,
          "target": target_label,
        }
      )
      persona.scratch.clear_current_action(keep_last_desc=True)
    else:
      if hasattr(persona.scratch, "clear_navigation_failure"):
        persona.scratch.clear_navigation_failure()
      persona.scratch.planned_path = path[1:]
      persona.scratch.act_path_set = True
      append_debug_log(
        "action_execution_debug.jsonl",
        {
          "persona": persona.name,
          "event": "path_set",
          "plan": plan,
          "curr_tile": curr_tile,
          "closest_target_tile": closest_target_tile,
          "path_length": len(path),
          "remaining_path": persona.scratch.planned_path,
          "act_description": persona.scratch.act_description,
          "act_event": persona.scratch.act_event,
          "act_command": persona.scratch.act_command,
        }
      )
      if getattr(persona.scratch, "social_dialogue_id", None):
        log_social_dialogue(
          persona,
          "path",
          "path_started",
          payload={
            "closest_target_tile": closest_target_tile,
            "path_length": len(path),
            "remaining_path": persona.scratch.planned_path,
            "act_address": persona.scratch.act_address,
          },
        )
  
  # Setting up the next immediate step. We stay at our curr_tile if there is
  # no <planned_path> left, but otherwise, we go to the next tile in the path.
  ret = persona.scratch.curr_tile
  if persona.scratch.planned_path: 
    ret = persona.scratch.planned_path[0]
    persona.scratch.planned_path = persona.scratch.planned_path[1:]

  # Dispatch physical and memory outcomes to Skill Packs upon arrival
  if not persona.scratch.planned_path and persona.scratch.act_path_set:
    if not getattr(persona.scratch, 'survival_applied', False):
      persona.scratch.survival_applied = True
      
      act_event = persona.scratch.act_event
      act_command = persona.scratch.act_command or infer_action_command_from_event(act_event, source="execute_fallback")
      action = act_command.get("skill_id", "") if act_command else ""
      target = act_command.get("target", "") if act_command else ""
      append_debug_log(
        "action_execution_debug.jsonl",
        {
          "persona": persona.name,
          "event": "arrive",
          "curr_tile": persona.scratch.curr_tile,
          "act_address": persona.scratch.act_address,
          "act_description": persona.scratch.act_description,
          "act_event": act_event,
          "act_command": act_command,
          "parsed_action": action,
          "parsed_target": target,
        }
      )
      if getattr(persona.scratch, "social_dialogue_id", None):
        log_social_dialogue(
          persona,
          "arrival",
          "path_arrived",
          target_name=target,
          payload={
            "curr_tile": persona.scratch.curr_tile,
            "act_address": persona.scratch.act_address,
            "act_description": persona.scratch.act_description,
            "action": action,
          },
        )
      
      skill = SKILL_REGISTRY.get(action.lower()) if action else None
      if skill:
        can_execute = skill.can_execute(persona, target, maze)
        append_debug_log(
          "action_execution_debug.jsonl",
          {
            "persona": persona.name,
            "event": "skill_lookup",
            "action": action,
            "target": target,
            "skill": skill.__class__.__name__,
            "can_execute": can_execute,
          }
        )
        if can_execute:
          skill.on_arrive(persona, target, maze, personas)
        else:
          if getattr(persona.scratch, "social_dialogue_id", None):
            log_social_dialogue(
              persona,
              "failure",
              "skill_blocked",
              target_name=target,
              payload={
                "action": action,
                "curr_tile": persona.scratch.curr_tile,
                "inventory": persona.scratch.inventory,
              },
            )
          append_debug_log(
            "action_execution_debug.jsonl",
            {
              "persona": persona.name,
              "event": "skill_blocked",
              "action": action,
              "target": target,
              "curr_tile": persona.scratch.curr_tile,
              "inventory": persona.scratch.inventory,
            }
          )
          # Objective physical failure: Clear current planned path and action, forcing LLM to re-evaluate in the next step
          persona.scratch.planned_path = []
          persona.scratch.act_path_set = False
          persona.scratch.act_address = None
          persona.scratch.act_description = None
          persona.scratch.act_event = None
          persona.scratch.act_command = None
          clear_social_dialogue_state(persona)
      else:
        if getattr(persona.scratch, "social_dialogue_id", None):
          log_social_dialogue(
            persona,
            "failure",
            "skill_missing",
            target_name=target,
            payload={
              "action": action,
              "act_event": act_event,
              "act_description": persona.scratch.act_description,
            },
          )
        append_debug_log(
          "action_execution_debug.jsonl",
          {
            "persona": persona.name,
            "event": "skill_missing",
            "action": action,
            "target": target,
            "act_event": act_event,
            "act_description": persona.scratch.act_description,
          }
        )

  description = f"{persona.scratch.act_description}"
  if not persona.scratch.act_address:
    actual_address = maze.get_tile_path(persona.scratch.curr_tile, "game_object")
    description = f"idling @ {actual_address}"
    execution = ret, persona.scratch.act_pronunciatio, description
    return execution

  if "<creator>" in persona.scratch.act_address:
    actual_address = maze.get_tile_path(persona.scratch.curr_tile, "game_object")
    description += f" @ {actual_address}"
  else:
    description += f" @ {persona.scratch.act_address}"

  execution = ret, persona.scratch.act_pronunciatio, description
  return execution









