import sys
import os
import json

sim_folder = r"g:\generative_agents\environment\frontend_server\storage\test_reconstruct_run_1"

for name in ["Isabella Rodriguez", "Maria Lopez", "Klaus Mueller"]:
    path = f"{sim_folder}/personas/{name}/bootstrap_memory/scratch.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[{name}] Stats: Satiety={data.get('satiety')}, Stamina={data.get('stamina')}, Health={data.get('health')}, Mood={data.get('mood')}")
        print(f"             Inventory={data.get('inventory')}")
        print(f"             Act={data.get('act_description')}")
        print(f"             Curr Tile={data.get('curr_tile')}")
        print(f"             Act Address={data.get('act_address')}")
    else:
        print(f"[{name}] scratch.json not found")
