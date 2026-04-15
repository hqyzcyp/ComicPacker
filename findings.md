# Findings & Decisions

## Requirements
- 选择漫画文件夹后，要自动读取该文件夹下的文件并在界面显示第一个文件名，帮助用户确认命名是否需要调整。
- 文件命名存在两种主要模式：`漫画名 Vol.01` 或 `Vol.01`。
- 文件夹名通常采用 `[漫画名][][]` 风格，但实际还可能混入作者、卷区间、状态、来源等信息。
- 输出命名期望统一为 `漫画名 Vol.xx`。
- 转换配置区域需要展示输出名预览，类似 `漫画名 Vol.01`。

## Sample Observations
- `/mnt/data/down/comic/[尖帽子的魔法工坊][白浜鸥][Vol.01-Vol.15][未完][bili]` 下文件名为 `尖帽子的魔法工坊 Vol.01.zip`。
- `/mnt/data/down/comic/[相反的你和我][阿賀沢紅茶][Vol.01-Vol.08]` 下文件名为 `Vol.01.cbz`。
- 文件夹元数据并不总是严格固定顺序，例如 `[甲斐谷忍][欺诈游戏][Vol.01-Vol.19][完结][bili]` 看起来作者在前、作品名在后。

## Technical Findings
- 当前前端在选择文件夹后只会自动切换模式并填充输出目录，不会读取首个漫画文件名，也不会展示输出命名预览。
- `web_server.py:/api/detect-mode` 已扩展为同时返回首个文件、推断漫画名、卷号示例、推荐输出目录和输出名预览。
- `book/cbz` 转换函数现在支持可选 `comic_name` 参数：
  - 若识别到卷号，则输出名统一为 `漫画名 Vol.xx.pdf`
  - 若未识别到卷号，则回退为源文件名（去扩展名）
- 前端新增“漫画输出名”输入框和“输出名预览”展示；用户修改漫画名后，预览与输出目录会同步更新，并会根据当前模式切换为 `漫画名 Vol.xx` 或批次范围示例。

## Implemented Heuristics
1. 按自然排序读取目标目录中的漫画文件（优先 `.zip` / `.cbz`，同时兼容 `.pdf` 作为示例文件）。
2. 展示首个漫画文件名作为“源文件示例”。
3. 自动推断漫画名：
   - 若首个文件名在 `Vol.xx` 前有文本，则优先使用该文本。
   - 若首个文件名只有 `Vol.xx`，则从文件夹 `[]` 片段中排除卷区间/状态/来源等元数据后做最佳努力推断。
4. 自动提取卷号文本（如 `01`），并生成 `漫画名 Vol.01` 形式的预览。
5. 启动任务时把 `comic_name` 一并提交给后端，用于 `book/cbz` 模式的规范输出命名。

## Verification Evidence
- `python3 -m py_compile web_server.py main.py` 通过。
- `node --check static/app.js` 通过。
- 在 `comic` 样本目录上运行 `analyze_comic_folder(...)`：
  - `尖帽子的魔法工坊 Vol.01.zip` -> `尖帽子的魔法工坊 Vol.01`
  - `Vol.01.cbz` + 文件夹 `[相反的你和我][阿賀沢紅茶][Vol.01-Vol.08]` -> `相反的你和我 Vol.01`
- 通过 Flask `test_client()` 调用 `/api/detect-mode`，返回了 `first_file_name`、`comic_name`、`output_preview`、`naming_source` 等新字段，且 `recommended_mode=cbz` 符合样本内容。

## Risks / Edge Cases
- 仅靠文件夹名很难 100% 区分“作者名”和“漫画名”，因此自动推断必须允许用户覆盖。
- 如果文件名完全不含 `Vol`，则规范输出名会回退为原始文件名，前端预览仍以示例形式提示用户。
- 系统 Python 环境未安装 Flask，运行时验证需要使用 conda `comic` 环境。

## Console Output Modal Enhancement
- 当前控制台输出已经通过 `/api/console-output` 每秒轮询刷新，因此新增大窗口时无需改后端。
- 为避免主窗口和弹窗各自维护一套渲染逻辑，前端改为通过统一 `renderConsoleOutputs(...)` 同步更新两个区域。
- 日志文本现在先做 HTML 转义，再写入 DOM，避免日志中若包含 `<` `>` 等字符时被浏览器当作 HTML。
- 弹窗支持三种关闭方式：关闭按钮、点击遮罩空白处、按 `Escape` 键。
- 大窗口使用更高的视口高度和独立滚动区，适合查看长日志。

## Browser Validation Closure
- 用户已明确反馈：弹窗日志功能在真实浏览器中验证成功。
- 因此“按钮可见性 / 弹窗开关 / 日志同步 / 长日志滚动”这一组交互风险已关闭。
- 当前不再需要为交互正确性继续追加结构或样式改动。

## Polling-risk Resolution
- 既然真实浏览器使用已经通过，剩余风险不再是“功能可不可用”，而是“当前轮询实现是否会造成不必要的负担”。
- 对当前需求来说，用户要解决的是“查看正在执行的转换日志”；这不要求 SSE / WebSocket 级别的推送时效。
- 因此本轮采取的是**保留现有轮询架构，但降低其副作用**：
  1. 活跃任务运行中，或弹窗处于打开状态时，保持 1 秒轮询。
  2. 页面可见但没有活跃任务时，退避到 4 秒轮询。
  3. 页面切到后台后，退避到 15 秒轮询。
  4. 如果返回的日志内容没有变化，则跳过重复 DOM 重绘，减少滚动抖动与无意义渲染。
  5. 弹窗关闭后恢复焦点到触发按钮，避免键盘用户丢失上下文。
