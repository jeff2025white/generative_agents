"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: spatial_memory.py
Description: Defines the MemoryTree class that serves as the agents' spatial
memory that aids in grounding their behavior in the game world. 
"""
import json
import sys
sys.path.append('../../')

from utils import *
from global_methods import *

class MemoryTree: 
  def __init__(self, f_saved): 
    self.tree = {}
    if check_if_file_exists(f_saved): 
      self.tree = json.load(open(f_saved))


  def print_tree(self): 
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
    
    _print_tree(self.tree, 0)
    

  def save(self, out_json):
    with open(out_json, "w") as outfile:
      json.dump(self.tree, outfile) 



  def get_str_accessible_sectors(self, curr_world): 
    """
    Returns a summary string of all the arenas that the persona can access 
    within the current sector. 

    Note that there are places a given persona cannot enter. This information
    is provided in the persona sheet. We account for this in this function. 

    INPUT
      None
    OUTPUT 
      A summary string of all the arenas that the persona can access. 
    EXAMPLE STR OUTPUT
      "bedroom, kitchen, dining room, office, bathroom"
    """
    curr_world = curr_world.strip().lower()
    for w in self.tree:
      if w.strip().lower() == curr_world:
        return ", ".join(list(self.tree[w].keys()))
    return ""


  def get_str_accessible_sector_arenas(self, sector): 
    """
    Returns a summary string of all the arenas that the persona can access 
    within the current sector. 

    Note that there are places a given persona cannot enter. This information
    is provided in the persona sheet. We account for this in this function. 

    INPUT
      None
    OUTPUT 
      A summary string of all the arenas that the persona can access. 
    EXAMPLE STR OUTPUT
      "bedroom, kitchen, dining room, office, bathroom"
    """
    curr_world, curr_sector = [x.strip().lower() for x in sector.split(":")]
    if not curr_sector: 
      return ""
    for w in self.tree:
      if w.strip().lower() == curr_world:
        for s in self.tree[w]:
          if s.strip().lower() == curr_sector:
            return ", ".join(list(self.tree[w][s].keys()))
    return ""


  def get_str_accessible_arena_game_objects(self, arena):
    """
    Get a str list of all accessible game objects that are in the arena. If 
    temp_address is specified, we return the objects that are available in
    that arena, and if not, we return the objects that are in the arena our
    persona is currently in. 

    INPUT
      temp_address: optional arena address
    OUTPUT 
      str list of all accessible game objects in the gmae arena. 
    EXAMPLE STR OUTPUT
      "phone, charger, bed, nightstand"
    """
    curr_world, curr_sector, curr_arena = [x.strip().lower() for x in arena.split(":")]

    if not curr_arena: 
      return ""

    for w in self.tree:
      if w.strip().lower() == curr_world:
        for s in self.tree[w]:
          if s.strip().lower() == curr_sector:
            for a in self.tree[w][s]:
              if a.strip().lower() == curr_arena:
                return ", ".join(list(self.tree[w][s][a]))
    return ""


  def find_nearest_object(self, obj_name):
    obj_name_lower = obj_name.strip().lower()
    # Fuzzy prefix match to strip 'the Ville:' or similar if it is prepended
    for w in self.tree:
      w_clean = w.split(":")[-1].strip().lower()
      for s in self.tree[w]:
        for a in self.tree[w][s]:
          for obj in self.tree[w][s][a]:
            if obj.strip().lower() == obj_name_lower or obj_name_lower in obj.strip().lower():
              return f"{w}:{s}:{a}:{obj}"
    return None



if __name__ == '__main__':
  x = f"../../../../environment/frontend_server/storage/the_ville_base_LinFamily/personas/Eddy Lin/bootstrap_memory/spatial_memory.json"
  x = MemoryTree(x)
  x.print_tree()

  print (x.get_str_accessible_sector_arenas("dolores double studio:double studio"))







