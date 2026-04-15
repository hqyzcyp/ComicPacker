# Task Plan: 输出根目录重构 + PDF→MOBI 模式

## Goal
将“输出目录”重新定义为输出根目录：实际执行转换时，自动在根目录下创建以漫画名命名的文件夹，并在其中创建 `pdf/` 与 `mobi/` 子目录，把生成结果按格式分别落盘；同时新增 `pdf` 转换模式，用于检测目录中的 PDF 文件并批量转换为 MOBI。

## Current Phase
Complete

## Phases
### Phase 0: Context Recovery
- [x] 运行 session catchup：`python3 ~/.codex/skills/planning-with-files/scripts/session-catchup.py "$(pwd)"`
- [x] 读取 `task_plan.md`、`findings.md`、`progress.md`
- [x] 运行 `git diff --stat` / `git status --short` 了解当前工作区状态
- [x] 确认 `omx explore` 在当前环境不可用（缺少 cargo），后续改走普通代码检查路径
- **Status:** complete

### Phase 1: Discovery & Design
- [x] 定位 `main.py`、`web_server.py`、`static/app.js`、`templates/index.html` 中与输出目录、模式检测、任务创建有关的代码
- [x] 确认当前行为：输出文件直接写入 `output`，推荐模式仅支持 `book/cbz/batch`
- [x] 设计统一输出布局 helper 与 `pdf` 模式接入点
- **Status:** complete

### Phase 2: Implementation
- [x] 调整后端输出目录布局：`<output_root>/<漫画名>/pdf` 与 `<output_root>/<漫画名>/mobi`
- [x] 让 `book` / `batch` / `cbz` / `pdf` 模式都遵循统一输出布局
- [x] 新增批量 `PDF -> MOBI` 转换函数与 Web worker 分支
- [x] 更新模式检测、前端模式选项与相关提示文案
- [x] 修正 CLI / README 中与输出目录或模式相关的说明
- **Status:** complete

### Phase 3: Verification
- [x] 运行 `python3 -m py_compile main.py web_server.py`
- [x] 运行 `node --check static/app.js`
- [x] 用 Flask `test_client()` 验证 `/api/detect-mode` 可识别 PDF 模式
- [x] 用真实 CBZ + smoke PDF 验证 `漫画名/pdf`、`漫画名/mobi` 结构以及 PDF→MOBI 落盘结果
- [x] 运行 `conda run -n comic python main.py --help`，确认 CLI 新模式/参数已暴露
- [x] 回写 `task_plan.md`、`findings.md`、`progress.md`
- **Status:** complete

## Key Questions
1. 统一输出目录布局应由哪一层负责，才能覆盖 CLI 与 Web 两条路径？
2. `pdf` 模式是“直接把现有 PDF 批量转成 MOBI”，还是仍受 `convert_to_mobi` 开关控制？
3. 批次模式在启用新布局后，文件名与清理逻辑是否还需要保留旧行为？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 输出参数改为“根目录”语义，最终落盘目录由 `main.py` 的统一 helper 派生 | 这样 CLI/Web 都复用同一规则，不必各自拼接漫画目录 |
| `pdf` 模式直接执行 PDF→MOBI，不依赖额外勾选项决定是否转换 | 模式本身的职责就是生成 MOBI，避免 UI/后端语义冲突 |
| `book/cbz` 在未显式传入漫画名时也会尽量根据文件名/文件夹名推断目录名 | 保证新输出结构默认可用，不强依赖手动输入 |
| 删除 CLI 中“启用 MOBI 后清理 PDF”的旧尾处理 | 新需求要求保留 `pdf/` 与 `mobi/` 两类产物 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `omx explore` 无法运行（缺少 cargo） | 1 | 记录后退回普通 shell / 源码阅读路径 |

## Notes
- `main.py` 现在负责统一创建输出结构；Web 前端只负责收集“输出根目录”。
- 新增 `pdf` 模式后，Web 自动检测 PDF 文件夹并切换到 `PDF 转 MOBI`。
- 验证期间使用了真实 `/mnt` 样本目录与临时目录组合，避免污染仓库输出目录。
