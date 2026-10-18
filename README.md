# MolVision

结构式图片 → SMILES → 2D/3D 分子 + 理化性质。

黑客松 demo 版：上传论文/专利/教材里的化学结构截图，自动识别成 SMILES，
再用 RDKit 重建 2D 结构、生成 3D 构象、计算分子量与类药性质，可导出 SDF。

## 快速开始

```powershell
# 1. 安装依赖（首次）
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt `
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 启动
.\run.ps1
# 演示用（自动预热 + 打开浏览器）
.\run_demo.ps1
# 或
.\.venv\Scripts\python.exe app\server.py --port 8765
```

打开 http://127.0.0.1:8765

首次识别会下载 DECIMER 权重（约 600 MB，Zenodo），之后直接走本地缓存。
`run.ps1` 会在后台预热模型并在控制台打印 `[preload] recognizer ready`；
看到这行后每张图约 4–7 秒（冷启动首次推理本身要 ~80 秒，预热已替你付掉）。

## 架构

```
浏览器（web/index.html，3Dmol.js 渲染，多结构选择器）
        │  POST /api/analyze   {smiles}
        │  POST /api/recognize {image: base64}
        ▼
app/server.py  (stdlib http.server，无框架依赖)
        ├── app/segment.py    投影切分：整图 → 单个分子区域
        ├── app/recognize.py  DECIMER 逐区域识别（串行 + 缓存）
        └── app/chem.py       RDKit: 校验 → 2D → 3D → 性质 + 结构警示
