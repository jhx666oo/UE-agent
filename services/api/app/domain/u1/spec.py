import json
import re
from pathlib import Path
from typing import Any


EXPECTED_PARAMETER_IDS = (
    [f"C{i}" for i in range(1, 14)]
    + [f"P{i}" for i in range(1, 12)]
    + [f"S{i}" for i in range(1, 9)]
    + [f"B{i}" for i in range(1, 17)]
    + [f"D{i}" for i in range(1, 9)]
    + [f"E{i}" for i in range(1, 9)]
    + [f"A{i}" for i in range(1, 7)]
    + [f"Z{i}" for i in range(1, 6)]
)


def repository_root() -> Path:
    for parent in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
        if (parent / "packages" / "model-spec").is_dir():
            return parent
    raise FileNotFoundError("Cannot locate packages/model-spec from the U1 service")


def load_json_spec(relative_path: str) -> Any:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Model spec paths must stay inside packages/model-spec")
    path = repository_root() / "packages" / "model-spec" / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def load_parameter_catalog() -> dict[str, dict[str, Any]]:
    payload = load_json_spec("parameters/u1.parameters.json")
    entries = payload.get("parameters")
    if not isinstance(entries, list) or not entries:
        raise ValueError("The U1 parameter spec must contain a non-empty parameters list")
    catalog: dict[str, dict[str, Any]] = {}
    for entry in entries:
        parameter_id = entry.get("id")
        if parameter_id in catalog:
            raise ValueError(f"Duplicate U1 parameter id: {parameter_id}")
        catalog[parameter_id] = entry
    return catalog


def validate_parameter_catalog(catalog: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if tuple(catalog) != tuple(EXPECTED_PARAMETER_IDS):
        errors.append("Parameter IDs must cover C/P/S/B/D/E/A/Z groups in Excel order")
    required_fields = {"id", "name", "unit", "excelCell", "inputKind", "valueType", "stage", "sourceType", "required", "parityStatus"}
    for parameter_id in EXPECTED_PARAMETER_IDS:
        entry = catalog.get(parameter_id)
        if entry is None:
            errors.append(f"Missing parameter: {parameter_id}")
            continue
        missing = sorted(required_fields - entry.keys())
        if missing:
            errors.append(f"{parameter_id} missing fields: {','.join(missing)}")
        if not re.fullmatch(r"控制台!E\d+", str(entry.get("excelCell", ""))):
            errors.append(f"{parameter_id} has invalid Excel cell: {entry.get('excelCell')}")
    return errors
