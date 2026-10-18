"""Build the TECHATHON submission deck in the opening-deck visual language."""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "提交材料"

BG = RGBColor(0xF7, 0xF7, 0xF7)
INK = RGBColor(0x11, 0x11, 0x11)
GRAY = RGBColor(0x66, 0x66, 0x66)
LIGHT = RGBColor(0xD9, 0xD9, 0xD9)
RED = RGBColor(0xE4, 0x00, 0x2B)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x0B, 0x0B, 0x0D)

FONT = "微软雅黑"


def set_font(run, size, bold=False, color=INK):
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        rPr.append(ea)
    ea.set("typeface", FONT)


def add_text(slide, x, y, w, h, text, size=12, bold=False, color=INK,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line=1.25):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    lines = text.split("\n")
    for i, line_text in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line
        r = p.add_run()
        r.text = line_text
        set_font(r, size, bold, color)
    return box


def add_rect(slide, x, y, w, h, fill=WHITE, line=None, shape=MSO_SHAPE.RECTANGLE):
    sp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(0.75)
    sp.shadow.inherit = False
    return sp


def add_rule(slide, x, y, w, color=RED, thickness=3):
    sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                Inches(w), Pt(thickness))
    sp.fill.solid()
    sp.fill.fore_color.rgb = color
    sp.line.fill.background()
    sp.shadow.inherit = False
    return sp


def new_slide(prs, bg=BG):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_rect(slide, 0, 0, 13.333, 7.5, fill=bg)
    return slide


def topbar(slide, section, page, color=GRAY):
    add_text(slide, 0.55, 0.35, 3.2, 0.3, "TECHATHON / 2026", 9, False, color)
    add_text(slide, 5.6, 0.35, 2.2, 0.3, section, 9, False, color, PP_ALIGN.CENTER)
    add_text(slide, 10.2, 0.35, 2.6, 0.3, str(page), 9, False, color, PP_ALIGN.RIGHT)


