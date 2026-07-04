import json
import os
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
BASE_SIM_ROOT = ROOT / "environment" / "frontend_server" / "storage" / "base_the_ville_n25"
BASE_ENV_SNAPSHOT = BASE_SIM_ROOT / "environment" / "0.json"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "numpy" not in sys.modules:
    numpy_stub = types.ModuleType("numpy")
    numpy_stub.dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    numpy_linalg_stub = types.ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda a: sum(x * x for x in a) ** 0.5
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub

if "openai" not in sys.modules:
    openai_stub = types.SimpleNamespace(
        api_key=None,
        api_base=None,
        ChatCompletion=types.SimpleNamespace(
            create=lambda **kwargs: {"choices": [{"message": {"content": "stub"}}]}
        ),
        Embedding=types.SimpleNamespace(
            create=lambda **kwargs: {"data": [{"embedding": [1.0, 0.0]}]}
        ),
    )
    sys.modules["openai"] = openai_stub


@contextmanager
def pushd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


with pushd(BACKEND_ROOT):
    from maze import Maze
    from path_finder import path_finder
    from persona.cognitive_modules.execute import (
        _expand_to_approach_tiles,
        _is_valid_navigation_path,
    )
    from utils import collision_block_id


def load_base_environment():
    return json.loads(BASE_ENV_SNAPSHOT.read_text(encoding="utf-8"))


def find_apple_tree_addresses(maze):
    return sorted(
        address
        for address in maze.address_tiles.keys()
        if address.lower().endswith(":apple tree")
    )


def resolve_reachable_path(maze, start_tile, target_address):
    raw_target_tiles = list(maze.address_tiles[target_address])
    approach_tiles = _expand_to_approach_tiles(maze, raw_target_tiles) or raw_target_tiles
    approach_tiles = sorted(
        approach_tiles,
        key=lambda tile: abs(tile[0] - start_tile[0]) + abs(tile[1] - start_tile[1]),
    )

    best_path = None
    best_target_tile = None
    for target_tile in approach_tiles:
        curr_path = path_finder(
            maze.collision_maze,
            start_tile,
            target_tile,
            collision_block_id,
        )
        if not _is_valid_navigation_path(start_tile, target_tile, curr_path):
            continue
        if best_path is None or len(curr_path) < len(best_path):
            best_path = curr_path
            best_target_tile = target_tile

    return {
        "raw_target_tiles": raw_target_tiles,
        "approach_tiles": approach_tiles,
        "target_tile": best_target_tile,
        "path": best_path,
    }


def find_nearby_reachable_tiles(maze, start_tile, raw_target_tiles, radius=3, limit=8):
    candidates = []
    seen = set()
    for raw_x, raw_y in raw_target_tiles:
        for x in range(raw_x - radius, raw_x + radius + 1):
            for y in range(raw_y - radius, raw_y + radius + 1):
                tile = (x, y)
                if tile in seen:
                    continue
                seen.add(tile)
                if x < 0 or y < 0 or x >= maze.maze_width or y >= maze.maze_height:
                    continue
                if maze.access_tile(tile)["collision"]:
                    continue
                curr_path = path_finder(
                    maze.collision_maze,
                    start_tile,
                    tile,
                    collision_block_id,
                )
                if not _is_valid_navigation_path(start_tile, tile, curr_path):
                    continue
                candidates.append((tile, len(curr_path)))
    candidates.sort(key=lambda item: item[1])
    return candidates[:limit]


class NpcAppleTreePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with pushd(BACKEND_ROOT):
            cls.maze = Maze("the_ville")
        cls.base_env = load_base_environment()
        cls.apple_tree_addresses = find_apple_tree_addresses(cls.maze)

    def test_map_contains_apple_tree_targets(self):
        self.assertTrue(
            self.apple_tree_addresses,
            "地图里没有找到 apple tree 地址，测试前提不成立。",
        )

    def test_all_default_npcs_can_reach_all_apple_trees(self):
        failures = []

        for persona_name, env_entry in sorted(self.base_env.items()):
            start_tile = (int(env_entry["x"]), int(env_entry["y"]))
            reachable_count = 0
            for target_address in self.apple_tree_addresses:
                result = resolve_reachable_path(self.maze, start_tile, target_address)
                if result["path"]:
                    reachable_count += 1

            if reachable_count > 0:
                continue

            for target_address in self.apple_tree_addresses:
                result = resolve_reachable_path(self.maze, start_tile, target_address)
                failures.append(
                    {
                        "persona": persona_name,
                        "start_tile": start_tile,
                        "target_address": target_address,
                        "raw_target_tiles": result["raw_target_tiles"],
                        "approach_tiles": result["approach_tiles"],
                        "nearby_reachable_tiles": find_nearby_reachable_tiles(
                            self.maze,
                            start_tile,
                            result["raw_target_tiles"],
                        ),
                    }
                )

        if failures:
            failure_lines = [
                (
                    f"{item['persona']} start={item['start_tile']} -> {item['target_address']} "
                    f"raw={item['raw_target_tiles']} approach={item['approach_tiles']} "
                    f"nearby_reachable={item['nearby_reachable_tiles']}"
                )
                for item in failures
            ]
            self.fail(
                "以下默认 NPC 出生点无法走到任何苹果树：\n" + "\n".join(failure_lines)
            )


if __name__ == "__main__":
    unittest.main()
