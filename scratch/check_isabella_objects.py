import sys
import os

# Set working directory to backend_server to match reverie.py execution context
backend_dir = r"g:\generative_agents\reverie\backend_server"
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

from persona.persona import Persona
from maze import Maze

maze = Maze("the_ville")
sim_folder = r"g:\generative_agents\environment\frontend_server\storage\test_reconstruct_run_1"

p = Persona("Isabella Rodriguez", f"{sim_folder}/personas/Isabella Rodriguez")

# Get all objects the persona knows about
objs = set()
for w in p.s_mem.tree:
  for s in p.s_mem.tree[w]:
    for a in p.s_mem.tree[w][s]:
      for obj in p.s_mem.tree[w][s][a]:
        objs.add(obj)
objs_list = list(objs)

object_states = []
for obj in objs_list:
  address = p.s_mem.find_nearest_object(obj)
  if address and address in maze.address_tiles:
    tiles = list(maze.address_tiles[address])
    events_on_obj = []
    for tile in tiles:
      tile_details = maze.access_tile(tile)
      if tile_details and tile_details["events"]:
        for ev in tile_details["events"]:
          events_on_obj.append(str(ev))
    if events_on_obj:
      object_states.append(f"{obj} (current state: {', '.join(events_on_obj)})")
    else:
      object_states.append(f"{obj} (idle/normal)")
  else:
    object_states.append(f"{obj} (normal)")

print("Isabella's Known Objects and States:")
for os_str in sorted(object_states):
    print(f"- {os_str}")
