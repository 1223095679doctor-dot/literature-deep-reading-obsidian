#!/usr/bin/env python3
"""Final-folder audit for literature-deep-reading-obsidian.

The script checks file/link/Markdown invariants and catches objective depth
collapse signals such as sub-minimum panel teaching and mechanically repeated
filler. It does not decide whether the scientific explanation is correct;
human sampled reading remains the authority for semantic quality.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
import re
import sys
from urllib.parse import unquote


NOTE_NAME = "作者思路与实验设计带读.md"
REQUIRED_DIRS = ("Source",)
OPTIONAL_DIRS = ("Figure",)
REQUIRED_SOURCE_PDFS = ("正文.pdf", "补充材料.pdf")
TEMP_NAME = re.compile(
    r"(?:ocr|render|contact.?sheet|cache|ledger|台账|日志|\.log$|\.tmp$|__pycache__)",
    re.I,
)
PLACEHOLDER = re.compile(r"\{\{|\}\}|\bTODO\b|\bTBD\b|待补|占位符", re.I)
WIKILINK = re.compile(r"!\[\[Figure/([^\]]+)\]\]")
MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*<?(?:\./)?Figure/([^>\)]+)>?\s*\)")
MARKDOWN_IMAGE_TARGET = re.compile(r"!\[[^\]]*\]\((?P<target>[^\n\)]+)\)")
PANEL_CALLOUT = re.compile(
    r"^>\s*\[![^\]]+\]\s*(Figure\s+S?\d+\s*[A-Za-z](?:\s*[–—-]\s*[A-Za-z])?)(?:\s*[｜|:：].*)?$",
    re.I | re.M,
)
PANEL_BLOCK = re.compile(
    r"(?m)^(?P<header>>\s*\[![^\]]+\]\s*Figure\s+S?\d+\s*[A-Za-z](?:\s*[–—-]\s*[A-Za-z])?.*)$\n"
    r"(?P<body>(?:^>(?!\s*\[!).*$\n?)*)"
)
PANEL_HEADER_LINE = re.compile(
    r"^>\s*\[![^\]]+\]\s*Figure\s+.*$", re.I | re.M
)
PANEL_RANGE = re.compile(
    r"(?:Figure\s+)?S?\d+\s*([A-Za-z])\s*[–—-]\s*([A-Za-z])", re.I
)
BARE_CALLOUT = re.compile(
    r"^\s*\[!(?:note|abstract|question|info|tip|warning|success|example|danger)\]",
    re.I | re.M,
)
CALLOUT_HEADER = re.compile(r"^>\s*\[![^\]]+\]")
FIGURE_KEY = re.compile(r"^(Figure\s+S?\d+)", re.I)
FIXED_LABEL = re.compile(
    r"\*\*(?:[^*：:]{1,30}·)?(?:前一步缺口|作者为什么做|为什么做|作者怎么做|怎么做|双向预期|预期|图上是什么|怎么看|证据衔接|方法原理|样品/?分组|视觉阅读|实际结果|直接含义(?:与边界)?|图例译文|数字怎么理解|作者如何解释|能说明/不能说明)[:：]\**"
)
GENERIC_PANEL_TITLE = re.compile(
    r"(?mi)^>\s*\[![^\]]+\]\s*(?:Figure\s+S?\d+[A-Za-z]?\s*[|｜]\s*)?(?:Panel\s+(?:deep\s+reading|analysis)|面板带读)\s*$"
)
VISIBLE_GATE = re.compile(
    r"(?mi)^>\s*\[!success\][^\n]*(?:门禁|gate)[^\n]*(?:PASS|通过)"
)
LEGEND_AS_BULLET = re.compile(
    r"(?mi)^>\s*-\s*\*\*[^*]{0,40}图例译文\*\*"
)
LAYERED_REVIEW = re.compile(r"第[一二三四五六七八九十百]+层复核")
DEFENSIVE_BOILERPLATE = (
    "样本单位与生物学重复必须先确认",
    "组间分离不能替代方差估计和独立验证",
    "患者、细胞与视野属于不同统计层级",
    "图上点数不能未经说明互相替代",
)
FIGURE_SECTION_HEADER = re.compile(
    r"(?mi)^#{2,4}\s+Figure\s+(S?\d+)\s*[｜|].*$"
)
PANEL_SUBHEADING = re.compile(
    r"(?mi)^#{3,6}\s+([^｜|\n]+?)\s*[｜|].*$"
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


def portable_image_link_errors(text: str) -> list[str]:
    """Reject Figure targets whose raw spaces break strict Markdown parsers."""
    issues: list[str] = []
    for match in MARKDOWN_IMAGE_TARGET.finditer(text):
        target = match.group("target").strip()
        wrapped = target.startswith("<") and target.endswith(">")
        unwrapped = target[1:-1] if wrapped else target
        if not re.match(r"(?:\./)?Figure/", unwrapped):
            continue
        if re.search(r"\s", unwrapped) and not wrapped:
            line_no = text.count("\n", 0, match.start()) + 1
            issues.append(
                f"图片链接路径含裸空格：第 {line_no} 行；"
                "请使用 ![说明](<Figure/文件名.ext>)"
            )
    return issues


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


def panel_granularity_errors(text: str) -> list[str]:
    """Require panel-by-panel teaching; broad ranges are not valid shortcuts."""
    issues: list[str] = []
    headers = PANEL_HEADER_LINE.findall(text)
    grouped_headers = 0
    for header in headers:
        ranges = PANEL_RANGE.findall(header)
        if ranges:
            grouped_headers += 1
        for start, end in ranges:
            span = ord(end.upper()) - ord(start.upper()) + 1
            if span >= 3:
                issues.append(
                    f"跨 {span} 个 panel 的大范围 Callout：{header.strip()}；"
                    "默认应逐 panel 拆分，只有真正不可拆的同一复合读出才可例外"
                )
    if len(headers) >= 8 and grouped_headers >= 4 and grouped_headers / len(headers) > 0.25:
        issues.append(
            f"panel 合并过多：{grouped_headers}/{len(headers)} 个 Figure Callout 使用字母范围；"
            "大部分 panel 应独立讲解，合并只能是少数紧密配套例外"
        )
    return issues


def expand_panel_letters(label_text: str) -> set[str]:
    """Expand A–C and collect standalone A/B/C tokens without matching words."""
    labels: set[str] = set()
    for start, end in re.findall(r"(?<![A-Za-z])([A-Z])\s*[–—-]\s*([A-Z])(?![A-Za-z])", label_text):
        if ord(start) <= ord(end):
            labels.update(chr(code) for code in range(ord(start), ord(end) + 1))
    labels.update(re.findall(r"(?<![A-Za-z])([A-Z])(?![A-Za-z])", label_text))
    return labels


def figure_section_coverage_errors(text: str) -> list[str]:
    """Ensure panel subheadings are backed by explicitly labelled Figure Callouts."""
    sections = list(FIGURE_SECTION_HEADER.finditer(text))
    issues: list[str] = []
    for index, section in enumerate(sections):
        start = section.end()
        end = sections[index + 1].start() if index + 1 < len(sections) else len(text)
        body = text[start:end]
        expected: set[str] = set()
        for heading in PANEL_SUBHEADING.findall(body):
            expected.update(expand_panel_letters(heading.upper()))
        if not expected:
            continue

        actual: set[str] = set()
        figure_number = section.group(1).upper()
        for label in PANEL_CALLOUT.findall(body):
            normalized = re.sub(r"\s+", "", label).upper()
            if not normalized.startswith("FIGURE" + figure_number):
                continue
            actual.update(expand_panel_letters(normalized))
        missing = sorted(expected - actual)
        if missing:
            issues.append(
                f"Figure {figure_number} 的面板小节没有对应的显式Figure Callout标签："
                + "、".join(missing)
                + "；小节标题或无图号的‘Panel deep reading’不能代替逐面板标注"
            )
    return issues


def callout_separation_errors(lines: list[str], file_label: str) -> list[str]:
    """Require each Callout to start after a truly empty physical line."""
    bad_lines: list[int] = []
    for index, line in enumerate(lines):
        if not CALLOUT_HEADER.match(line):
            continue
        if index > 0 and lines[index - 1] != "":
            bad_lines.append(index + 1)
    if not bad_lines:
        return []
    preview = "、".join(str(line) for line in bad_lines[:20])
    suffix = "" if len(bad_lines) <= 20 else f"等（共 {len(bad_lines)} 处）"
    return [
        f"{file_label}相邻 Callout 未用完全空行分隔：第 {preview} 行{suffix}；"
        "Callout 标题前一行不得是 >、空格或正文"
    ]


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


def panel_depth_errors(text: str) -> list[str]:
    """Block indisputable panel-level shrinkage without pretending to score meaning."""
    blocks = list(PANEL_BLOCK.finditer(text))
    if not blocks:
        return []

    measured: list[tuple[str, int]] = []
    for match in blocks:
        header = re.sub(r"^>\s*\[![^\]]+\]\s*", "", match.group("header")).strip()
        length = len(re.findall(r"[\u4e00-\u9fff]", match.group("body")))
        measured.append((header, length))

    issues: list[str] = []
    below_floor = [(header, length) for header, length in measured if length < 120]
    if below_floor:
        preview = "、".join(f"{header}={length}" for header, length in below_floor[:12])
        suffix = "" if len(below_floor) <= 12 else f"等（共{len(below_floor)}个）"
        issues.append(
            "独立面板低于120个有效中文字符的绝对下限："
            + preview
            + suffix
            + "；面板数量多或全文总字数大不能豁免，须补回样本、分组、方法、读法、结果和意义中的缺失项"
        )

    short_band = [(header, length) for header, length in measured if 120 <= length < 200]
    # A tiny number of genuine labels/mechanical quantifications may sit in
    # the documented 120–200 exception band. A paper-wide cluster is no
    # longer an exception and signals systematic compression.
    allowed_exception_count = max(1, int(len(measured) * 0.03))
    if len(short_band) > allowed_exception_count:
        preview = "、".join(f"{header}={length}" for header, length in short_band[:12])
        suffix = "" if len(short_band) <= 12 else f"等（共{len(short_band)}个）"
        issues.append(
            f"120–199字的短面板过多（允许少量机械定量例外，本稿上限{allowed_exception_count}个）："
            + preview
            + suffix
            + "；逐项核实豁免，其余按真实信息负荷返工"
        )

    if len(measured) >= 10:
        ordered = sorted(length for _, length in measured)
        median = ordered[len(ordered) // 2]
        if median < 240:
            issues.append(
                f"逐面板教学密度整体塌缩：{len(measured)}个面板的有效中文字符中位数约{median}，低于240；"
                "总文件很长也不能抵扣多数面板被压成高级图注"
            )
    return issues


def normalize_for_shingles(body: str) -> str:
    """Normalize identifiers while preserving prose used to detect copied filler."""
    cleaned = re.sub(r"(?m)^>\s?", "", body)
    cleaned = re.sub(r"Figure\s+S?\d+[A-Za-z]?(?:\s*[–—-]\s*[A-Za-z])?", "图号", cleaned, flags=re.I)
    cleaned = re.sub(r"[“\"][^”\"]{1,80}[”\"]", "术语", cleaned)
    cleaned = re.sub(r"[A-Za-z][A-Za-z0-9_+/#.()-]*", "符号", cleaned)
    cleaned = re.sub(r"\d+(?:\.\d+)?", "数值", cleaned)
    cleaned = re.sub(r"[*_`#>\-\s，。；：、！？!?（）()\[\]【】]", "", cleaned)
    return cleaned


def repeated_teaching_fill_errors(text: str) -> list[str]:
    """Find long prose fragments copied across many nominally different panels."""
    blocks = list(PANEL_BLOCK.finditer(text))
    if len(blocks) < 12:
        return []

    window = 54
    owners: dict[str, set[str]] = {}
    for match in blocks:
        header = re.sub(r"^>\s*\[![^\]]+\]\s*", "", match.group("header")).strip()
        normalized = normalize_for_shingles(match.group("body"))
        if len(normalized) < window:
            continue
        panel_windows = {
            normalized[index : index + window]
            for index in range(len(normalized) - window + 1)
        }
        for fragment in panel_windows:
            if len(re.findall(r"[\u4e00-\u9fff]", fragment)) < 30:
                continue
            owners.setdefault(fragment, set()).add(header)

    threshold = max(4, (len(blocks) + 19) // 20)  # at least 5% of panels
    repeated = sorted(
        ((fragment, sorted(headers)) for fragment, headers in owners.items() if len(headers) >= threshold),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    if not repeated:
        return []

    fragment, headers = repeated[0]
    preview_headers = "、".join(headers[:8])
    return [
        f"跨面板机械填充：同一段约{window}字符的通用文字出现在{len(headers)}个面板（{preview_headers}）；"
        f"重复片段形如“{fragment[:42]}…”；删除可移植审稿话术，补写各面板独有的图面教学"
    ]


def audit(root: Path, advisory: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notices: list[str] = []

    if not root.is_dir():
        return [f"最终目录不存在：{root}"], notices

    current_prefix = datetime.now().astimezone().strftime("%y.%m.%d-")
    if not root.name.startswith(current_prefix):
        errors.append(f"文件夹日期不是当前本地日期：应以 {current_prefix} 开头")

    allowed = {NOTE_NAME, *REQUIRED_DIRS, *OPTIONAL_DIRS}
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
        errors.append(f"缺少主笔记：{NOTE_NAME}")
    else:
        try:
            text = note.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append("主笔记不是有效 UTF-8")
        if text and not text.startswith("---\n"):
            errors.append("YAML frontmatter 不是文件首行")
        if PLACEHOLDER.search(text):
            errors.append("笔记仍含占位符/TODO")
        errors.extend(portable_image_link_errors(text))
        for match in BARE_CALLOUT.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            errors.append(f"裸 Callout 语法（缺少 >）：第 {line_no} 行")
        errors.extend(
            callout_separation_errors(text.splitlines(), "主笔记")
        )
        errors.extend(panel_granularity_errors(text))
        errors.extend(figure_section_coverage_errors(text))
        errors.extend(panel_depth_errors(text))
        errors.extend(repeated_teaching_fill_errors(text))
        generic_titles = len(GENERIC_PANEL_TITLE.findall(text))
        if generic_titles:
            errors.append(
                f"发现 {generic_titles} 个占位式带读标题（Panel deep reading/analysis）；"
                "每个标题必须写明对应Figure标签和当前面板的真实判别问题"
            )
        visible_gates = len(VISIBLE_GATE.findall(text))
        if visible_gates:
            errors.append(
                f"最终笔记暴露 {visible_gates} 个内部Figure门禁/PASS标记；"
                "门禁只留在内部状态，不能成为读者正文"
            )
        legend_bullets = len(LEGEND_AS_BULLET.findall(text))
        if legend_bullets:
            errors.append(
                f"发现 {legend_bullets} 个作为项目符号字段的‘图例译文’；"
                "作者legend必须使用就近独立的[!quote]作者图注翻译Callout"
            )
        layered_review = len(LAYERED_REVIEW.findall(text))
        if layered_review >= 3:
            errors.append(
                f"发现 {layered_review} 处‘第X层复核’审计阶梯；"
                "逐图主体应引导读图和形成认识，不得用分层复核话术批量补长"
            )
        repeated_defensive = {
            phrase: text.count(phrase)
            for phrase in DEFENSIVE_BOILERPLATE
            if text.count(phrase) >= 3
        }
        if repeated_defensive:
            detail = "、".join(f"“{phrase}”={count}" for phrase, count in repeated_defensive.items())
            errors.append(
                "跨面板防御性套话重复：" + detail + "；"
                "统计单位、独立验证和系统性边界应在整图或全文集中一次说明"
            )
        errors.extend("Markdown 表格格式错误：" + x for x in table_errors(text.splitlines()))
        if text and not re.search(r"读前地图|阅读地图|研究地图", text):
            errors.append("主笔记缺少读前地图")
        if text and not re.search(r"Figure\s+S?\d+|Scheme\s*\d*", text, re.I):
            errors.append("主笔记缺少逐Figure/Scheme主体")
        if text and not re.search(r"全文收束|证据边界|证据强度", text):
            errors.append("主笔记缺少全文证据收束")
        if text and not re.search(r"迁移|复现|停止条件|转向条件", text):
            errors.append("主笔记缺少复现或迁移收束")

    figure_dir = root / "Figure"
    source_dir = root / "Source"
    if source_dir.is_dir() and not any(p.is_file() for p in source_dir.iterdir()):
        errors.append("Source/ 为空")
    if source_dir.is_dir():
        source_names = {p.name for p in source_dir.iterdir() if p.is_file()}
        for required_source in REQUIRED_SOURCE_PDFS:
            if required_source not in source_names:
                errors.append(f"Source/ 缺少标准命名文件：{required_source}")
        obsolete_source_names = {"原文.pdf", "main.pdf", "supp.pdf", "supplement.pdf"}
        found_obsolete = sorted(source_names & obsolete_source_names)
        if found_obsolete:
            errors.append(
                "Source/ 仍使用非标准正文/补充材料文件名："
                + "、".join(found_obsolete)
            )

    if text and figure_dir.is_dir():
        linked = WIKILINK.findall(text) + MARKDOWN_IMAGE.findall(text)
        linked_set = {Path(unquote(x.strip())).name for x in linked}
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
        if panel_count >= 5 and len(labels) >= max(20, panel_count * 3):
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

        figure_body = text
        obsolete = OBSOLETE_STAGE.findall(figure_body)
        if len(obsolete) >= 2:
            errors.append(
                f"逐Figure主体恢复旧阶段结构：识别到 {len(obsolete)} 个阶段正文/导航标题；"
                "主笔记应直接以 Figure 实验单元讲述，不得叠加第二套固定阶段叙事"
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
            "读图前补课": figure_body.count("读图前补课"),
            "看完Figure": figure_body.count("看完Figure"),
            "Take-home message": figure_body.count("Take-home message"),
        }
        if all(count >= 3 for count in wrapper_counts.values()):
            errors.append(
                "系统性 Figure 包装模板：反复出现“读图前补课—看完Figure—Take-home message”组合；"
                "这些组件只能按实际需要使用，不能成为每图固定三件套"
            )

        # Over-expansion remains advisory because length alone cannot tell
        # whether a scientifically dense panel genuinely needed the space.
        panel_lengths = [
            len(re.findall(r"[\u4e00-\u9fff]", match.group("body")))
            for match in PANEL_BLOCK.finditer(text)
        ]
        if len(panel_lengths) >= 20:
            overlong = sum(length > 650 for length in panel_lengths)
            if advisory and overlong / len(panel_lengths) >= 0.30:
                notices.append(
                    f"识别到 {overlong}/{len(panel_lengths)} 个面板超过650个中文字符（尚未扣除无效内容）；"
                    "请检查是否将重复提醒、统计教程或全文收束中的系统性批判提前写入普通面板"
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
        "--content-advisory",
        action="store_true",
        help="显示非阻断的重复/固定标签提示；这些提示不能作为批量补字依据。",
    )
    args = parser.parse_args()

    root = args.final_dir.resolve()
    errors, notices = audit(root, args.content_advisory)

    for item in errors:
        print(f"ERROR: {item}")
    for item in notices:
        print(f"ADVISORY: {item}")

    status = "PASS" if not errors else "FAIL"
    print(f"SUMMARY: {status} — {len(errors)} objective error(s), {len(notices)} advisory notice(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