- 这样可以在不扩大架构复杂度的前提下，把“刷新机制”从开放风险收敛为可接受实现。

## Deferred Follow-up
- 如果未来出现以下任一信号，再单独立项评估 SSE / WebSocket：
  - 需要多客户端同时观察同一转换任务
  - 需要亚秒级刷新频率
  - 需要更长日志历史或服务端主动推送事件模型
- 在这些需求出现前，当前自适应轮询方案已经足够覆盖本项目现有场景。

## MOBI Output Missing Investigation (2026-04-15)
- 实际文件系统检查显示：`output/相反的你和我/` 里只有 `Vol.01` 到 `Vol.08` 的 PDF，没有任何 `.mobi` 或 `.epub`。
- `main.py` 在三处调用 `convert_pdf_to_mobi(...)` 后，都会立刻根据“返回的预期路径”打印 `✓ MOBI已创建`，但该函数并未检查文件是否真实存在。
- `convert_pdf_to_mobi(...)` 实际上是异步启动 `multiprocessing.Process`，函数本身只返回 `expected_mobi_path`，并不会等待 KCC 完成，因此 `✓ MOBI已创建` 当前语义是“已提交转换任务”，不是“文件已经落盘”。
- Web worker 在 `web_server.py` 中执行完 `pack_*` / `convert_cbz_to_pdf(...)` 后，立即将 job 标记为 `completed successfully`，没有等待 `main.conversion_processes` 里的 MOBI 子进程结束。
- Web worker 还会把 `sys.stdout` 重定向到 `ConsoleCapture`；而 MOBI 转换是单独的 `multiprocessing.Process`。这导致子进程里的失败日志不会可靠进入当前 job 的前端日志流，因此用户只看到了父线程的“已创建/已完成”。
- 当前运行中的 Web 进程使用的是 conda `comic` 环境，但其 `PATH` 不包含项目根目录；仓库根下虽有 `./kindlegen`，却既不在 `PATH` 中，也没有执行权限（当前权限 `-rw-r--r--`）。
- 在该环境下直接运行 KCC CLI 会稳定报错：`ERROR: KindleGen is missing!`。
- 用项目自己的 `convert_pdf_to_mobi(...)` 复现时，函数返回 `output/相反的你和我/相反的你和我 Vol.02.mobi`，但 `join()` 后该文件依旧不存在，并打印 `✗ MOBI转换失败 ... (退出码: 1)`。

### Root Cause Summary
1. **真实转换失败**：KCC 找不到可执行的 `kindlegen`，所以根本没有生成 `.mobi`。
2. **状态与日志误报成功**：主线程把“预期路径”当成“创建成功”，worker 也没有等待 MOBI 子进程完成。
3. **失败细节对前端不可见**：MOBI 在独立进程里跑，失败日志没有可靠汇入当前 job 的控制台输出。

### Likely Fix Directions
- 把 `kindlegen` 设为可执行并确保它出现在 Web 进程/子进程的 `PATH` 中，或改为代码里显式传递绝对路径。
- `convert_pdf_to_mobi(...)` 不要在未验证文件存在前返回“成功”；至少应区分“已启动转换”和“转换完成”。
- Web worker 在标记 job 完成前，应等待并检查所有 MOBI 子进程结果。
- 失败时打印/回传 `stdout` 与 `stderr`，不要只看 `stderr`。

## MOBI Fix Implementation (2026-04-15)
- `main.py` 已改为**同步执行** KCC 转换，不再先返回“预期路径”后异步慢慢跑。
- KCC 现在使用 `sys.executable` 调本地 `kcc-c2e.py`，确保 Web 进程在 conda `comic` 环境下启动时，KCC 也复用同一 Python 解释器与依赖集。
- KCC 子进程环境现在会自动：
  - 将项目根目录加入 `PYTHONPATH`
  - 将项目根目录加入 `PATH`
  - 若仓库根目录存在 `./kindlegen`，则自动补执行权限
- 在真正检测到 `.mobi` 文件落盘前，`convert_pdf_to_mobi(...)` 不会返回成功路径。
- 若 KCC 返回码非 0 或未检测到 `.mobi` 输出文件，会打印 KCC 输出尾部关键日志，并返回失败。
- 三个 MOBI 调用点（book / batch / cbz）现在在失败时直接抛出异常，因此 Web worker 不会再把缺失 MOBI 的任务标记为 `completed successfully`。
- 仓库内 `kindlegen` 当前已具备执行权限；后续在运行时若权限丢失，代码也会再次尝试修复。

## Verification Evidence: MOBI Fix
- 语法检查：`python3 -m py_compile main.py web_server.py` 通过。
- Smoke test：在 `output/__mobi_smoketest__/smoke.pdf` 上调用 `main.convert_pdf_to_mobi(...)`，成功生成 `smoke.mobi`。
- 真实数据回填：对 `output/相反的你和我/*.pdf` 顺序执行修复后的 `main.convert_pdf_to_mobi(...)`，8/8 成功生成 `.mobi`。
- 最终落盘核对：`output/相反的你和我/` 现已同时存在 `Vol.01` 到 `Vol.08` 的 `.pdf` 与 `.mobi`。
