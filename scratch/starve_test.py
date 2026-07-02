import json
import os

personas = ["Isabella Rodriguez", "Maria Lopez", "Klaus Mueller"]
base_dir = r"g:\generative_agents\environment\frontend_server\storage\test_reconstruct_run_1\personas"

for p in personas:
    scratch_path = os.path.join(base_dir, p, "bootstrap_memory", "scratch.json")
    if os.path.exists(scratch_path):
        with open(scratch_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Modify stats for test
        data["satiety"] = 5.0
        data["stamina"] = 100.0
        data["health"] = 100.0
        data["mood"] = 90.0
        
        # Reset current action to some non-survival action if they are resting, so we can test the starvation interruption!
        # Isabella's current action is resting. Let's make it work or something, or we can just leave it since "resting" is a Stamina recovery action, not satiety!
        # Since satiety is 5.0 and they are resting, and resting is NOT resolving starvation (is_resolving_starvation is False), the starvation interruption SHOULD trigger immediately!
        
        with open(scratch_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Successfully set Satiety to 5.0 for {p}")
    else:
        print(f"Error: {scratch_path} not found!")
