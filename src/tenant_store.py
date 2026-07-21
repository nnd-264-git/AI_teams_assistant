import json
import os

_STORE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tenants.json")


def _load() -> list:
    if not os.path.exists(_STORE_PATH):
        return []
    with open(_STORE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(tenants: list) -> None:
    with open(_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(tenants, f, indent=2)


def list_tenants() -> list:
    return _load()


def add_tenant(tenant_id: str, label: str = "") -> None:
    tenants = _load()
    if any(t["tenant_id"] == tenant_id for t in tenants):
        return
    tenants.append({"tenant_id": tenant_id, "label": label or tenant_id})
    _save(tenants)
