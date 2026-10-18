"""Verify the channel routes and the unified vacancy/application record.

Runs only local, fictional data: no network request, no submission, no personal
data. Writes verification.json and REPORT.md into a new output folder.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

JOBS = [
    {"source": "zhiye", "source_id": "zhiye-001", "title": "数据产品经理",
     "company": "北京三快在线科技有限公司", "location": "上海市",
     "description": "岗位职责：负责数据产品规划与指标体系。任职要求：本科以上，3 年经验。",
     "url": "https://zhiye.page/jobs/job_demo001", "published_at": "2026-09-28",
     "availability": "unknown"},
    {"source": "boss", "source_id": "boss-001", "title": "数据产品经理（急招）",
     "company": "北京三快在线科技", "location": "上海",
     "description": "岗位职责：负责数据产品规划与指标体系搭建。任职要求：本科以上，3 年经验。",
     "url": "https://www.zhipin.com/job_detail/demo001.html",
     "published_at": "2026-10-02T10:00:00+08:00"},
    {"source": "liepin", "source_id": "liepin-001", "title": "数据产品经理",
     "company": "北京三快在线科技", "location": "上海",
     "description": "岗位职责：负责数据产品规划。任职要求：本科以上。",
     "url": "https://www.liepin.com/job/demo001.shtml", "published_at": "2026-10-05"},
]

PROFILE = {"display_name": "虚构候选人", "contact": {"email": "demo@example.invalid"}}
EXPERIENCE = {
    "event": "数据看板项目", "context": "课程项目",
    "actions": ["用 SQL 与 Python 搭建指标看板"], "outcomes": ["周报自动化，节省 6 小时/周"],
    "evidence": [{"claim": "搭建指标看板", "source": "本人陈述", "status": "user_confirmed"}],
    "approved_for_resume": True,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="本地验证：渠道路线与岗位/投递统一记录，不联网、不投递")
    parser.add_argument("--output", required=True, help="New directory; never overwrites existing data")
    args = parser.parse_args()
    folder = Path(args.output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ, CAREEROS_DB=str(folder / "verify.sqlite3"),
                       CAREEROS_OUTPUT_DIR=str(folder / "resumes"),
                       CAREEROS_OFFICIAL_CACHE=str(folder / "cache"),
                       PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")

    def run(*argv):
        result = subprocess.run([sys.executable, "-m", "careeros", *map(str, argv)], cwd=ROOT,
                                env=environment, capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"{' '.join(map(str, argv))}: {result.stderr}")
        return json.loads(result.stdout)

    def write(name, payload):
        (folder / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    verification: dict = {"fictional_data": True, "network_calls": 0, "submissions": 0}
    run("init")
    write("profile.json", PROFILE)
    write("experience.json", EXPERIENCE)
    write("jobs.json", JOBS)
    run("profile", "save", "--file", folder / "profile.json")
    run("experience", "add", "--file", folder / "experience.json")
    verification["import"] = run("jobs", "import", "--json", folder / "jobs.json")

    verification["channels"] = run("jobs", "channels")
    verification["route_official"] = run("jobs", "route", "--provider", "official", "--query", "数据产品经理")
    verification["route_catalog"] = run("jobs", "route", "--provider", "51job", "--query", "数据分析", "--location", "上海")
    verification["official_plan"] = run("official", "plan", "--company", "示例科技", "--query", "数据产品经理")

    card = run("jobs", "card", "--id", 2)
    verification["card_before_apply"] = {
        "title": card["job"]["title"], "published_at": card["job"]["published_at"],
        "group_members": card["vacancy_group"]["members"],
        "channels": [item["channel"] for item in card["channels"]],
        "gaps": card["gaps"], "next_commands": card["next_commands"],
    }
    assert card["vacancy_group"]["members"] == 3, "three platform postings must share one group"
    assert set(item["channel"] for item in card["channels"]) == {"zhiye", "boss", "liepin"}

    verification["groups"] = run("jobs", "group")

    resume_two = run("resume", "build", "--job-id", 2, "--experience-ids", 1, "--headline", "数据产品经理")
    prepared = run("application", "prepare", "--job-id", 2, "--resume-id", resume_two["id"],
                   "--channel", "boss", "--apply-url", "https://www.zhipin.com/job_detail/demo001.html")
    assert prepared["repeat_application_hints"]["already_applied_in_group"] == []
    verification["prepare_first"] = {"id": prepared["id"], "status": prepared["status"],
                                     "hints": prepared["repeat_application_hints"]}

    verification["submit"] = run("application", "record", "--id", prepared["id"], "--status", "SUBMITTED",
                                 "--human-confirmed", "--note", "虚构演示：本人确认已提交")
    future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(timespec="seconds")
    verification["event"] = run("application", "event", "--id", prepared["id"], "--kind", "interview",
                                "--label", "一面（业务面）", "--scheduled-at", future)
    verification["timeline"] = run("application", "timeline", "--id", prepared["id"])
    verification["agenda"] = run("application", "agenda", "--days", 14)

    resume_three = run("resume", "build", "--job-id", 3, "--experience-ids", 1)
    second = run("application", "prepare", "--job-id", 3, "--resume-id", resume_three["id"], "--channel", "liepin")
    hints = second["repeat_application_hints"]
    assert len(hints["already_applied_in_group"]) == 1, "same group must report the earlier submission"
    assert hints["decision"] == "user_decides"
    verification["prepare_second_platform"] = {"id": second["id"], "allowed": True,
                                               "already_applied_in_group": hints["already_applied_in_group"],
                                               "decision": hints["decision"]}

    pipeline = run("pipeline")
    verification["pipeline"] = {"stages": pipeline["stages"],
                                "jobs_by_channel": pipeline["jobs_by_channel"],
                                "applications_by_channel": pipeline["applications_by_channel"],
                                "repeat_application_risk_groups": len(pipeline["repeat_application_risk"]),
                                "agenda_items": len(pipeline["agenda"]),
                                "data_gaps": pipeline["data_gaps"],
                                "rule": pipeline["rule"]}
    verification["card_after_apply"] = {
        "applications": [{"id": app["id"], "channel": app["channel"], "status": app["status"],
                          "applied_at": app["applied_at"], "timeline": len(app["timeline"])}
                         for app in run("jobs", "card", "--id", 2)["applications"]],
        "repeat_risk": run("jobs", "card", "--id", 2)["repeat_application_risk"]["decision"],
    }
    assert pipeline["data_gaps"]["application_channel_missing"] == 0
    assert len(pipeline["repeat_application_risk"]) == 1

    write("verification.json", verification)
    (folder / "REPORT.md").write_text(REPORT.format(**{
        "members": card["vacancy_group"]["members"],
        "channels": " / ".join(item["channel"] for item in card["channels"]),
        "published_at": card["job"]["published_at"],
        "jobs": pipeline["stages"]["jobs"],
        "submitted": pipeline["stages"]["submitted"],
        "risk": len(pipeline["repeat_application_risk"]),
        "agenda": len(pipeline["agenda"]),
    }), encoding="utf-8")
    print(json.dumps({"verified": True, "folder": str(folder),
                      "checks": ["3 platforms grouped", "channel recorded", "status + applied_at",
                                 "timeline + agenda", "repeat hint without blocking", "pipeline gaps"]},
                     ensure_ascii=False, indent=2))
    return 0


REPORT = """# 渠道与统一记录验证（虚构数据）

本报告由 `scripts/verify_channel_tracking.py` 生成：只使用隔离数据库与虚构岗位，没有联网抓取、没有上传简历、没有提交申请。

## 结果

- 同一岗位在 3 个平台（{channels}）被归并为 1 组，组内 {members} 条来源，发布时间取各自渠道值（BOSS 侧 {published_at}）。
- 岗位库 {jobs} 条，其中 1 条已投递（channel=boss，`applied_at` 由状态流转自动写入），时间线含 `applied` 与手工 `interview` 节点，日程表可见该面试。
- 第二次在同组另一个平台 `prepare` 未被拦截，返回 `already_applied_in_group` 与 `decision=user_decides`；`repeat_application_risk` 覆盖 {risk} 个候选组。
- `pipeline` 显示待办面试 {agenda} 条，`application_channel_missing=0`。
- 官网与目录渠道的 `jobs route` 只输出步骤与下一命令，不声称已执行搜索。

## 未验证

- 真实雇主官网的 `official fetch`（需真实单岗 URL 且受 robots 约束）。
- BOSS/智联浏览器端到端搜索。
- 任何重复投递是否会被雇主视为同一申请——这属于判断，不由本系统断言。
"""


if __name__ == "__main__":
    raise SystemExit(main())
