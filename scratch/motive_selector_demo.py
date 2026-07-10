import sys
from pathlib import Path
from pprint import pformat


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "reverie" / "backend_server"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from persona.cognitive_modules.motive_selector import select_motives


def print_case(title, motive_attributes):
    result = select_motives(motive_attributes)
    print(f"=== {title} ===")
    print("Input:")
    print(pformat(motive_attributes, sort_dicts=False))
    print("Output:")
    print(
        pformat(
            {
                "dominant_motive": result["dominant_motive"],
                "secondary_motive": result["secondary_motive"],
                "guard_motive": result["guard_motive"],
                "motive_sentence": result["motive_sentence"],
                "top_scores": result["scores"][:3],
            },
            sort_dicts=False,
        )
    )
    print()


def main():
    print_case(
        "Hungry And Tired",
        {
            "satiety": {
                "current_value": 22.0,
                "initial_value": 60.0,
                "safe_threshold": 50.0,
                "critical_threshold": 20.0,
            },
            "stamina": {
                "current_value": 35.0,
                "initial_value": 70.0,
                "safe_threshold": 45.0,
                "critical_threshold": 20.0,
            },
            "mood": {
                "current_value": 65.0,
                "initial_value": 60.0,
                "safe_threshold": 50.0,
                "critical_threshold": 30.0,
            },
        },
    )
    print_case(
        "Sad And Embarrassed",
        {
            "mood": {
                "current_value": 28.0,
                "initial_value": 60.0,
                "safe_threshold": 50.0,
                "critical_threshold": 30.0,
            },
            "status": {
                "current_value": 42.0,
                "initial_value": 55.0,
                "safe_threshold": 45.0,
                "critical_threshold": 25.0,
            },
            "autonomy": {
                "current_value": 58.0,
                "initial_value": 60.0,
                "safe_threshold": 50.0,
                "critical_threshold": 30.0,
            },
        },
    )


if __name__ == "__main__":
    main()
