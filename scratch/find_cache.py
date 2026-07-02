import json
import os

cache_file = r"g:\generative_agents\reverie\backend_server\.prompt_cache\llm_cache.json"
if os.path.exists(cache_file):
    with open(cache_file, "r", encoding="utf-8") as f:
        cache = json.load(f)
    print(f"Loaded {len(cache)} entries.")
    
    # We want to find cache entries that have Maria Lopez or Klaus Mueller
    matches = 0
    for key, val in cache.items():
        if isinstance(val, str) and "Maria Lopez" in val:
            print(f"Key: {key}")
            print(f"Val: {val[:200]}...")
            matches += 1
            if matches >= 5:
                break
else:
    print("Cache file not found.")
