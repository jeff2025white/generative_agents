"""Deterministic address resolution helpers for action targets."""


RESTABLE_OBJECT_TARGETS = ("bed", "sofa", "couch", "chair", "bench")
PLACE_TARGET_CANDIDATES = {
    "study": ("library table", "bookshelf", "desk", "library"),
    "work": ("office", "counter", "computer", "desk", "classroom"),
    "use": ("computer", "game console", "tv", "fitness machine", "pool table", "piano"),
    "leisure_use": ("game console", "tv", "pool table", "piano", "park garden", "cafe customer seating"),
    "hangout_social_venue": ("pub", "bar", "tavern", "rose and crown"),
    "wander": ("park garden", "park", "plaza", "courtyard", "common room"),
}


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
    "chair": ["chair", "armchair"],
    "bench": ["bench", "park bench"],
    "park garden": ["park garden", "garden path"],
}


KNOWN_ARENA_RULES = [
    {
        "triggers": ["park garden", "park", "garden", "courtyard", "plaza"],
        "preferred_keywords": ["park", "garden", "plaza", "courtyard", "green"],
        "excluded_keywords": ["parking"],
    },
    {
        "triggers": ["hobbs cafe", "cafe"],
        "preferred_keywords": ["cafe"],
        "excluded_keywords": [],
    },
    {
        "triggers": ["pub", "bar", "tavern", "rose and crown"],
        "preferred_keywords": ["pub", "bar", "tavern", "cafe"],
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

ARENA_ONLY_SKILLS = {"use", "work", "study", "leisure_use", "hangout_social_venue", "wander"}


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


def _build_resolution_result(ok, *, address=None, target_type=None, matched=None, kind=None, failure_reason=None, candidates=None):
    return {
        "ok": bool(ok),
        "resolved_address": address,
        "resolved_target": matched,
        "target_type": target_type,
        "resolution_kind": kind,
        "failure_reason": failure_reason,
        "candidate_targets": list(candidates or []),
    }


def _get_failed_resource_address_set(persona, target=None):
    scratch = getattr(persona, "scratch", None)
    normalized_target = _normalize_text(target)
    result = set()
    for item in (getattr(scratch, "failed_resource_instances", None) or []):
        if not isinstance(item, dict):
            continue
        item_target = _normalize_text(item.get("target"))
        if normalized_target and item_target and item_target != normalized_target:
            continue
        address = _normalize_text(item.get("target_address"))
        if address:
            result.add(address)
    return result


def _get_successful_resource_address_ranking(persona, target=None):
    scratch = getattr(persona, "scratch", None)
    normalized_target = _normalize_text(target)
    scored_candidates = []
    for item in (getattr(scratch, "successful_resource_instances", None) or []):
        if not isinstance(item, dict):
            continue
        item_target = _normalize_text(item.get("target"))
        if normalized_target and item_target and item_target != normalized_target:
            continue
        address = str(item.get("target_address") or "").strip()
        if not address:
            continue
        try:
            progress_score = float(item.get("progress_score", 0.0) or 0.0)
        except Exception:
            progress_score = 0.0
        try:
            curr_step = int(item.get("curr_step", -1) or -1)
        except Exception:
            curr_step = -1
        scored_candidates.append((progress_score, curr_step, address))

    scored_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    ranked = []
    for _progress_score, _curr_step, address in scored_candidates:
        if address not in ranked:
            ranked.append(address)
    return ranked


def _pick_preferred_address(candidate_addresses, preferred_addresses=None, blocked_addresses=None):
    preferred_addresses = [str(item).strip() for item in (preferred_addresses or []) if str(item).strip()]
    blocked_set = {_normalize_text(item) for item in (blocked_addresses or []) if str(item or "").strip()}
    filtered = [
        str(address).strip()
        for address in (candidate_addresses or [])
        if str(address or "").strip() and _normalize_text(address) not in blocked_set
    ]
    if not filtered:
        return None
    for preferred in preferred_addresses:
        if preferred in filtered:
            return preferred
    return filtered[0]


def _to_arena_address(address):
    return _parent_arena_address(address)


def _get_failed_arena_address_set(persona, target=None):
    object_addresses = _get_failed_resource_address_set(persona, target=target)
    return {_normalize_text(_to_arena_address(address)) for address in object_addresses if _to_arena_address(address)}


def _get_successful_arena_address_ranking(persona, target=None):
    ranked = []
    for address in _get_successful_resource_address_ranking(persona, target=target):
        arena_address = _to_arena_address(address)
        if arena_address and arena_address not in ranked:
            ranked.append(arena_address)
    return ranked


def resolve_known_object_address(persona, target=None, detail=None):
    combined_text = _combined_text(target, detail)
    blocked_addresses = _get_failed_resource_address_set(persona, target=target)
    preferred_addresses = _get_successful_resource_address_ranking(persona, target=target)
    for canonical_name, hints in KNOWN_OBJECT_HINTS.items():
        if any(hint in combined_text for hint in hints):
            candidate_addresses = []
            for candidate_name in [canonical_name] + hints:
                if not getattr(persona, "s_mem", None):
                    continue
                finder = getattr(persona.s_mem, "find_all_objects", None)
                if callable(finder):
                    candidate_addresses.extend(finder(candidate_name))
                else:
                    address = persona.s_mem.find_nearest_object(candidate_name)
                    if address:
                        candidate_addresses.append(address)
            address = _pick_preferred_address(candidate_addresses, preferred_addresses, blocked_addresses)
            if address:
                return address, canonical_name, "known_object"
    return None, None, None


def resolve_candidate_object_address(persona, candidate_names):
    blocked_addresses = _get_failed_resource_address_set(persona)
    preferred_addresses = _get_successful_resource_address_ranking(persona)
    for candidate_name in candidate_names or []:
        candidate_addresses = []
        if getattr(persona, "s_mem", None):
            finder = getattr(persona.s_mem, "find_all_objects", None)
            if callable(finder):
                candidate_addresses.extend(finder(candidate_name))
            else:
                address = persona.s_mem.find_nearest_object(candidate_name)
                if address:
                    candidate_addresses.append(address)
        address = _pick_preferred_address(candidate_addresses, preferred_addresses, blocked_addresses)
        if address:
            return address, candidate_name, "candidate_object"
    return None, None, None


def resolve_candidate_place_address(persona, maze, skill_id, candidate_names):
    for candidate_name in candidate_names or []:
        result = resolve_action_target(persona, maze, skill_id, target=candidate_name, detail=str(candidate_name or ""))
        if result.get("ok"):
            return result.get("resolved_address"), result.get("resolved_target"), result.get("resolution_kind")
    return None, None, None


def resolve_target_persona(personas, target_name):
    normalized_target = _normalize_text(target_name)
    if not normalized_target:
        return None, None
    if isinstance(personas, dict):
        candidates = personas.values()
    else:
        candidates = personas or []
    for candidate in candidates:
        candidate_name = str(getattr(candidate, "name", "") or "").strip()
        if _normalize_text(candidate_name) == normalized_target:
            return candidate, candidate_name
    return None, None


def resolve_persona_target(personas, target_name):
    candidate, candidate_name = resolve_target_persona(personas, target_name)
    if candidate_name:
        return _build_resolution_result(
            True,
            address=f"<persona> {candidate_name}",
            target_type="persona",
            matched=candidate_name,
            kind="persona_target",
        )
    return _build_resolution_result(
        False,
        target_type="persona",
        failure_reason="persona_not_found",
        candidates=[],
    )


def resolve_matching_object_address(persona, target=None, detail=None):
    combined_text = _combined_text(target, detail)
    best_match = None
    best_score = -1
    blocked_addresses = _get_failed_resource_address_set(persona, target=target)
    preferred_addresses = _get_successful_resource_address_ranking(persona, target=target)
    scored_matches = []
    for obj_name, address in _iter_object_entries(persona):
        normalized_obj = _normalize_text(obj_name)
        if normalized_obj and normalized_obj in combined_text:
            score = len(normalized_obj)
            scored_matches.append((score, address, obj_name, "direct_object_match"))
            if score > best_score:
                best_match = (address, obj_name, "direct_object_match")
                best_score = score
    if scored_matches:
        max_score = max(item[0] for item in scored_matches)
        candidate_addresses = [item[1] for item in scored_matches if item[0] == max_score]
        chosen_address = _pick_preferred_address(candidate_addresses, preferred_addresses, blocked_addresses)
        if chosen_address:
            for score, address, obj_name, kind in scored_matches:
                if score == max_score and address == chosen_address:
                    return address, obj_name, kind
    return best_match or (None, None, None)


def resolve_known_arena_address(maze, target=None, detail=None, persona=None):
    combined_text = _combined_text(target, detail)
    blocked_addresses = _get_failed_arena_address_set(persona, target=target) if persona else set()
    preferred_addresses = _get_successful_arena_address_ranking(persona, target=target) if persona else []
    for rule in KNOWN_ARENA_RULES:
        if any(trigger in combined_text for trigger in rule["triggers"]):
            candidate_addresses = []
            for address in _iter_arena_addresses(maze):
                normalized_address = _normalize_text(address)
                if any(keyword in normalized_address for keyword in rule.get("excluded_keywords", [])):
                    continue
                score = sum(1 for keyword in rule["preferred_keywords"] if keyword in normalized_address)
                if score > 0:
                    candidate_addresses.append(address)
            arena_address = _pick_preferred_address(candidate_addresses, preferred_addresses, blocked_addresses)
            if arena_address:
                return arena_address, arena_address.split(":")[-1], "known_arena"
    return None, None, None


def resolve_matching_arena_address(maze, target=None, detail=None, persona=None):
    combined_text = _combined_text(target, detail)
    best_match = None
    best_score = -1
    blocked_addresses = _get_failed_arena_address_set(persona, target=target) if persona else set()
    preferred_addresses = _get_successful_arena_address_ranking(persona, target=target) if persona else []
    scored_matches = []
    for address in _iter_arena_addresses(maze):
        score = _arena_match_score(address, combined_text)
        if score > best_score:
            best_match = address
            best_score = score
        if score > 0:
            scored_matches.append((score, address))
    if scored_matches:
        max_score = max(item[0] for item in scored_matches)
        candidate_addresses = [item[1] for item in scored_matches if item[0] == max_score]
        chosen_address = _pick_preferred_address(candidate_addresses, preferred_addresses, blocked_addresses)
        if chosen_address:
            return chosen_address, chosen_address.split(":")[-1], "direct_arena_match"
    if best_match and best_score > 0 and _normalize_text(best_match) not in blocked_addresses:
        return best_match, best_match.split(":")[-1], "direct_arena_match"
    return None, None, None


def resolve_action_target_address(persona, maze, normalized_skill_id, target=None, detail=None):
    result = resolve_action_target(persona, maze, normalized_skill_id, target=target, detail=detail)
    if not result.get("ok"):
        return None, None
    return result.get("resolved_address"), {
        "kind": result.get("resolution_kind"),
        "matched": result.get("resolved_target"),
    }


def resolve_action_target(persona, maze, normalized_skill_id, target=None, detail=None):
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
            return _build_resolution_result(
                True,
                address=arena_address,
                target_type="place",
                matched=resolved_name,
                kind=f"{resolved_kind}_parent_arena",
            )
        return _build_resolution_result(
            True,
            address=object_address,
            target_type="object",
            matched=resolved_name,
            kind=resolved_kind,
        )

    direct_object_address, resolved_name, resolved_kind = resolve_matching_object_address(
        persona,
        target=target,
        detail=detail,
    )
    if direct_object_address:
        if skill_id in ARENA_ONLY_SKILLS:
            arena_address = _parent_arena_address(direct_object_address)
            return _build_resolution_result(
                True,
                address=arena_address,
                target_type="place",
                matched=resolved_name,
                kind=f"{resolved_kind}_parent_arena",
            )
        return _build_resolution_result(
            True,
            address=direct_object_address,
            target_type="object",
            matched=resolved_name,
            kind=resolved_kind,
        )

    arena_address, resolved_name, resolved_kind = resolve_known_arena_address(
        maze,
        target=target,
        detail=detail,
        persona=persona,
    )
    if arena_address:
        return _build_resolution_result(
            True,
            address=arena_address,
            target_type="place",
            matched=resolved_name,
            kind=resolved_kind,
        )

    arena_address, resolved_name, resolved_kind = resolve_matching_arena_address(
        maze,
        target=target,
        detail=detail,
        persona=persona,
    )
    if arena_address:
        return _build_resolution_result(
            True,
            address=arena_address,
            target_type="place",
            matched=resolved_name,
            kind=resolved_kind,
        )

    return _build_resolution_result(
        False,
        target_type="place" if skill_id in ARENA_ONLY_SKILLS else "object",
        failure_reason="target_not_found",
    )
