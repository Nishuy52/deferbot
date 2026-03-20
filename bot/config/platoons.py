import os
import yaml

with open(os.path.join(os.path.dirname(__file__), "platoons.yaml")) as f:
    _data = yaml.safe_load(f)

PLATOONS: list[str] = _data["platoons"]


def format_platoon_menu() -> str:
    return "\n".join(f"{i+1}\\. {p}" for i, p in enumerate(PLATOONS))


def platoon_from_index(n: int) -> str | None:
    try:
        return PLATOONS[n - 1]
    except IndexError:
        return None
