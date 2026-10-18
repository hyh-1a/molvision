"""Build the expert-review DOCX for MolVision."""
from __future__ import annotations

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ACCENT = RGBColor(0x8C, 0x3B, 0x12)
INK = RGBColor(0x1F, 0x24, 0x2B)
MUTED = RGBColor(0x5B, 0x63, 0x6B)
HEAD_FILL = "EDE3D0"
ZEBRA_FILL = "F8F4EA"

BODY_FONT = "微软雅黑"
LATIN_FONT = "Calibri"


def set_run_font(run, size=None, bold=None, color=None, font=BODY_FONT):
    run.font.name = LATIN_FONT
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), font)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def body(doc, text, size=10.5, space_after=4, justify=True):
    p = doc.add_paragraph()
    if justify:
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.28
    r = p.add_run(text)
    set_run_font(r, size, color=INK)
    return p


def bullet(doc, text, size=10.5):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.22
    r = p.add_run(text)
    set_run_font(r, size, color=INK)
    return p


def heading(doc, text, level=1):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14 if level == 1 else 9)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    if level == 1:
        set_run_font(r, 15, bold=True, color=INK)
    else:
        set_run_font(r, 12, bold=True, color=ACCENT)
    # bottom rule for level-1 headings
    if level == 1:
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "4")
        bottom.set(qn("w:color"), "D8CBB4")
        pBdr.append(bottom)
        pPr.append(pBdr)
    return p


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def cell_text(cell, text, size=9.5, bold=False, color=INK, align=None):
    cell.text = ""
    p = cell.paragraphs[0]
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.space_before = Pt(1)
    for i, line in enumerate(str(text).split("\n")):
        if i:
            p = cell.add_paragraph()
            p.paragraph_format.space_after = Pt(1)
        r = p.add_run(line)
        set_run_font(r, size, bold=bold, color=color)


def table(doc, headers, rows, widths, header_fill=HEAD_FILL, font_size=9.5,
          align_right_cols=()):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.style = "Table Grid"
    t.autofit = False
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.width = widths[i]
        cell_text(c, h, size=font_size, bold=True, color=INK)
        shade(c, header_fill)
    for ridx, row in enumerate(rows):
        cells = t.add_row().cells
        trPr = t.rows[-1]._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        cant_split.set(qn("w:val"), "true")
        trPr.append(cant_split)
        for i, val in enumerate(row):
            cells[i].width = widths[i]
            align = WD_ALIGN_PARAGRAPH.RIGHT if i in align_right_cols else None
            cell_text(cells[i], val, size=font_size, align=align)
            if ridx % 2 == 1:
                shade(cells[i], ZEBRA_FILL)
    # repeat header row
    trPr = t.rows[0]._tr.get_or_add_trPr()
    tblHeader = OxmlElement("w:tblHeader")
    tblHeader.set(qn("w:val"), "true")
    trPr.append(tblHeader)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def caption(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run(text)
    set_run_font(r, 8.5, color=MUTED)
    return p


def add_page_number(paragraph):
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)
    set_run_font(run, 8.5, color=MUTED)


