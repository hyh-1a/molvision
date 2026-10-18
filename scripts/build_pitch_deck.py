"""Build the MolVision pitch deck draft (8 slides, editable)."""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "MolVision-pitch.pptx"

# palette
PAPER = RGBColor(0xF5, 0xF1, 0xE8)
PAPER_2 = RGBColor(0xFB, 0xF8, 0xF1)
INK = RGBColor(0x15, 0x18, 0x1A)
MUTED = RGBColor(0x7B, 0x73, 0x64)
FAINT = RGBColor(0xA7, 0x9E, 0x8C)
ACCENT = RGBColor(0x1D, 0x3F, 0x66)
COPPER = RGBColor(0xB0, 0x57, 0x2F)
LINE = RGBColor(0xD6, 0xCD, 0xB9)
HEAD_FILL = RGBColor(0xE9, 0xE1, 0xD0)

TITLE_FONT = "Georgia"
BODY_FONT = "Microsoft YaHei"

W, H = Inches(13.333), Inches(7.5)


def _set_ea(run, name: str) -> None:
    rpr = run._r.get_or_add_rPr()
    ea = rpr.find(qn("a:ea"))
    if ea is None:
        ea = rpr.makeelement(qn("a:ea"), {})
        rpr.append(ea)
    ea.set("typeface", name)


def style_run(run, size=18, color=INK, bold=False, font=BODY_FONT, italic=False):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = font
    _set_ea(run, font)


def strip_style(shape) -> None:
    """Drop the theme style reference so LibreOffice/PowerPoint show no shadow."""
    sp = shape._element
    style = sp.find(qn("p:style"))
    if style is not None:
        sp.remove(style)


def add_bg(slide) -> None:
    rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
    rect.fill.solid()
    rect.fill.fore_color.rgb = PAPER
    rect.line.fill.background()
    rect.shadow.inherit = False
    strip_style(rect)


def textbox(slide, x, y, w, h, text, size=18, color=INK, bold=False,
            font=BODY_FONT, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
            spacing=1.0):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = spacing
    run = p.add_run()
    run.text = text
    style_run(run, size, color, bold, font)
    return box


def add_lines(slide, x, y, w, items, size=18, color=INK, gap=8):
    """items: (text, size, color, bold[, space_after_pt])."""
    box = slide.shapes.add_textbox(x, y, w, Inches(3))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = 0
    for i, item in enumerate(items):
        text, sz, col, bold = item[:4]
        after = item[4] if len(item) > 4 else gap
        before = item[5] if len(item) > 5 else 0
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(after)
        if before:
            p.space_before = Pt(before)
        run = p.add_run()
        run.text = text
        style_run(run, sz or size, col or color, bold)
    return box


def kicker(slide, text, y=Inches(0.55)):
    textbox(slide, Inches(0.8), y, Inches(8), Inches(0.35), text,
            size=11, color=COPPER, bold=True)


def rule(slide, x, y, w):
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, Pt(1))
    line.fill.solid()
    line.fill.fore_color.rgb = LINE
    line.line.fill.background()
    line.shadow.inherit = False
    strip_style(line)


def add_table(slide, rows, cols, x, y, w, h, col_widths=None):
    shape = slide.shapes.add_table(rows, cols, x, y, w, h)
    table = shape.table
    if col_widths:
        for i, cw in enumerate(col_widths):
            table.columns[i].width = cw
    return table


def cell_text(cell, text, size=14, color=INK, bold=False, font=BODY_FONT,
              align=PP_ALIGN.LEFT):
    cell.text = ""
    tf = cell.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    style_run(run, size, color, bold, font)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    cell.margin_left = Inches(0.12)
    cell.margin_right = Inches(0.08)
    cell.margin_top = Inches(0.04)
    cell.margin_bottom = Inches(0.04)


