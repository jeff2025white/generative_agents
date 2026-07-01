"""
Helpers for building structured creator-to-agent chat context.
"""

from persona.cognitive_modules.retrieve import new_retrieve


def _stringify_inventory(inventory):
  if not inventory:
    return "empty"
  parts = []
  for item, count in inventory.items():
    parts.append(f"{item} x{count}")
  return ", ".join(parts)


def _format_conversation_history(conversation_history, limit=6):
  if not conversation_history:
    return "- No recent creator conversation"

  lines = []
  for turn in conversation_history[-limit:]:
    role = str(turn.get("role", "unknown"))
    content = str(turn.get("content", "")).strip()
    if not content:
      continue
    speaker = "Creator" if role == "user" else "Agent"
    lines.append(f"- {speaker}: {content}")

  return "\n".join(lines) if lines else "- No recent creator conversation"


def _build_self_state(persona):
  scratch = persona.scratch
  return (
    f"- Satiety: {float(scratch.satiety):.1f}\n"
    f"- Stamina: {float(scratch.stamina):.1f}\n"
    f"- Health: {float(scratch.health):.1f}\n"
    f"- Mood: {float(scratch.mood):.1f}\n"
    f"- Current action: {scratch.act_description}\n"
    f"- Inventory: {_stringify_inventory(scratch.inventory)}"
  )


def _build_environment(persona, maze):
  tile = persona.scratch.curr_tile
  if not tile:
    return "- Current tile unavailable"

  world = maze.get_tile_path(tile, "world")
  sector = maze.get_tile_path(tile, "sector")
  arena = maze.get_tile_path(tile, "arena")
  obj = maze.get_tile_path(tile, "game object")
  return (
    f"- World: {world}\n"
    f"- Sector: {sector}\n"
    f"- Area: {arena}\n"
    f"- Object: {obj}\n"
    f"- Address: {persona.scratch.act_address}"
  )


def _build_plans(persona, limit=8):
  schedule = getattr(persona.scratch, "f_daily_schedule", []) or []
  if not schedule:
    return "- No active schedule"
  lines = []
  for item in schedule[:limit]:
    if isinstance(item, (list, tuple)) and len(item) >= 2:
      lines.append(f"- {item[0]} ({item[1]} minutes)")
    else:
      lines.append(f"- {item}")
  return "\n".join(lines)


def _build_memories(persona, user_message, limit=8):
  focal_points = [user_message, persona.name]
  try:
    retrieved = new_retrieve(persona, focal_points, limit)
  except Exception:
    return "- Failed to retrieve relevant memories"

  lines = []
  for nodes in retrieved.values():
    for node in nodes:
      desc = str(getattr(node, "description", "") or getattr(node, "embedding_key", "")).strip()
      if not desc:
        continue
      lines.append(f"- {desc}")
      if len(lines) >= limit:
        return "\n".join(lines)

  return "\n".join(lines) if lines else "- No relevant memory retrieved"


def _build_relationships(persona, limit=8):
  graph = getattr(persona.a_mem, "social_relationship_graph", {}) or {}
  relations = graph.get("relations", {})
  if not relations:
    return "- No strong relationships recorded"

  lines = []
  for target_name, rel in list(relations.items())[:limit]:
    relationship = rel.get("relationship", "stranger")
    trust = float(rel.get("trust", 0.5))
    recent_events = rel.get("recent_events", [])
    recent_note = recent_events[-1] if recent_events else "none"
    lines.append(
      f"- {target_name}: relationship={relationship}, trust={trust:.2f}, recent={recent_note}"
    )
  return "\n".join(lines)


def build_creator_query_context(persona, maze, user_message, conversation_history=None):
  return {
    "self_state": _build_self_state(persona),
    "environment": _build_environment(persona, maze),
    "plans": _build_plans(persona),
    "memories": _build_memories(persona, user_message),
    "relationships": _build_relationships(persona),
    "history": _format_conversation_history(conversation_history or []),
  }


def build_creator_instruction_context(persona, maze, user_message, conversation_history=None):
  query_context = build_creator_query_context(persona, maze, user_message, conversation_history)
  return {
    "self_state": query_context["self_state"],
    "environment": query_context["environment"],
    "memories": query_context["memories"],
    "history": query_context["history"],
  }


def build_creator_notify_context(persona, maze, user_message, conversation_history=None):
  instruction_context = build_creator_instruction_context(persona, maze, user_message, conversation_history)
  return {
    "self_state": instruction_context["self_state"],
    "memories": instruction_context["memories"],
    "history": instruction_context["history"],
  }
