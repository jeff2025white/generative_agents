"""Deterministic address resolution helpers for action targets."""


KNOWN_OBJECT_HINTS = {
    "refrigerator": ["refrigerator", "fridge", "kitchen fridge"],
    "piano": ["piano"],
    "library table": ["library table", "library desk"],
    "game console": ["game console", "console"],
    "computer": ["computer desk", "computer", "laptop"],
    "desk": ["desk"],
    "pool table": ["pool table"],
    "behind the cafe counter": ["behind the cafe counter", "cafe counter"],
    "cafe customer seating": ["cafe customer seating", "customer seating"],
    "blackboard": ["blackboard"],
    "bookshelf": ["bookshelf"],
    "tv": ["tv", "television"],
    "sofa": ["sofa", "couch"],
    "bed": ["bed"],
}


KNOWN_ARENA_RULES = [
    {
        "triggers": ["hobbs cafe", "cafe"],
        "preferred_keywords": ["cafe"],
        "excluded_keywords": [],
    },
    {
        "triggers": ["library", "library table", "bookshelf", "blackboard"],
        "preferred_keywords": ["library", "classroom"],
        "excluded_keywords": [],
    },
    {
        "triggers": ["common room"],
        "preferred_keywords": ["common room"],
        "excluded_keywords": [],
    },
    {
        "triggers": ["fitness machine", "exercise machine", "workout machine", "gym"],
        "preferred_keywords": ["gym", "fitness", "exercise", "recreation"],
        "excluded_keywords": ["cafe"],
    },
    {
        "triggers": ["piano", "music"],
        "preferred_keywords": ["piano", "music", "recreation", "common room"],
        "excluded_keywords": [],
    },
]

ARENA_ONLY_SKILLS = {"use", "work", "study", "leisure_use"}


def _normalize_text(value):
    return str(value or "").strip().lower()


def _combined_text(*values):
    return " ".join(_normalize_text(value) for value in values if value).strip()


def _iter_arena_addresses(maze):
    for address in maze.address_tiles:
        if len(address.split(":")) == 3:
            yield address


def _iter_object_entries(persona):
    seen = set()
    tree = getattr(getattr(persona, "s_mem", None), "tree", {}) or {}
    for world, sectors in tree.items():
        for sector, arenas in sectors.items():
            for arena, objects in arenas.items():
                for obj in objects:
                    address = f"{world}:{sector}:{arena}:{obj}"
                    normalized_obj = _normalize_text(obj)
                    if not normalized_obj or normalized_obj in seen:
                        continue
                    seen.add(normalized_obj)
                    yield obj, address


def _find_matching_arena_address(maze, preferred_keywords, excluded_keywords=None):
    excluded_keywords = excluded_keywords or []
    best_address = None
    best_score = -1
    for address in _iter_arena_addresses(maze):
        normalized_address = _normalize_text(address)
        if any(keyword in normalized_address for keyword in excluded_keywords):
            continue
        score = sum(1 for keyword in preferred_keywords if keyword in normalized_address)
        if score > best_score and score > 0:
            best_address = address
            best_score = score
    return best_address


def _arena_match_score(address, combined_text):
    parts = [_normalize_text(part) for part in str(address).split(":")]
    score = 0
    for part in parts[1:]:
        if part and part in combined_text:
            score += max(1, len(part.split()))
    return score


def _parent_arena_address(address):
    if not address:
        return None
    parts = str(address).split(":")
    if len(parts) >= 3:
        return ":".join(parts[:3])
    return address


def resolve_known_object_address(persona, target=None, detail=None):
    combined_text = _combined_text(target, detail)
    for canonical_name, hints in KNOWN_OBJECT_HINTS.items():
        if any(hint in combined_text for hint in hints):
            for candidate_name in [canonical_name] + hints:
                address = persona.s_mem.find_nearest_object(candidate_name)
                if address:
                    return address, candidate_name, "known_object"
    return None, None, None


def resolve_matching_object_address(persona, target=None, detail=None):
    combined_text = _combined_text(target, detail)
    best_match = None
    best_score = -1
    for obj_name, address in _iter_object_entries(persona):
        normalized_obj = _normalize_text(obj_name)
        if normalized_obj and normalized_obj in combined_text:
            score = len(normalized_obj)
            if score > best_score:
                best_match = (address, obj_name, "direct_object_match")
                best_score = score
    return best_match or (None, None, None)


def resolve_known_arena_address(maze, target=None, detail=None):
    combined_text = _combined_text(target, detail)
    for rule in KNOWN_ARENA_RULES:
        if any(trigger in combined_text for trigger in rule["triggers"]):
            arena_address = _find_matching_arena_address(
                maze,
                rule["preferred_keywords"],
                rule.get("excluded_keywords", []),
            )
            if arena_address:
                return arena_address, arena_address.split(":")[-1], "known_arena"
    return None, None, None


def resolve_matching_arena_address(maze, target=None, detail=None):
    combined_text = _combined_text(target, detail)
    best_match = None
    best_score = -1
    for address in _iter_arena_addresses(maze):
        score = _arena_match_score(address, combined_text)
        if score > best_score:
            best_match = address
            best_score = score
    if best_match and best_score > 0:
        return best_match, best_match.split(":")[-1], "direct_arena_match"
    return None, None, None


def resolve_action_target_address(persona, maze, normalized_skill_id, target=None, detail=None):
    target = str(target or "").strip()
    detail = str(detail or "").strip()
    skill_id = _normalize_text(normalized_skill_id)

    object_address, resolved_name, resolved_kind = resolve_known_object_address(
        persona,
        target=target,
        detail=detail,
    )
    if object_address:
        if skill_id in ARENA_ONLY_SKILLS:
            arena_address = _parent_arena_address(object_address)
            return arena_address, {
                "kind": f"{resolved_kind}_parent_arena",
                "matched": resolved_name,
            }
        return object_address, {"kind": resolved_kind, "matched": resolved_name}

    direct_object_address, resolved_name, resolved_kind = resolve_matching_object_address(
        persona,
        target=target,
        detail=detail,
    )
    if direct_object_address:
        if skill_id in ARENA_ONLY_SKILLS:
            arena_address = _parent_arena_address(direct_object_address)
            return arena_address, {
                "kind": f"{resolved_kind}_parent_arena",
                "matched": resolved_name,
            }
        return direct_object_address, {"kind": resolved_kind, "matched": resolved_name}

    arena_address, resolved_name, resolved_kind = resolve_known_arena_address(
        maze,
        target=target,
        detail=detail,
    )
    if arena_address:
        return arena_address, {"kind": resolved_kind, "matched": resolved_name}

    arena_address, resolved_name, resolved_kind = resolve_matching_arena_address(
        maze,
        target=target,
        detail=detail,
    )
    if arena_address:
        return arena_address, {"kind": resolved_kind, "matched": resolved_name}

    return None, None
