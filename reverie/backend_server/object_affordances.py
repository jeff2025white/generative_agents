"""Semantic object affordances shared by planning and map loading.

The JSON configuration is intentionally the single source of truth for
object capabilities.  This module has no Maze dependency so it is also safe
to use in lightweight unit tests and command translation helpers.
"""
import json
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).with_name("object_properties.json")


class ObjectAffordanceRegistry:
  def __init__(self, config_path=DEFAULT_CONFIG_PATH):
    with open(config_path, encoding="utf-8") as config_file:
      raw_props = json.load(config_file)
    self._props = {
      name.strip().lower(): value
      for name, value in raw_props.items()
      if not name.startswith("_")
    }

  def get_affordances(self, object_name):
    return self._props.get(str(object_name or "").strip().lower(), {}).get("affordances", {})

  def has_affordance(self, object_name, motive_key, capability):
    return bool(self.get_affordances(object_name).get(motive_key, {}).get(capability))

  def has_any_affordance(self, object_name, motive_key):
    return bool(self.get_affordances(object_name).get(motive_key))

  def find_objects_by_affordance(self, motive_key, capability):
    return [
      object_name for object_name in self._props
      if self.has_affordance(object_name, motive_key, capability)
    ]

  def get_purpose_text(self, object_name):
    return self._props.get(str(object_name or "").strip().lower(), {}).get("display", {}).get("purpose_text", "")

  def get_emoji(self, object_name):
    return self._props.get(str(object_name or "").strip().lower(), {}).get("display", {}).get("emoji", "")

  def get_gather_description(self, object_name):
    return self.get_affordances(object_name).get("satiety", {}).get("gather_description", "")


default_registry = ObjectAffordanceRegistry()
