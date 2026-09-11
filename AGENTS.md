# AGENTS.md — pdf-translate-pro

## 工作目录与访问范围

- 本项目当前工作目录为 `D:\AGICO-PDF-TRANSLATE-PRO`；项目代码、测试及中间文件默认在仓库内读写，相对路径以仓库根目录为基准。
- 允许读取用户指定的输入文件，以及任务所需的技能说明、依赖和运行环境；允许将成果写入用户指定的输出位置。
- 不修改与任务无关的仓库外文件。仓库迁移时以当前实际检出的根目录为准，不将旧盘符作为唯一访问限制。

## 第一原则：简单高效

- 一切实现以「简单高效」为最高原则：最短的路径、最少的依赖、最少的方法完成需求。
- 拒绝过度设计：不加用不到的抽象层、配置项、兼容分支。
- 能复用已有代码就不新写；能一个文件解决就不拆多个。

## 项目（来自 AGICO-PDF-TRANSLATE-PRO）

专业 PDF / 静态 PNG-JPEG 翻译技能库，根目录 `SKILL.md` 是唯一入口（路由器）。远端分支：`main`、`codex`、`glm`。

### 架构边界（改动前必读）

- 根 `SKILL.md` 按文件格式路由：PDF → `formats/pdf/SKILL.md`（内容级路由）；静态 PNG/JPEG → `formats/image/SKILL.md`。
- PDF 内容分类仍为 native-text、mixed、scan-only；结合输出模式选择 4 个互斥执行适配器，同一输入只跑一个：
  - `formats/pdf/native/` — 可选文本/混合 PDF（保留可选中文字，单独处理图内文字）
  - `formats/pdf/scan/` — 纯扫描/图像 PDF
  - `formats/pdf/bilingual/` — 双语对照覆盖层
  - `formats/pdf/native-cad/` — 原生/混合工程图的替换模式，保留矢量
- 路由必须运行 `python formats/pdf/scripts/route_pdf_file.py <file>` 依内容判断，禁止按扩展名/文件名/用户措辞路由。
- 用户指定目标单语走替换，明确双语走叠加；工程图仅在未指定模式时默认双语。直通要求现有语言组合与用户请求一致且语义覆盖完整，不是任意“中文+外语”都可跳过。
- 每个适配器目录结构固定：`SKILL.md` + `scripts/` + `tests/` + `references/`。

### 常用命令

- 安装依赖：`pip install -r formats/pdf/scan/scripts/requirements.txt`（numpy、Pillow、pdfplumber、pypdf、rapidocr-onnxruntime、reportlab）
- 测试（pytest）：仓库根目录运行 `python -m pytest -q`；`pytest.ini` 包含四个 PDF 适配器、图片、路由和 `formats/test_independent_quality_gates.py`，并处理同名测试模块。
- PDF 分类：`python formats/pdf/scripts/route_pdf_file.py <file>`（在仓库根目录运行）
- SKILL.md 中出现的相对路径命令按对应适配器自己的目录解析。

### 已知坑

- `formats/pdf/*/scripts/sync-install.ps1`（部署脚本）目标路径硬编码为 `C:\Users\Administrator\.codex\skills\...`，在本机（用户 AGICO）会失败，使用前需改路径。
- 本机直连 GitHub 会被重置，git 操作需走本地代理：`git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 fetch ...`。
- 先检查当前解释器、依赖和字体；不要依据旧机器的 Python 版本假设安装状态。CAD 还需要 PyMuPDF。翻译过程中不升级依赖；重构对照固定解释器和依赖版本。

### 改敏感区域前先读的文档

- `docs/superpowers/plans/` 与 `docs/superpowers/specs/` — 设计与实施计划
- `formats/pdf/native/references/`（manifest-schema.md、quality-gates.md、direct-v6-workflow.md 等）与 `formats/pdf/bilingual/references/workflow.md` — 各适配器的权威工作流与质量门禁