def build() -> None:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = Cm(2.0)
    sec.bottom_margin = Cm(1.8)

    normal = doc.styles["Normal"]
    normal.font.name = LATIN_FONT
    normal.font.size = Pt(10.5)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)

    # footer
    footer_p = sec.footer.paragraphs[0]
    footer_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = footer_p.add_run("MolVision · 专家评审材料 · 2026-10-18 · 第 ")
    set_run_font(r, 8.5, color=MUTED)
    add_page_number(footer_p)
    r = footer_p.add_run(" 页")
    set_run_font(r, 8.5, color=MUTED)

    # ---------------- cover ----------------
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(70)
    r = p.add_run("MOLVISION")
    set_run_font(r, 11, bold=True, color=ACCENT)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    r = p.add_run("结构式识图系统")
    set_run_font(r, 30, bold=True, color=INK)

    p = doc.add_paragraph()
    r = p.add_run("从一张结构图到可计算的分子")
    set_run_font(r, 16, color=ACCENT)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(26)
    r = p.add_run("专家评审材料 · 方法、证据与边界")
    set_run_font(r, 12.5, bold=True, color=INK)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    r = p.add_run("版本 v1.0　|　2026-10-18　|　全部数字来自本仓库可复跑脚本")
    set_run_font(r, 9.5, color=MUTED)

    # quick facts box
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    cell = t.rows[0].cells[0]
    shade(cell, "F3EDE1")
    cell.text = ""
    facts = [
        ("识别基线", "Golden set 14 用例，13/13 严格命中；结构级 F1 = 1.00"),
        ("大规模识别", "100 个 NCI 分子 98/100 精确；connectivity 100/100"),
        ("3D 构象生成（气相）", "12 个 PDB 晶体配体，中位 RMSD 1.82 Å → 0.90 Å（20 构象）"),
        ("3D 规模", "4,999 个 NCI 分子 99.6% 生成成功"),
        ("回归", "selfcheck 23/23，单结构 3.4–4.5 s（缓存热/冷）"),
    ]
    first = True
    for k, v in facts:
        p = cell.paragraphs[0] if first else cell.add_paragraph()
        first = False
        p.paragraph_format.space_after = Pt(2)
        rr = p.add_run(f"{k}　")
        set_run_font(rr, 9.5, bold=True, color=ACCENT)
        rr = p.add_run(v)
        set_run_font(rr, 9.5, color=INK)

    doc.add_page_break()

    # ---------------- 1 summary ----------------
    heading(doc, "1　摘要")
    body(doc,
         "MolVision 是一个本地运行的化学结构式识图工作台：输入结构式图片（论文截图、专利图、"
         "手绘、PDF 页面），输出标准 SMILES、分子描述符、2D 重绘图与 3D 构象，并支持多结构"
         "切分、批量 PDF、Markush / R 基、常见缩写基团与 SDF / CSV 导出。系统不做“端到端黑箱”，"
         "而是把识别模型放进一条可检查的化学流水线：切分 → 识别 → 化学归一 → RDKit 校验 → "
         "2D/3D/描述符 → 导出，每一步都有失败兜底与人工介入点。")
    body(doc,
         "本材料的定位是让评审专家在 15 分钟内判断三件事：系统做了什么、证据有多硬、"
         "边界在哪里。所有评测脚本、测试图与结果文件都在仓库内，可按第 6 节命令复跑。")

    # ---------------- 2 architecture ----------------
    heading(doc, "2　系统架构")
    body(doc,
         "流水线：图片 → 预处理 → 结构切分 → DECIMER 识别 → 化学归一 → RDKit 校验 → "
         "2D 重绘 / 3D 构象 / 描述符 → SDF / CSV。")
    table(doc,
          ["模块", "职责", "关键实现"],
          [
              ["图像预处理", "EXIF 校正、超大图缩放、二值化", "Pillow + OpenCV"],
              ["结构切分", "投影切分、表格线/箭头过滤、标签重挂", "app/segment.py"],
              ["结构识别", "DECIMER 2.8；失败回退手绘模型；90°/270° 旋转回退", "app/recognize.py"],
              ["化学归一", "R 基 → *、未定义 R → CH3、30+ 缩写展开、D/²H → H", "app/chem.py"],
              ["校验与描述符", "canonical SMILES、InChIKey、警示、SAscore、Lipinski/TPSA", "RDKit 2026.09.1"],
              ["3D 构象", "ETKDGv3 嵌入 + MMFF94 优化（金属回退 UFF），可选多构象", "RDKit"],
              ["PDF 批量", "页面筛选（图像/文字/矢量判断）+ 逐页识别 + 去重导出", "app/pdf.py + PyMuPDF"],
              ["交付层", "Web 单页、SDF/CSV、深链接、Crop 手动框选", "web/index.html"],
          ],
          [Cm(3.0), Cm(8.6), Cm(5.0)])
    caption(doc, "表 1　模块划分。识别与建模解耦：换识别模型不影响下游化学校验与导出。")

    # ---------------- 3 evidence ----------------
    heading(doc, "3　评测方法与结果")

    heading(doc, "3.1　识别", 2)
    body(doc,
         "识别准确率按 InChIKey 集合比较（Markush 等 InChIKey 为空时退回 canonical SMILES），"
         "因此同一分子的不同画法不会误判。Golden set 共 14 个用例：单分子、手性、多结构、"
         "旋转 90°、Markush、缩写 Ph/Me、合成反应式、纯文字段、表格线、低分辨率；其中低清为"
         "软用例，不计入严格分。")
    table(doc,
          ["测试集", "规模", "结果", "说明"],
          [
              ["Golden set", "14 用例", "13/13 严格命中", "TP=15，FP=0，FN=0，F1=1.00"],
              ["NCI 渲染压测", "100 分子", "98/100 精确", "connectivity 100/100；2 个仅 E/Z 过度指定"],
              ["多结构图", "2×2、1×3", "4/4、3/3", "切分 + 逐结构识别"],
              ["合成反应式", "3 结构", "3/3", "箭头不产生伪结构"],
              ["纯文字 / 表格", "2 页", "0 / 0", "不得瞎认"],
              ["回归", "23 项", "23/23", "健康、缓存、并发、Markush、缩写"],
          ],
          [Cm(3.4), Cm(2.6), Cm(3.6), Cm(7.0)])
    caption(doc, "表 2　识别评测。单结构 3.4–4.5 s（缓存热/冷），100 分子批量约 5.7 min。")
    body(doc,
         "已修复的典型失败：中央 S/P 标签把分子切成两半并误读成碘（三苯基膦、亚砜、砜、"
         "二硫键四个用例现已精确命中）；“Ph”被读成铅 [Pb]（按苯基修复）；“Me”被读成 [14CH3]"
         "（折叠为甲基）。剩余 2 个失败均为双键 E/Z 过度指定，connectivity 正确，系统通过 "
         "stereo 标记提示人工核对。")
    bullet(doc, "CC(=NO)C(C)=NO（肟）→ 输出多标了 E/Z，骨架正确")
    bullet(doc, "CC(OC(=O)C1=CC=CC=C1)=CC2=CC=CC=C2（烯醇酯）→ 同上")
    body(doc,
         "为什么不对 E/Z 做自动剥离：2D 图中的双键顺反常常是被画出来的，模型多标时无法区分"
         "“图上确实画了”还是“模型脑补”；自动剥离会破坏真实构型，因此只做标记与 connectivity "
         "评测，由人工核对。")

    doc.add_page_break()
    heading(doc, "3.2　3D 构象生成精度（气相）：PDB 晶体配体 RMSD", 2)
    body(doc,
         "先限定口径：这里的“精度”指气相力场下的构象生成误差，不是蛋白口袋内的结合构象预测，"
         "也没有做口袋约束优化；它回答的是“同一分子，生成构象离晶体构象多远”。")
    body(doc,
         "从 PDB 条目提取配体的实验坐标，用 CCD 的 stereo SMILES 重建参考分子，ETKDGv3 + "
         "MMFF94 生成构象；PDB 键级不可靠，因此用 MCS（忽略键级）建立原子映射，并对脒基等"
         "对称基团枚举映射取最小 RMSD。CCD “ideal” 几何作为对照基线。")
    rows = [
        ["雌二醇", "1ERE", "20", "0.14", "0.14", "0.21"],
        ["苯甲脒", "3PTB", "9", "0.23", "0.23", "0.07"],
        ["维甲酸", "1CBS", "22", "0.69", "0.55", "1.09"],
        ["生物素", "1STP", "16", "0.81", "0.81", "1.21"],
        ["4-羟基他莫昔芬", "3ERT", "29", "1.18", "0.75", "1.15"],
        ["N3 抑制剂", "6LU7", "13", "1.18", "0.89", "1.59"],
        ["厄洛替尼", "1M17", "29", "1.82", "0.90", "1.05"],
        ["伊马替尼", "1IEP", "37", "2.25", "1.15", "2.19"],
        ["甲氨蝶呤", "4DFR", "33", "2.49", "1.63", "1.77"],
        ["ATP", "1ATP", "31", "3.56", "1.57", "1.95"],
        ["印地那韦", "1HSG", "45", "3.17", "1.94", "4.03"],
        ["HIV 蛋白酶抑制剂", "1HVR", "46", "2.75", "2.26", "4.58"],
    ]
    table(doc,
          ["配体", "PDB", "重原子", "单构象 / Å", "20 构象最好 / Å", "CCD ideal / Å"],
          rows,
          [Cm(4.0), Cm(1.8), Cm(2.0), Cm(3.2), Cm(3.4), Cm(2.8)],
          align_right_cols=(2, 3, 4, 5))
    caption(doc, "表 3　晶体配体 RMSD（重原子，对称映射取最小）。中位：单构象 1.82 Å，20 构象 0.90 Å。")
    body(doc,
         "结论：刚性/小分子单构象即可接近晶体（0.14–0.81 Å）；柔性药物单构象偏差 1.8–3.6 Å，"
         "20 构象采样把中位压到 0.90 Å；CCD ideal 几何常常比我们的最佳构象更差（印地那韦 "
         "4.03 vs 1.94 Å），说明“ideal”不等于结合构象。因此产品默认单构象，柔性分子建议开"
         "多构象。")

    heading(doc, "3.3　规模与稳定性", 2)
    table(doc,
          ["测试", "规模", "结果", "备注"],
          [
              ["NCI 3D 压测", "4,999", "4,978 成功（99.6%）", "21 个失败全部为金属有机体系"],
              ["复杂分子 3D", "20", "18/20", "2 个 PubChem 抓取失败；万古霉素 3.8 s、环孢素 5.2 s、gramicidin 17.6 s"],
              ["并发分析", "12 路", "全部通过", "RDKit 分析全局锁；HTTP 层保持并发"],
              ["缓存", "128 条 LRU", "命中 0.01 s 量级", "按图像 SHA256；内存态，重启失效"],
          ],
          [Cm(3.2), Cm(2.2), Cm(4.2), Cm(7.0)])
    caption(doc, "表 4　规模测试。识别推理串行（DECIMER 非线程安全），吞吐约 3.4 s/结构。")

    heading(doc, "3.4　证据强度自评", 2)
    table(doc,
          ["证据", "强度", "理由"],
          [
              ["Golden 基线", "强", "用例固定、脚本可复跑、按 InChIKey 比较"],
              ["100 分子识别压测", "中", "NCI 合成渲染图，不等于真实论文扫描件"],
              ["PDB RMSD", "中", "12 个配体、气相力场，未考虑蛋白环境"],
              ["真实论文泛化", "弱", "样本少，密集反应式仍依赖 Crop 人工框选"],
          ],
          [Cm(4.0), Cm(2.0), Cm(10.6)])

    # ---------------- 4 decisions ----------------
    heading(doc, "4　关键设计决策")
    bullet(doc, "不信任端到端：识别模型只负责“读图”，切分、化学归一、校验、兜底都在流水线里，"
                "失败可定位、可人工修正。")
    bullet(doc, "Markush：R/R1/R''/Ar 统一映射为 *；未定义时按甲基（CH3）代入生成 3D 与描述符，"
                "界面标注 R assumed: CH3 并保留原始骨架 SMILES。")
    bullet(doc, "缩写基团：30+ 常见缩写（Ph/Me/Et/iPr/tBu/Bn/Ac/Boc/Cbz/Fmoc/Ts/Ms/TBS/CO2Et…）"
                "自动展开；环内展开使用独立 %90+ 环编号，避免与宿主环编号冲突。")
    bullet(doc, "同位素氢：D/²H 在识别路径折叠为普通 H；手动输入的 [2H] SMILES 保留原样。")
    bullet(doc, "立体化学：不做 AssignStereochemistryFrom3D，避免把任意对映体写死；SDF 中写 "
                "STEREO 字段说明未定义中心数。")
    bullet(doc, "多构象：ETKDGv3 采样 → MMFF94/UFF 优化 → 能量排序 → 10 kcal/mol 窗口 → "
                "0.5 Å 去重；SDF 每个构象带 ENERGY_KCAL。")
    bullet(doc, "并发：RDKit 分析与 DECIMER 推理各自全局锁，HTTP 层仍可并发；本地部署，数据不出机器。")

    # ---------------- 5 limits ----------------
    heading(doc, "5　已知边界与风险")
    table(doc,
          ["边界", "表现", "缓解 / 现状"],
          [
              ["真实论文密集反应式", "自动切分可能拆错或漏结构", "提供 Crop 手动框选；演示用已验证图"],
              ["手绘 / 低清扫描", "准确率明显下降", "手绘模型回退；结果需人工核对"],
              ["E/Z 过度指定", "100 个中 2 个，结构对但多标构型", "stereo 标记 + connectivity 评测；不自动剥离"],
              ["金属配合物 3D", "UFF 几何不可靠", "仅用于看连接关系，不作为构象证据"],
              ["Markush R 未定义", "所有 R 统一按 CH3", "界面标注；可手动改 SMILES 指定取代基"],
              ["缩写覆盖", "表外缩写（Alloc/Dde/MOM/Trt 等）不支持", "手动输入 SMILES；表可持续扩充"],
              ["单构象", "柔性分子偏差 1.8–3.6 Å", "界面可选 5/10/20 构象"],
              ["缓存与并发", "重启后缓存失效；批量吞吐受限", "可加持久化缓存；当前 3.4 s/结构"],
              ["部署", "仅绑定 127.0.0.1，无鉴权", "定位本地单机工具，不暴露公网"],
          ],
          [Cm(3.6), Cm(5.6), Cm(7.4)])

    # ---------------- 6 reproduce ----------------
    heading(doc, "6　复现与演示")
    body(doc, "环境：Windows，项目根目录 molvision；Python 虚拟环境 .venv（已迁至 E 盘，"
              "原路径为 junction），RDKit 2026.09.1，DECIMER 2.8 + TensorFlow 2.20。")
    code_lines = [
        "cd C:\\Users\\何宇辉\\Documents\\deepseek-harness\\default-workspace\\molvision",
        ".\\run.ps1                     # 启动 http://127.0.0.1:8765（首次预热约 3.5 min）",
        "python scripts\\selfcheck.py     # 23 项回归",
        "python scripts\\evaluate.py      # Golden set（14 用例）",
        "python scripts\\pdb_rmsd.py --confs 20",
        "python scripts\\stress_recognition.py --n 100",
        "python scripts\\stress_3d.py --n 5000",
        "python scripts\\run_pdf.py paper.pdf --out data\\pdf_out --max-pages 20",
    ]
    for line in code_lines:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.4)
        p.paragraph_format.space_after = Pt(1)
        r = p.add_run(line)
        set_run_font(r, 8.5, font="Consolas")
        r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

    table(doc,
          ["接口", "方法", "作用"],
          [
              ["/api/health", "GET", "健康状态与模型是否加载"],
              ["/api/recognize", "POST", "图片 → 多结构 SMILES（可 single=true 强制单结构）"],
              ["/api/analyze", "POST", "SMILES → 2D/3D/描述符，可指定 n_conformers"],
              ["/api/pdf", "POST", "PDF → 逐页识别结果"],
              ["/samples/*、/static/*", "GET", "示例图与前端静态资源"],
          ],
          [Cm(3.6), Cm(1.8), Cm(11.2)])

    # ---------------- 7 qa ----------------
    heading(doc, "7　专家问答预案")
    qa = [
        ("和 MolScribe / OSRA / 商用工具比过吗？",
         "没有做严格 head-to-head，这是当前证据缺口。我们的优势在工程闭环（切分、归一、校验、"
         "批量、导出），而不是声称识别模型本身最强。"),
        ("准确率怎么定义？",
         "按 InChIKey 集合比较；同时报 connectivity（去立体）准确率，用来区分“结构看错”和"
         "“多标了构型”。"),
        ("3D 构象准不准？",
         "12 个 PDB 晶体配体中位 RMSD：单构象 1.82 Å，20 构象 0.90 Å；刚性分子 0.14–0.81 Å。"
         "这是气相力场结果，不含蛋白环境，也不做口袋约束优化。"),
        ("R 基不同怎么办？",
         "未定义时统一按 CH3 代入并在界面标注；需要具体取代基时手动改 SMILES。逐个 R 指定"
         "是明确的下一版功能。"),
        ("数据隐私？",
         "全部本地运行，图片与结构不上传；服务只绑定本机 127.0.0.1。"),
        ("速度？",
         "单结构 3.4–4.5 s（缓存热/冷）；100 分子约 5.7 min；缓存命中 0.01 s 量级。"),
        ("失败了怎么办？",
         "多结构可用 Crop 手动框选；单图识别失败可改用手绘模型或直接输入 SMILES。"),
    ]
    for q, a in qa:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(1)
        r = p.add_run("Q　" + q)
        set_run_font(r, 10.5, bold=True, color=ACCENT)
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.5)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run("A　" + a)
        set_run_font(r, 10, color=INK)

    # ---------------- 8 reviewer response ----------------
    heading(doc, "8　对评审意见的回应与补强计划")
    body(doc,
         "以下回应基于本轮评审提出的五点追问。已完成的改动直接写入本材料；未完成的给出"
         "具体做法与范围，不把计划写成结果。")
    table(doc,
          ["评审意见", "我们的判断", "已做 / 计划"],
          [
              ["Golden set 仅 14 例，统计意义不足",
               "同意。13/13 的置信区间确实很宽，且低清软用例不计入严格分。",
               "计划扩到 100+：先做 30 张真实论文/专利/扫描图（人工标注），再补到 100；"
               "分开报“合成渲染”和“真实图”两组数字。"],
              ["NCI 100 是渲染图，与真实截图差距大",
               "同意，这是泛化证据的最大缺口。",
               "真实图测试集与上一条同一批；错误按切分 / 识别 / 归一 / 校验四类归因，"
               "单独报密集反应式的切分成功率。"],
              ["3D RMSD 只有 12 个配体，且是气相",
               "部分同意。12 个里刚性分子偏多；气相口径此前表述不够严谨。",
               "已把口径改为“气相 3D 构象生成精度”，并在正文与问答中注明不含蛋白环境、"
               "不做口袋约束；计划再补 8 个柔性配体，并做一组口袋约束后的对照。"],
              ["缺 MolScribe / OSRA 对比",
               "同意，这是证据链最薄弱的一环。",
               "已搭好 MolScribe CPU 推理栈并跑通单张推理；但其 1.1.1 依赖 2023 年的 "
               "torchtext / OpenNMT-py 2.3 解码器接口，与 Python 3.12 不兼容。计划用 "
               "Python 3.10 独立环境跑 50 张真实图，OSRA 同批对比。"],
              ["核心贡献是什么，复制门槛高吗",
               "贡献在工程闭环与化学归一规则，不在识别模型本身；门槛需要用消融来量化。",
               "计划做消融：去掉切分 / 去掉归一 / 去掉 RDKit 校验后的准确率变化，"
               "用数字说明每一层的增量。"],
          ],
          [Cm(4.2), Cm(4.6), Cm(7.8)], font_size=9)

    # ---------------- appendix ----------------
    heading(doc, "附录 A　材料与文件清单")
    table(doc,
          ["文件", "内容"],
          [
              ["EVAL.md", "评测基线、用例说明、RMSD 与压测记录"],
              ["DEMO.md", "5 分钟演示脚本、兜底方案、评委问答"],
              ["PITCH.md / MolVision-pitch.pptx", "8 页路演稿与可编辑 PPT"],
              ["scripts/evaluate.py、selfcheck.py", "Golden 评测与 23 项回归"],
              ["scripts/pdb_rmsd.py", "晶体配体 RMSD 验证"],
              ["scripts/stress_recognition.py、stress_3d.py", "100 / 5000 规模压测"],
              ["samples/golden/", "14 个 Golden 用例图片"],
              ["data/*.json、*.log", "评测与压测原始结果"],
          ],
          [Cm(6.4), Cm(10.2)])

    heading(doc, "附录 B　术语")
    glossary = [
        ("SMILES", "分子线性编码；本系统输出 RDKit canonical SMILES。"),
        ("InChIKey", "结构哈希，用于跨画法比对与去重。"),
        ("Markush", "通式结构，R 基位置用占位符表示。"),
        ("RMSD", "两组原子坐标对齐后的均方根偏差，单位 Å。"),
        ("ETKDGv3", "RDKit 的 3D 构象嵌入算法；MMFF94 为后续力场优化。"),
    ]
    for term, desc in glossary:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(term + "　")
        set_run_font(r, 10, bold=True, color=INK)
        r = p.add_run(desc)
        set_run_font(r, 10, color=INK)

    out = "MolVision-专家评审材料.docx"
    doc.save(out)
    print("saved", out)


if __name__ == "__main__":
    build()
