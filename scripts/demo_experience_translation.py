"""Run two fictional adult career stories through real, isolated CLI processes.

This is a reproducible engineering demonstration, not a real user trial or
market validation. It never sets approval flags, submits, searches or edits
generated resume Markdown. Optional document packages are needed for export.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / ".agents/skills/document-export/scripts/export_documents.py"


STORIES = [
    {
        "slug": "store-to-operations", "name": "陈知远（虚构）", "role": "运营协调专员",
        "education": "虚构南川职业学院 · 物流管理专科 · 2005.09—2008.06",
        "account": "我先在配送站做单据，后来做仓库，再和家人经营社区杂货店。我不是公司运营经理，但每天都要安排进货、库存、顾客问题和帮工交接。没有算过降本比例。想把这些经历讲明白，试试运营协调类工作。",
        "jd": "虚构演示岗位，不是真实招聘：维护日常运营台账，跟进采购与库存，协调门店和供应方处理异常，整理周度问题清单并跟进完成。",
        "histories": [
            {"event": "社区杂货店经营", "kind": "business", "period": "2017.03—2026.06",
             "context": {"organization": "虚构邻里杂货店", "location": "演示城市"},
             "actions": ["根据缺货和销售情况列进货清单，向供货商订货并验收", "用电子表格记录进销存，定期盘点临期和积压商品", "安排两位帮工排班，交接收银和到货事项", "处理退换货，记录顾客常见问题并与供货商沟通"],
             "outcomes": ["保持进货、到货与退换货记录可追溯", "将交接事项整理为固定清单"]},
            {"event": "仓库收发与单据跟进", "kind": "work", "period": "2011.07—2016.12",
             "context": {"organization": "虚构远川日用品商行", "location": "演示城市"},
             "actions": ["核对到货数量与送货单，登记差异并联系采购同事", "按发货计划准备货品，跟进缺货和错发问题", "每月参与盘点并汇总待处理差异"],
             "outcomes": ["形成可交接的异常记录与处理进展"]},
            {"event": "配送站文员", "kind": "work", "period": "2008.07—2011.05",
             "context": {"organization": "虚构顺程配送站"},
             "actions": ["登记配送单据，核对签收回单并联系司机补齐缺项", "按线路整理当日未完成配送事项"],
             "outcomes": ["供交班人员继续跟进未完成事项"]}
        ],
        "polished": ["结合缺货与销售情况编制采购清单，跟进订货、验收及供货异常。", "维护进销存台账，定期盘点临期和积压商品，为日常补货提供依据。", "安排两位帮工的排班与交接，统一记录收银、到货和待办事项。", "承接退换货并整理常见问题，协调供货商跟进处理。"],
        "correction": "刚才人数说得不准确，是一位固定帮工，忙时家人临时帮忙。我没有管理两名员工。",
        "corrected_action": "安排一位固定帮工的排班，忙时由家人临时协助，交接收银和到货事项",
        "corrected_bullet": "安排一位固定帮工的排班与交接，忙时协调家人临时协助，统一记录收银和到货事项。",
        "correction_index": 2, "old_phrase": "两位帮工", "new_phrase": "一位固定帮工",
        "learning": "用虚构门店进销存数据做一页周度异常跟进表",
        "gap": "尚未制作过面向运营岗位的周度汇报样例"
    },
    {
        "slug": "returner-to-support", "name": "林若安（虚构）", "role": "服务支持与事务协调",
        "education": "虚构江岸成人教育学院 · 行政管理专科 · 2010.03—2013.01",
        "account": "早些年我做过售后文员，后来零散接过网店客服，也帮社区活动做报名。中间有几年主要在家，现在想重新找工作。不是这些年什么也没做，但一直不知道怎么写。希望先找能按流程跟进、和人沟通的支持工作，每周能拿出三小时学习。",
        "jd": "虚构演示岗位，不是真实招聘：登记服务请求与资料，按优先顺序跟进待办，协调内部人员回复，维护常见问题与交接记录。",
        "histories": [
            {"event": "社区活动报名协助", "kind": "other", "period": "2024.04—2026.08（按活动参与）",
             "context": {"organization": "虚构江岸社区活动组"},
             "actions": ["协助登记报名信息，核对联系方式和参加场次", "提醒参加者时间地点，将临时变更转达活动负责人", "活动后汇总未到场与重复报名情况"],
             "outcomes": ["形成报名名单和需负责人继续处理的事项清单"]},
            {"event": "网店客服零散协作", "kind": "work", "period": "2020.06—2025.12（间歇协作）",
             "context": {"organization": "虚构拾光小店"},
             "actions": ["在店主安排的时段回复订单状态和售后问题", "将无法当场解决的情况交给店主，记录待回复事项", "整理重复咨询的问题和店主给出的处理口径"],
             "outcomes": ["协作时段结束前交接未完成咨询，不把未回复问题当作已解决"]},
            {"event": "售后服务文员", "kind": "work", "period": "2013.03—2017.09",
             "context": {"organization": "虚构合益家电服务部"},
             "actions": ["接听报修电话，记录故障描述、联系方式和可上门时段", "向维修人员转交工单，跟进改约和未完成事项", "整理服务回访记录并向负责人反馈重复问题"],
             "outcomes": ["服务工单、改约信息和回访结果集中留存"]}
        ],
        "polished": ["维护活动报名信息，核对联系方式及参加场次，形成可交接的名单。", "同步时间地点与临时变更，将需负责人处理的问题整理为待办。", "活动后汇总未到场和重复报名情况，支持下一次安排。"],
        "correction": "社区活动那段应当是2024年9月开始，不是4月，其他事情不变。中间的空档不用写私人原因。",
        "corrected_period": "2024.09—2026.08（按活动参与）",
        "old_phrase": "2024.04", "new_phrase": "2024.09",
        "learning": "制作服务请求登记表、交接清单和三种异常回复样例",
        "gap": "尚未形成可展示的标准化服务请求与交接模板"
    }
]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run_case(folder, story, renderer):
    folder.mkdir()
    environment = dict(os.environ, ORIWARD_DB=str(folder / "demo.sqlite3"),
                       ORIWARD_OUTPUT_DIR=str(folder / "resumes"),
                       PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    receipts = []

    def save(name, data):
        path = folder / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return str(path)

    def call(arguments, *, export=False):
        command = [sys.executable, str(EXPORTER)] if export else [sys.executable, "-m", "oriward"]
        command += list(map(str, arguments))
        result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                                text=True, encoding="utf-8", timeout=120 if export else 30)
        receipt = {"command": command, "returncode": result.returncode,
                   "stdout": result.stdout, "stderr": result.stderr}
        receipts.append(receipt)
        save("command-receipts.json", receipts)
        require(result.returncode == 0, f"Command failed: {command}: {result.stderr}")
        payload = json.loads(result.stdout)
        receipt["result"] = payload
        save("command-receipts.json", receipts)
        return payload

    def cli(*arguments):
        return call(arguments)

    cli("init")
    cli("twin", "status")
    cli("onboarding", "missing")
    cli("profile", "save", "--file", save("profile.json", {
        "display_name": story["name"], "contact": {"email": "fictional@example.invalid"},
        "education": [story["education"]], "target_roles": [story["role"]],
        "constraints": ["每周学习安排以三小时为限"]}))
    topic = cli("onboarding", "topic", "--title", "恢复经历并翻译为新岗位表达",
                "--next-action", "整理过去实际做过的事")
    save("fictional-conversation.json", {"notice": "脚本编写的虚构对话，不是真实用户试用",
         "user_account": story["account"], "later_correction": story["correction"],
         "follow_up_policy": "仅针对会改变表达的歧义提问，不逐条批准或补齐字段"})
    # Actual event-only ordinary intake: no evidence fields or approval flags.
    ids = [cli("experience", "add", "--file", save("event-only.json", {
        "event": story["histories"][0]["event"]}))["id"]]
    cli("experience", "revise", "--id", ids[0], "--file", save("intake-details.json", story["histories"][0]),
        "--reason", "同一事件的自然补充", "--expected-version", 1)
    for number, history in enumerate(story["histories"][1:], 1):
        ids.append(cli("experience", "add", "--file", save(f"experience-{number}.json", history))["id"])
    cli("onboarding", "pause", "--reason", "虚构对话暂时离开")
    brief = cli("context", "brief")
    resumed = cli("onboarding", "resume", "--id", topic["id"])
    require(resumed["id"] == topic["id"], "same topic resumes")
    cli("experience", "index", "--budget", 2200)
    job = {"source": "fictional-experience-translation-demo", "source_id": story["slug"],
           "title": story["role"] + "（虚构演示）", "company": "不存在的演示机构",
           "description": story["jd"], "url": "https://example.invalid/" + story["slug"],
           "availability": "unknown", "retrieved_at": datetime.now(timezone.utc).isoformat()}
    jid = cli("jobs", "import", "--json", save("fictional-job.json", [job]))["job_ids"][0]
    seen, offset, pages = set(), 0, 0
    while True:
        packet = cli("resume", "tailor-packet", "--job-id", jid, "--offset", offset, "--budget", 950)
        pages += 1
        seen.update(item["id"] for item in packet["experience_index"]["items"])
        if not packet["has_more"]:
            break
        require(packet["next_offset"] > offset, "pagination makes progress")
        offset = packet["next_offset"]
        require(pages < 20, "bounded pagination")
    require(seen == set(ids), "complete inventory coverage")
    cli("experience", "detail", "--ids", ",".join(map(str, ids)), "--sections", "event,actions,outcomes,time_period,context")
    first = {"reason": "从实际动作组织迁移价值，保留完整职业阶段与教育",
             "headline": story["role"],
             "section_order": ["经营经历", "工作经历", "其他经历", "教育经历", "专业技能"],
             "sections": [{"experience_id": ids[0],
             "category": "经营经历" if story["slug"].startswith("store") else "其他经历",
             "bullets": story["polished"]}, {"experience_id": ids[1],
             "category": "工作经历", "bullets": story["histories"][1]["actions"]}]}
    initial = cli("resume", "compose", "--job-id", jid, "--file", save("compose-initial.json", first))
    original_path = Path(initial["path"])
    original_bytes = original_path.read_bytes()
    original = original_bytes.decode("utf-8")
    require(story["education"] in original and story["old_phrase"] in original,
            "education and original source details present")
    # No per-experience approval or complete-draft confirmation is performed.
    changes = {}
    final_bullets = list(story["polished"])
    if "corrected_action" in story:
        actions = list(story["histories"][0]["actions"])
        actions[story["correction_index"]] = story["corrected_action"]
        changes["actions"] = actions
        final_bullets[story["correction_index"]] = story["corrected_bullet"]
    else:
        changes["period"] = story["corrected_period"]
    correction = cli("experience", "revise", "--id", ids[0], "--file", save("user-correction.json", changes),
                     "--reason", story["correction"], "--expected-version", 2)
    revised = cli("resume", "revise", "--file", save("resume-revision.json", {
        "base_resume_id": initial["id"], "reason": "直接应用用户更正，保留原稿和来源版本",
        "sections": [{"experience_id": ids[0], "bullets": final_bullets}]}))
    history = cli("experience", "history", "--id", ids[0])
    require([item["version"] for item in history] == [1, 2, 3], "original and both updates preserved")
    require(all(not item["data"].get("approved_for_resume", False) for item in history),
            "no experience approval manufactured")
    resume_history = cli("resume", "history", "--id", revised["id"])
    cli("resume", "tailor-packet")
    general = cli("resume", "compose", "--file", save("compose-general.json", {
        "reason": "无指定岗位的通用职业履历，不生成虚构招聘岗位",
        "section_order": first["section_order"],
        "sections": [{"experience_id": ids[0], "bullets": final_bullets},
                     {"experience_id": ids[1], "bullets": story["histories"][1]["actions"]}]}))
    direction = cli("career", "add", "--file", save("direction.json", {
        "title": story["role"] + "方向（探索假设）", "rationale": "实际登记、跟进、协调动作可以迁移，尚未以真实岗位验证",
        "supporting_experience_ids": ids, "gaps": [story["gap"]],
        "transferable_skills": ["信息整理", "异常跟进", "事项交接"],
        "entry_route": ["制作小型工作样例", "后续阅读真实岗位检查资格和任务"],
        "validation_status": "hypothesis", "market_sources": []}))
    learning = cli("learning", "save", "--file", save("learning.json", {
        "target_role": story["role"], "job_ids": [jid], "gaps": [story["gap"]], "weekly_hours": 3,
        "milestones": [{"title": story["learning"], "deliverable": "一份可打开和复用的表格或说明文档",
          "acceptance_criteria": "用10条虚构事项演练，区分已完成、待回复、需升级并保留交接人；说明两处局限",
          "effort_hours": 3}], "review_date": "2026-11-07", "status": "active"}))
    exports = []
    for label, resume in (("targeted-final", revised), ("general-final", general)):
        content = Path(resume["path"]).read_text(encoding="utf-8")
        require(story["education"] in content, "education retained")
        require(story["new_phrase"] in content and story["old_phrase"] not in content, "correction reflected")
        for experience in story["histories"][1:]:
            require(experience["event"] in content, "other career stages retained")
        require(not re.search(r"approved_for_resume|experience_id|来源记录|factual_status|data/private", content),
                "candidate document has no internal metadata")
        require(resume.get("factual_status") == "draft", "ordinary draft without confirmation")
        destination = folder / label
        manifest = call(["--resume-id", resume["id"], "--output-dir", destination,
                         "--template", "modern-cn", "--renderer", renderer], export=True)
        exports.append({"label": label, "resume_id": resume["id"], "directory": str(destination),
                        "renderer": manifest["renderer"], "visual_review": "pending"})
    require(original_path.read_bytes() == original_bytes, "historical Markdown untouched")
    checks = {"event_only_intake": True, "approval_commands": 0, "all_history_covered": True,
              "pagination_pages": pages, "pause_resume": True, "education_present": True,
              "source_corrected_version": correction["version"], "source_history_snapshots": len(history),
              "original_sha256": hashlib.sha256(original_bytes).hexdigest(), "original_unchanged": True,
              "final_factual_status": revised["factual_status"], "internal_metadata_absent": True,
              "human_trial": False, "market_validated": False}
    result = {"case": story["slug"], "checks": checks, "initial": initial, "revision": revised,
              "general": general, "direction": direction, "learning": learning,
              "exports": exports, "resume_history": resume_history,
              "paused_context_receipt": brief, "command_count": len(receipts)}
    save("result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New folder; never overwrites existing output")
    parser.add_argument("--renderer", choices=("auto", "word", "libreoffice", "reportlab"), default="auto")
    args = parser.parse_args()
    folder = Path(args.output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    report = {"notice": "虚构成人故事的真实CLI工程演示，不是真实用户试用或市场验证", "cases": []}
    try:
        for story in STORIES:
            result = run_case(folder / story["slug"], story, args.renderer)
            report["cases"].append(result)
            print(json.dumps({"case": story["slug"], "checks": result["checks"],
                              "exports": result["exports"]}, ensure_ascii=False), flush=True)
        report["status"] = "PASSED_ENGINEERING_DEMO_VISUAL_REVIEW_PENDING"
    except Exception as exc:
        report.update(status="FAILED", error=str(exc))
        raise
    finally:
        (folder / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
