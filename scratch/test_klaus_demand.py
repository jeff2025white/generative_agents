import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
backend_dir = ROOT / "reverie" / "backend_server"
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

from persona.persona import Persona
from persona.cognitive_modules.plan import decide_demand_action
from maze import Maze

print("Initializing test environment...")
maze = Maze("the_ville")
default_sim = ROOT / "environment" / "frontend_server" / "storage" / "sim_20260708_232103"
sim_folder = Path(os.environ.get("TEST_SIM_FOLDER", str(default_sim)))

# Load Klaus Mueller
p = Persona("Klaus Mueller", str(sim_folder / "personas" / "Klaus Mueller"))

print(f"Loaded Klaus Mueller. Stats: Satiety={p.scratch.satiety}, Stamina={p.scratch.stamina}, Health={p.scratch.health}, Mood={p.scratch.mood}")
print("Calling decide_demand_action...")

decide_demand_action(p, maze)
