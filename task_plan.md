# Task Plan: 规范漫画命名预览与自动识别

## Goal
修改 Web 端文件夹选择与转换配置逻辑：选择漫画文件夹后自动读取首个漫画文件并展示文件名，结合文件夹名/文件名推断更规范的漫画输出名，并在界面展示类似“漫画名 Vol.01”的输出预览，方便用户确认或修改。

## Current Phase
Phase 5

## Phases
### Phase 1: Discovery & Rules
- [x] 阅读 `web_server.py`、前端模板与脚本
- [x] 检查现有漫画目录命名样本
- [x] 梳理文件名/文件夹名推断规则与约束
- **Status:** complete

### Phase 2: Naming Design
- [x] 设计漫画名提取、卷号提取、输出预览规则
- [x] 确定前后端接口返回的数据结构
- [x] 记录边界情况与降级策略
- **Status:** complete

### Phase 3: Implementation
- [x] 修改 `web_server.py` 增加文件夹漫画元数据分析与命名辅助
- [x] 修改前端界面，展示首个文件名、漫画名、输出预览
- [x] 让启动任务时使用更规范的输出命名参数
- **Status:** complete

### Phase 4: Verification
- [x] 运行语法/行为验证
- [x] 使用真实 `comic/` 目录样本验证推断结果
- [x] 记录测试结果与剩余风险
- **Status:** complete

### Phase 5: Delivery
- [x] 总结改动文件
- [x] 说明命名规则与自动推断行为
- [x] 说明剩余风险/后续建议
- **Status:** complete

## Key Questions
1. 文件名仅为 `Vol.xx` 时，如何从文件夹名中尽量可靠地提取漫画名？
2. 如何在不大改核心转换逻辑的前提下，让输出名尽量规范且对用户可预期？
3. 前端应该展示哪些命名线索，才能让用户快速确认是否需要手动修改？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 先展示首个漫画文件名，再展示自动推断出的漫画名和输出预览 | 让用户能同时看到原始输入与规范化结果 |
| 优先从文件名提取漫画名，文件名只有 `Vol` 时再回退到文件夹名 | 文件名比文件夹元数据更接近最终输出对象 |
| 输出预览统一使用 `漫画名 Vol.xx` 形式 | 与用户要求一致，且便于理解最终命名 |
| `book/cbz` 模式新增 `comic_name` 规范命名参数 | 让 Web 端可在不破坏 CLI 默认行为的前提下统一输出名 |
| 输出目录默认使用推断/确认后的漫画名 | 比直接使用原始方括号文件夹名更规范 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| 系统 `python3` 导入 `web_server.py` 时缺少 Flask | 1 | 改用 `conda run -n comic python ...` 执行运行时相关验证 |

## Notes
- 样本目录同时存在 `漫画名 Vol.xx` 与 `Vol.xx` 两种源文件名。
- 文件夹名中除漫画名外，还可能包含作者、卷区间、完结状态、来源站点等元数据。
- 文件夹推断仍属于“最佳努力”，UI 保留可编辑输入供用户最终确认。
