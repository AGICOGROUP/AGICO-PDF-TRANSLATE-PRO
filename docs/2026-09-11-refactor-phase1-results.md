# 重构第一阶段：任务与交付契约

本阶段基于 `dade7e537b4ca36a8541b40de169b741bdcd68e2`，在用户指定的 `codex` 检出目录实施。未移动 main、未提交或推送，未更换翻译模型、字体策略、DPI 或验收严重度。

## 稳定对照

- Git archive：`tmp/refactor-baselines/dade7e53/source.zip`。
- 独立解压源码：`tmp/refactor-baselines/dade7e53/source/`。
- ZIP SHA-256：`C72B200419EE28B6212122A3989BEEDA7E09E051DEBDBC690C2F76084CAA0055`。
- 解压的根 SKILL blob 与基线提交一致：`b0098839f510a12274bc44cec02eb258cca368dc`。
- 安装中的 Skill Junction 没有改动，仍指向当前 codex 工作目录。因此本机默认发现的是实验版，不能把它称作已隔离安装的稳定版。A/B 对照必须显式调用稳定源码目录，保持相同解释器和字体。

环境记录：Python 3.14.7，`C:/Program Files/Python314/python.exe`；PyMuPDF 1.28.2，pypdf 6.18.0，pdfplumber 0.11.10，Pillow 12.3.0，numpy 2.5.2，reportlab 5.0.1，rapidocr-onnxruntime 1.2.3，onnxruntime 1.29.0，pytest 9.1.1。没有安装或升级依赖。这是本机复现实测记录，不是跨环境兼容承诺。

CAD 回归使用的 SimHei SHA-256：`AA4560DD8FE5645745FED3FFA301C3CA4D6C03CBD738145B613303961BA733B8`。

## 已实现

1. 新的原生任务按源文件和语言请求隔离；同请求初始化可以续用，换语言不会复用已有 manifest。新任务固定为本适配器支持的 replace/all-pages，不新增页面选择能力。
2. 原生 init 增加 `--fresh`，CAD prepare 增加 `--target-language` 与 `--fresh`。fresh 创建独立目录，不删除旧任务、不复用旧 OCR/译文/复核；返回实际 job_dir。
3. CAD 新绑定的任务校验 packet 的目标请求；换语言使用新目录或 fresh。旧无绑定任务可以按原路径继续，不能把已有旧译文静默绑定为新语言。
4. 双语直通须匹配实际和请求的语言组合，并且五项覆盖计数完整。语言不匹配、证据不全时继续清点/翻译，而不是把任务判失败。
5. CAD 在删除任何源文字前检查译文框是否有限、有效且完全在可见页面内。错误报告定位 ID；现有“正常框但译文装不下”的保留原文预览机制不变。
6. pytest 统一入口覆盖四类 PDF 适配器、图片、路由与独立检查，修复同名测试收集冲突。相关 Skill/API 说明覆盖旧内容。

## 红灯到绿灯

- 原默认测试命令复现三个模块重名收集错误；加入 pytest.ini 后，未改行为前全套 **295 passed、13 subtests passed，29.93 秒**。
- 新测试在旧实现上得到 **18 failed、12 passed、2 subtests passed**（失败计数包含 unittest 子测试）。覆盖语言串用、fresh 缺失、manifest 意图改变、CAD 请求接口缺失、页外/退化/非有限框，以及错误双语直通。
- 最小修复后定向测试 **24 passed、8 subtests passed，6.68 秒**。
- 第一轮全套行为回归 **308 passed、19 subtests passed，36.25 秒**；独立复查修正后最终全套 **320 passed、19 subtests passed，37.89 秒**。
- 六个修改过的 Skill 入口均通过官方 quick_validate；该验证只检查元数据/结构，不证明语义决策质量。语言契约还通过 CLI 集成测试。
- 独立只读复查发现旋转页面坐标系问题：page.rect 已旋转，但原生文字坐标未旋转。补充 90°/180°/270°、裁剪/未裁剪、合法/页外布局 12 个组合，修复前 8 失败、4 通过。边界改用 `page.rect * page.derotation_matrix` 后，整个短语/布局测试文件 22 项通过；独立复查再次验证并确认无剩余发现。
- 最终 `git diff --check` 通过；main 仍为上述稳定提交。没有提交、推送或合并。

## 本阶段遇到的问题

除上面已修正的旋转坐标回归外，官方 quick_validate 脚本使用系统默认文本编码，在本机 GBK 环境读取 UTF-8 Skill 时报 UnicodeDecodeError。改用 `python -X utf8 .../quick_validate.py` 后六个入口都通过；没有修改仓库外验证脚本或全局配置。Git 提示 LF 将按已有配置转换为 CRLF，不是代码测试失败。

## 尚未完成的后续工作

本阶段没有重新翻译真实用户文件，也没有证明端到端提速。全新翻译性能对照、统一阶段计时、保守句段分组、单元格约束、局部构建/复核、OCR 缓存版本与按需并发仍属于后续阶段。

下一阶段优先将 CAD 原始文字片段组织为可审阅的完整标签/条款建议，保留所有源 ID、数字和单元格边界。先验证建议正确性，再减少执行者手动逐词映射；不自动把相邻文字全部合并。