```

- **识别**：DECIMER 2.8（TensorFlow，EfficientNetV2 编码 + Transformer 解码）
- **多结构切分**：投影切分（`app/segment.py`）——先按行、再按列找空白带，
  1×N / N×M 的论文多面板图自动拆成单分子，逐个识别；标签会并入相邻面板
- **批量导出**：多文件批量识别，跨文件汇总；按 InChIKey 去重并标记重复；
  可导出多分子 SDF 或描述符 CSV；识别失败的条目可直接用 “+ Manual” 手动补录
- **结果缓存**：按图片 SHA-256 做 LRU（128 条），重复上传同一张图 <0.1 s 返回
- **校验/标准化**：RDKit 解析 + canonical SMILES + InChIKey
- **3D**：ETKDGv3 嵌入 + MMFF94 优化（失败回退 UFF）；界面可选 1/5/10/20 个构象，
  按能量排序、保留 ±10 kcal/mol 窗口，SDF 导出整个 ensemble
- **气相 3D 构象生成精度**：`scripts/pdb_rmsd.py` 用 12 个 PDB 晶体配体做 RMSD，
  中位 1.82 Å（单构象）→ 0.90 Å（20 构象）；不含蛋白环境与口袋约束
- **性质**：分子式、MW、精确质量、logP、TPSA、HBD/HBA、可旋转键、环数、
  形式电荷、手性中心（含未指定）、构象能

## 实测（渲染图 + 模拟扫描噪声）

| 分子 | 识别结果 | 耗时 |
|---|---|---|
| 阿司匹林 | ✅ 精确匹配 | ~5 s |
| 咖啡因 | ✅ | ~5 s |
| 布洛芬 | ✅ | ~5 s |
| 丙氨酸（手性） | ✅ 含 `[C@@H]` | ~4 s |
| 对乙酰氨基酚 | ✅ | ~5 s |
| 葡萄糖（多手性中心） | ✅ | ~7 s |

6/6 精确匹配。识别耗时不含首次模型加载（约 90 s）。

多结构图（2×2，四个分子 + 编号标签）：**4/4 精确匹配**，总耗时约 22 s；
1×3 布局：3/3。编号文字会被裁剪算法排除——否则 DECIMER 会把 “1” 读成碘离子。

双图批量（2×2 + 1×3）：7 个结构、7 个识别成功、**去重后 4 个唯一分子**。

结构警示（`/api/analyze` 的 `alerts`）：未指定手性中心、盐/多片段、净电荷、
Lipinski 越界、TPSA 过高、自由基、PAINS 命中。

## API

| 方法 | 路径 | 请求 | 返回 |
|---|---|---|---|
| GET | `/api/health` | — | `{ok, recognizer, model_loaded}` |
| POST | `/api/analyze` | `{"smiles": "..."}` | 性质 + 2D PNG(base64) + molblock |
| POST | `/api/recognize` | `{"image": "data:image/png;base64,..."}` | `{count, structures: [{smiles, thumb, bbox, ok}], engine}` |

深链可直接加载：`/?smiles=CCO`、`/?sample=咖啡因`、或 `/?image=multi_4.png`（走多结构流程）。

## 设计取舍（黑客松场景）

- **确定性优先**：所有几何/性质来自 RDKit 计算，同样的输入永远同样的输出，
  现场重跑不会变。
- **离线兜底**：3Dmol.js 已本地化（`web/vendor/`），断网也能渲染；
  识别失败时可手动输入 SMILES，主链路不断。
- **无重框架**：stdlib HTTP 服务 + 单页 HTML，少一个依赖少一个坑。
- **识别可替换**：`app/recognize.py` 对外暴露 `recognize_image(bytes) -> dict`，
  换后端只改这一个文件。
- **Markush / R 基**：`R`、`R1`、`R''`、`Ar` 等占位符映射为 `*`；未定义时默认按
  **甲基（CH3）** 代入，正常生成 3D 与描述符，界面标注 `R assumed: CH3`，
  同时保留原始骨架 SMILES；同位素标记（如 ²H）会单独告警
- **缩写基团展开**：`Ph / Me / Et / iPr / tBu / Bn / Ac / Boc / Cbz / Fmoc /
  Ts / Ms / TBS / CO2Et` 等 30+ 常见缩写（识别成 `[Ph]` 这类伪原子）自动展开，
  界面提示展开了哪些基团
- **同位素氢归一**：图中的 `D` / `²H` 按普通氢处理，2D/3D 里不再出现 ²H 标签
- **手动框选**：图片太大或排版太密（反应式、表格）时，点 `Crop` 拖框只识别选中区域
- **图片预处理**：遵守 EXIF 方向（手机拍摄），超 3000 px 自动降采样
- **识别回退**：印刷体识别失败时自动改用 DECIMER 手绘模型再试一次
- **S/P 分割修复**：中央 S/P 标签会把分子切成两半并误读成碘；检测到 I/Br+S/P
  且两半水平相邻时，合并后重新识别
- **立体化学标注**：识别结果含手性/E-Z 时标 `stereo`；评测同时报
  connectivity（去立体）准确率，区分“看错结构”和“多标构型”
- **去重按 InChIKey**：同一化合物不同画法（互变异构/芳香写法）也能合并
- **并发安全**：TensorFlow 推理串行化（`_INFER_LOCK`），RDKit 分析也串行化（全局锁）。
- **健康检查可信**：`/api/health` 的 `model_loaded` 只在权重真正加载后为 true。

## 自检

```powershell
.\.venv\Scripts\python.exe scripts\selfcheck.py
```

23 项检查：健康状态、单图/多结构识别、Markush（R→甲基）、缩写展开、缓存、12 路并发分析。

## PDF 批量

```powershell
# 服务已启动的前提下
.\.venv\Scripts\python.exe scripts\run_pdf.py paper.pdf --out data\pdf_out --max-pages 20
```

输出 `results.csv`（每个结构一行：SMILES、分子式、MW、logP、TPSA、SAscore、警示、是否重复）、
`structures.sdf`（去重后的多分子文件）、`summary.json`（页数/结构数/唯一数/耗时）。

## 能查什么、不能查什么

| 能 | 不能 |
|---|---|
| 结构合法性（价键、芳香性、电荷） | 能否合成（只有 SAscore 启发式，不是合成路线） |
| 通式 / R 基、盐、多片段 | 毒性、稳定性、反应性 |
| 手性是否指定 | 安全性结论 |
| PAINS 警示、Lipinski / TPSA 越界 | 药理活性 |
| 重复结构、SAscore 难度分 | 取代专家判断 |

SAscore 是 1–10 的经验分（越低越容易），高分只代表“值得细看”，不代表“做不出来”。

## 文档与评测

| 文件 | 用途 |
|---|---|
| [`DEMO.md`](DEMO.md) | 5 分钟演示脚本、兜底方案、评委问答 |
| [`PITCH.md`](PITCH.md) | 8 页 PPT 大纲与制作提示 |
| [`MolVision-pitch.pptx`](MolVision-pitch.pptx) | 8 页可编辑 PPT 草稿，每页带讲稿备注 |
| [`EVAL.md`](EVAL.md) | 评测基线、用例说明、如何加用例 |
| [`MolVision-专家评审材料.docx`](MolVision-专家评审材料.docx) / [`.pdf`](MolVision-专家评审材料.pdf) | 专家评审：方法、证据表、边界与复现 |
| `scripts/selfcheck.py` | 23 项回归（健康/识别/Markush/缩写/缓存/并发） |
| `scripts/evaluate.py` | golden set 评测（14 用例，13/13 严格命中） |
| `scripts/pdb_rmsd.py` | 晶体配体 RMSD 验证（3D 精度） |
| `scripts/stress_3d.py` / `stress_recognition.py` | 规模压测（5000 / 100） |

## 已知限制

- 手绘、低分辨率、复杂立体化学的图，识别可能出错——这是模型能力边界，
  不是代码 bug；前端已经允许用 SMILES 兜底。
- 3D 只生成**一个**低能构象，不做构象搜索；柔性分子存在多个合理构象。
- 盐/混合物会取最大片段做 3D，完整结构仍保留性质计算。
