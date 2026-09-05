# Native-CAD 路由设计

## 目标

为可选文字或原生文字与图片混合的工程图增加原文替换能力，同时保留当前“工程图默认双语覆盖”的安全策略。

默认行为不变：用户没有明确指定输出模式时，工程图保留原文并添加译文。只有用户明确要求删除或替换原文、仅保留译文时，才允许进入 `native-cad`。

## 分类维度

PDF 路由继续按三个相互独立的维度判断：

- 内容形态：`native-text`、`mixed`、`scan-only`；
- 版式类型：沿用现有的 `document`、`engineering-drawing`；
- 输出模式：`auto`、`replace`、`bilingual`。

`native-cad` 不是新的文件格式，也不是与内容形态并列的 PDF 类型。它是以下条件组合对应的执行适配器：

```text
(native-text | mixed) + engineering-drawing + replace -> native-cad
```

## 路由规则

`route_pdf_file.py` 接受 `--mode auto|replace|bilingual`，默认值为 `auto`。

| 内容形态 | 版式类型 | 模式 | 适配器与行为 |
|---|---|---|---|
| native-text / mixed | document | auto / replace | `native`，替换原文 |
| native-text / mixed | document | bilingual | `bilingual`，保留原文并添加译文 |
| native-text / mixed | engineering-drawing | auto / bilingual | `bilingual`，保留当前工程图默认策略 |
| native-text / mixed | engineering-drawing | replace | `native-cad`，按原坐标替换文字 |
| scan-only | document | auto / replace | `scan`，替换原文 |
| scan-only | document | bilingual | 沿用现有 scan 行为；不得路由到依赖原生文字的适配器 |
| scan-only | engineering-drawing | auto / bilingual | `scan` 的双语工程图模式 |
| scan-only | engineering-drawing | replace | `scan` 的替换模式；不得路由到 `native-cad` |

无法读取、已加密、页面结构异常或模式值无效时必须停止，不得静默切换适配器。

## Native-CAD 边界

新增 `formats/pdf/native-cad/` 独立适配器，处理可选文字或混合型工程图的替换输出。它：

- 从原 PDF 提取稳定文字记录及坐标；
- 保护图号、型号、尺寸、公差、单位和标准号；
- 仅删除目标文字，不删除图片或矢量图形；
- 在原区域写入可选择、可提取的译文，并保留文字方向；
- 对 Form/XObject 等不能直接安全删除的文字采用显式审批覆盖记录；
- 任何漏译、适配失败、图线损伤或视觉复核不完整都阻止交付。

它不处理 scan-only PDF，不与 `native`、`scan` 或 `bilingual` 工作流合并运行。

## Skill 文案调整

- 根 `SKILL.md`：将“工程图无条件双语”改为“默认双语；明确 replace 时允许专用替换流程”。
- `formats/pdf/SKILL.md`：说明三个分类维度及唯一适配器选择规则。
- `formats/pdf/native/SKILL.md`：工程图只有在 `auto` 或 `bilingual` 时跳转 bilingual；`replace` 跳转 native-cad。
- `formats/pdf/bilingual/SKILL.md`：保留工程图默认入口，同时明确用户的 replace 指令优先。
- 新增 `formats/pdf/native-cad/SKILL.md` 及其必要脚本、质量门和测试。

## 测试与验收

先增加失败的路由测试，再修改实现。至少覆盖：

1. 普通原生 PDF 的 `auto` 与 `replace` 仍进入 native；
2. 普通原生 PDF 的 `bilingual` 进入 bilingual；
3. 原生/混合工程图的 `auto` 仍进入 bilingual；
4. 原生/混合工程图的 `replace` 进入 native-cad；
5. scan-only PDF 在所有模式下都不进入 native-cad；
6. 无效模式、加密文件和不可读 PDF 继续失败关闭；
7. Native-CAD 的准备、翻译包校验、坐标替换和最终质量门均有针对性测试；
8. 完整 PDF、native、native-cad、scan、bilingual 与 image 测试集通过。

## 非目标

- 不增加 Word、Excel、PowerPoint 等 Office 输入格式；
- 不改变 PNG/JPEG 与 scan PDF 的现有关系；
- 不重命名或扩展现有 `document_kind`；
- 不让 `native-cad` 处理 scan-only 页面；
- 不取消工程图在 `auto` 模式下默认双语的策略；
- 不在本次工作中重构无关的 scan 页面区域布局改动。
