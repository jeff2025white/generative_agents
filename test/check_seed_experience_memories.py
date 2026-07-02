import datetime
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.array = lambda value, *args, **kwargs: value
    numpy_stub.dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda a: sum(x * x for x in a) ** 0.5
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub


from persona.memory_structures.associative_memory import AssociativeMemory
from utils import embedding_model, ollama_api_base


DEFAULT_EXPERIENCE_SEEDS = {
    "Maria Lopez": [
        {
            "type": "thought",
            "description": "Maria Lopez gathered apples from the refrigerator and restored her satiety effectively.",
            "s": "Maria Lopez",
            "p": "restored satiety via",
            "o": "refrigerator",
            "keywords": {"maria lopez", "refrigerator", "apple", "food", "satiety", "gather"},
            "poignancy": 8.0,
            "attribute_effects": {"satiety": 20.0, "stamina": 0.0, "health": 0.0, "mood": 2.0},
        },
        {
            "type": "event",
            "description": "Maria Lopez consumed a cooked meal and recovered from hunger quickly.",
            "s": "Maria Lopez",
            "p": "consumed",
            "o": "cooked meal",
            "keywords": {"maria lopez", "consume", "meal", "food", "hunger", "satiety"},
            "poignancy": 7.0,
            "attribute_effects": {"satiety": 40.0, "stamina": 0.0, "health": 5.0, "mood": 10.0},
        },
    ],
    "Klaus Mueller": [
        {
            "type": "thought",
            "description": "Klaus Mueller found food in the dorm refrigerator and solved his hunger problem there.",
            "s": "Klaus Mueller",
            "p": "restored satiety via",
            "o": "refrigerator",
            "keywords": {"klaus mueller", "refrigerator", "food", "hunger", "satiety"},
            "poignancy": 8.0,
            "attribute_effects": {"satiety": 18.0, "stamina": 0.0, "health": 0.0, "mood": 1.0},
        },
        {
            "type": "event",
            "description": "Klaus Mueller consumed food from inventory after gathering it and felt less hungry.",
            "s": "Klaus Mueller",
            "p": "consumed",
            "o": "food",
            "keywords": {"klaus mueller", "consume", "inventory", "food", "satiety"},
            "poignancy": 7.0,
            "attribute_effects": {"satiety": 35.0, "stamina": 0.0, "health": 3.0, "mood": 6.0},
        },
    ],
    "Isabella Rodriguez": [
        {
            "type": "thought",
            "description": "Isabella Rodriguez used the Hobbs Cafe refrigerator to recover from hunger before returning to work.",
            "s": "Isabella Rodriguez",
            "p": "restored satiety via",
            "o": "refrigerator",
            "keywords": {"isabella rodriguez", "refrigerator", "food", "hunger", "satiety", "hobbs cafe"},
            "poignancy": 8.0,
            "attribute_effects": {"satiety": 16.0, "stamina": 0.0, "health": 0.0, "mood": 2.0},
        },
        {
            "type": "event",
            "description": "Isabella Rodriguez ate prepared food and regained enough energy to continue cafe duties.",
            "s": "Isabella Rodriguez",
            "p": "consumed",
            "o": "prepared food",
            "keywords": {"isabella rodriguez", "consume", "prepared food", "satiety", "recovery"},
            "poignancy": 7.0,
            "attribute_effects": {"satiety": 35.0, "stamina": 4.0, "health": 4.0, "mood": 8.0},
        },
    ],
}


