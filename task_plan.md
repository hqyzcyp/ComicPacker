# Task Plan: 漫画转换性能优化（第二阶段）

## Goal
在第一阶段完成热点预处理优化后，继续降低真实整卷转换的峰值内存与整体耗时。第二阶段聚焦于消除“整卷图片一次性读入 + 整卷预处理后再统一写 PDF”的结构性问题，改为按章节/按压缩包增量处理，并用真实样本重新对比时间与 RSS。

## Current Phase
Complete

## Phases
### Phase 0: Context Recovery
- [x] 运行 session catchup 并读取现有 planning files
- [x] 确认第一阶段优化已完成且验证通过
- [x] 检查当前工作区改动基于第一阶段结果继续推进
- **Status:** complete

### Phase 1: Baseline + Design
- [x] 对真实 ZIP / CBZ 单卷运行做时间与 RSS 基线测量
- [x] 确认当前剩余主问题是“整卷全量持有导致的 >1GiB 峰值内存”
- [x] 设计保持输出顺序不变的增量处理方案
- **Status:** complete

### Phase 2: Regression Lock + Refactor
- [x] 为 batch/book/cbz 三条 PDF 生成路径补充端到端回归测试
- [x] 将 `main.py` 改为按章节/按压缩包增量读取、预处理、写 PDF
- [x] 保持现有输出命名、页顺序与书签行为不变
- **Status:** complete

### Phase 3: Verification
- [x] 运行语法检查与完整测试
- [x] 用真实样本重新测量时间与峰值 RSS
- [x] 记录收益、风险和后续更大范围优化项
- **Status:** complete

## Key Questions
1. 能否在不改变输出顺序和现有接口的前提下，把 ZIP/CBZ 处理改为增量式？
2. 这样做能否显著压低真实单卷转换的峰值 RSS？
3. 在降低内存的同时，整卷总耗时是否也会改善，至少不明显回退？
4. batch/book/cbz 三条路径是否都能在这一轮统一收敛到更小的内存占用模式？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 第二阶段优先解决全量持有图片的问题 | 第一阶段后，真实样本仍有约 1.1~1.2 GiB 峰值 RSS，这是最突出的剩余问题 |
| 先补回归测试，再做结构性重排 | 这一轮会改动 PDF 生成路径，先锁住页数和生成成功率更稳妥 |
| 采用按章节/按压缩包增量处理 | 能在不大改上层 API 的前提下，把内存占用从“整卷级”降到“章节级/单包级” |
| 默认再叠加 32 页分块预处理 | 这样即使是单章节/默认章节的大卷，也不会再次退化成整卷级内存占用 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| 暂无 | - | - |

## Notes
- 第一阶段结论与验证保留在 `findings.md` / `progress.md`，本轮只补充第二阶段证据。
- 若第二阶段完成后仍有明显瓶颈，后续候选项包括：复用持久进程池、减少 ZIP 重复打开、进一步降低 ReportLab 重复解码、以及 Web worker 并行模型优化。
