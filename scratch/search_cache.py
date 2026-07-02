import json
import os

cache_file = r"g:\generative_agents\reverie\backend_server\.prompt_cache\llm_cache.json"
if os.path.exists(cache_file):
    with open(cache_file, "r", encoding="utf-8") as f:
        cache = json.load(f)
    print(f"Loaded cache with {len(cache)} entries.")
    
    # Search for "midday break"
    found = False
    for k, v in cache.items():
        if "midday break" in str(v):
            print(f"Key: {k}")
            print(f"Value: {v}")
            found = True
    if not found:
        print("Not found in cache.")
else:
    print(f"Cache file not found at {cache_file}.")
