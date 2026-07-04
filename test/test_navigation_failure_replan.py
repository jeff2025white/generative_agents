import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "openai" not in sys.modules:
    openai_stub = SimpleNamespace(
        api_key=None,
        api_base=None,
        ChatCompletion=SimpleNamespace(create=lambda **kwargs: {"choices": [{"message": {"content": "stub"}}]}),
        Embedding=SimpleNamespace(create=lambda **kwargs: {"data": [{"embedding": [1.0, 0.0]}]}),
    )
    sys.modules["openai"] = openai_stub

if "numpy" not in sys.modules:
    numpy_stub = ModuleType("numpy")
    numpy_stub.dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    numpy_linalg_stub = ModuleType("numpy.linalg")
    numpy_linalg_stub.norm = lambda a: sum(x * x for x in a) ** 0.5
    numpy_stub.linalg = numpy_linalg_stub
    sys.modules["numpy"] = numpy_stub
    sys.modules["numpy.linalg"] = numpy_linalg_stub


from path_finder import path_finder
from persona.cognitive_modules.execute import _is_valid_navigation_path


class NavigationFailureReplanTests(unittest.TestCase):
    def test_path_finder_returns_empty_for_unreachable_target(self):
        maze = [
            ["X", "X", "X"],
            ["X", "X", "X"],
            ["X", "X", "X"],
        ]

        path = path_finder(maze, (0, 0), (2, 2), "X")

        self.assertEqual(path, [])

    def test_navigation_path_validator_rejects_single_tile_fake_path(self):
        self.assertFalse(
            _is_valid_navigation_path(
                curr_tile=[77, 16],
                target_tile=[24, 44],
                path=[(24, 44)],
            )
        )
        self.assertTrue(
            _is_valid_navigation_path(
                curr_tile=[24, 44],
                target_tile=[24, 44],
                path=[(24, 44)],
            )
        )


if __name__ == "__main__":
    unittest.main()
