# Task Plan: Web 页面布局与 PDF 保留逻辑调整

## Goal
根据用户最新需求调整 ComicPacker Web 页面：重排四块面板布局、压缩配置表单、补充 hover 说明、移除“命名来源”行，并新增“保留 PDF 格式”选项及其后端删除 PDF 目录逻辑，确保现有转换流程不回归。

## Scope
- `templates/index.html`
- `static/style.css`
- `static/app.js`
- `web_server.py`
- `main.py`
- `tests/` 下与 Web/API/输出保留逻辑直接相关的测试
- `task_plan.md`
- `findings.md`
- `progress.md`

## Current Phase
Phase 3 — Verification & Report (complete)

## Implementation Plan
1. 复查当前四面板布局、表单结构、MOBI/PDF 相关前后端参数流。
2. 先确定 UI 结构与状态规则，再最小修改 HTML/CSS/JS。
3. 为“保留 PDF”逻辑补后端支持与回归测试。
4. 完成后运行语法与测试验证，并记录剩余风险。

## Phases
### Phase 0: Audit & Design
- [x] 读取 planning-with-files 技能与现有 planning files
- [x] 审查当前 HTML/CSS/JS 与后端转换入口
- [x] 记录本轮 UI/功能变更约束与实现方案
- **Status:** complete

### Phase 1: UI / UX Implementation
- [x] 重排四块面板为统一自适应网格
- [x] 调整表单为紧凑的 inline label/control 布局
- [x] 为 select 增加 hover 说明按钮并更新模式文案
- [x] 删除“命名来源”展示行
- **Status:** complete

### Phase 2: Conversion Retention Logic
- [x] 前端新增“保留 PDF 格式”选项与启用/禁用逻辑
- [x] 后端接收 `keep_pdf` 参数并在不保留时删除 PDF 目录
- [x] 为 API/转换输出保留逻辑补充回归测试
- **Status:** complete

### Phase 3: Verification & Report
- [x] 运行 JS / Python 语法检查
- [x] 运行相关单元测试
- [x] 复查 diff、更新 findings/progress、整理结果
- **Status:** complete

## Key Questions
1. 四个面板如何在保持信息层级的同时实现上下同列宽、左右同行高？
2. “保留 PDF”在 PDF->MOBI 模式下是否只影响输出目录中的 `pdf/` 子目录？
3. 哪些现有测试最适合承接新参数与目录清理行为？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 继续使用 planning-with-files 落盘 | 任务跨 UI、前端状态、后端逻辑与测试多个阶段 |
| 优先做最小范围结构调整 | 用户需求明确，但需避免无关大改 |
| 沿用原生 HTML/CSS/JS | 现有页面无构建系统，不引入新依赖 |
| `keep_pdf` 在 Web API 层默认受 `convert_to_mobi` 约束 | 避免前端以外调用传入不一致状态 |
| PDF 目录删除收敛到 `main.py` 公共 helper | 减少 batch/book/cbz/pdf 四种流程中的重复逻辑 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| 暂无 | - | - |

## Notes
- 本轮任务基于 2026-04-16 已完成的 UI 重构继续迭代，优先满足用户新增交互与布局要求。
- `keep_pdf=false` 时，batch/book/cbz 会在 MOBI 成功生成后删除输出目录中的 `pdf/` 子目录；pdf 模式则删除空的输出 `pdf/` 子目录，只保留 `mobi/`。
- 已完成验证：`node --check static/app.js`、`python3 -m py_compile web_server.py main.py tests/test_web_ui_api.py tests/test_output_retention.py`、`conda run -n comic python -m unittest discover -s tests -p 'test_*.py'`。
