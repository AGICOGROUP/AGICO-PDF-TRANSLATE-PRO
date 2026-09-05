# Native-CAD PDF 中文替换流水线复刻说明

## 1. 目标

在原有 `native`、`scan`、`image` 处理能力之外，增加一条独立的
`native-cad` 流水线，用于以下文件：

- PDF 属于工程图纸、安装图、零部件图或设备总图；
- 图中文字可选择、可提取，或属于原生文字与图片混合结构；
- 用户要求中文版、格式不变，并用中文替换外文；
- 必须保留页面尺寸、矢量线、尺寸线、引线、边框、标题栏和图片。

这条流水线不重新绘制整张图纸，不把页面栅格化，也不采用双语叠加。
其核心方法是：提取文字坐标，在原坐标范围内删除外文，再写入适配字号
的中文，并通过结构检查与逐页视觉检查决定是否可以交付。

## 2. 已完成版本

源仓库：`AGICOGROUP/AGICO` 的 `AGICO-PDF-TRANSLATE-PRO`

本地提交：

```text
7e18ca2 feat: add native CAD replacement pipeline
```

如果另一台电脑可以访问该提交，优先使用 Git 获取：

```powershell
git clone https://github.com/AGICOGROUP/AGICO-PDF-TRANSLATE-PRO.git
cd AGICO-PDF-TRANSLATE-PRO
git checkout main
git pull
git show 7e18ca2 --stat
```

如果提交尚未推送，则复制本说明第 3 节列出的文件，保持相同目录结构。

## 3. 需要同步的文件

### 新增文件

```text
formats/pdf/native-cad/SKILL.md
formats/pdf/native-cad/agents/openai.yaml
formats/pdf/native-cad/references/quality-gates.md
formats/pdf/native-cad/scripts/native_cad_pipeline.py
formats/pdf/native-cad/tests/test_native_cad_pipeline.py
formats/pdf/native/tests/test_form_text_manifest_extraction.py
```

### 修改文件

```text
SKILL.md
formats/pdf/SKILL.md
formats/pdf/scripts/route_pdf_file.py
formats/pdf/tests/test_route_pdf_file.py
formats/pdf/native/scripts/apply_image_vector_text.py
formats/pdf/native/scripts/native_selectable_rebuild.py
formats/pdf/native/scripts/pdf_translation_pipeline.py
formats/pdf/native/tests/test_apply_image_vector_text.py
formats/pdf/native/tests/test_native_layout_engine.py
```

不要复制以下运行期目录：

```text
.venv-argos/
jobs/
jobs-v2/
deliverables/
.auth-temp/
scripts/__pycache__/
```

## 4. 路由规则

路由器增加 `--mode` 参数：

```powershell
python formats/pdf/scripts/route_pdf_file.py "<PDF文件>" --mode replace
python formats/pdf/scripts/route_pdf_file.py "<PDF文件>" --mode bilingual
```

路由结果应遵循：

| 文件类型和用户要求 | 流水线 |
|---|---|
| 普通可选文字 PDF，替换模式 | `native` |
| 可选文字或混合型工程图，替换模式 | `native-cad` |
| 扫描型 PDF | `scan` |
| PNG/JPEG 静态图片 | `image` |
| 明确要求保留原文并增加中文 | `bilingual` |

工程图使用替换模式时，路由报告的关键字段应为：

```json
{
  "document_kind": "engineering-drawing",
  "adapter": "formats/pdf/native-cad/SKILL.md",
  "translation_mode": "replace",
  "next_action": "translate"
}
```

路由失败、PDF 无法读取、文件加密或页面结构异常时必须停止，禁止静默切换
到其他流水线。

## 5. Native-CAD 执行流程

### 5.1 准备作业

```powershell
python formats/pdf/native-cad/scripts/native_cad_pipeline.py prepare `
  "<源文件.pdf>" `
  --job-dir "<作业目录>"
```

程序应执行：

1. 将源文件复制为作业目录中的 `SOURCE.pdf`；
2. 记录源文件 SHA-256，后续所有阶段绑定该哈希；
3. 提取每页尺寸、旋转角度、图片数量和矢量图元数量；
4. 按页、行、文字片段提取文本、坐标、字号、颜色和方向；
5. 为每个文字片段生成稳定 ID，例如 `p0001-s00001`；
6. 生成 `source-inventory.json` 和 `translation-packet.json`。

### 5.2 翻译清单

只处理 `status: pending` 的记录：

```json
{
  "id": "p0001-s00001",
  "source": "SECTION A-A",
  "translation": "A-A剖面",
  "status": "translated"
}
```

以下内容原则上标记为 `protected`，不得擅自翻译或改写：

- 图号、版本号、设备型号和物料编码；
- 数字、尺寸、公差、比例和坐标；
- `Ø`、`R`、`M` 等工程符号；
- `mm`、`kg`、`kW` 等单位；
- ISO、DIN、EN、GB 等标准号；
- 用户明确要求保留的品牌和专有名称。

所有待翻译记录必须填写完整。缺项、空译文或状态错误均应停止应用阶段。

### 5.3 坐标替换

```powershell
python formats/pdf/native-cad/scripts/native_cad_pipeline.py apply `
  "<作业目录>" `
  --packet "<已填写翻译包.json>"
```

