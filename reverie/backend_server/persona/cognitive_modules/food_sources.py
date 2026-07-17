from object_affordances import default_registry


# Compatibility export for callers outside this module.  Its contents come
# from configuration rather than a source-code list.
VALID_GATHER_FOOD_SOURCES = frozenset(
    default_registry.find_objects_by_affordance("satiety", "can_gather_food")
)


def normalize_food_source_target(target):
    t_lower = target.lower().strip() if target else ""
    if "refrigerator" in t_lower or "fridge" in t_lower:
        return "refrigerator"
    if "stove" in t_lower:
        return "stove"
    if "cafe customer seating" in t_lower:
        return "cafe counter"
    if "behind the cafe counter" in t_lower:
        return "cafe counter"
    if "cooked meal" in t_lower:
        return "cafe counter"
    if t_lower in {"cafe", "café"}:
        return "cafe counter"
    if "cafe" in t_lower and "counter" in t_lower:
        return "cafe counter"
    if "counter" in t_lower and "cafe" in t_lower:
        return "cafe counter"
    if "apple_tree" in t_lower or ("apple" in t_lower and "tree" in t_lower) or t_lower == "tree":
        return "apple tree"
    return target


def is_valid_gather_food_source(target):
    normalized = normalize_food_source_target(target)
    return default_registry.has_affordance(normalized, "satiety", "can_gather_food")
