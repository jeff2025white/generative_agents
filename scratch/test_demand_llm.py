import sys
import os

# Set working directory to backend_server to match reverie.py execution context
backend_dir = r"g:\generative_agents\reverie\backend_server"
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

from persona.prompt_template.run_gpt_prompt import run_gpt_prompt_demand_decision
from persona.persona import Persona
from maze import Maze

print("Initializing test environment...")
maze = Maze("the_ville")
sim_folder = r"g:\generative_agents\environment\frontend_server\storage\test_reconstruct_run_1"
persona_name = "Isabella Rodriguez"
persona_folder = f"{sim_folder}/personas/{persona_name}"

p = Persona(persona_name, persona_folder)

# Override stats: low satiety, full stamina
p.scratch.satiety = 0.0
p.scratch.stamina = 100.0
p.scratch.health = 100.0
p.scratch.mood = 90.0
p.scratch.inventory = {} # Empty inventory

print(f"Stats set: Satiety={p.scratch.satiety}, Stamina={p.scratch.stamina}, Health={p.scratch.health}, Mood={p.scratch.mood}")
print("Calling run_gpt_prompt_demand_decision...")

# Call demand decision
decision = run_gpt_prompt_demand_decision(
    p, 
    nearby_resources=["bed", "desk", "closet", "shelf"], 
    verbose=True
)

print("\n--- DECISION OUTPUT ---")
print(decision)