关键实现要求：

- 只在原文字矩形中建立文字删除区域；
- PyMuPDF 应使用 `images=0, graphics=0, text=0` 应用 redaction；
- 不得删除或覆盖尺寸线、引线、剖面线、边框和其他矢量图元；
- 使用中文字体，例如黑体或微软雅黑；
- 中文从原字号开始逐级缩小，直至放入目标框；
- 保持原文字方向，支持常见的 0、90、270 度文字；
- 任何无法放入目标框的记录写入 `fit_failures`，并阻止交付；
- 输出 `translated-native-cad.pdf` 和 `apply-report.json`。

白色矩形覆盖只能用于无法直接删除的 Form/XObject 文字，而且必须同时满足：

- 背景经过检查确认为纯色或空白；
- 矩形内不含线条、符号和其他图元；
- 覆盖坐标明确记录在 `approved-covers.json`；
- 覆盖后对该区域进行放大视觉复核。

## 6. 验证与交付门

先执行结构验证并渲染页面：

```powershell
python formats/pdf/native-cad/scripts/native_cad_pipeline.py verify `
  "<作业目录>" `
  --candidate "<作业目录>\translated-native-cad.pdf"
```

逐页检查渲染图后创建 `visual-review.json`：

```json
{
  "candidate_sha256": "候选文件SHA-256",
  "all_pages_reviewed": true,
  "all_changed_regions_reviewed": true,
  "visible_foreign_descriptive_text": [],
  "text_overlap_failures": [],
  "line_or_graphic_damage": [],
  "notes": ""
}
```

然后执行最终验证：

```powershell
python formats/pdf/native-cad/scripts/native_cad_pipeline.py verify `
  "<作业目录>" `
  --candidate "<作业目录>\translated-native-cad.pdf" `
  --visual-review "<作业目录>\visual-review.json"
```

只有 `final-qa.json` 中出现以下结果才允许交付：

```json
{
  "passed": true
}
```

最终质量门至少包括：

- `SOURCE.pdf` 的 SHA-256 未改变；
- 页面数量、页面尺寸和旋转方向一致；
- 原有图片数量没有减少；
- 所有待翻译记录已经处理；
- 没有文字适配失败；
- 中文可以正常显示并可提取；
- 每页和全部修改区域均经过视觉检查；
- 没有外文说明残留、文字重叠或线条损伤。

## 7. 安装到另一台电脑的 Codex Skill 目录

确认仓库版本测试通过后，把整个项目 Skill 同步至：

```text
C:\Users\<用户名>\.codex\skills\pdf-translate-pro\
```

至少确保以下入口存在：

```text
C:\Users\<用户名>\.codex\skills\pdf-translate-pro\SKILL.md
C:\Users\<用户名>\.codex\skills\pdf-translate-pro\formats\pdf\SKILL.md
C:\Users\<用户名>\.codex\skills\pdf-translate-pro\formats\pdf\native-cad\SKILL.md
```

不要只复制 `native-cad` 文件夹，因为总路由器和 PDF 路由器也包含必要修改。

## 8. 环境与验证命令

建议使用 Python 3.11 或更新版本，并安装项目依赖。至少需要：

```text
PyMuPDF
pypdf
reportlab
pytest
```

执行测试：

```powershell
python -m pytest -q formats/pdf/tests
python -m pytest -q formats/pdf/native/tests
python -m pytest -q formats/pdf/native-cad/tests
python -m py_compile `
  formats/pdf/scripts/route_pdf_file.py `
  formats/pdf/native-cad/scripts/native_cad_pipeline.py
```

使用 Codex 的 Skill 校验器时执行：

```powershell
$env:PYTHONUTF8='1'
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" `
  "formats/pdf/native-cad"
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" `
  "."
```

本次实现的验证结果：

- PDF 路由测试：17 项通过；
- native 流水线测试：135 项通过；
- native-cad 测试：1 项通过；
- Python 语法检查通过；
- native-cad Skill 与总 Skill 结构校验通过。

## 9. 复刻验收清单

- [ ] `native-cad` 文件夹和五个核心文件存在；
- [ ] `route_pdf_file.py` 支持 `--mode replace|bilingual|auto`；
- [ ] 工程图替换模式能路由至 `native-cad`；
- [ ] 普通 PDF、扫描 PDF、图片和双语模式的原路由未被破坏；
- [ ] 源文件保持不变并有 SHA-256 绑定；
- [ ] 翻译包具有稳定记录 ID；
- [ ] 尺寸、单位、图号和标准等受保护内容不会被误译；
- [ ] 坐标替换不会删除图片和矢量线；
- [ ] 适配失败会阻止交付；
- [ ] 所有页面已渲染并人工检查；
- [ ] `final-qa.json` 为 `passed: true` 后才交付。

## 10. 关键经验

普通 `native` 流水线适合段落、表格和一般版式，但工程图中的文字往往是
大量离散文字片段、旋转标注、Form/XObject 内容和极小字号。直接按普通文档
重排容易造成标题栏错位、标注越界或图线损伤。

`native-cad` 的关键不是“重新排版”，而是“以原坐标为约束进行局部替换”，
并把结构一致性、文字适配和逐页视觉检查设置为不可跳过的交付门。
