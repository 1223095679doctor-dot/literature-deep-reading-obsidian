#!/usr/bin/env python3
"""Static audit for the final Obsidian deep-reading folder."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path


REQUIRED_DIRS = ("Figure", "Source")
NOTE_NAME = "设计思路与证据审查.md"
TEMP_PATTERNS = (
    re.compile(r"ocr", re.I),
    re.compile(r"render", re.I),
    re.compile(r"contact.?sheet", re.I),
    re.compile(r"cache", re.I),
    re.compile(r"\.log$", re.I),
    re.compile(r"\.py$", re.I),
    re.compile(r"\.DS_Store$"),
)
PLACEHOLDER = re.compile(r"\{\{|\}\}|待填写|占位符|TODO|TBD", re.I)
WIKILINK = re.compile(r"!\[\[Figure/([^\]]+)\]\]")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
FIGURE_NAME = re.compile(r"^(?:Figure|Scheme)(?:\s+S?\d+)(?:-\d+)?\.(?:png|jpe?g|tiff?)$", re.I)
STAGE_HEADING = re.compile(r"^#{1,2}\s+.*阶段\s*(?:\d+|[一二三四五六七八九十百]+).*?$", re.M)
IMAGE_ONLY_LINE = re.compile(r"^\s*!\[\[Figure/[^\]]+\]\]\s*$")
NUMBER_SIGNAL = re.compile(
    r"(?:\bn\s*[=＝]\s*\d+|\d+(?:\.\d+)?\s*%|[Pp]\s*[<=>≤≥]\s*0?\.\d+|"
    r"\d+(?:\.\d+)?\s*(?:mg|μg|ug|ng|mL|μL|h|小时|天|周|倍|mm|cm|μm|nm))"
)
FIGURE_READING_HEADER = re.compile(
    r"面板\s*\|\s*作者图注（中文）\s*\|\s*"
    r"(?:图中具体展示什么|技术与图中内容|对象与读出|颜色与标记对象)\s*\|\s*"
    r"(?:这张图应该怎么看|看什么特征|关键比较|区域和组别)\s*\|\s*"
    r"(?:关键变化或数值|实际结果|可见变化)\s*\|\s*"
    r"(?:读图结论与易误读边界|结构判断与局限|生物学含义与边界|量化要求与取景偏倚)"
)
BARE_CALLOUT = re.compile(r"^\s*\[!(?:note|abstract|question|info|tip|warning|success|example|danger)\]", re.M | re.I)
TABLE_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
TERM_SECTION = re.compile(
    r"^#\s+阅读前置｜重点名词、缩写与核心概念\s*$([\s\S]*?)(?=^#\s+一、)", re.M
)
META_STAGE_CLICHES = (
    "本阶段必须回答的问题来自前一步仍然不够的证据",
    "作者的解决思路是把该缺口拆成相互补充的实验任务",
    "以下先写实验设计与报告完整性",
    "阶段性评价将明确证据等级",
    "最有判别力的下一步实验之后，再说明结果怎样推动到下一阶段",
)
FIGURE_FILLER = re.compile(
    r"见图及图注|见原图(?:及图注)?|本行按对应面板读取|详见(?:原文|论文|图注)|如图所示|\|\s*同上\s*\|",
    re.I,
)
GENERIC_FIGURE_FILLER = re.compile(
    r"论文相应(?:材料|对象|细菌|细胞|动物|组别)|"
    r"按作者报告方向分离|"
    r"提供空间或形态证据|"
    r"支持组间存在(?:图像层面的)?(?:表型)?差异|"
    r"不能(?:单独)?证明(?:上游靶点必要性或)?完整机制链",
    re.I,
)
PANEL_GROUP = re.compile(r"^(?:[A-Za-z]\d?)\s*(?:[–—-]|/|、|,|，|及)\s*(?:[A-Za-z]\d?)", re.I)
FUNCTIONAL_STAGE_TITLE = re.compile(
    r"前一步|必须回答|实验拆解|作者为什么安排|预期结果|失败结果|实际观察|作者.*推理|阶段性评价|下一步实验|推动到下一阶段"
)


def chineseish_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def prose_only(text: str) -> str:
    """Remove tables, image links, callout markers, code fences and headings."""
    kept: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped or stripped.startswith("#") or stripped.startswith("|"):
            continue
        if IMAGE_ONLY_LINE.match(line) or stripped.startswith("> [!"):
            continue
        kept.append(re.sub(r"^>\s?", "", line))
    return "\n".join(kept)


def narrative_only(text: str) -> str:
    """Keep reader-facing paragraphs; exclude tables, headings, images, code and callouts."""
    kept: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped:
            continue
        if stripped.startswith(("#", "|", ">")) or IMAGE_ONLY_LINE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def h1_section(text: str, title_pattern: str) -> str | None:
    match = re.search(rf"^#\s+.*(?:{title_pattern}).*$", text, re.M | re.I)
    if not match:
        return None
    next_h1 = re.search(r"^#\s+", text[match.end():], re.M)
    end = match.end() + next_h1.start() if next_h1 else len(text)
    return text[match.end():end]


def numbered_h2_section(text: str, number: str) -> str | None:
    match = re.search(rf"^##\s+{re.escape(number)}\s+.*$", text, re.M)
    if not match:
        return None
    next_heading = re.search(r"^#{1,2}\s+", text[match.end():], re.M)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end():end]


def data_table_rows(section: str, columns: int) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        cells = table_cells(line)
        if len(cells) != columns or all(TABLE_SEPARATOR_CELL.match(cell) for cell in cells):
            continue
        if cells[0] in {"推进节点", "因果箭头", "阶段"}:
            continue
        rows.append(cells)
    return rows


def section_spans(text: str, pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    matches = list(pattern.finditer(text))
    result: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result.append((match.group(0).lstrip("# ").strip(), text[match.end():end]))
    return result


def table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith(">"):
        stripped = stripped[1:].strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def audit_markdown_tables(text: str) -> list[str]:
    issues: list[str] = []
    lines = text.splitlines()
    for i in range(len(lines) - 1):
        header = table_cells(lines[i])
        separator = table_cells(lines[i + 1])
        if not header or not separator or not all(TABLE_SEPARATOR_CELL.match(cell) for cell in separator):
            continue
        expected = len(header)
        if len(separator) != expected:
            issues.append(f"第 {i + 1} 行附近表格表头 {expected} 列、分隔行 {len(separator)} 列")
        j = i + 2
        while j < len(lines):
            cells = table_cells(lines[j])
            if not cells:
                break
            if len(cells) != expected:
                issues.append(f"第 {j + 1} 行表格应为 {expected} 列，实际 {len(cells)} 列")
            j += 1
    return issues


def audit(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not root.is_dir():
        return [f"最终目录不存在：{root}"], warnings

    current_prefix = datetime.now().astimezone().strftime("%y.%m.%d-")
    if not root.name.startswith(current_prefix):
        errors.append(
            f"文件夹日期不是当前本地日期：应以 {current_prefix} 开头；论文发表日期只写入 frontmatter published"
        )

    note = root / NOTE_NAME
    if not note.is_file():
        errors.append(f"缺少核心笔记：{NOTE_NAME}")
        text = ""
    else:
        text = note.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            errors.append("YAML frontmatter 不是文件首行")
        if PLACEHOLDER.search(text):
            errors.append("笔记仍含占位符/TODO")
        n_chars = chineseish_count(text)
        if n_chars < 12000:
            warnings.append(f"正文仅约 {n_chars} 个非空白字符；复杂论文通常应明显更长")

    for name in REQUIRED_DIRS:
        if not (root / name).is_dir():
            errors.append(f"缺少目录：{name}/")

    allowed_top = {NOTE_NAME, *REQUIRED_DIRS}
    extras = sorted(p.name for p in root.iterdir() if p.name not in allowed_top)
    if extras:
        errors.append("最终目录含额外项目：" + ", ".join(extras))

    for p in root.rglob("*"):
        if any(pattern.search(p.name) for pattern in TEMP_PATTERNS):
            errors.append(f"发现临时/禁止文件：{p.relative_to(root)}")

    if text:
        for phrase in META_STAGE_CLICHES:
            count = text.count(phrase)
            if count:
                errors.append(f"检测到阶段元叙述/模板套话 {count} 次：{phrase}")
        filler_matches = list(FIGURE_FILLER.finditer(text))
        if filler_matches:
            examples = sorted({match.group(0) for match in filler_matches})[:4]
            errors.append(f"逐图/正文含无信息占位 {len(filler_matches)} 处：{'、'.join(examples)}")
        generic_figure_fillers = list(GENERIC_FIGURE_FILLER.finditer(text))
        if generic_figure_fillers:
            examples = sorted({match.group(0) for match in generic_figure_fillers})[:4]
            errors.append(f"逐图表含跨面板通用套话 {len(generic_figure_fillers)} 处：{'、'.join(examples)}")

        if BARE_CALLOUT.search(text):
            for match in BARE_CALLOUT.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                errors.append(f"裸 Callout 语法（缺少 >）：第 {line_no} 行")

        for issue in audit_markdown_tables(text):
            errors.append("Markdown 表格格式错误：" + issue)

        grouped_panels: list[str] = []
        for line in text.splitlines():
            cells = table_cells(line)
            if not cells or all(TABLE_SEPARATOR_CELL.match(cell) for cell in cells):
                continue
            first = re.sub(r"[*`]", "", cells[0]).strip()
            if PANEL_GROUP.match(first) or first in {"全部面板", "所有面板", "全图"}:
                grouped_panels.append(first)
            elif re.match(r"^Figure\s+S?\d+", first, re.I) and len(cells) > 1:
                second = re.sub(r"[*`]", "", cells[1]).strip()
                if re.search(r"(?:^|[；;])\s*[A-Za-z]\d?\s*(?:[–—-]|/|、|,|，|及)\s*[A-Za-z]\d?", second):
                    grouped_panels.append(f"{first}: {second[:35]}")
        if grouped_panels:
            errors.append(
                f"逐面板表存在 {len(grouped_panels)} 个合并行，必须一面板一行：{'；'.join(grouped_panels[:8])}"
            )

        headings = list(HEADING.finditer(text))
        for index, match in enumerate(headings):
            start = match.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            body = re.sub(r"<!--.*?-->", "", text[start:end], flags=re.S).strip()
            if chineseish_count(body) < 40:
                warnings.append(f"标题下内容过薄：{match.group(2)}")

        for stage_name, stage_body in section_spans(text, STAGE_HEADING):
            prose_chars = chineseish_count(prose_only(stage_body))
            figure_links = len(WIKILINK.findall(stage_body))
            number_signals = len(NUMBER_SIGNAL.findall(stage_body))
            stage_layers = {
                "必须回答的问题/前一步缺口": r"必须回答|这一步要回答|为什么不能直接|前一步.*不够|阶段入口",
                "实验任务拆解": r"作者为什么安排|实验拆解|每项表征|分别在证明什么|推理链中的作用",
                "设计与报告完整性": r"实验设计与报告完整性|关键对照|n\s*与|统计单位",
                "成功与失败判定": r"预期结果与失败结果|如果.*成立|如果只是|若假设成立|若假设不成立",
                "实际观察": r"实际观察|证据基础",
                "作者推理": r"作者由这些观察得出什么|作者结论|作者的推理",
                "隐藏前提/推理跳跃": r"隐藏前提|推理跳跃|替代解释",
                "阶段性评价": r"阶段性批判|阶段性评价|证据等级",
                "判别实验": r"最有判别力的下一步实验|最有判别力.*实验",
                "推进下一阶段": r"结果怎样推动到下一阶段|推动到下一阶段|为什么.*下一阶段",
            }
            present_layers = [label for label, pattern in stage_layers.items() if re.search(pattern, stage_body)]
            core_layers = {
                "必须回答的问题/前一步缺口",
                "实验任务拆解",
                "成功与失败判定",
                "实际观察",
                "作者推理",
                "阶段性评价",
                "推进下一阶段",
            }
            for label in sorted(core_layers - set(present_layers)):
                errors.append(f"阶段缺少核心递进层“{label}”：{stage_name}")
            if len(present_layers) < 8:
                warnings.append(
                    f"阶段递进层不完整：{stage_name}（识别到 {len(present_layers)}/10：{'、'.join(present_layers)}）"
                )
            progression_signals = {
                "问题": r"问题|缺口|仍未知|不能区分|不够",
                "思路": r"思路|解决方式|为此|因此选择|打算从|拆解.*问题",
                "方案": r"方案|实验设计|实验拆解|关键对照|作者为什么安排",
                "判定": r"判定|若.*成立|如果.*成立|失败结果|预期结果",
                "结果": r"实际观察|结果显示|证据基础|作者由这些观察",
                "评价": r"阶段性评价|阶段性批判|能支持|证据上限|方法.*不足",
                "残余问题": r"仍然|尚不能|仍不能|留下.*问题|残余",
                "下一步": r"下一步|下一阶段|推动到下一阶段|引出.*实验",
            }
            missing_progression = [
                label for label, pattern in progression_signals.items() if not re.search(pattern, stage_body)
            ]
            if missing_progression:
                errors.append(f"单个阶段闭环不完整：{stage_name}（缺：{'、'.join(missing_progression)}）")
            bridge_count = len(re.findall(r"前一步|上一.*证据|承接|仍不能|仍然不够|由此|因此.*下一|推动.*下一", stage_body))
            if bridge_count < 3:
                warnings.append(f"阶段内部递进连接偏少：{stage_name}（识别到 {bridge_count} 个缺口/推进桥）")
            opening = prose_only(stage_body)[:900]
            if re.search(r"阶段性评价|证据等级|当前能支持|当前不能支持|设计优点|设计缺点", opening):
                warnings.append(f"阶段开头疑似先批判后引题：{stage_name}")
            if prose_chars < 1200 and figure_links >= 1:
                errors.append(
                    f"阶段分析正文严重不足：{stage_name}（有效叙述约 {prose_chars} 字符，图片 {figure_links} 张）"
                )
            elif prose_chars < 2000 and figure_links >= 2:
                errors.append(
                    f"核心阶段未达到深度下限：{stage_name}（有效叙述约 {prose_chars} 字符，图片 {figure_links} 张；至少 2000）"
                )
            elif prose_chars < 3000 and figure_links >= 4:
                warnings.append(
                    f"复杂承重阶段仍可能偏薄：{stage_name}（有效叙述约 {prose_chars} 字符，图片 {figure_links} 张）"
                )
            if figure_links >= 2 and number_signals == 0:
                warnings.append(f"阶段缺少可识别定量信号：{stage_name}")

        repeated_stage_paragraphs: dict[str, list[str]] = {}
        for stage_name, stage_body in section_spans(text, STAGE_HEADING):
            for paragraph in re.split(r"\n\s*\n", prose_only(stage_body)):
                normalized = re.sub(r"\s+", "", paragraph)
                if len(normalized) >= 120:
                    repeated_stage_paragraphs.setdefault(normalized, []).append(stage_name)
        for paragraph, stages in repeated_stage_paragraphs.items():
            unique_stages = list(dict.fromkeys(stages))
            if len(unique_stages) >= 2:
                errors.append(
                    f"多个阶段复制同一长段，疑似模板污染：{'；'.join(unique_stages)}（段首：{paragraph[:45]}…）"
                )

        consecutive_images = 0
        max_consecutive_images = 0
        for line in text.splitlines():
            if IMAGE_ONLY_LINE.match(line):
                consecutive_images += 1
                max_consecutive_images = max(max_consecutive_images, consecutive_images)
            elif line.strip() and not line.strip().startswith("<!--"):
                consecutive_images = 0
        if max_consecutive_images >= 2:
            errors.append(f"检测到最多 {max_consecutive_images} 张图片连续堆放，图片之间缺少实质分析")

        if re.search(r"^#\s+.*逐图.*(?:Supporting Information|SI|证据审查)", text, re.M | re.I):
            errors.append("检测到孤立的逐图/SI证据审查大章节；图片必须拆回它们服务的阶段并就地分析")

        linked = WIKILINK.findall(text)
        figure_dir = root / "Figure"
        for name in linked:
            if not (figure_dir / name).is_file():
                errors.append(f"图片链接不存在：Figure/{name}")

        if figure_dir.is_dir():
            files = [p.name for p in figure_dir.iterdir() if p.is_file()]
            for name in files:
                if not FIGURE_NAME.match(name):
                    warnings.append(f"图片命名可能不符合原图号规则：{name}")
                if name not in linked:
                    warnings.append(f"Figure 文件未在笔记中引用：{name}")

        data_figures = len(re.findall(r"!\[\[Figure/Figure\s+S?\d+[^\]]*\]\]", text, re.I))
        evidence_tables = len(FIGURE_READING_HEADER.findall(text))
        takehomes = len(re.findall(r"take[- ]?home|真正的?\s*take-home|真正结论", text, re.I))
        if data_figures and evidence_tables < data_figures:
            errors.append(f"数据 Figure 链接 {data_figures} 个，但逐面板六列读图导航表仅识别到 {evidence_tables} 个")
        if data_figures and takehomes < data_figures:
            warnings.append(f"数据 Figure 链接 {data_figures} 个，但 take-home 标记仅识别到 {takehomes} 个")

        image_matches = list(WIKILINK.finditer(text))
        for index, match in enumerate(image_matches):
            name = match.group(1)
            end = image_matches[index + 1].start() if index + 1 < len(image_matches) else len(text)
            block = text[match.end():end]
            if re.match(r"Figure\s+S?\d+", name, re.I):
                if not FIGURE_READING_HEADER.search(block):
                    errors.append(f"Figure 缺少含作者中文图注的逐面板六列读图导航表：{name}")
                if not re.search(r"take[- ]?home|真正结论", block, re.I):
                    errors.append(f"Figure 缺少独立 take-home message：{name}")

        inspiration_match = re.search(
            r"^##\s+1\.2\s+.*灵感.*$([\s\S]*?)(?=^##\s+1\.[3-9]|^#\s+)",
            text,
            re.M,
        )
        if inspiration_match:
            inspiration = inspiration_match.group(1)
            inspiration_prose = chineseish_count(prose_only(inspiration))
            point_pattern = re.compile(r"^###\s+(.+?)\s*$", re.M)
            inspiration_points = section_spans(inspiration, point_pattern)
            if len(inspiration_points) >= 3 and inspiration_prose < 1200:
                errors.append(
                    f"灵感部分分析深度不足：{len(inspiration_points)} 个灵感点仅约 {inspiration_prose} 个有效叙述字符（至少 1200）"
                )
            for point_name, point_body in inspiration_points:
                point_chars = chineseish_count(prose_only(point_body))
                if point_chars < 220:
                    errors.append(f"灵感点展开不足：{point_name}（有效叙述约 {point_chars} 字符；至少 220）")
            design_signals = len(
                re.findall(r"为什么会想到|已知线索|构思来源|设计要求|设计约束|单靠.*不够|为什么.*不够", inspiration)
            )
            if design_signals < 3:
                warnings.append("灵感部分的构思来源/设计约束信号不足，可能仍在回放实验步骤")
            if len(re.findall(r"Figure\s+S?\d+|Fig\.\s*S?\d+", inspiration, re.I)) >= 3:
                warnings.append("灵感部分频繁引用 Figure，可能把 Results 路线误写成构思来源")
        else:
            warnings.append("未识别到 1.2 灵感形成部分")

        for match_index, heading_match in enumerate(headings):
            title = heading_match.group(2)
            if not FUNCTIONAL_STAGE_TITLE.search(title):
                continue
            start = heading_match.end()
            end = headings[match_index + 1].start() if match_index + 1 < len(headings) else len(text)
            body_chars = chineseish_count(prose_only(text[start:end]))
            if body_chars < 180:
                errors.append(f"阶段功能小节只有摘要、缺少分析展开：{title}（有效叙述约 {body_chars} 字符）")

        term_match = TERM_SECTION.search(text)
        if term_match:
            term_body = term_match.group(1)
            term_rows = []
            for line in term_body.splitlines():
                cells = table_cells(line)
                if cells and cells[0] not in {"名词 / 缩写", "---"} and not all(TABLE_SEPARATOR_CELL.match(c) for c in cells):
                    term_rows.append(cells)
            category_count = len(re.findall(r"^##\s+", term_body, re.M))
            if len(term_rows) >= 8 and category_count < 2:
                warnings.append(f"重点名词共识别到 {len(term_rows)} 条但未按至少两个真实知识系统分类")
            if len(term_rows) < 8:
                warnings.append(f"重点名词仅识别到 {len(term_rows)} 条；请确认是否足以独立读懂主线")
            for cells in term_rows:
                term = cells[0] if cells else ""
                if re.search(r"\s/\s|、|；|\b(?:and|vs\.?|or)\b", term, re.I):
                    warnings.append(f"重点名词可能挤入多个独立概念：{term}")
                if len(cells) >= 4 and chineseish_count(cells[3]) < 18:
                    warnings.append(f"重点名词“在本文中的作用”过短：{term}")
        else:
            warnings.append("未识别到重点名词模块")

        map_section = h1_section(text, r"整篇论证地图")
        if map_section is None:
            errors.append("未识别到整篇论证地图章节")
        else:
            map_titles = {
                "2.1 全文工作模型": r"^##\s+2\.1\s+全文工作模型",
                "2.2 每一步为什么不能被前一步替代": r"^##\s+2\.2\s+每一步为什么不能被前一步替代",
                "2.3 关键箭头的证据状态": r"^##\s+2\.3\s+关键箭头的证据状态",
                "2.4 全文阶段导航": r"^##\s+2\.4\s+全文阶段导航",
            }
            for label, pattern in map_titles.items():
                if not re.search(pattern, map_section, re.M):
                    errors.append(f"整篇论证地图缺少固定模块：{label}")

            map_22 = numbered_h2_section(map_section, "2.2") or ""
            map_23 = numbered_h2_section(map_section, "2.3") or ""
            map_24 = numbered_h2_section(map_section, "2.4") or ""
            rows_22 = data_table_rows(map_22, 5)
            rows_23 = data_table_rows(map_23, 5)
            rows_24 = data_table_rows(map_24, 6)
            stage_count = len(section_spans(text, STAGE_HEADING))
            if stage_count >= 3 and len(rows_22) < 3:
                errors.append(f"论证地图2.2深度不足：仅 {len(rows_22)} 个有效推进节点")
            if stage_count >= 3 and len(rows_23) < 3:
                errors.append(f"论证地图2.3深度不足：仅 {len(rows_23)} 个关键箭头")
            if stage_count and len(rows_24) != stage_count:
                errors.append(f"论证地图2.4未覆盖全部阶段：导航 {len(rows_24)} 行，阶段主体 {stage_count} 个")
            vague_map = re.compile(r"^(?:进一步验证|继续探究|机制不明|未知|待验证|同上|无)$")
            for section_no, rows in (("2.2", rows_22), ("2.3", rows_23), ("2.4", rows_24)):
                for row_index, cells in enumerate(rows, 1):
                    for col_index, cell in enumerate(cells, 1):
                        compact = re.sub(r"\s+", "", cell)
                        if section_no == "2.2":
                            too_thin = len(compact) < 4 or vague_map.match(compact)
                        elif section_no == "2.3":
                            minimum = (4, 6, 2, 6, 2)[col_index - 1]
                            too_thin = len(compact) < minimum or (col_index == 4 and vague_map.match(compact))
                        else:
                            minimum = (1, 6, 4, 4, 4, 4)[col_index - 1]
                            too_thin = len(compact) < minimum or (col_index > 1 and vague_map.match(compact))
                        if too_thin:
                            errors.append(
                                f"论证地图{section_no}表格信息过薄：第{row_index}行第{col_index}列“{cell}”"
                            )

        competition = h1_section(text, r"竞争性?解释|双向压力测试|压力测试")
        if competition is None:
            errors.append("未识别到竞争解释与压力测试章节")
        else:
            competition_chars = chineseish_count(narrative_only(competition))
            if competition_chars < 1000:
                errors.append(
                    f"竞争解释与压力测试深度不足：有效叙述约 {competition_chars} 字符（至少 1000，不计表格/Callout）"
                )
            competition_models = len(re.findall(r"竞争模型\s*[一二三四五六七八九十\d]+", competition))
            if competition_models < 1:
                errors.append("竞争解释章节没有可识别的具体竞争模型")
            elif competition_models < 2:
                warnings.append("仅识别到一个竞争模型；复杂论文通常至少需要两个实质模型")
            competition_requirements = {
                "解释多项现有结果": r"能解释哪些现有结果|同时解释|解释.*结果",
                "模型解释失败处": r"无法解释|解释不了",
                "差异预测": r"真正能区分|特异预测|不同预测|差异预测",
                "A/B双向判定": r"结果\s*A|结果A.*结果B|结果\s*B",
                "机制失败后的剩余贡献": r"最小可发表故事|即使.*失败|还剩下什么",
            }
            for label, pattern in competition_requirements.items():
                if not re.search(pattern, competition, re.I | re.S):
                    errors.append(f"竞争解释章节缺少：{label}")

        final_review = h1_section(text, r"最终复盘")
        if final_review is None:
            errors.append("未识别到最终复盘章节")
        else:
            final_chars = chineseish_count(narrative_only(final_review))
            if final_chars < 800:
                errors.append(
                    f"最终复盘深度不足：有效叙述约 {final_chars} 字符（至少 800，不计表格/Callout）"
                )
            final_requirements = {
                "稳健核心": r"稳健核心|即使.*错误.*仍.*成立",
                "条件性结论": r"条件性结论|依赖.*前提",
                "脆弱机制": r"脆弱机制|分叉实验.*失败",
                "未建立外推": r"未建立外推|未直接检验.*外推",
                "真正完成了什么": r"真正完成了什么|论文真正完成|已完成",
                "尚未证明什么": r"尚未证明|还没有证明|论文还没有证明|未完成",
                "关键因果断点": r"关键.*因果断点|最关键.*因果",
            }
            for label, pattern in final_requirements.items():
                if not re.search(pattern, final_review, re.I | re.S):
                    errors.append(f"最终复盘缺少：{label}")

        supplementary_figures = len(re.findall(r"!\[\[Figure/Figure\s+S\d+[^\]]*\]\]", text, re.I))
        supplementary_mentions = len(re.findall(r"Figure\s+S\d+", text, re.I))
        if supplementary_figures and supplementary_mentions < supplementary_figures * 2:
            warnings.append("部分 Figure S 可能只有图片链接，缺少独立正文或逐图分析")

        required_concepts = {
            "统计/偏倚审查": r"统计.*偏倚|偏倚.*统计",
            "竞争解释/压力测试": r"竞争.*解释|压力测试|红队",
            "证据矩阵": r"证据矩阵",
            "真正完成了什么": r"真正完成了什么",
            "尚未证明什么": r"还没有证明什么|尚未证明什么",
        }
        for label, pattern in required_concepts.items():
            if not re.search(pattern, text):
                warnings.append(f"未识别到关键模块：{label}")

    source_dir = root / "Source"
    if source_dir.is_dir() and not any(p.is_file() for p in source_dir.iterdir()):
        errors.append("Source/ 为空")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("final_dir", type=Path)
    args = parser.parse_args()
    errors, warnings = audit(args.final_dir.resolve())
    for item in errors:
        print(f"ERROR: {item}")
    for item in warnings:
        print(f"WARNING: {item}")
    print(f"SUMMARY: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
