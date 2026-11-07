"""Stable navigation contract for Oriward's five user-facing workflows."""

LAYERS = (
    {"id": "long_term", "question": "我有哪些经历、能力线索和稳定约束？",
     "state": ["experiences", "user_assertions", "profile"],
     "updates": "新经历、补充证据、用户确认或纠正"},
    {"id": "mid_term", "question": "我正在探索什么，阶段目标是什么？",
     "state": ["career_directions", "career_goals", "learning_plans"],
     "updates": "探索结果、资源变化、目标调整或能力差距变化"},
    {"id": "short_term", "question": "现在推进到哪里，下一步做什么？",
     "state": ["jobs", "resumes", "applications", "next_actions", "current_topic"],
     "updates": "实际操作、用户反馈和任务进展"},
)

MODULES = (
    {"id": "experience_discovery", "name": "经历挖掘", "primary_layer": "long_term",
     "reads": ["用户讲述", "授权历史", "已有经历与断言"],
     "writes": ["experience_id", "assertion_id", "待展开线索"],
     "entry": ["intake next", "experience index", "experience detail"],
     "feeds": ["career_planning", "resume_creation", "personal_growth"]},
    {"id": "career_planning", "name": "职业规划", "primary_layer": "mid_term",
     "reads": ["experience_id", "assertion_id", "岗位市场证据", "资源与约束"],
     "writes": ["direction_id", "goal_id", "能力差距"],
     "entry": ["career list", "goal list", "context section --name who_could_i_become"],
     "feeds": ["job_search_application", "resume_creation", "personal_growth"]},
    {"id": "resume_creation", "name": "简历制作", "primary_layer": "short_term",
     "reads": ["experience_id", "assertion_id", "direction_id", "job_id"],
     "writes": ["resume_id", "简历版本与来源映射", "岗位评级与模拟面试反馈"],
     "entry": ["resume workflow", "resume tailor-packet", "resume compose", "resume revise"],
     "feeds": ["job_search_application", "personal_growth"]},
    {"id": "job_search_application", "name": "岗位搜索与投递", "primary_layer": "short_term",
     "reads": ["direction_id", "goal_id", "job_id", "resume_id"],
     "writes": ["job_id", "application_id", "岗位流水线与真实反馈"],
     "entry": ["jobs channels", "pipeline list", "application prepare"],
     "feeds": ["career_planning", "resume_creation", "personal_growth"]},
    {"id": "personal_growth", "name": "个人提升", "primary_layer": "mid_term",
     "reads": ["experience_id", "goal_id", "岗位差距与反馈", "时间预算"],
     "writes": ["learning_id", "学习行动与实践证据"],
     "entry": ["learning list", "action list", "context section --name what_next"],
     "feeds": ["experience_discovery", "career_planning", "resume_creation"]},
)


def map_workflows():
    """Return the module boundaries and feedback paths without user data."""
    return {"layers": LAYERS, "modules": MODULES,
            "note": "五个业务模块共享一个 Core；时间层是状态视图，不是独立数据库。实际保存以各模块 CLI 回执为准。"}