def get_embedding(text, model=embedding_model):
    text = str(text or "").replace("\n", " ")
    if not text:
        text = "this is blank"

    base_url = str(ollama_api_base).rstrip("/")
    payload = json.dumps({"model": model, "input": [text]}).encode("utf-8")
    request = urllib.request.Request(
        url=f"{base_url}/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    embedding = data["data"][0]["embedding"]
    if len(embedding) < 1536:
        embedding = embedding + [0.0] * (1536 - len(embedding))
    elif len(embedding) > 1536:
        embedding = embedding[:1536]
    return embedding


def ensure_associative_memory_dir(memory_dir):
    os.makedirs(memory_dir, exist_ok=True)
    for file_name, default_data in [
        ("nodes.json", {}),
        ("embeddings.json", {}),
        ("kw_strength.json", {"kw_strength_event": {}, "kw_strength_thought": {}}),
        ("social_relationship_graph.json", {"relations": {}}),
    ]:
        file_path = Path(memory_dir) / file_name
        if not file_path.exists():
            file_path.write_text(json.dumps(default_data, ensure_ascii=False), encoding="utf-8")


def _slug(value):
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text or "memory"


def _embedding_pair(persona_name, description, index, embedding_fn):
    embedding_key = f"seed:{_slug(persona_name)}:{index}:{_slug(description)[:40]}"
    return embedding_key, embedding_fn(description)


def seed_associative_memory(a_mem, persona_name, entries, created=None, embedding_fn=None):
    embedding_fn = embedding_fn or get_embedding
    created = created or datetime.datetime.now()
    inserted_nodes = []
    for index, entry in enumerate(entries):
        description = entry["description"]
        s = entry.get("s", persona_name)
        p = entry.get("p", "experienced")
        o = entry.get("o", "experience")
        keywords = set(entry.get("keywords", [])) or set(description.lower().split())
        poignancy = float(entry.get("poignancy", 5.0))
        expiration = entry.get("expiration")
        filling = entry.get("filling")
        attribute_effects = entry.get("attribute_effects")
        embedding_pair = _embedding_pair(persona_name, description, index, embedding_fn)
        if entry.get("type") == "event":
            node = a_mem.add_event(created, expiration, s, p, o, description, keywords, poignancy, embedding_pair, filling, attribute_effects=attribute_effects)
        elif entry.get("type") == "chat":
            node = a_mem.add_chat(created, expiration, s, p, o, description, keywords, poignancy, embedding_pair, filling, attribute_effects=attribute_effects)
        else:
            node = a_mem.add_thought(created, expiration, s, p, o, description, keywords, poignancy, embedding_pair, filling, attribute_effects=attribute_effects)
        inserted_nodes.append(node)
    return inserted_nodes


def load_current_sim_code():
    path = ROOT / "environment" / "frontend_server" / "temp_storage" / "curr_sim_code.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["sim_code"]


def _load_sim_time(sim_dir):
    meta_path = Path(sim_dir) / "reverie" / "meta.json"
    if not meta_path.exists():
        return datetime.datetime.now()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    curr_time = meta.get("curr_time")
    if not curr_time:
        return datetime.datetime.now()
    return datetime.datetime.strptime(curr_time, "%B %d, %Y, %H:%M:%S")


def seed_sim_experience_memories(sim_code=None, seeds=None, embedding_fn=None):
    sim_code = sim_code or load_current_sim_code()
    seeds = seeds or DEFAULT_EXPERIENCE_SEEDS
    sim_dir = ROOT / "environment" / "frontend_server" / "storage" / sim_code
    created = _load_sim_time(sim_dir)

    results = {}
    for persona_name, entries in seeds.items():
        memory_dir = sim_dir / "personas" / persona_name / "bootstrap_memory" / "associative_memory"
        ensure_associative_memory_dir(memory_dir)
        a_mem = AssociativeMemory(str(memory_dir))
        before = len(a_mem.id_to_node)
        inserted = seed_associative_memory(a_mem, persona_name, entries, created=created, embedding_fn=embedding_fn)
        a_mem.save(str(memory_dir))
        results[persona_name] = {
            "before": before,
            "inserted": len(inserted),
            "after": len(a_mem.id_to_node),
            "memory_dir": str(memory_dir),
        }
    return sim_code, results


if __name__ == "__main__":
    sim_code = sys.argv[1] if len(sys.argv) > 1 else None
    seeded_sim_code, results = seed_sim_experience_memories(sim_code=sim_code)
    print(json.dumps({"sim_code": seeded_sim_code, "results": results}, ensure_ascii=False, indent=2))
