import sys
import os

# Set working directory to backend_server to match reverie.py execution context
backend_dir = r"g:\generative_agents\reverie\backend_server"
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

from persona.persona import Persona
from persona.cognitive_modules.plan import decide_demand_action
from maze import Maze

print("Initializing test environment...")
maze = Maze("the_ville")
sim_folder = r"g:\generative_agents\environment\frontend_server\storage\test_reconstruct_run_1"

# Load Maria Lopez
p = Persona("Maria Lopez", f"{sim_folder}/personas/Maria Lopez")

print(f"Loaded Maria Lopez. Stats: Satiety={p.scratch.satiety}, Stamina={p.scratch.stamina}, Health={p.scratch.health}, Mood={p.scratch.mood}")
print("Calling decide_demand_action...")

# We can run decide_demand_action
decide_demand_action(p, maze)
