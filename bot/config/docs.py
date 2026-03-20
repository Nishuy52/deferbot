import os
import yaml

with open(os.path.join(os.path.dirname(__file__), "deferment_docs.yaml")) as f:
    DEFERMENT_TYPES: dict = yaml.safe_load(f)

TYPE_KEYS = list(DEFERMENT_TYPES.keys())


def get_type_label(key: str) -> str:
    return DEFERMENT_TYPES.get(key, {}).get("label", key)


def get_required_docs(type_key: str) -> list[dict]:
    return DEFERMENT_TYPES.get(type_key, {}).get("docs", [])


def get_missing_docs(type_key: str, uploaded: list[str]) -> list[dict]:
    done = set(uploaded)
    return [d for d in get_required_docs(type_key) if d["key"] not in done]


def format_type_menu(esc=None) -> str:
    """Format the type selection menu. Pass esc= for MarkdownV2 escaping."""
    e = esc or (lambda x: x)
    return "\n".join(f"{i+1}\\. {e(DEFERMENT_TYPES[k]['label'])}" for i, k in enumerate(TYPE_KEYS))


def type_key_from_index(n: int) -> str | None:
    try:
        return TYPE_KEYS[n - 1]
    except IndexError:
        return None


def get_doc_label(type_key: str, doc_key: str) -> str:
    """Return the human-readable label for a document key within a deferment type."""
    for d in get_required_docs(type_key):
        if d["key"] == doc_key:
            return d["label"]
    return doc_key


def doc_key_from_index(type_key: str, n: int) -> dict | None:
    """Return the doc dict for 1-based index n within a deferment type's required docs."""
    docs = get_required_docs(type_key)
    try:
        return docs[n - 1]
    except IndexError:
        return None
