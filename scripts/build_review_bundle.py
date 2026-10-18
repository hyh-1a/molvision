"""Assemble the code-review bundle (core -> frontend -> evidence)."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "MolVision-代码评审包"

CORE = ["segment.py", "recognize.py", "chem.py", "pdf.py", "server.py"]

DESCRIPTIONS = {
    "segment.py": {
        "_ink_mask": "灰度 → 二值化，自动判断前景/背景",
        "_bands": "一维投影切分：按空白带把图分成行/列",
        "looks_like_structure": "裁剪块是否像结构式（笔画长度/长宽比）",
        "_has_table_rules": "检测表格线，整页跳过",
        "segment_image": "入口：返回按阅读顺序排列的裁剪块",
    },
    "recognize.py": {
        "recognize_image": "入口：缓存、预处理、切分、逐块识别",
        "_recognize_crops": "逐块 DECIMER + 失败回退 + 合并修复",
        "_predict": "DECIMER 推理（印刷体/手绘两套权重）",
        "_parse_candidate": "原始 SMILES → RDKit 解析 → 归一化 → 垃圾过滤",
        "_looks_like_junk": "片段数/重复片段/长烷烃等噪声判定",
        "_has_suspicious_halogen": "I/Br 与 S/P 共现的幻觉检测",
        "_merge_split_fragments": "S/P 标签把分子切成两半时的合并重识别",
        "_has_stereo": "是否含手性/E-Z 标记",
    },
    "chem.py": {
        "parse_smiles": "入口解析：Markush / 缩写 / 原样多路尝试",
        "normalize_markush": "R/R1/R''/Ar → *",
        "substitute_r_groups": "未定义 R → 甲基（3D 与描述符默认假设）",
        "expand_abbreviations": "30+ 缩写展开，环编号用 %90+ 隔离",
        "properties": "分子描述符与 Lipinski/TPSA 等",
        "structural_alerts": "结构警示（R 基、同位素、金属、PAINS 等）",
        "embed_3d": "单构象：ETKDGv3 + MMFF94/UFF",
        "embed_conformers": "多构象：采样、优化、能量窗口、RMSD 去重",
        "analyze": "入口：加锁后调用 _analyze",
        "_analyze": "完整分析流水线：解析 → 描述符 → 2D → 3D",
        "largest_fragment": "去盐/溶剂：保留最大片段",
        "sa_score": "SAscore 合成难度启发式",
    },
    "pdf.py": {
        "figure_score": "页面是否像图（矢量图形/图片/字符数）",
        "page_to_png": "页面渲染为 PNG（限制最长边）",
        "render_pdf": "入口：逐页渲染并返回 (pages, skipped)",
    },
    "server.py": {
        "_json_response": "统一 JSON 响应",
        "_recognizer": "懒加载识别模块",
        "_model_loaded": "模型是否已加载",
        "do_GET": "GET 路由：health / samples / static",
        "do_POST": "POST 路由：analyze / recognize / pdf",
    },
}

EVIDENCE = [
    ("eval_report.json", "Golden 评测原始报告（13/13、TP=15）"),
    ("evaluate.log", "本次 evaluate 运行日志"),
    ("selfcheck.log", "本次 selfcheck 运行日志（23/23）"),
    ("stress_recognition.json", "100 分子识别逐条结果（98 exact）"),
    ("stress_recognition3.log", "100 分子识别运行日志（98/100）"),
    ("pdb_rmsd.json", "12 个 PDB 配体 RMSD 逐条结果"),
    ("pdb_rmsd.log", "RMSD 运行日志（中位 1.82 / 0.90）"),
    ("stress3d.log", "4,999 分子 3D 压测日志（4,978 成功）"),
    ("EVAL.md", "评测说明与历史记录"),
]

SCRIPTS = ["evaluate.py", "selfcheck.py", "pdb_rmsd.py",
           "stress_recognition.py", "make_golden.py"]

CLAIMS = [
    ("13/13 严格命中", "03-evidence/eval_report.json",
     "strict_exact=13, strict_total=13, strict_accuracy=1.0"),
    ("TP=15 / FP=0 / FN=0", "03-evidence/eval_report.json", "tp=15, fp=0, fn=0"),
    ("98/100 识别", "03-evidence/stress_recognition.json",
     "100 条记录中 exact=true 共 98 条"),
    ("23/23 回归", "03-evidence/selfcheck.log", "末行：23 passed, 0 failed"),
    ("RMSD 中位 1.82 / 0.90 Å", "03-evidence/pdb_rmsd.json",
     "12 条记录；中位数由脚本汇总"),
    ("4,978 / 4,999 3D 成功", "03-evidence/stress3d.log",
     "success: 4978 (99.6%)"),
]


def func_index(path: Path) -> list[tuple[str, int]]:
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = re.match(r"^(?:def|class)\s+(\w+)", line)
        if m:
            rows.append((m.group(1), i))
    return rows


def js_index(path: Path) -> list[tuple[str, int]]:
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = re.match(r"^(?:async\s+)?function\s+(\w+)", line.strip())
        if m:
            rows.append((m.group(1), i))
    return rows


def build_readme(core_stats, js_stats) -> str:
    lines = []
    add = lines.append
    add("# MolVision 代码级评审包")
    add("")
    add("本包按评审要求组织：**核心脚本 → 前端 → 可核对的结果文件**。")
    add("所有数字都能在 `03-evidence/` 里找到对应原始记录，命令见第 5 节。")
    add("")
    add("## 1. 阅读顺序")
    add("")
    add("| 顺序 | 目录 | 内容 | 建议关注 |")
    add("|---|---|---|---|")
    add("| 1 | `01-core/` | `segment.py` `recognize.py` `chem.py` `pdf.py` `server.py` | 切分启发式、识别回退与合并、"
        "R 基/缩写/立体化学处理、PDF 页筛选 |")
    add("| 2 | `02-frontend/` | `index.html`（单文件，含 JS） | Crop 坐标映射、AbortController 超时、"
        "SDF ensemble 导出 |")
    add("| 3 | `03-evidence/` | JSON、日志、评测脚本、14 个 Golden 图 | 核对 13/13、98/100、23/23、RMSD |")
    add("")
    add("## 2. 流水线一句话")
    add("")
    add("图片 → 预处理 → 投影切分 → DECIMER 识别（失败回退手绘）→ 化学归一"
        "（R 基/缩写/D→H）→ RDKit 校验 → 2D/3D/描述符 → SDF/CSV。")
    add("")
    add("## 3. 核心脚本索引")
    add("")
    for fname, (nlines, rows) in core_stats.items():
        add(f"### `{fname}`（{nlines} 行）")
        add("")
        add("| 函数 / 类 | 行 | 说明 |")
        add("|---|---|---|")
        desc = DESCRIPTIONS.get(fname, {})
        for name, ln in rows:
            add(f"| `{name}` | {ln} | {desc.get(name, '')} |")
        add("")
    add("## 4. 前端要点")
    add("")
    add("| 函数 | 行 | 说明 |")
    add("|---|---|---|")
    for name, ln in js_stats:
        add(f"| `{name}` | {ln} | |")
    add("")
    add("Crop 的关键在鼠标坐标到 canvas 像素的换算，以及裁剪框与原图坐标的一致性；"
        "上传后先做 EXIF/缩放，再进入识别。")
    add("")
    add("## 5. 数字出处（逐条可核）")
    add("")
    add("| 材料中的说法 | 文件 | 核对方式 |")
    add("|---|---|---|")
    for claim, path, how in CLAIMS:
        add(f"| {claim} | `{path}` | {how} |")
    add("")
    add("## 6. 复现命令")
    add("")
    add("```powershell")
    add("cd C:\\Users\\何宇辉\\Documents\\deepseek-harness\\default-workspace\\molvision")
    add(".\\run.ps1                          # http://127.0.0.1:8765，首次预热约 3.5 min")
    add("python scripts\\selfcheck.py        # 23 项回归")
    add("python scripts\\evaluate.py         # Golden 14 用例")
    add("python scripts\\pdb_rmsd.py --confs 20")
    add("python scripts\\stress_recognition.py --n 100")
    add("python scripts\\stress_3d.py --n 5000")
    add("```")
    add("")
    add("## 7. 环境说明")
    add("")
    add("- Windows，Python 3.12；RDKit 2026.09.1，DECIMER 2.8 + TensorFlow 2.20。")
    add("- `.venv` 已迁至 `E:\\MolVisionData\\venv`，原路径是 junction；模型权重不入包。")
    add("- `requirements.txt` 在包根目录；服务默认只绑 `127.0.0.1:8765`。")
    add("")
    add("## 8. 主动标注的薄弱点（便于评审直接开火）")
    add("")
    add("- `segment.py`：投影切分是启发式，密集反应式/双栏仍会拆错；S/P 中央标签靠 `_merge_split_fragments` 兜底。")
    add("- `recognize.py`：DECIMER 推理串行（全局锁）；手绘回退只重试一次；缓存为内存态。")
    add("- `chem.py`：未定义 R 全部按 CH3；缩写表 30+ 但不含 Alloc/Dde/MOM 等；多构象去重阈值 0.5 Å 是经验值。")
    add("- `pdf.py`：`figure_only` 是启发式；没有断点续跑；扫描件/跨页图会漏。")
    add("- 前端：Crop 与导出是手写 DOM/canvas，没有自动化测试，只有 API 层 selfcheck。")
    add("")
    return "\n".join(lines)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "01-core").mkdir(parents=True)
    (OUT / "02-frontend").mkdir(parents=True)
    (OUT / "03-evidence" / "scripts").mkdir(parents=True)
    (OUT / "03-evidence" / "golden").mkdir(parents=True)

    core_stats = {}
    for name in CORE:
        src = ROOT / "app" / name
        shutil.copy2(src, OUT / "01-core" / name)
        core_stats[name] = (len(src.read_text(encoding="utf-8").splitlines()),
                            func_index(src))
    shutil.copy2(ROOT / "requirements.txt", OUT / "requirements.txt")

    web = ROOT / "web" / "index.html"
    shutil.copy2(web, OUT / "02-frontend" / "index.html")
    js_stats = js_index(web)
    (OUT / "02-frontend" / "NOTES.md").write_text(
        "3D 渲染依赖 web/vendor/3Dmol-min.js（第三方，未随包复制）。\n"
        "页面为单文件应用，样式与 JS 都内联在 index.html。\n",
        encoding="utf-8")

    for name, _desc in EVIDENCE:
        src = ROOT / name if name == "EVAL.md" else ROOT / "data" / name
        shutil.copy2(src, OUT / "03-evidence" / name)
    for name in SCRIPTS:
        shutil.copy2(ROOT / "scripts" / name, OUT / "03-evidence" / "scripts" / name)
    for img in sorted((ROOT / "samples" / "golden").glob("*.png")):
        shutil.copy2(img, OUT / "03-evidence" / "golden" / img.name)

    (OUT / "00-REVIEW.md").write_text(build_readme(core_stats, js_stats), encoding="utf-8")
    print("bundle:", OUT)
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(OUT)}  {p.stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()
