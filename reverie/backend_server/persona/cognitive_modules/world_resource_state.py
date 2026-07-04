import json
import os

from persona.cognitive_modules.food_sources import normalize_food_source_target


INFINITE_STOCK = -1
WORLD_RESOURCE_STATE_FILE = "world_resource_state.json"


class WorldResourceState:
  """Track persistent public food-source availability in the world."""

  def __init__(self, stock_by_address=None):
    self.stock_by_address = stock_by_address or {}
    self._refresh_lower_index()


  def _refresh_lower_index(self):
    self._lower_index = {
      str(address).strip().lower(): address
      for address in self.stock_by_address.keys()
    }


  @classmethod
  def load_or_create(cls, sim_folder, maze):
    state_path = os.path.join(sim_folder, WORLD_RESOURCE_STATE_FILE)
    if os.path.exists(state_path):
      try:
        with open(state_path, "r", encoding="utf-8") as infile:
          payload = json.load(infile)
        stock_by_address = payload.get("stock_by_address", payload)
        return cls(stock_by_address=stock_by_address)
      except Exception:
        pass

    state = cls._bootstrap_from_maze(maze)
    state.save(sim_folder)
    return state


  @classmethod
  def _bootstrap_from_maze(cls, maze):
    stock_by_address = {}
    for address in getattr(maze, "address_tiles", {}).keys():
      normalized_target = normalize_food_source_target(address.split(":")[-1])
      if normalized_target == "apple tree":
        stock_by_address[address] = {
          "target": normalized_target,
          "stock": INFINITE_STOCK,
          "kind": "wild_food",
        }
      elif normalized_target in {"refrigerator", "stove", "cafe counter"}:
        stock_by_address[address] = {
          "target": normalized_target,
          "stock": 1,
          "kind": "town_food",
        }
    return cls(stock_by_address=stock_by_address)


  def save(self, sim_folder):
    state_path = os.path.join(sim_folder, WORLD_RESOURCE_STATE_FILE)
    with open(state_path, "w", encoding="utf-8") as outfile:
      json.dump({"stock_by_address": self.stock_by_address}, outfile, ensure_ascii=False, indent=2)


  def canonical_address(self, address):
    if not address:
      return None
    address_text = str(address).strip()
    if address_text in self.stock_by_address:
      return address_text
    return self._lower_index.get(address_text.lower())


  def get_entry(self, address):
    canonical = self.canonical_address(address)
    if not canonical:
      return None
    return self.stock_by_address.get(canonical)


  def get_stock(self, address):
    entry = self.get_entry(address)
    if not entry:
      return None
    return int(entry.get("stock", 0))


  def is_infinite(self, address):
    return self.get_stock(address) == INFINITE_STOCK


  def is_available(self, address):
    stock = self.get_stock(address)
    if stock is None:
      return True
    return stock == INFINITE_STOCK or stock > 0


  def consume(self, address, amount=1):
    canonical = self.canonical_address(address)
    if not canonical:
      return True
    entry = self.stock_by_address.get(canonical)
    stock = int(entry.get("stock", 0))
    if stock == INFINITE_STOCK:
      return True
    if stock < amount:
      return False
    entry["stock"] = max(0, stock - amount)
    return True


  def _matching_addresses(self, target):
    normalized_target = normalize_food_source_target(target)
    matches = []
    for address, entry in self.stock_by_address.items():
      if entry.get("target") == normalized_target:
        matches.append(address)
    return matches


  def has_available_target(self, target):
    for address in self._matching_addresses(target):
      if self.is_available(address):
        return True
    return False


  def available_targets(self):
    targets = []
    seen = set()
    for address, entry in self.stock_by_address.items():
      target = entry.get("target")
      if not target or target in seen:
        continue
      if self.is_available(address):
        targets.append(target)
        seen.add(target)
    return targets


  def describe_address(self, address):
    entry = self.get_entry(address)
    if not entry:
      return "unknown"
    stock = int(entry.get("stock", 0))
    if stock == INFINITE_STOCK:
      return "infinite"
    if stock <= 0:
      return "empty"
    return f"{stock} use left"
