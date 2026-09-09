# 本地 Skill 取舍方案实施记录

## 范围与基线

- 仅覆盖 `D:\AGICO-PDF-TRANSLATE-PRO` 内的 Skill、对应实现和测试。没有 push、改远端分支、提交混合工作区或覆盖其他任务文件。
- 固定对照 main：`e9c1fd38b0326589325c339e1d94f49f407de388`。本地 HEAD 保持 `6809d729128d0cbb5ce3a478a6b16af8ae8c7d6d`。
- 使用选择性覆盖，不做整库 reset：保留 main 的原生重建/图像文字层架构；回撤无证据的 OCR 内容抑制，覆盖验收误判和冲突规则；保留经前次审计确认有价值的缓存、兼容与段落排版改动。
- 原有 CAD 改动没有覆盖。全局安装目录 `C:\Users\Administrator\.codex\skills` 未同步；本次用户指定的是本地项目。后续使用本版应加载项目根 `SKILL.md`，不能把全局旧副本当成本次更新。
- 改动前副本：`tmp/skill-backup-20260909-150721/`，包含当时的 SKILL、AGENTS、formats、references、agents（存在时）、docs。未删除原文件或旧 PDF。恢复时仅取需要的文件，避免覆盖随后新增的工作。

## 取舍结果

| 处理 | 内容 |
|---|---|
| 保留 | OCR 单次主扫描与按页断点、清理底图缓存、局部背景采样、原子输出、CJK 字体/换行、空原生页面修复 |
| 保留 | 整页语境翻译、逐项源文 ID、只对溢出整段缩字、已核验且内容未变的页面证据复用 |
| 覆盖 | 隐藏 OCR 扫描件误走 native；全标 `ocr-artifact` 后不绘制正文的旁路；正文图内文字默认逐行居中 |
| 覆盖 | 缺失像素指标默认 0、native 零对象误过、语义记录未被 runner 检查、总 QA 固定 passed、旧 verified 布尔值直接交付 |
| 覆盖 | 工程图纸无条件双语、中文输出被英文专用要求误导、一个段落挤就缩小全页正文、固定 6/7 门禁的旧测试 |

只保留三类阻断：内容正确、完整可读、关键结构完整。字号、字重、轻微对齐及无实质遮挡的几何相交作为提醒，不恢复苛刻样式门槛。扫描页仍按每页 120 秒的端到端预算；超时停止自动修复，未完成时交真实状态预览。

## 已落地的关键行为

1. PDF 路由与 scan 分类共用非绘制文字判定，处理 `Tr=3/7`、q/Q 状态和 Form XObject；native 初始化也拒绝仅隐藏 OCR 的扫描件。该检测不声称覆盖透明度、遮挡等所有隐藏机制。
2. 图内正文支持源对齐，body 默认左/顶对齐；不能拟合时明确失败，不返回仍溢出的最小字号。
3. 清理前检查坐标与长结构线，拒绝明显不适合整块填充的区域；恢复声明的签字、印章等 `protected_boxes`，报告实测区外/保护区像素变化。长线检测只是有限筛查，不能证明未声明的所有艺术内容安全。
4. native verifier 检查实际绘制的源 ID；runner 消费原有语义复核记录并核验哈希、页序及 native/image label 覆盖。缺失、过期、有未解决问题的记录不放行。软件只验证证据一致性，不自动证明翻译准确，也不能替代真实人工/模型阅读。
5. 旧 verified 作业缺少当前证据时返回 `revalidate_evidence`。官方 verify 支持重新核验，不需要手动重置阶段或重建未变化的内容。
6. native 入口精简，细节放到已有参考文件；相互冲突的句子已原位替换。默认提示也同步服从明确单语要求。

## 验证

先新增失败用例复现，再修复通过：隐藏 OCR 路由、Form 隐藏文字、图形状态恢复后可见文字保留、边框填白、保护区像素、正文对齐、拟合失败、OCR 抑制、空排版检查、语义记录缺失/过期/漏项、旧 verified、完整 runner 链路及复核更新。

测试分适配器独立进程运行，避免仓库现有同名测试模块的导入冲突：

```powershell
python -m pytest formats/pdf/native/tests -q
python -m pytest formats/pdf/scan/tests -q
python -m pytest formats/pdf/bilingual/tests formats/image/tests formats/pdf/tests formats/test_independent_quality_gates.py -q
```

最近一次完整回归合计：242 tests（native 140、scan 65、其余 37），另 11 subtests。根/PDF 路由/native/scan 四份 Skill 均通过 quick_validate；`git diff --check` 通过。

术语表未修改。旧测试失败来自 LF 与 CRLF 的字节差别，已核对本地与固定 main 的词表完全一致，测试改用规范 LF 哈希，仍检查完整词表内容。

文档压力复测覆盖“隐藏 OCR + 已伪通过 + 20 分钟催交 + 大白框损伤 + 明确中文单语”：决策均为正确路由、保持单语、保护结构、缺证据不冒充完成，且不追加重复 OCR/门禁流水线。

## 原 10 页文件的只读复核

- 原始输入 SHA-256：`54923a74276f352bfa61c917244e671b91379a2112a3b2626a8f672d49bf745b`。
- 两个分类入口均返回 scan-only，10 页，native_text_pages 为 0，替换模式。
- 第 5 页旧 `[250,250,2350,2740]` 整块 solid_fill 在内存复核中被拒绝，错误为 probable structure；未写回任何源图/译图。
- 旧作业 resume 返回 `revalidate_evidence`，不再返回 deliver。只读检查没有改写旧作业状态。

这次完成的是项目 Skill 与执行逻辑更新，没有重新翻译或替换旧 10 页交付 PDF，也没有做同模型的新版/云端完整翻译 A/B。不能据这些测试宣称旧 PDF 已合格，或保证后续每页一定在 2 分钟内完成。