def heading(slide, text, y=0.95, size=30):
    add_text(slide, 0.55, y, 12.2, 1.0, text, size, True, INK)


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def build() -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # ---------------------------------------------------------------- cover
    s = new_slide(prs, DARK)
    add_text(s, 0.55, 0.4, 6.0, 0.3, "SHANGHAITECH  /  TECHATHON 2026", 9, True, WHITE)
    add_text(s, 0.55, 1.55, 12.0, 0.4, "MOLVISION", 12, True, RED)
    add_text(s, 0.55, 1.95, 12.0, 1.3, "结构式识图", 60, True, WHITE)
    add_rule(s, 0.6, 3.35, 3.2, RED, 4)
    add_text(s, 0.55, 3.6, 11.5, 0.6, "从一张结构图，到可计算的分子", 22, False, WHITE)
    add_text(s, 0.55, 4.25, 11.5, 0.5,
             "图片 → SMILES → 2D / 3D / 描述符 → SDF", 13, False, RGBColor(0xB5, 0xB5, 0xB5))
    add_text(s, 0.55, 6.55, 8.0, 0.4, "团队 MolVision　|　2026.10.18", 11, False, RGBColor(0x9A, 0x9A, 0x9A))
    add_text(s, 10.2, 6.55, 2.6, 0.4, "5 min pitch", 10, False, RGBColor(0x9A, 0x9A, 0x9A), PP_ALIGN.RIGHT)
    notes(s, "开场 15 秒：我们做的是把图片里的化学结构，变成能搜索、能计算的数据。")

    # ---------------------------------------------------------------- pain
    s = new_slide(prs)
    topbar(s, "痛点", 2)
    heading(s, "结构式在论文里，是死图片。")
    items = [
        ("01", "搜不到", "结构图没有文本层，\n无法检索、复用、比对。"),
        ("02", "画得慢", "手工重画一个分子 5–15 分钟，\n复杂结构更容易画错。"),
        ("03", "算不了", "OCR 只认字，不懂键级、\n芳香性、立体化学。"),
    ]
    for i, (num, title, desc) in enumerate(items):
        x = 0.55 + i * 4.15
        add_rect(s, x, 2.35, 3.85, 3.1, WHITE, LIGHT)
        add_text(s, x + 0.3, 2.55, 0.8, 0.4, num, 22, True, RED)
        add_text(s, x + 0.3, 3.05, 3.2, 0.5, title, 19, True, INK)
        add_text(s, x + 0.3, 3.65, 3.25, 1.5, desc, 12, False, GRAY, line=1.35)
    add_text(s, 0.55, 5.95, 12.0, 0.5, "我们想把「图」变成「可计算的数据」。", 18, True, INK)
    notes(s, "40 秒：三个痛点，落在同一件事——结构图不是数据。")

    # ---------------------------------------------------------------- solution
    s = new_slide(prs)
    topbar(s, "解决方案", 3)
    heading(s, "一条能检查的化学流水线。")
    steps = ["图片", "切分", "识别", "化学归一", "2D / 3D / 描述符", "SDF / CSV"]
    widths = [1.15, 1.15, 1.35, 1.75, 2.35, 1.55]
    x = 0.55
    for i, (label, w) in enumerate(zip(steps, widths)):
        add_rect(s, x, 2.55, w, 0.95, WHITE, LIGHT, MSO_SHAPE.ROUNDED_RECTANGLE)
        add_text(s, x + 0.05, 2.78, w - 0.1, 0.5, label, 11, True, INK, PP_ALIGN.CENTER)
        if i < len(steps) - 1:
            add_text(s, x + w + 0.02, 2.75, 0.18, 0.5, "→", 14, True, RED, PP_ALIGN.CENTER)
        x += w + 0.22
    add_text(s, 0.55, 4.0, 12.0, 0.9,
             "识别模型只负责读图；切分、归一、校验、3D 和导出由确定性代码完成。",
             15, False, INK)
    add_text(s, 0.55, 4.55, 12.0, 0.9,
             "换模型不换行为，失败可定位，结果可复现。",
             15, True, RED)
    add_text(s, 0.55, 5.7, 12.0, 0.5,
             "输入：PNG / JPG / 手绘 / 整页 PDF　→　输出：SMILES / SDF / CSV / 描述符",
             11, False, GRAY)
    notes(s, "50 秒：强调解耦。模型可替换，下游是确定的。")

    # ---------------------------------------------------------------- tech
    s = new_slide(prs)
    topbar(s, "技术亮点", 4)
    heading(s, "难的不是识别，是化学。")
    cards = [
        ("化学归一", "R → CH3（未定义时）\n30+ 缩写展开，环编号隔离\nD / ²H → H"),
        ("失败兜底", "手绘模型回退\nS/P 标签切开 → 合并重识别\nCrop 手动框选"),
        ("多构象", "ETKDGv3 + MMFF94\n能量窗口 + 0.5 Å 去重\nSDF 带 ENERGY_KCAL"),
        ("工程化", "RDKit / DECIMER 全局锁\n128 条 LRU 缓存\n本地运行，数据不出机器"),
    ]
    for i, (title, desc) in enumerate(cards):
        x = 0.55 + (i % 2) * 6.15
        y = 2.3 + (i // 2) * 2.25
        add_rect(s, x, y, 5.85, 1.95, WHITE, LIGHT)
        add_text(s, x + 0.3, y + 0.2, 5.2, 0.4, title, 16, True, INK)
        add_text(s, x + 0.3, y + 0.72, 5.25, 1.1, desc, 11, False, GRAY, line=1.3)
    notes(s, "60 秒：四个点，每个一句话，不展开算法。")

    # ---------------------------------------------------------------- evidence
    s = new_slide(prs)
    topbar(s, "证据", 5)
    heading(s, "数字说话，也说边界。")
    stats = [
        ("13 / 13", "Golden set 严格命中", "TP=15，FP=0，FN=0，F1=1.00"),
        ("98 / 100", "NCI 分子识别", "connectivity 100/100"),
        ("0.90 Å", "晶体配体 RMSD", "20 构象中位；单构象 1.82 Å"),
        ("4,978", "3D 生成成功", "4,999 分子，99.6%"),
    ]
    for i, (big, label, sub) in enumerate(stats):
        x = 0.55 + (i % 2) * 6.15
        y = 2.2 + (i // 2) * 2.05
        add_text(s, x, y, 5.6, 0.7, big, 34, True, RED)
        add_text(s, x, y + 0.72, 5.6, 0.35, label, 13, True, INK)
        add_text(s, x, y + 1.08, 5.6, 0.35, sub, 10, False, GRAY)
    add_text(s, 0.55, 6.6, 12.2, 0.4,
             "口径：识别为合成渲染图，真实论文泛化仍在补；RMSD 为气相构象生成，不含蛋白环境。",
             9, False, GRAY)
    notes(s, "60 秒：先给四个数，再主动说口径。")

    # ---------------------------------------------------------------- demo
    s = new_slide(prs)
    topbar(s, "Demo", 6)
    heading(s, "现场演示：三步。")
    img = ROOT / "data" / "ui_1440.png"
    if img.exists():
        pic = s.shapes.add_picture(str(img), Inches(0.55), Inches(2.15), width=Inches(7.3))
        pic.line.color.rgb = LIGHT
        pic.line.width = Pt(0.75)
    steps = [
        ("01", "上传结构图", "自动切分多结构，失败可 Crop"),
        ("02", "选一个结构", "SMILES / 描述符 / 2D / 3D"),
        ("03", "导出", "多构象 SDF + CSV"),
    ]
    for i, (num, title, desc) in enumerate(steps):
        y = 2.25 + i * 1.45
        add_text(s, 8.25, y, 0.6, 0.4, num, 16, True, RED)
        add_text(s, 8.85, y - 0.03, 4.0, 0.4, title, 15, True, INK)
        add_text(s, 8.85, y + 0.35, 4.0, 0.5, desc, 10.5, False, GRAY)
    add_text(s, 8.25, 6.6, 4.6, 0.4, "备用：直接输入 SMILES", 9, False, GRAY)
    notes(s, "60 秒：现场只点三次；如果模型没预热，直接用 SMILES 深链接兜底。")

    # ---------------------------------------------------------------- limits
    s = new_slide(prs)
    topbar(s, "边界", 7)
    heading(s, "我们明确不做什么。")
    rows = [
        ("密集反应式", "自动切分可能拆错", "Crop 手动框选，演示用已验证图"),
        ("E/Z 过度指定", "结构对、多标构型", "只标记，不自动剥离，交人工核对"),
        ("金属配合物 3D", "UFF 几何不可靠", "只看连接关系，不当构象证据"),
        ("Markush R 未定义", "统一按 CH3 代入", "界面标注 R assumed: CH3，可改 SMILES"),
    ]
    for i, (a, b, c) in enumerate(rows):
        y = 2.2 + i * 1.05
        add_rule(s, 0.55, y + 0.42, 12.2, LIGHT, 1)
        add_text(s, 0.55, y, 3.2, 0.4, a, 14, True, INK)
        add_text(s, 3.9, y, 3.6, 0.4, b, 11, False, GRAY)
        add_text(s, 7.7, y, 5.2, 0.4, c, 11, False, INK)
    add_text(s, 0.55, 6.45, 12.0, 0.5, "知道哪里会错，比「我们全对」更可信。", 17, True, RED)
    notes(s, "40 秒：主动暴露边界，评委反而信。")

    # ---------------------------------------------------------------- team
    s = new_slide(prs, DARK)
    add_text(s, 0.55, 0.4, 6.0, 0.3, "TECHATHON / 2026", 9, False, RGBColor(0x9A, 0x9A, 0x9A))
    add_text(s, 0.55, 1.3, 6.5, 0.4, "07  /  TEAM & NEXT", 10, True, RED)
    add_text(s, 0.55, 1.75, 6.5, 0.9, "团队 MolVision", 30, True, WHITE)
    add_text(s, 0.55, 2.85, 5.8, 1.6,
             "何宇辉　识别流水线 / 化学归一 / 评测\n"
             "【成员 2】　前端 / Demo\n"
             "【成员 3】　材料 / 路演", 12, False, RGBColor(0xC8, 0xC8, 0xC8), line=1.6)
    add_text(s, 7.0, 1.75, 5.8, 0.4, "NEXT", 10, True, RED)
    add_text(s, 7.0, 2.15, 5.8, 2.6,
             "1. 真实论文图测试集 100+，错误四类归因\n"
             "2. MolScribe / OSRA 同批对比\n"
             "3. 持久化缓存与批量断点续跑", 12, False, RGBColor(0xC8, 0xC8, 0xC8), line=1.5)
    add_rule(s, 0.6, 5.35, 3.0, RED, 3)
    add_text(s, 0.55, 5.6, 12.0, 0.6, "谢谢，欢迎提问。", 26, True, WHITE)
    add_text(s, 0.55, 6.7, 12.0, 0.4, "MolVision · 本地运行 · 数据不出机器", 10, False, RGBColor(0x9A, 0x9A, 0x9A))
    notes(s, "20 秒：收尾，留联系方式/仓库二维码（现场可补）。")

    out = OUT / "04-项目展示PPT.pptx"
    prs.save(out)
    print("saved", out, "slides:", len(prs.slides))


if __name__ == "__main__":
    build()
