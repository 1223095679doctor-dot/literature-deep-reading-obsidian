#!/usr/bin/env python3
"""Objective final-folder audit for literature-deep-reading-obsidian.

The script checks file/link/Markdown invariants. It deliberately does not grade
teaching depth by word count or by requiring fixed prose labels. Human sampled
reading is the authority for explanation quality.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
import re
import sys


NOTE_NAME = "设计思路与证据审查.md"
REQUIRED_DIRS = ("Figure", "Source")
TEMP_NAME = re.compile(
    r"(?:ocr|render|contact.?sheet|cache|ledger|台账|日志|\.log$|\.tmp$|__pycache__)",
    re.I,
)
PLACEHOLDER = re.compile(r"\{\{|\}\}|\bTODO\b|\bTBD\b|待补|占位符", re.I)
WIKILINK = re.compile(r"!\[\[Figure/([^\]]+)\]\]")
MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\((?:\./)?Figure/([^\)]+)\)")
PANEL_CALLOUT = re.compile(
    r"^>\s*\[![^\]]+\]\s*(Figure\s+S?\d+\s*[A-Za-z])(?:\s*[｜|:：].*)?$",
    re.I | re.M,
)
PANEL_BLOCK = re.compile(
    r"(?m)^>\s*\[![^\]]+\]\s*Figure\s+S?\d+\s*[A-Za-z].*$\n"
    r"(?P<body>(?:^>(?!\s*\[!).*$\n?)*)"
)
BARE_CALLOUT = re.compile(
    r"^\s*\[!(?:note|abstract|question|info|tip|warning|success|example|danger)\]",
    re.I | re.M,
)
FIGURE_KEY = re.compile(r"^(Figure\s+S?\d+)", re.I)
FIXED_LABEL = re.compile(
    r"\*\*(?:前一步缺口|作者为什么做|为什么做|作者怎么做|怎么做|双向预期|预期|图上是什么|怎么看|实际结果|数字怎么理解|作者如何解释|能说明/不能说明)[:：]\**"
)
REPEATED_CUES = (
    "实验中",
    "这套设计的判别逻辑是",
    "读图时",
    "图中可见",
    "证据边界是",
)
ROTATING_TEMPLATE_CUES = (
    "此时真正悬而未决的是",
    "前一结果尚不能回答",
    "这一面板承接的具体疑问是",
    "进入图面后可先",
    "面对这些组别，先",
    "图上有效的阅读顺序是",
    "定位数据时先找",
    "作为证据审查，需要保留",
    "把代表图和定量对应起来时",
    "读这张图时应从",
    "横向阅读的第一步是",
)
OBSOLETE_STAGE = re.compile(
    r"(?m)^#{2,4}\s+(?:\d+(?:\.\d+)?\s*)?(?:阶段\d+|本阶段|阶段导航卡|证据强度的最终校准|从结果到下一步的递进)"
)


def table_errors(lines: list[str]) -> list[str]:
    issues: list[str] = []
    for i in range(len(lines) - 1):
        if "|" not in lines[i] or "|" not in lines[i + 1]:
            continue
        separator = [x.strip() for x in lines[i + 1].strip().strip("|").split("|")]
        if not separator or not all(re.fullmatch(r":?-{3,}:?", x) for x in separator):
            continue
        expected = len(lines[i].strip().strip("|").split("|"))
        if len(separator) != expected:
            issues.append(f"第 {i + 1} 行附近表格表头与分隔行列数不一致")
        j = i + 2
        while j < len(lines) and "|" in lines[j] and lines[j].strip():
            if len(lines[j].strip().strip("|").split("|")) != expected:
                issues.append(f"第 {j + 1} 行表格列数不一致")
            j += 1
    return issues


def repeated_sentence_starters(panel_bodies: list[str]) -> dict[str, int]:
    """Find shared prose skeletons without relying on known template labels."""
    counts: Counter[str] = Counter()
    for body in panel_bodies:
        cleaned = re.sub(r"(?m)^>\s?", "", body)
        starters: set[str] = set()
        for sentence in re.split(r"[。！？!?\n]+", cleaned):
            sentence = re.sub(r"[*_`#]", "", sentence).strip()
            if not sentence or sentence.startswith("作者图注完整翻译"):
                continue
            sentence = re.sub(r"Figure\s+S?\d+[A-Za-z]?|\d+(?:\.\d+)?", "#", sentence, flags=re.I)
            # Compare the opening clause, not a long raw substring. A templated
            # sentence often appends a different gene/drug/figure immediately
            # after the same discourse cue, which made a 10-character prefix
            # split one repeated skeleton into many apparently distinct ones.
            opening = re.split(r"[，,:：；;]", sentence, maxsplit=1)[0].strip()
            # Five-character Chinese discourse cues such as a repeated reading
            # instruction are already distinctive when they recur across a
            # large fraction of panels. Keeping eight characters previously
            # let the changing gene/drug name fragment the same cue.
            prefix = opening[:5]
            if len(prefix) >= 4:
                starters.add(prefix)
        counts.update(starters)
    return dict(counts)


def audit(root: Path, advisory: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notices: list[str] = []

    if not root.is_dir():
        return [f"最终目录不存在：{root}"], notices

    current_prefix = datetime.now().astimezone().strftime("%y.%m.%d-")
    if not root.name.startswith(current_prefix):
        errors.append(f"文件夹日期不是当前本地日期：应以 {current_prefix} 开头")

    allowed = {NOTE_NAME, *REQUIRED_DIRS}
    extras = sorted(p.name for p in root.iterdir() if p.name not in allowed)
    if extras:
        errors.append("最终目录含额外项目：" + ", ".join(extras))

    for name in REQUIRED_DIRS:
        if not (root / name).is_dir():
            errors.append(f"缺少目录：{name}/")

    for item in root.rglob("*"):
        if TEMP_NAME.search(item.name):
            errors.append(f"发现临时/禁止文件：{item.relative_to(root)}")

    note = root / NOTE_NAME
    text = ""
    if not note.is_file():
        errors.append(f"缺少核心笔记：{NOTE_NAME}")
    else:
        try:
            text = note.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append("核心笔记不是有效 UTF-8")
        if text and not text.startswith("---\n"):
            errors.append("YAML frontmatter 不是文件首行")
        if PLACEHOLDER.search(text):
            errors.append("笔记仍含占位符/TODO")
        for match in BARE_CALLOUT.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            errors.append(f"裸 Callout 语法（缺少 >）：第 {line_no} 行")
        errors.extend("Markdown 表格格式错误：" + x for x in table_errors(text.splitlines()))

    figure_dir = root / "Figure"
    source_dir = root / "Source"
    if source_dir.is_dir() and not any(p.is_file() for p in source_dir.iterdir()):
        errors.append("Source/ 为空")

    if text and figure_dir.is_dir():
        linked = WIKILINK.findall(text) + MARKDOWN_IMAGE.findall(text)
        linked_set = {Path(x).name for x in linked}
        actual = {p.name for p in figure_dir.iterdir() if p.is_file()}

        for name in sorted(linked_set - actual):
            errors.append(f"图片链接不存在：Figure/{name}")
        for name in sorted(actual - linked_set):
            errors.append(f"Figure 文件未在笔记中引用：{name}")

        panel_labels = [re.sub(r"\s+", "", x).upper() for x in PANEL_CALLOUT.findall(text)]
        duplicates = sorted(x for x, n in Counter(panel_labels).items() if n > 1)
        if duplicates:
            errors.append("逐子图 Callout 标签重复：" + "、".join(duplicates[:20]))

        for name in sorted(linked_set):
            match = FIGURE_KEY.match(Path(name).stem)
            if not match:
                continue
            key = re.sub(r"\s+", "", match.group(1)).upper()
            if not any(label.startswith(key) and len(label) > len(key) for label in panel_labels):
                errors.append(f"Figure 缺少逐子图 Callout：{name}")

        if actual and not linked_set:
            errors.append("Figure/ 含图片，但正文没有 Figure 图片链接")

    if text:
        labels = FIXED_LABEL.findall(text)
        panel_count = len(PANEL_CALLOUT.findall(text))
        # The user explicitly forbids a questionnaire repeated across most panels.
        # Isolated labels are allowed; systemic repetition is an objective format defect.
        if len(labels) >= 100 and panel_count >= 20:
            errors.append(
                f"系统性固定模板：{panel_count} 个逐子图 Callout 中识别到 {len(labels)} 个重复教学字段；"
                "请改为围绕每个面板的真实理解障碍自然讲解"
            )

        panel_bodies = [match.group("body") for match in PANEL_BLOCK.finditer(text)]
        if len(panel_bodies) >= 50:
            body_lengths = [len(re.sub(r"\s+|^>\s?", "", body, flags=re.M)) for body in panel_bodies]
            legend_led = sum("作者图注" in body for body in panel_bodies)
            short = sum(length < 240 for length in body_lengths)
            median = sorted(body_lengths)[len(body_lengths) // 2]
            if legend_led / len(panel_bodies) >= 0.70 and short / len(panel_bodies) >= 0.70:
                errors.append(
                    "批量图注摘要退化："
                    f"{legend_led}/{len(panel_bodies)} 个 Callout 由作者图注主导，"
                    f"{short}/{len(panel_bodies)} 个少于240个非空白字符，中位数约{median}；"
                    "完整图注翻译不能替代逐图教学，请按实验单元和面板负荷返工"
                )

        module_two_match = re.search(
            r"(?ms)^#\s*模块二\b(?P<body>.*?)(?=^#\s*模块三\b|\Z)", text
        )
        module_two = module_two_match.group("body") if module_two_match else text
        obsolete = OBSOLETE_STAGE.findall(module_two)
        if len(obsolete) >= 2:
            errors.append(
                f"模块二恢复旧阶段结构：识别到 {len(obsolete)} 个阶段正文/导航标题；"
                "模块二应直接以 Figure 实验单元讲述，不得叠加第二套阶段叙事"
            )

        panel_count = len(panel_bodies)
        if panel_count >= 20:
            cue_counts = {cue: sum(cue in body for body in panel_bodies) for cue in REPEATED_CUES}
            threshold = max(12, int(panel_count * 0.30))
            systemic = {cue: count for cue, count in cue_counts.items() if count >= threshold}
            if len(systemic) >= 4:
                detail = "、".join(f"{cue}={count}" for cue, count in systemic.items())
                errors.append(
                    "无标签固定句序：大量面板重复同一讲解骨架（" + detail + "）；"
                    "删除粗体栏目并不等于自然讲解，请按各面板真实障碍重写"
                )

            starter_counts = repeated_sentence_starters(panel_bodies)
            starter_threshold = max(12, int(panel_count * 0.30))
            shared_starters = sorted(
                ((starter, count) for starter, count in starter_counts.items() if count >= starter_threshold),
                key=lambda item: item[1],
                reverse=True,
            )
            # Two discourse cues repeated across nearly a third of all panels
            # already indicate a stable hidden questionnaire. Requiring three
            # allowed a common two-cue skeleton (for example an identical
            # reading instruction plus an identical caveat) to pass.
            if len(shared_starters) >= 2:
                detail = "、".join(f"“{starter}…”={count}" for starter, count in shared_starters[:8])
                errors.append(
                    "跨面板句首骨架重复：" + detail + "；"
                    "疑似用同义词隐藏固定模板，请按内部小批次重新撰写并逐批验收"
                )

            rotating_panels = sum(
                any(cue in body for cue in ROTATING_TEMPLATE_CUES)
                for body in panel_bodies
            )
            if rotating_panels / panel_count >= 0.35:
                cue_detail = "、".join(
                    f"{cue}={sum(cue in body for body in panel_bodies)}"
                    for cue in ROTATING_TEMPLATE_CUES
                    if any(cue in body for body in panel_bodies)
                )
                errors.append(
                    f"轮换式隐藏模板：{rotating_panels}/{panel_count} 个面板使用同一功能问卷的不同句首（"
                    + cue_detail
                    + "）；删除这些元提示语并按面板真实理解障碍重写"
                )

        wrapper_counts = {
            "读图前补课": module_two.count("读图前补课"),
            "看完Figure": module_two.count("看完Figure"),
            "Take-home message": module_two.count("Take-home message"),
        }
        if all(count >= 3 for count in wrapper_counts.values()):
            errors.append(
                "系统性 Figure 包装模板：反复出现“读图前补课—看完Figure—Take-home message”组合；"
                "这些组件只能按实际需要使用，不能成为每图固定三件套"
            )

        # This is a whole-document collapse signal, not an optional style
        # advisory. Isolated short panels remain allowed, but when a large
        # majority are extremely short the promised per-Figure teaching gate
        # plainly did not happen.
        panel_lengths = [
            len(re.sub(r"\s+|^>\s?", "", match.group("body"), flags=re.M))
            for match in PANEL_BLOCK.finditer(text)
        ]
        if len(panel_lengths) >= 20:
            short = sum(length < 180 for length in panel_lengths)
            ordered = sorted(panel_lengths)
            median = ordered[len(ordered) // 2]
            if short / len(panel_lengths) >= 0.70:
                errors.append(
                    f"逐子图讲解篇幅分布异常：{short}/{len(panel_lengths)} 个面板少于180个非空白字符，"
                    f"中位数约{median}；大多数面板被系统性压成高级图注，阻断交付"
                )

    if advisory and text:
        labels = FIXED_LABEL.findall(text)
        if 12 <= len(labels) < 100:
            notices.append(
                f"识别到 {len(labels)} 个固定教学标签；请人工检查是否又形成逐面板填空"
            )
        normalized_paragraphs: list[str] = []
        for paragraph in re.split(r"\n\s*\n", text):
            compact = re.sub(r"Figure\s+S?\d+[A-Za-z]?|\d+(?:\.\d+)?|\s+", "", paragraph, flags=re.I)
            if len(compact) >= 100:
                normalized_paragraphs.append(compact)
        repeated = [p for p, n in Counter(normalized_paragraphs).items() if n >= 2]
        if repeated:
            notices.append(f"发现 {len(repeated)} 组长段落重复；请人工检查模板污染")
    return errors, notices


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("final_dir", type=Path)
    parser.add_argument(
        "--visual-qa-attested",
        action="store_true",
        help="确认已把最终 Figure 与原始页面逐张并排核验；不得在未核验时使用。",
    )
    parser.add_argument(
        "--content-advisory",
        action="store_true",
        help="显示非阻断的重复/固定标签提示；这些提示不能作为批量补字依据。",
    )
    args = parser.parse_args()

    root = args.final_dir.resolve()
    errors, notices = audit(root, args.content_advisory)
    figure_dir = root / "Figure"
    has_figures = figure_dir.is_dir() and any(p.is_file() for p in figure_dir.iterdir())
    if has_figures and not args.visual_qa_attested:
        errors.append(
            "缺少人工视觉核验确认：逐张核对全部面板后使用 --visual-qa-attested"
        )

    for item in errors:
        print(f"ERROR: {item}")
    for item in notices:
        print(f"ADVISORY: {item}")

    status = "PASS" if not errors else "FAIL"
    print(f"SUMMARY: {status} — {len(errors)} objective error(s), {len(notices)} advisory notice(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
