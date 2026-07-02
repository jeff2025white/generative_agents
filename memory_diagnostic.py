"""
Memory System Diagnostic Script
"""
import json, os, sys

STORAGE_BASE = r"g:\generative_agents\environment\frontend_server\storage"

def diagnose(sim_name, persona_name):
    base = os.path.join(STORAGE_BASE, sim_name, "personas", persona_name, "bootstrap_memory")
    
    print(f"\n{'='*60}")
    print(f"  Memory Diagnostic: {persona_name} @ {sim_name}")
    print(f"{'='*60}")
    
    # 1. Associative Memory
    nodes_path = os.path.join(base, "associative_memory", "nodes.json")
    with open(nodes_path, "r", encoding="utf-8") as f:
        nodes = json.load(f)
    
    total = len(nodes)
    events = sum(1 for n in nodes.values() if n["type"] == "event")
    thoughts = sum(1 for n in nodes.values() if n["type"] == "thought")
    chats = sum(1 for n in nodes.values() if n["type"] == "chat")
    poig_vals = [n["poignancy"] for n in nodes.values()]
    idle_count = sum(1 for n in nodes.values() if "idle" in n.get("description","").lower())
    
    print(f"\n[1] Associative Memory (nodes.json)")
    print(f"  Total: {total} | Events: {events} | Thoughts: {thoughts} | Chats: {chats}")
    print(f"  Poignancy: avg={sum(poig_vals)/len(poig_vals):.1f}, min={min(poig_vals)}, max={max(poig_vals)}")
    print(f"  Idle nodes: {idle_count} ({idle_count/total*100:.0f}%)")
    
    print(f"\n  Latest 5 nodes:")
    sorted_nodes = sorted(nodes.items(), key=lambda x: int(x[0].split("_")[1]), reverse=True)
    for nid, n in sorted_nodes[:5]:
        icon = {"event": "E", "thought": "T", "chat": "C"}.get(n["type"], "?")
        print(f"    [{icon}] {nid} poig={n['poignancy']} | {n['description'][:80]}")
    
    # 2. Embeddings
    emb_path = os.path.join(base, "associative_memory", "embeddings.json")
    with open(emb_path, "r", encoding="utf-8") as f:
        embeddings = json.load(f)
    
    emb_count = len(embeddings)
    node_emb_keys = set(n["embedding_key"] for n in nodes.values())
    emb_keys = set(embeddings.keys())
    missing = node_emb_keys - emb_keys
    
    print(f"\n[2] Embeddings")
    print(f"  Count: {emb_count}")
    if embeddings:
        first_key = list(embeddings.keys())[0]
        print(f"  Dimension: {len(embeddings[first_key])}")
    print(f"  Consistency: {'OK' if not missing else f'MISSING {len(missing)} keys!'}")
    
    # 3. Scratch
    scratch_path = os.path.join(base, "scratch.json")
    with open(scratch_path, "r", encoding="utf-8") as f:
        scratch = json.load(f)
    
    print(f"\n[3] Scratch (Working Memory)")
    print(f"  Name: {scratch['name']}")
    print(f"  Time: {scratch.get('curr_time', 'N/A')}")
    print(f"  Tile: {scratch.get('curr_tile', 'N/A')}")
    print(f"  Action: {scratch.get('act_description', 'N/A')}")
    print(f"  Schedule items: {len(scratch.get('f_daily_schedule', []))}")
    tc = scratch.get('importance_trigger_curr', 'N/A')
    tm = scratch.get('importance_trigger_max', 'N/A')
    print(f"  Reflection counter: {tc} / {tm}")
    print(f"  Satiety: {scratch.get('satiety','N/A')} | Stamina: {scratch.get('stamina','N/A')} | Health: {scratch.get('health','N/A')}")
    print(f"  Inventory: {json.dumps(scratch.get('inventory',{}), ensure_ascii=False)}")
    
    # 4. Spatial Memory
    spatial_path = os.path.join(base, "spatial_memory.json")
    with open(spatial_path, "r", encoding="utf-8") as f:
        spatial = json.load(f)
    
    worlds = len(spatial)
    sectors = sum(len(v) for v in spatial.values())
    arenas = sum(len(a) for w in spatial.values() for a in w.values())
    objs = sum(len(o) for w in spatial.values() for s in w.values() for o in s.values())
    
    print(f"\n[4] Spatial Memory")
    print(f"  Worlds: {worlds} | Sectors: {sectors} | Arenas: {arenas} | Objects: {objs}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    issues = []
    if total < 5: issues.append("X Node count too low (<5)")
    if thoughts == 0: issues.append("! No thought nodes - reflection may not be working")
    if missing: issues.append(f"X {len(missing)} nodes missing embeddings")
    if idle_count / total > 0.5: issues.append(f"! High idle ratio ({idle_count/total*100:.0f}%)")
    if objs == 0: issues.append("X No objects in spatial memory")
    
    if issues:
        for i in issues: print(f"  {i}")
    else:
        print(f"  ALL CHECKS PASSED - Memory system is healthy!")
    print()

# Run for all 3 personas in latest sim
sims_to_check = ["sim_20260628_154846"]
personas = ["Isabella Rodriguez", "Klaus Mueller", "Maria Lopez"]

for sim in sims_to_check:
    for p in personas:
        path = os.path.join(STORAGE_BASE, sim, "personas", p)
        if os.path.exists(path):
            diagnose(sim, p)
