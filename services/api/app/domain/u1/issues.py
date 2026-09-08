from .models import ModelIssue
from .spec import load_json_spec, load_parameter_catalog


def load_known_issues() -> tuple[ModelIssue, ...]:
    payload = load_json_spec("issues/u1.issues.json")
    issues = payload.get("issues")
    if not isinstance(issues, list):
        raise ValueError("The U1 issue spec must contain an issues list")
    return tuple(ModelIssue(**issue) for issue in issues)


def missing_input_issue(parameter_id: str) -> ModelIssue:
    excel_cell = load_parameter_catalog().get(parameter_id, {}).get("excelCell", f"控制台!{parameter_id}")
    return ModelIssue(
        code="MISSING_REQUIRED_INPUT",
        excelCell=excel_cell,
        severity="error",
        status="blocked",
        message=f"Required U1 input {parameter_id} is missing but is used by the current Excel formulas.",
    )
