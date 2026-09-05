# AGENTS.md — pdf-translate-pro

## 工作目录（唯一目录）

- 本项目唯一工作目录为 `E:\pdf-translate-pro`，所有读写、创建文件的操作必须限定在此目录内。
- 不得读取、写入或引用该目录之外的路径；所有路径均相对于此根目录。

## 第一原则：简单高效

- 一切实现以「简单高效」为最高原则：最短的路径、最少的依赖、最少的方法完成需求。
- 拒绝过度设计：不加用不到的抽象层、配置项、兼容分支。
- 能复用已有代码就不新写；能一个文件解决就不拆多个。

## 项目（来自 AGICO-PDF-TRANSLATE-PRO）

专业 PDF / 静态 PNG-JPEG 翻译技能库，根目录 `SKILL.md` 是唯一入口（路由器）。远端分支：`main`、`codex`、`glm`。

### 架构边界（改动前必读）

- 根 `SKILL.md` 按文件格式路由：PDF → `formats/pdf/SKILL.md`（内容级路由）；静态 PNG/JPEG → `formats/image/SKILL.md`。
- PDF 按内容分成 3 个互斥子适配器，同一输入只允许跑一个，禁止合并工作流：
  - `formats/pdf/native/` — 可选文本/混合 PDF（保留可选中文字，单独处理图内文字）
  - `formats/pdf/scan/` — 纯扫描/图像 PDF
  - `formats/pdf/bilingual/` — 双语对照覆盖层
- 路由必须运行 `python formats/pdf/scripts/route_pdf_file.py <file>` 依内容判断，禁止按扩展名/文件名/用户措辞路由。
- 工程图纸默认走双语覆盖；已是"中文+外语"完整的图纸直接保留原样并标记完成。
- 每个适配器目录结构固定：`SKILL.md` + `scripts/` + `tests/` + `references/`。

### 常用命令

- 安装依赖：`pip install -r formats/pdf/scan/scripts/requirements.txt`（numpy、Pillow、pdfplumber、pypdf、rapidocr-onnxruntime、reportlab）
- 测试（pytest）：`python -m pytest formats/pdf/native/tests formats/pdf/scan/tests formats/pdf/bilingual/tests formats/image/tests formats/pdf/tests -q`；根目录另有 `test_independent_quality_gates.py`
- PDF 分类：`python formats/pdf/scripts/route_pdf_file.py <file>`（在仓库根目录运行）
- SKILL.md 中出现的相对路径命令按对应适配器自己的目录解析。

### 已知坑

- `formats/pdf/*/scripts/sync-install.ps1`（部署脚本）目标路径硬编码为 `C:\Users\Administrator\.codex\skills\...`，在本机（用户 AGICO）会失败，使用前需改路径。
- 本机直连 GitHub 会被重置，git 操作需走本地代理：`git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 fetch ...`。
- 全局 Python 3.12 尚未安装 pytest，跑测试前先 `pip install pytest`。

### 改敏感区域前先读的文档

- `docs/superpowers/plans/` 与 `docs/superpowers/specs/` — 设计与实施计划
- `formats/pdf/native/references/`（manifest-schema.md、quality-gates.md、direct-v6-workflow.md 等）与 `formats/pdf/bilingual/references/workflow.md` — 各适配器的权威工作流与质量门禁
