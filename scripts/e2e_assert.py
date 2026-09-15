#!/usr/bin/env python3
"""端到端验证的断言与格式化助手（避免 shell 与 Python 的引号嵌套地狱）。

用法：<命令输出> | python3 scripts/e2e_assert.py <step-name>
每个 step 对应一段解析逻辑，解析失败或断言不通过时以非零码退出。
"""

from __future__ import annotations

import json
import os
import sys


def money(value) -> str:
    return "—" if value is None else str(value)


def pct(value) -> str:
    return f"{value:.0%}" if isinstance(value, (int, float)) else "—"


def step_targets(data: dict) -> None:
    print(f"   字段目录：{len(data['fieldCatalog'])} 个自动爬虫字段")
    print(f"   禁止估算：{data['neverEstimateFields']}")
    print(f"   字段族：{len(data['fieldFamilies'])} 组")
    for family in data["fieldFamilies"]:
        print(f"     · {family['family']}（{len(family['fields'])} 字段）→ {family['sourceHint']}")
    for city in data["cities"]:
        print(f"   城市 {city['cityName']}：{len(city['sources'])} 个来源")
        for source in city["sources"]:
            print(
                f"     · {source['name']}：待填 {len(source['fieldsToFill'])} 个字段，"
                f"已有值 {len(source['alreadyFilled'])} 个"
            )


def step_fetch(data: dict) -> None:
    assert data["succeeded"] == 1, data
    assert data["failed"] == 0, data
    print(f"   成功 {data['succeeded']} / 失败 {data['failed']} / 未变 {data['unchanged']}")
    for item in data["results"]:
        if item["status"] != "success":
            print(f"   ✗ {item['url']}: {item['errorMessage']}")
            continue
        print(f"   changeStatus={item['changeStatus']} httpStatus={item['httpStatus']}")
        print(f"   artifactId={item['artifactId']}")
        print(f"   sha256={(item['sha256'] or '')[:16]}…  正文长度={item['textLength']}")
        print(f"   正文片段：{(item['text'] or '')[:70]}…")


def step_crawl_all(data: dict) -> None:
    assert data["total"] == 1, data
    assert data["succeeded"] == 1, data
    assert data["failed"] == 0, data
    assert data["changed"] + data["unchanged"] == 1, data
    item = data["results"][0]
    assert item["status"] == "success", item
    assert item["changeStatus"] in {"first_fetch", "new_version", "unchanged"}, item
    print(f"   全部来源：{data['total']} 个；成功 {data['succeeded']}；有更新 {data['changed']}；未变 {data['unchanged']}")


def step_onboarding(data: dict) -> None:
    assert data["status"] == "completed", data
    assert data["discoveredCount"] >= 1, data
    assert data["officialSourceCount"] >= 1, data
    assert data["crawledCount"] >= 1, data
    assert data["suggestionCount"] >= 17, data
    print(
        f"   {data['cityName']} 入场完成：发现 {data['discoveredCount']} 个来源，"
        f"正式来源 {data['officialSourceCount']} 个，建议值 {data['suggestionCount']} 个"
    )


def step_artifacts(data: list[dict]) -> None:
    assert data, "没有抓取原文记录"
    artifact = data[0]
    assert artifact["status"] == "success", artifact
    assert artifact.get("storedPath"), artifact
    print(f"   原文记录：{artifact['artifactId']}；指纹 {(artifact.get('sha256') or '')[:16]}…")


def step_artifact_content(raw: str) -> None:
    assert "长沙市长期护理保险实施办法" in raw, raw[:300]
    assert "基金支付比例" in raw, raw[:300]
    print(f"   原文回看成功：{len(raw.encode('utf-8'))} bytes")


def step_submission(data: dict) -> None:
    print(
        f"   结果：{data['resultStatus']}  "
        f"接受 {data['acceptedCount']} / 拒绝 {data['rejectedCount']}"
    )
    print(f"   未披露字段：{data['notDisclosed']}   影响场景数：{data['affectedScenarioCount']}")
    print("   已接受：")
    for item in data["accepted"]:
        print(f"     ✓ {item['fieldId']} = {money(item['value'])} (置信 {pct(item.get('confidence'))})")
    if data["rejected"]:
        print("   被拒绝（防幻觉闸门）：")
        for item in data["rejected"]:
            print(f"     ✗ {item['fieldId']}: {item['reason']}")
    for warn in data.get("warnings", []):
        print(f"     ⚠ {warn['fieldId']}: {warn['warning']}")