def notes(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


def slide_number(slide, n: int) -> None:
    textbox(slide, Inches(12.3), Inches(7.05), Inches(0.6), Inches(0.3),
            f"{n:02d}", size=10, color=FAINT, align=PP_ALIGN.RIGHT)


def main() -> None:
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    blank = prs.slide_layouts[6]

    # ---------------------------------------------------------------- 1 title
    s = prs.slides.add_slide(blank)
    add_bg(s)
    textbox(s, Inches(0.9), Inches(1.6), Inches(9), Inches(0.4),
            "MOLVISION", size=13, color=COPPER, bold=True)
    textbox(s, Inches(0.9), Inches(2.05), Inches(11), Inches(1.2),
            "From a drawing to a molecule.", size=52, color=INK,
            font=TITLE_FONT)
    textbox(s, Inches(0.95), Inches(3.25), Inches(11), Inches(0.6),
            "从论文插图到可检索分子", size=26, color=ACCENT)
    rule(s, Inches(0.95), Inches(4.15), Inches(4.2))
    textbox(s, Inches(0.95), Inches(4.4), Inches(10), Inches(0.5),
            "图片  →  SMILES  →  2D / 3D  +  分子描述符", size=16, color=MUTED)
    textbox(s, Inches(0.95), Inches(6.55), Inches(8), Inches(0.4),
            "Hackathon draft · 2026-10", size=11, color=FAINT)
    notes(s, "开场一句话：把论文里的结构变成可检索、可计算的数据。不要先讲技术。")
    slide_number(s, 1)

    # ------------------------------------------------------------- 2 problem
    s = prs.slides.add_slide(blank)
    add_bg(s)
    kicker(s, "PROBLEM")
    textbox(s, Inches(0.8), Inches(1.0), Inches(11.6), Inches(1.1),
            "文献里的结构，是图片，不是数据。", size=34, color=INK, font=TITLE_FONT)
    add_lines(s, Inches(0.8), Inches(2.45), Inches(7.2), [
        ("40 个结构", 40, ACCENT, True, 2),
        ("一篇 JACS 论文里的典型数量", 15, MUTED, False, 20),
        ("5 分钟", 40, ACCENT, True, 2),
        ("手画一个结构的时间", 15, MUTED, False, 20),
        ("3 小时 / 篇", 40, COPPER, True, 2),
        ("画完仍然是死数据：不能搜、不能算、不能进库", 15, MUTED, False, 4),
    ])
    textbox(s, Inches(8.6), Inches(2.35), Inches(4), Inches(4),
            "图片\n\n不可搜索\n不可计算\n不可复用", size=20, color=FAINT,
            align=PP_ALIGN.LEFT, spacing=1.4)
    notes(s, "痛点用数字讲，不要讲模型。40 个结构 × 5 分钟 = 3 小时，而且结果还是图片。")
    slide_number(s, 2)

    # ----------------------------------------------------------- 3 why not
    s = prs.slides.add_slide(blank)
    add_bg(s)
    kicker(s, "WHY EXISTING TOOLS FAIL")
    textbox(s, Inches(0.8), Inches(0.95), Inches(11.6), Inches(0.9),
            "缺的不是识别模型，是工作流。", size=30, color=INK, font=TITLE_FONT)
    table = add_table(s, 4, 2, Inches(0.8), Inches(2.15), Inches(11.7), Inches(3.6),
                      [Inches(3.4), Inches(8.3)])
    rows = [
        ("方案", "问题"),
        ("手画（ChemDraw）", "规模上不可行：一篇论文三个小时"),
        ("通用 OCR / 视觉模型", "不认识化学键、立体化学和 R 基"),
        ("识别模型（OSRA / DECIMER）", "只认单张干净图；多结构、表格、反应式就崩"),
    ]
    for r, (a, b) in enumerate(rows):
        for c, val in enumerate((a, b)):
            cell = table.cell(r, c)
            cell_text(cell, val, size=16 if r else 12,
                      color=INK if r else MUTED, bold=(r == 0))
            cell.fill.solid()
            cell.fill.fore_color.rgb = HEAD_FILL if r == 0 else PAPER_2
    notes(s, "这一页回答“为什么不是已经有工具了”。结论落在工作流，而不是模型能力。")
    slide_number(s, 3)

    # ---------------------------------------------------------- 4 pipeline
    s = prs.slides.add_slide(blank)
    add_bg(s)
    kicker(s, "WHAT WE BUILT")
    textbox(s, Inches(0.8), Inches(0.95), Inches(11.6), Inches(0.8),
            "一张图进，结构化数据出。", size=30, color=INK, font=TITLE_FONT)

    steps = [
        ("图片 / PDF", "上传或拖入"),
        ("切分", "多结构 · 去标签"),
        ("识别", "DECIMER"),
        ("校验", "RDKit"),
        ("结果", "2D/3D + 描述符"),
    ]
    x = Inches(0.75)
    bw, bh = Inches(2.05), Inches(1.15)
    for i, (title, sub) in enumerate(steps):
        box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, Inches(2.35), bw, bh)
        box.fill.solid()
        box.fill.fore_color.rgb = PAPER_2
        box.line.color.rgb = LINE
        box.shadow.inherit = False
        strip_style(box)
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = title
        style_run(run, 18, INK, True)
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = sub
        style_run(r2, 11, MUTED)
        if i < len(steps) - 1:
            arrow = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW,
                                       x + bw + Inches(0.06), Inches(2.78),
                                       Inches(0.38), Inches(0.3))
            arrow.fill.solid()
            arrow.fill.fore_color.rgb = FAINT
            arrow.line.fill.background()
            arrow.shadow.inherit = False
            strip_style(arrow)
        x += bw + Inches(0.5)

    chips = ["一图多分子", "结构校验与警示", "Markush 不丢弃"]
    cx = Inches(0.8)
    for chip in chips:
        shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(4.35),
                                 Inches(3.0), Inches(0.55))
        shp.fill.solid()
        shp.fill.fore_color.rgb = PAPER
        shp.line.color.rgb = ACCENT
        shp.shadow.inherit = False
        strip_style(shp)
        tf = shp.text_frame
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = chip
        style_run(run, 14, ACCENT, True)
        cx += Inches(3.35)

    textbox(s, Inches(0.8), Inches(5.5), Inches(11.6), Inches(1.2),
            "自动的交给模型，判断的交给化学：切分、校验、R 基、失败兜底——这些不在模型里。",
            size=15, color=MUTED)
    notes(s, "pipeline 一页讲完，重点说“自动的交给模型，判断的交给化学”。")
    slide_number(s, 4)

    # --------------------------------------------------------------- 5 demo
    s = prs.slides.add_slide(blank)
    add_bg(s)
    textbox(s, Inches(0.8), Inches(2.4), Inches(11.6), Inches(1.2),
            "Live demo", size=64, color=INK, font=TITLE_FONT)
    textbox(s, Inches(0.85), Inches(3.75), Inches(11), Inches(0.5),
            "http://127.0.0.1:8765", size=20, color=ACCENT)
    textbox(s, Inches(0.85), Inches(4.4), Inches(11), Inches(0.5),
            "30 秒讲完，剩下交给操作。", size=14, color=MUTED)
    notes(s, "这一页只放 Live demo。演示顺序：多结构 → 单分子 + 警示 → Crop。"
             "卡住就切到预置样例，不要现场 debug。")
    slide_number(s, 5)

    # ------------------------------------------------------------- 6 depth
    s = prs.slides.add_slide(blank)
    add_bg(s)
    kicker(s, "TECHNICAL DEPTH")
    textbox(s, Inches(0.8), Inches(0.95), Inches(11.6), Inches(0.8),
            "三个别人不会做的点。", size=30, color=INK, font=TITLE_FONT)

    cols = [
        ("01  切分", "投影找空白带 + 长笔画过滤\n排除编号、表格线、箭头"),
        ("02  校验", "RDKit 重算价键/手性/芳香性\nPAINS、Lipinski、幻觉金属告警"),
        ("03  Markush", "R / R1 / R'' → *，未定义按甲基\nPh / Me / Boc 等缩写自动展开"),
    ]
    x = Inches(0.8)
    for title, body in cols:
        textbox(s, x, Inches(2.2), Inches(3.7), Inches(0.5),
                title, size=20, color=ACCENT, bold=True)
        textbox(s, x, Inches(2.8), Inches(3.7), Inches(1.6),
                body, size=14, color=INK, spacing=1.5)
        x += Inches(4.0)
    rule(s, Inches(0.8), Inches(4.85), Inches(11.7))
    textbox(s, Inches(0.8), Inches(5.1), Inches(11.6), Inches(1.2),
            "工程侧：TF 推理串行化、图片哈希缓存、失败自动切手绘模型、旋转 90°/270° 重试。",
            size=14, color=MUTED)
    notes(s, "每点一句话，不要展开算法。评委记住三个词：切分、校验、Markush。")
    slide_number(s, 6)

    # ------------------------------------------------------------ 7 evidence
    s = prs.slides.add_slide(blank)
    add_bg(s)
    kicker(s, "EVIDENCE")
    textbox(s, Inches(0.8), Inches(0.95), Inches(11.6), Inches(0.8),
            "可重复的评测，不靠感觉。", size=30, color=INK, font=TITLE_FONT)

    table = add_table(s, 8, 2, Inches(0.8), Inches(2.0), Inches(7.0), Inches(3.3),
                      [Inches(4.4), Inches(2.6)])
    data = [
        ("测试集", "结果"),
        ("合成单分子（6）", "6 / 6"),
        ("多结构 2×2 + 1×3", "4/4 + 3/3"),
        ("合成反应式（3 结构）", "3 / 3"),
        ("Golden set（14 用例）", "13 / 13"),
        ("100 分子识别压测", "98%"),
        ("晶体配体 RMSD（12）", "0.90 Å"),
        ("缓存命中", "0.01 s"),
    ]
    for r, (a, b) in enumerate(data):
        for c, val in enumerate((a, b)):
            cell = table.cell(r, c)
            cell_text(cell, val, size=14 if r else 11,
                      color=INK if r else MUTED, bold=(r == 0))
            cell.fill.solid()
            cell.fill.fore_color.rgb = HEAD_FILL if r == 0 else PAPER_2

    textbox(s, Inches(8.2), Inches(2.0), Inches(4.4), Inches(0.4),
            "失败分析（主动放）", size=12, color=COPPER, bold=True)
    add_lines(s, Inches(8.2), Inches(2.45), Inches(4.4), [
        ("反应式 / 稠密图", 14, INK, True, 2),
        ("自动切分不可靠 → 提供 Crop 手动框选", 12, MUTED, False, 14),
        ("手绘 / 低清", 14, INK, True, 2),
        ("准确率下降，标记为已知边界", 12, MUTED, False, 14),
        ("R 基", 14, INK, True, 2),
        ("未定义时按甲基假设，可手动替换", 12, MUTED, False, 2),
    ])

    textbox(s, Inches(0.8), Inches(5.45), Inches(11.6), Inches(0.8),
            "知道哪里会错，比“我们全对”更可信。", size=16, color=ACCENT, bold=True)
    notes(s, "数字要背：6/6、3/3、13/13、98%、0.90 Å、0.01s。然后主动讲失败，评委反而信。")
    slide_number(s, 7)

    # --------------------------------------------------------------- 8 close
    s = prs.slides.add_slide(blank)
    add_bg(s)
    kicker(s, "VALUE & NEXT")
    textbox(s, Inches(0.8), Inches(0.95), Inches(11.6), Inches(0.9),
            "让文献里的结构，第一次变成数据。", size=30, color=INK,
            font=TITLE_FONT)

    add_lines(s, Inches(0.8), Inches(2.15), Inches(5.6), [
        ("用户", 12, COPPER, True, 4, 0),
        ("专利审查员 · 文献数据库标注员 · 实验室 ELN", 15, INK, False, 20, 0),
        ("价值", 12, COPPER, True, 4, 10),
        ("一篇论文 3 小时 → 3 分钟", 15, INK, True, 4, 0),
        ("结构可检索、可计算、可导出", 15, INK, False, 4, 0),
    ])

    add_lines(s, Inches(7.0), Inches(2.15), Inches(5.4), [
        ("下一步", 12, COPPER, True, 4, 0),
        ("1. PDF 分页批量 + 进度", 15, INK, False, 2, 0),
        ("2. 20 张真实文献评测集", 15, INK, False, 2, 0),
        ("3. 对接 ELN / 数据库", 15, INK, False, 18, 0),
        ("团队", 12, COPPER, True, 4, 10),
        ("化学 × 工程（按实际填写）", 15, INK, False, 4, 0),
    ])

    rule(s, Inches(0.8), Inches(5.6), Inches(11.7))
    textbox(s, Inches(0.8), Inches(5.85), Inches(11.6), Inches(0.8),
            "MolVision · 本地运行 · 不上传任何图片", size=14, color=MUTED)
    notes(s, "收尾落在“数据”而不是“识别”。最后一句：我们想解决的不是识别一张图，"
             "是让文献里的结构第一次变成数据。")
    slide_number(s, 8)

    prs.save(OUT)
    print("saved", OUT)


if __name__ == "__main__":
    main()
