# Task Plan: CPU 利用率与单 Job 多漫画并行可行性调研

## Goal
评估当前 `web_server.py` 的 3 个并行 worker 为什么对 CPU 占用提升有限；同时研究单 job 在“一个漫画目录内含多本漫画文件”场景下，是否值得从当前串行转换升级为“同一 job 内多本漫画并行转换”，若可行且收益明显，则给出可执行修改计划。

## Current Phase
Phase 3: 并行可行性分析与方案规划

## Phases
### Phase 0: Context Recovery
- [x] 运行 session catchup 并读取现有 planning files
- [x] 读取 OMX 状态 / notepad / project memory
- [x] 确认当前仓库无更深层 AGENTS 影响业务代码改动
- **Status:** complete

### Phase 1: Code Path Mapping
- [x] 定位 Web worker pool、job queue 与系统资源统计入口
- [x] 定位主转换路径（batch/book/cbz/pdf）与现有并行逻辑
- [x] 确认单 job 内“多本漫画”当前是否为串行处理
- **Status:** complete

### Phase 2: Baseline Measurement
- [x] 选取代表性样本并测量当前单 job / 多 job 的 CPU 利用率与耗时
- [x] 判断瓶颈更偏向 CPU、I/O、进程池创建开销还是串行外围逻辑
- [x] 记录当前 3 worker 继续加大时的潜在限制因素
- **Status:** complete

### Phase 3: Parallelization Feasibility
- [x] 评估单 job 内对多本漫画做并行转换的改造点、风险点与约束
- [x] 估算潜在收益（吞吐 / CPU 占用 / 内存）
- [x] 判断是否值得推进实现
- **Status:** complete

### Phase 4: Planning Output
- [x] 汇总结论
- [x] 若值得实施，输出分阶段修改计划、测试计划与回滚关注点
- **Status:** complete

## Key Questions
1. 当前 3 个 web worker 对 CPU 利用率提升有限，究竟卡在 Web 层、单 job 内部串行逻辑，还是图片预处理/压缩流程本身？
2. 现有单 job 内每本漫画（ZIP/CBZ/PDF）是否确实逐本串行执行？
3. 如果把“逐本漫画”提升为 job 内并行，是否会与现有 `ProcessPoolExecutor` 预处理并行产生过度嵌套并发？
4. 在 12 核机器上，更高 CPU 占用是否能换来稳定吞吐提升，还是会被磁盘 IO / 内存 / 子进程开销抵消？
5. 如果推进改造，最小可行方案应该落在哪一层：Web worker 数、预处理 worker 数、自适应限流，还是 job 内多漫画 worker pool？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 先做代码路径与基线测量，再讨论改造 | 用户要求的是“研究是否值得改”，需要先确认瓶颈来源而不是直接实施 |
| 优先选择真实样本的子集做代表性压测 | 合成样本难以准确体现 ZIP/CBZ 解压、PIL 解码、PDF 写入与 KCC 等混合负载 |
| 若做 job 内并行评估，要同时考虑与现有图片预处理进程池的叠加效应 | 外层多漫画并行 + 内层图片预处理并行，可能导致 CPU 超卖和内存放大 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `omx explore` 依赖缺失（cargo not found） | 1 | 回退为直接读取源码、测试和运行本地 benchmark |

## Notes
- 现有 planning files 中保留了此前任务的长期记录；本次 `task_plan.md` 已切换为当前调研主题。
- 当前重点是“是否值得改 + 怎么改”，不是立刻提交实现。