def step_city_values(data: dict) -> None:
    by_id = {field["fieldId"]: field for field in data["fields"]}
    expected_ids = (
        "C2", "C3", "C4", "C5", "C10", "C11", "C13",
        "P1", "P2", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11",
    )
    assert all(field_id in by_id for field_id in expected_ids), by_id.keys()
    for field_id in expected_ids:
        field = by_id.get(field_id)
        assert field is not None and field.get("suggestedValue") is not None, field_id
        assert field.get("valueState") == "suggestion_ready", field
        baseline_raw = os.environ.get("E2E_BASELINE_INPUTS", "")
        if baseline_raw:
            baseline = json.loads(baseline_raw)
            assert field.get("currentValue") == baseline.get(field_id), f"建议值静默覆盖当前参数：{field_id}"
        source = field.get("suggestedSource") or {}
        assert source.get("artifactId"), field
        assert source.get("quote"), field
        print(
            f"   {field_id} {field['name']}: {money(field['suggestedValue'])}"
            f" ({field['valueState']}, 置信 {pct(source.get('confidence'))})"
        )
        print(f"        原文引用：{(source.get('quote') or '')[:46]}")


def step_dashboard(data: dict) -> None:
    cities = {city["cityId"]: city for city in data.get("cities", [])}
    assert "changsha" in cities, data
    print(f"   总览已读取长沙：{cities['changsha']['cityName']}（{cities['changsha']['dataStatus']}）")


def step_export_json(data: dict) -> None:
    assert data.get("cityId") == "changsha", data
    assert data.get("fieldValues"), data
    assert any(row.get("fieldId") == "P1" for row in data["fieldValues"]), data
    print(f"   JSON 导出字段：{len(data['fieldValues'])} 条，来源 {len(data.get('sources', []))} 个")


def step_export_csv(raw: str) -> None:
    assert "参数编号" in raw.splitlines()[0].lstrip("\ufeff"), raw[:300]
    assert "P1" in raw, raw[:300]
    print(f"   CSV 导出成功：{len(raw.encode('utf-8'))} bytes")


def step_candidates(data: dict) -> None:
    print(f"   入池 {data['createdCount']} 条，跳过 {data['skippedCount']} 条")
    for item in data["created"]:
        print(f"     + {item['name']} ({item['domain']}) 目标字段 {item['targetFields']}")
    for item in data["skipped"]:
        print(f"     - 跳过 {item['url']}: {item['reason']}")


def step_sources(items: list[dict]) -> None:
    for source in items:
        print(f"   · {source['name']}  [{source['status']}]  {source.get('url') or '无链接'}")


def step_submissions(items: list[dict]) -> None:
    if not items:
        print("   （无回传记录）")
    for item in items:
        print(
            f"   run={item['agentRunId']} ver={item.get('agentVersion')} "
            f"接受 {item['acceptedCount']} 拒绝 {item['rejectedCount']} @ {item['submittedAt'][:19]}"
        )


STEPS = {
    "targets": step_targets,
    "fetch": step_fetch,
    "crawl-all": step_crawl_all,
    "onboarding": step_onboarding,
    "artifacts": step_artifacts,
    "artifact-content": step_artifact_content,
    "submission": step_submission,
    "city-values": step_city_values,
    "dashboard": step_dashboard,
    "export-json": step_export_json,
    "export-csv": step_export_csv,
    "candidates": step_candidates,
    "sources": step_sources,
    "submissions": step_submissions,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in STEPS:
        print(f"用法：{sys.argv[0]} <{'|'.join(STEPS)}>", file=sys.stderr)
        return 2
    raw = sys.stdin.read()
    if sys.argv[1] in {"artifact-content", "export-csv"}:
        STEPS[sys.argv[1]](raw)
        return 0
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        print(f"   解析响应失败：{error}", file=sys.stderr)
        print(f"   原始响应：{raw[:300]}", file=sys.stderr)
        return 1
    STEPS[sys.argv[1]](data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
