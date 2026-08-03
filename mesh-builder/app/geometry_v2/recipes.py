from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECIPE_PATH = PACKAGE_ROOT / "profiles" / "geometry_recipes_v1.json"
DEFAULT_SCHEMA_PATH = PACKAGE_ROOT / "profiles" / "geometry_recipes_v1.schema.json"


class UnsupportedGeometryProfile(ValueError):
    """Raised when an experimental profile has no explicit reviewed recipe."""


class HeightBandContractError(ValueError):
    """Raised when a recipe omits or misnames a required semantic height group."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load_recipe(profile_id: str, recipe_path: Path = DEFAULT_RECIPE_PATH) -> tuple[dict[str, Any], str]:
    document = json.loads(recipe_path.read_text(encoding="utf-8"))
    schema = json.loads(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(document)
    recipes = [recipe for recipe in document["recipes"] if recipe["profileId"] == profile_id]
    if len(recipes) != 1:
        raise UnsupportedGeometryProfile(f"No unique geometry recipe for profile: {profile_id}")
    recipe = recipes[0]
    if recipe["componentCount"]["minimum"] > recipe["componentCount"]["maximum"]:
        raise ValueError("Recipe component-count range is inverted")
    names = [component["name"] for component in recipe["components"]]
    if len(names) != len(set(names)):
        raise ValueError("Recipe component names must be unique")
    model = recipe["heightBandModel"]
    required_groups = ("shell", "body", "semanticPeak")
    if set(model["groups"]) != set(required_groups):
        raise HeightBandContractError(
            "heightBandModel.groups must define shell, body, semanticPeak"
        )
    available_names = {"base_shell", *names}
    unknown = sorted(
        name for members in model["groups"].values() for name in members if name not in available_names
    )
    if unknown:
        raise HeightBandContractError("heightBandModel references unknown components: " + ", ".join(unknown))
    digest = hashlib.sha256(canonical_json_bytes(recipe)).hexdigest()
    return recipe, digest
