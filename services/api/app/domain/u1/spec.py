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

# PRD 14.1 参数分组：编号前缀 -> 分组名称（顺序即页面展示顺序）。
BLOCK_ORDER = (
    "城市与市场",
    "政策准入",
    "站点空间",
    "成本参数",
    "阶段参数",
    "效率与风险",
    "辅助收入",
    "战略情景",
)
BLOCK_BY_PREFIX = {prefix: block for prefix, block in zip("CPSBDEAZ", BLOCK_ORDER)}
# 值只能从固定清单中选择的枚举参数（PRD 12.3 字段字典）。
ENUM_PARAMETER_OPTIONS: dict[str, tuple[str, ...]] = {
    "C2": ("一线", "新一线", "二线", "三线"),
    "C12": ("盈利型", "政治型", "混合型"),
    "P10": ("是", "否"),
    "P11": ("是", "否"),
    "B3": ("挂证", "全职", "兼任"),
    "D4": ("线性", "S曲线"),
    "Z1": ("自营", "收购"),
    "Z5": ("乐观", "基准", "悲观"),
}


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
    required_fields = {"id", "name", "unit", "excelCell", "inputKind", "valueType", "stage", "sourceType", "required", "parityStatus", "block", "blockOrder"}
    for parameter_id in EXPECTED_PARAMETER_IDS:
        entry = catalog.get(parameter_id)
        if entry is None:
            errors.append(f"Missing parameter: {parameter_id}")
            continue
        missing = sorted(required_fields - entry.keys())
        if missing:
            errors.append(f"{parameter_id} missing fields: {','.join(missing)}")
            continue
        if not re.fullmatch(r"控制台!E\d+", str(entry.get("excelCell", ""))):
            errors.append(f"{parameter_id} has invalid Excel cell: {entry.get('excelCell')}")
        expected_block = BLOCK_BY_PREFIX.get(parameter_id[0])
        if entry.get("block") != expected_block:
            errors.append(f"{parameter_id} block must be {expected_block}, got {entry.get('block')}")
        expected_order = BLOCK_ORDER.index(expected_block) + 1 if expected_block else None
        if entry.get("blockOrder") != expected_order:
            errors.append(f"{parameter_id} blockOrder must be {expected_order}, got {entry.get('blockOrder')}")
        if parameter_id in ENUM_PARAMETER_OPTIONS:
            expected_options = list(ENUM_PARAMETER_OPTIONS[parameter_id])
            options = entry.get("options")
            if not isinstance(options, list) or options != expected_options:
                errors.append(f"{parameter_id} options must be {expected_options}, got {options}")
            elif len(set(options)) != len(options):
                errors.append(f"{parameter_id} options contain duplicates")
    return errors
