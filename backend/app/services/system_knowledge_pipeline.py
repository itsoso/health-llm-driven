"""Deterministic V2 scanner/classifier for the system health knowledge corpus.

This module deliberately avoids reading or exporting paid lesson bodies. It
only inventories source files and classifies health relevance from course/file
metadata so the serving KB can be expanded through reviewed artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re


SKIP_DIRS = {
    ".git",
    ".obsidian",
    ".compile-cache",
    "__pycache__",
    "agents",
    "artifacts",
    "output",
    "pipeline",
    "raw",
    "wiki",
}

SUPPORTED_SUFFIXES = {".md", ".pdf", ".epub", ".txt"}

PRIORITY_COURSES = {
    "冯雪·科学减肥16讲": 1,
    "冯雪·高血压医学课": 1,
    "冯雪·高血糖医学课": 1,
    "冯雪·高血脂医学课": 1,
    "冯雪·高尿酸医学课": 1,
    "给忙碌者的糖尿病医学课": 1,
    "给忙碌者的营养健康公开课": 1,
    "仝卿·营养科学20讲": 1,
    "仇子龙·基因科学20讲": 1,
    "王家伟·日常用药健康课": 1,
}

SOURCE_KEY_OVERRIDES = {
    "冯雪·科学减肥16讲": "dedao:fengxue-weight-loss",
    "冯雪·高血压医学课": "dedao:fengxue-gaoxueya-yixueke",
    "冯雪·高血糖医学课": "dedao:fengxue-gaoxuetang-yixueke",
    "冯雪·高血脂医学课": "dedao:fengxue-gaoxuezhi-yixueke",
    "冯雪·高尿酸医学课": "dedao:fengxue-gaoniaosuan-yixueke",
    "仝卿·营养科学20讲": "dedao:tongqing-nutrition-20",
    "仇子龙·基因科学20讲": "dedao:qiuzilong-genetics-20",
    "王家伟·日常用药健康课": "dedao:wangjiawei-medication-safety",
    "给忙碌者的糖尿病医学课": "dedao:busy-diabetes",
    "给忙碌者的营养健康公开课": "dedao:busy-nutrition",
}

DOMAIN_RULES = [
    ("metabolic_health", ("减肥", "体重", "腰围", "血糖", "糖尿病", "尿酸", "血脂", "代谢")),
    ("cardiovascular", ("血压", "心脏", "冠心病", "心血管", "血脂", "胆固醇")),
    ("nutrition", ("营养", "饮食", "蛋白", "膳食", "纤维", "减肥")),
    ("genetics", ("基因", "遗传", "SNP")),
    ("medication_safety", ("用药", "药", "药物", "处方")),
    ("sleep_recovery", ("睡眠", "恢复", "精力")),
    ("movement", ("运动", "训练", "跑步", "力量")),
    ("mental_health", ("情绪", "压力", "心理", "抑郁", "焦虑")),
    ("respiratory_allergy", ("鼻炎", "过敏", "呼吸", "哮喘")),
    ("microbiome", ("微生物", "肠道", "菌群")),
    ("longevity", ("衰老", "长寿", "抗衰", "活过100岁")),
    ("general_wellness", ("健康", "医学", "体检")),
]

STRONG_COURSE_KEYWORDS = (
    "健康",
    "医学",
    "营养",
    "减肥",
    "睡眠",
    "血糖",
    "血压",
    "血脂",
    "尿酸",
    "基因",
    "用药",
    "心脏",
    "微生物组",
    "运动",
)


@dataclass(frozen=True)
class ClassifiedSource:
    is_health: bool
    domains: list[str]
    priority: int


@dataclass(frozen=True)
class HealthSource:
    course_name: str
    source_key: str
    path: str
    domains: list[str]
    priority: int
    lesson_count: int
    file_count: int


def classify_health_source(course_name: str, file_names: list[str] | None = None) -> ClassifiedSource:
    file_names = file_names or []
    strong_course_match = course_name in PRIORITY_COURSES or any(
        keyword in course_name for keyword in STRONG_COURSE_KEYWORDS
    )
    file_health_hits = sum(
        1
        for file_name in file_names
        if any(keyword in file_name for _, keywords in DOMAIN_RULES for keyword in keywords)
    )
    if not strong_course_match and file_names:
        hit_ratio = file_health_hits / len(file_names)
        if file_health_hits < 3 or hit_ratio < 0.1:
            return ClassifiedSource(is_health=False, domains=[], priority=99)

    haystack = " ".join([course_name, *file_names])
    domains = [
        domain
        for domain, keywords in DOMAIN_RULES
        if any(keyword.lower() in haystack.lower() for keyword in keywords)
    ]
    if len(domains) > 1 and "general_wellness" in domains:
        domains.remove("general_wellness")
    if not domains:
        return ClassifiedSource(is_health=False, domains=[], priority=99)

    priority = PRIORITY_COURSES.get(course_name, 2 if domains[0] != "general_wellness" else 3)
    return ClassifiedSource(is_health=True, domains=domains, priority=priority)


def scan_health_sources(source_root: str | Path) -> list[HealthSource]:
    root = Path(source_root)
    sources: list[HealthSource] = []
    for course_dir in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda p: p.name):
        if course_dir.name in SKIP_DIRS or course_dir.name.startswith("."):
            continue
        files = [
            path
            for path in course_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_SUFFIXES
            and not any(part in SKIP_DIRS for part in path.relative_to(course_dir).parts)
        ]
        if not files:
            continue
        classification = classify_health_source(course_dir.name, [path.name for path in files])
        if not classification.is_health:
            continue
        sources.append(
            HealthSource(
                course_name=course_dir.name,
                source_key=_source_key(course_dir.name),
                path=str(course_dir),
                domains=classification.domains,
                priority=classification.priority,
                lesson_count=_lesson_count(files),
                file_count=len(files),
            )
        )
    return sorted(sources, key=lambda source: (source.priority, source.course_name))


def _lesson_count(files: list[Path]) -> int:
    lesson_prefixes = {
        match.group(1)
        for path in files
        if (match := re.match(r"^(\d{1,3}|第?\d+)[\s｜丨.-]", path.name))
    }
    return len(lesson_prefixes) or len(files)


def _source_key(course_name: str) -> str:
    if course_name in SOURCE_KEY_OVERRIDES:
        return SOURCE_KEY_OVERRIDES[course_name]
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", course_name).strip("-").lower()
    if slug:
        return f"dedao:{slug}"
    digest = hashlib.sha1(course_name.encode("utf-8")).hexdigest()[:12]
    return f"dedao:{digest}"
