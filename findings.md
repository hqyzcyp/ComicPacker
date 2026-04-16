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

## Web Status Tightening + README Follow-up (2026-04-15)
- `web_server.py` 的 worker 完成日志已收紧为 “completed successfully with verified outputs”，避免继续沿用含糊的成功语义。
- Worker 在完成时会确保 job.progress 至少拥有明确的 `completed` 阶段、100% 进度和“任务已完成，输出文件已写入目标目录”消息。
- Worker 失败分支移除了 `jobs_lock` 内部再次调用 `tracker.update(...)` 的锁重入风险，避免失败时潜在死锁。
- `static/app.js` 现在会在非运行态任务卡片上显示最终消息，因此 `completed` / `failed` / `cancelled` 不再只有标签，没有结果说明。
- `README.md` 已补充：若使用项目根目录自带的 `./kindlegen`，Linux 下需先执行 `chmod +x ./kindlegen`；同时注明 Web 模式会尝试自动修复权限。

## Verification Evidence: Status + Docs Follow-up
- `python3 -m py_compile main.py web_server.py` 通过。
- `node --check static/app.js` 通过。
- 再次运行 MOBI smoke test：`output/__mobi_smoketest__/smoke-status-docs.pdf` 成功生成 `smoke-status-docs.mobi`。

## Web config.toml + /mnt sandbox + download feature (2026-04-15)
- Web 现在改为使用项目根目录 `config.toml` 保存默认漫画目录和默认输出目录，不再依赖浏览器 `localStorage`。
- `config.toml` 当前使用最小 TOML 结构：
  - `comic_folder = "..."`
  - `output_folder = "..."`
- Web 启动或读取配置时会自动规范化配置：
  - 漫画目录必须位于 `/mnt/` 下且存在
  - 输出目录必须位于 `/mnt/` 下；若不存在会自动创建
  - 若配置非法，则回退到 `/mnt/data/down/comic`（存在时）或 `/mnt`
- 点击前端“📌 设为默认路径”后，后端会：
  1. 把当前浏览路径写入 `comic_folder`
  2. 把 `output_folder` 同步为“漫画目录上一级目录下的 `comic_output`”
  3. 自动创建该输出目录
- 文件浏览器与下载接口都已收紧到 `/mnt/` 沙箱内：
  - `/api/browse` 仅允许浏览 `/mnt/` 下路径
  - `/api/detect-mode` / `/api/jobs` / `/api/download` 也会拒绝 `/mnt/` 外路径
- 文件浏览器现在会为可下载文件显示“⬇️ 下载”按钮，支持扩展名：`.zip/.cbz/.pdf/.mobi/.epub`
- 前端输出目录输入框现在优先跟随配置文件里的 `output_folder`，不再使用浏览器本地默认路径。

## Verification Evidence: config + sandbox + download
- `python3 -m py_compile web_server.py main.py` 通过。
- `node --check static/app.js` 通过。
- Flask `test_client()` 验证：
  - `GET /api/config` 返回 `comic_folder=/mnt/data/down/comic`、`output_folder=/mnt/data/down/comic_output`
  - `POST /api/browse` 访问 `/mnt/data/down/comic` 返回 200
  - `POST /api/browse` 访问 `/root` 返回 403，错误为“只允许访问 /mnt/ 下的文件”
  - `POST /api/config/default-path` 返回 200，且 `/mnt/data/down/comic_output` 已确认存在
  - `GET /api/download` 对真实 ZIP 文件返回 200，并带有 `Content-Disposition: attachment`

## Default-path save error follow-up (2026-04-15)
- 用户看到的 `Unexpected token '<', "<!doctype ..." is not valid JSON` 并不是配置写入逻辑本身失败，而是前端拿到了 HTML 错误页后仍按 JSON 解析。
- 排查时发现运行中的 `python web_server.py` 进程启动于 14:51 之前的旧代码版本；在旧进程未重启时，浏览器已加载到新的 `static/app.js`，但后端尚未注册 `/api/config/default-path`，因此会返回 HTML 404/错误页。
- 现在前端新增了 `readApiPayload(response)`：即使后端返回 HTML 或其他非 JSON 响应，也会转成可读错误信息，例如“服务端返回了 HTML（HTTP xxx），可能需要重启 Web 服务”。
- 同时已重启 Web 服务进程，使新的 `/api/config` 与 `/api/config/default-path` 路由真正生效。

## Output-root restructure + PDF mode (2026-04-15)
- 当前 `main.py` 的 `book` / `batch` / `cbz` 三个入口都把 `output_folder` 当作最终落盘目录，PDF 与 MOBI 会直接混写在同一级目录。
- Web 前端的“输出目录”当前已经更接近“根目录”输入：`config.toml` 保存的是统一输出目录，`create_job()` 也把该路径直接发给后端；因此真正需要调整的是后端落盘语义，而不是再让前端继续拼 `漫画名` 子目录。
- CLI 末尾仍保留“启用 MOBI 后删除输出目录下所有 PDF”的旧逻辑；这与新需求“保留 `pdf/` 与 `mobi/` 子目录”冲突，后续需要移除或重写。
- `detect_mode()` 目前只统计 `zip/cbz`，虽然 `analyze_comic_folder()` 已把 `.pdf` 纳入漫画文件样本，但不会推荐 `pdf` 模式。
- 现有单文件 `convert_pdf_to_mobi(...)` 已具备：
  1. KCC / kindlegen 环境准备
  2. 真实 `.mobi` 落盘校验
  3. 失败日志输出
  因此新增 `pdf` 模式时，重点在“批量扫描 + 目标目录布局 + 进度回调”。
- 当前 Web UI 下拉框没有 `pdf` 模式，且“转换为 MOBI 格式”复选框默认选中；若新增 `pdf` 模式，界面语义需要避免出现“已经是 PDF→MOBI 模式，但还要再勾一次 MOBI”的重复表达。

## Output-root restructure implementation (2026-04-15)
- `main.py` 新增统一输出布局 helper：给定输出根目录、漫画名/推断名后，统一创建：
  - `<output_root>/<漫画名>/pdf`
  - `<output_root>/<漫画名>/mobi`
- `book` / `batch` / `cbz` 三种模式现在都把 PDF 写入 `pdf/` 子目录；若启用 MOBI，则输出到 `mobi/` 子目录。
- `batch` 模式现在也会把推断出的漫画名用于默认前缀，避免只在目录层有漫画名、文件名却完全缺少标题。
- CLI 新增 `--comic-name` 参数；当显式传入时，它同时参与：
  1. 漫画目录名
  2. `book/cbz` 的规范卷名输出
  3. `batch` 的默认前缀（若未手填 `--prefix`）
- CLI 删除了旧的“启用 MOBI 后删除输出目录下所有 PDF”尾处理，因为新需求要求同时保留 `pdf/` 与 `mobi/` 产物。

## PDF mode implementation (2026-04-15)
- `main.py` 新增 `convert_pdf_folder_to_mobi(...)`：
  - 扫描目录内 `.pdf`
  - 使用现有 `convert_pdf_to_mobi(...)` 逐个转换
  - 通过 `progress_callback` 回传扫描/处理/完成阶段
  - 输出到 `<output_root>/<漫画名>/mobi`
- `web_server.py`：
  - worker 新增 `pdf` 分支
  - `/api/detect-mode` 新增 `pdf_count` 统计与 `recommended_mode='pdf'`
  - `create_job()` 在 `mode=pdf` 时强制 `convert_to_mobi=True`
- `templates/index.html` / `static/app.js`：
  - 模式下拉新增 `PDF 转 MOBI`
  - `pdf` 模式下隐藏“转换为 MOBI”复选框（因为模式自身已经隐含该语义）
  - 预览文本与帮助文案会显示新的输出结构：`输出根目录/漫画名/pdf|mobi`
  - 自动检测到 PDF 文件夹时会切换到 `pdf` 模式并弹出提示

## Verification Evidence: output-root + PDF mode
- `python3 -m py_compile main.py web_server.py` 通过。
- `node --check static/app.js` 通过。
- `conda run -n comic python main.py --help` 已显示：
  - `--comic-name`
  - `--mode {batch,book,cbz,pdf}`
  - 更新后的输出根目录帮助文案
- Flask `test_client()` 调用 `/api/detect-mode`：
  - 输入：`/mnt/data/down/comic/[想结束这场“我爱你”的游戏][堂本裕貴][Vol.01-Vol.06][长鸿][电子版][PDF]`
  - 返回：`recommended_mode=pdf`，`pdf_count=6`
- 真实 CBZ 样本验证：
  - 输入：复制 `Vol.01.cbz` 到临时目录
  - 调用：`main.convert_cbz_to_pdf(..., convert_to_mobi=True, comic_name='相反的你和我')`
  - 结果：生成
    - `.../相反的你和我/pdf/相反的你和我 Vol.01.pdf`
    - `.../相反的你和我/mobi/相反的你和我 Vol.01.mobi`
- PDF 模式 smoke test：
  - 输入：临时目录中的 `测试漫画 Vol.01.pdf`
  - 调用：`main.convert_pdf_folder_to_mobi(..., comic_name='测试漫画')`
  - 结果：生成 `.../测试漫画/mobi/测试漫画 Vol.01.mobi`，同时 `.../测试漫画/pdf/` 目录已创建

## Remaining Risks / Follow-up
- `book` / `cbz` 在 CLI 未显式传入 `--comic-name` 时依赖“首个文件名/文件夹名推断”；对于极端命名样本仍可能需要用户手动覆盖。
- `pdf` 模式目前只扫描所选目录的一级 PDF 文件，不做递归子目录遍历；这是当前行为，不是 bug。

## Performance Investigation Kickoff (2026-04-15)
- 当前仓库已有历史 planning 记录，但本轮任务已切换为“在线分析漫画转换性能瓶颈”。
- 运行时采样显示当前最高相关负载进程是 `python web_server.py`（PID 526516），累计 CPU 约 39%，已运行约 8 分钟。
- 目前尚未看到独立的 `kindlegen` / `kcc` 子进程出现在进程列表顶部，说明热点很可能仍在 Python 进程内部或其线程中。

## Runtime Profiling Findings: 漫画转换性能（2026-04-15）
- 运行中的核心转换进程是 `python web_server.py`（PID 526516）。
- `/proc/526516/task` 显示该进程在采样时有 2 个线程，其中 `TID 526517` 为 `R (running)`，主线程 `TID 526516` 为 `S (sleeping)`，说明真正跑转换的是后台 worker 线程。
- `pidstat -durh -p 526516 1 3` 在 15:19:45~15:19:47 连续 3 秒显示：
  - `%usr=100`、`%system=0`、`%wait=0`
  - `kB_rd/s=0`、`kB_wr/s=0`
  这说明瓶颈是**纯用户态 CPU 计算**，不是磁盘 I/O 或系统调用等待。
- 同期系统级 `vmstat` / `iostat` 显示：
  - 全机 12 核大部分空闲（idle ~90%）
  - iowait 接近 0
  - NVMe util 很低
  说明当前任务只吃满**单核**，机器总体算力没有被利用。
- 进程 RSS 约 1.18~1.29 GiB，但宿主机可用内存充足（available ~26 GiB），当前不是内存不足或 swap 导致的慢。
- 真实输出时间线（`/mnt/data/down/comic_output/尖帽子的魔法工坊`）显示：
  - `Vol.04.pdf` 完成于 15:19:20，`Vol.04.mobi` 完成于 15:19:32（MOBI 阶段约 13s）
  - `Vol.05.pdf` 完成于 15:20:28，距上一个 MOBI 完成约 56s（PDF 阶段约 56s）
  - `Vol.05.mobi` 完成于 15:20:42（MOBI 阶段约 14s）
  - `Vol.06.pdf` 完成于 15:21:30，距上一个 MOBI 完成约 48s（PDF 阶段约 48s）
  - `Vol.06.mobi` 完成于 15:21:43（MOBI 阶段约 13s）
- 由以上样本可估算：**每卷约 66s，其中 PDF 生成约 48~56s，占总耗时约 75%~80%；PDF→MOBI 仅约 13~14s，占 20% 左右。**

## Code Path Findings: 根因映射
- `web_server.py` 只有一个后台 `worker_thread()` 消费 `job_queue`，单任务执行路径串行，天然只能由一个 worker 线程推进。
- `main.py` 中 `get_images_from_zip()` / `get_chapters_from_zip()` 会先把 ZIP/CBZ 内所有图片**整批读入内存**。
- `pack_comics_by_book()` / `convert_cbz_to_pdf()` 会把整卷图片收集到 `all_images`，然后调用 `preprocess_images()` 进行**全量预处理**。
- `preprocess_images()` 当前实现是**顺序 for-loop**，没有实际使用多进程/多线程；而 `preprocess_image()` 对每张图会：
  1. `Image.open(...)` 解码
  2. 可能 `resize(..., Image.LANCZOS)`
  3. `convert('RGB')`
  4. `img.save(..., format='JPEG', quality=95, optimize=True)` 重新编码
- 预处理完成后，组装 PDF 时又会对 `img_info['data']` 再次创建 `ImageReader(io.BytesIO(...))` 交给 ReportLab 绘制，形成**解码 → 重采样/编码 → 再解码**的重复 CPU 开销。
- 因为先收集整卷、再整卷预处理、再整卷写 PDF，所以不仅串行，而且会把大量图片字节和预处理结果同时留在内存里，造成 1GiB+ RSS。
- 代码注释写着“在独立进程中执行”，但实际 `preprocess_images()` 并没有进程池，这是一个明显的“设计意图与当前实现不一致”信号。

## Bottleneck Summary
1. **主瓶颈：PDF 生成阶段的单线程图片预处理与重复编解码。**
2. **次瓶颈：单 worker / 单任务串行流程，无法利用 12 核机器。**
3. **次要问题：整卷全量加载到内存，增加内存占用并恶化缓存/GC 行为。**
4. **不是主要瓶颈：磁盘 I/O、系统调用等待、MOBI 转换阶段。**

## Performance Optimization Design: 第一阶段实现选择（2026-04-15）
- 为继续上一轮性能调查，本轮先回看 `main.py` 热点实现，范围限定在 `preprocess_image()` / `preprocess_images()`。
- 真实样本格式抽样：
  - `/mnt/data/down/comic/[相反的你和我].../Vol.01.cbz` 前 40 张均为 `RGB` + `.jpeg`
  - 这 40 张样本按当前阈值判断 `needs_resize = 0`
  - 说明“已经是可直接用于 PDF 的 JPEG 页面”在真实输入中占比很高，避免重复 JPEG 重编码有现实收益。
- 小型微基准（使用 `conda run -n comic python`，样本为 `Vol.01.cbz` 前 40 张）：
  - 串行 `preprocess_image`：约 `1.445s`
  - `ThreadPoolExecutor(max_workers=4)`：约 `0.870s`（~`1.66x`）
  - `ProcessPoolExecutor(max_workers=4)`：24 张样本约 `0.257s`，显示出比线程更强的潜在加速空间
- 由此决定本轮首选方案：
  1. 在**无需缩放、无需颜色模式转换**时直接复用原始 JPEG 字节，跳过 `img.save(... optimize=True)`
  2. 为 `preprocess_images()` 增加**有界并行预处理**，优先使用多进程来利用空闲 CPU 核心
  3. 保持返回顺序、返回结构和上层调用方式不变，尽量把变更限制在热点函数内部
- 顺手发现的同区域运行时缺口：`pack_comics_to_pdf()` 内打印和文件名前缀使用了未定义变量 `effective_prefix`，这是一个潜在运行时 `NameError`，若改动波及该段逻辑可一并收敛。

## Performance Optimization Implementation: 第一阶段结果（2026-04-15）
- `main.py` 新增三个 helper：
  - `calculate_page_dimensions(...)`：统一计算页面适配尺寸
  - `get_preprocess_worker_count(...)`：统一计算预处理并行度，支持 `COMICPACKER_PREPROCESS_WORKERS`
  - `should_parallelize_preprocess(...)`：通过抽样元数据判断当前卷是否值得开多进程
- `preprocess_image(...)` 现在新增 **RGB JPEG 直通 fast path**：
  - 若页面无需缩放、原始格式就是 JPEG、颜色模式已是 RGB，则直接复用原始字节
  - 跳过原先 `img.save(... format='JPEG', quality=95, optimize=True)` 的重复 JPEG 编码
- `preprocess_images(...)` 现在支持 **有界多进程预处理**：
  - 默认自动选取最多 4 个进程
  - 但只在抽样判断“存在足够多需要缩放/转码的页面”时才启用
  - 若并行执行异常，会自动回退到串行路径，不影响功能可用性
- 同路径顺手修复：`pack_comics_to_pdf()` 中恢复 `effective_prefix` 定义，避免批次模式在有 ZIP 输入时触发运行时 `NameError`。

## Verification Evidence: performance optimization phase 1
- 语法/回归：
  - `python3 -m py_compile main.py web_server.py tests/test_preprocess.py` 通过
  - `conda run -n comic python -m unittest discover -s tests -p 'test_*.py'` 通过（4 个测试）
- 新增回归测试覆盖：
  1. 无需缩放的 RGB JPEG 会走直通 fast path
  2. RGBA PNG 会被正确压平成 RGB JPEG
  3. `COMICPACKER_PREPROCESS_WORKERS` 会被正确读取并受图片数限制
  4. 并行预处理后仍保持输入顺序不变
- 合成 smoke test：
  - 使用临时目录构造一个 ZIP 和一个 CBZ 样本
  - `pack_comics_to_pdf(...)` 成功生成 `zip_input/pdf/测试漫画_CH-001_to_CH-001.pdf`
  - `convert_cbz_to_pdf(...)` 成功生成 `测试漫画/pdf/测试漫画 Vol.01.pdf`
- 真实样本预处理基准（前 40 页）：
  - `fast_jpeg_cbz`：`Vol.01.cbz`
    - `workers=1`：约 `0.010s`
    - `workers=4`：约 `0.003s`
    - 由于启发式判断为 fast-path 卷，4 workers 下也不会错误开启多进程，说明 fast path 已把该类页面成本压到很低
  - `resize_heavy_zip`：`尖帽子的魔法工坊 Vol.04.zip`
    - `workers=1`：约 `4.541s`
    - `workers=4`：约 `1.226s`
    - 同样 40 页样本下约 **3.7x** 加速，证明“需要缩放的卷”会明显受益于并行化

## Remaining Risks / Follow-up: performance optimization
- 当前并行启发式基于前 12 张图片抽样，是经验型策略；若后续遇到“前几页轻、后面很重”的极端卷，可能仍需再调参。
- 现有实现仍保持“先整卷收集，再批量预处理，再统一写 PDF”的总体结构，因此大卷内存占用问题只部分缓解，尚未根治。
- `web_server.py` 仍是单 worker 串行消费任务；本轮优化提升的是**单任务处理速度**，不是多任务吞吐。

## Performance Optimization Design: 第二阶段基线与方案（2026-04-15）
- 真实整卷基线（第一阶段代码上测得）：
  - `pack_comics_by_book()` 对 `尖帽子的魔法工坊 Vol.04.zip`
    - wall time: 约 `50.38s`
    - `Maximum resident set size`: `1223900 kB`
  - `convert_cbz_to_pdf()` 对 `Vol.01.cbz`
    - wall time: 约 `59.29s`
    - `Maximum resident set size`: `1145536 kB`
- 这表明在第一阶段优化后，**整卷级的图片持有与预处理结果持有**仍然把峰值 RSS 推到约 `1.1~1.2 GiB`。
- 剩余结构性问题来自：
  1. `get_chapters_from_zip()` / `get_images_from_zip()` 直接把整包图片读成字节列表
  2. `pack_comics_by_book()` / `convert_cbz_to_pdf()` 先把整卷所有页面收集进 `all_images`
  3. 再一次性 `preprocess_images(all_images, ...)`
  4. 最后才统一写 PDF
- 第二阶段方案：
  - 新增“ZIP 内图片条目元数据”层，先只拿排序后的条目清单，不急着读图片字节
  - 读取范围缩小到“当前章节”或“当前 ZIP 文件”
  - 当前批次预处理完成后立即写入 PDF，再释放对应列表
  - 保持对外 CLI / Web API、输出文件名、页顺序和现有调用方式不变
- 预期收益：
  - 峰值 RSS 从“整卷级”下降到“单章节级/单包级”
  - 对大卷更友好，也给后续真正流式/迭代式处理打基础
  - 总耗时理论上也有机会下降，因为更少的大列表拼接和内存压力会改善缓存/GC 行为

## Performance Optimization Implementation: 第二阶段结果（2026-04-15）
- 新增 ZIP/CBZ 图片条目元数据层：
  - `list_image_entries(...)`
  - `get_image_entries_from_zip(...)`
  - `group_image_entries_by_chapter(...)`
  - `get_chapter_entries_from_zip(...)`
  - `read_images_from_zip(...)`
  - `read_single_image_from_zip(...)`
- 这些 helper 先拿“排序后的图片条目”，延迟到真正需要处理当前章节/当前 chunk 时才读图片字节。
- `main.py` 新增 `draw_preprocessed_image(...)`，统一预处理后图片写 PDF 的逻辑，避免三条路径重复拼装页面代码。
- `create_pdf_from_chapters()` 现在改为：
  - 对每个 ZIP 逐个读取条目
  - 当前 ZIP 的图片读入并预处理后立即写 PDF
  - 不再把整个 batch 的所有图片攒进 `all_images`
- `pack_comics_by_book()` 现在改为：
  - 先按章节拿条目元数据
  - 每个章节单独读取/预处理/写入 PDF
  - 不再把整本书的所有章节图片与预处理结果同时留在内存中
- `convert_cbz_to_pdf()` 现在改为：
  - 封面只单独读取第一张图
  - 其余页面按章节或默认章节增量读取并写入 PDF
  - 对无章节结构的大 CBZ，也会继续按 **32 页默认分块** 处理，避免重新退化成整卷级内存占用
- 新增 `get_preprocess_chunk_size(...)`，支持环境变量 `COMICPACKER_PREPROCESS_CHUNK_SIZE` 覆盖分块大小。

## Verification Evidence: performance optimization phase 2
- 语法/回归：
  - `python3 -m py_compile main.py web_server.py tests/test_preprocess.py tests/test_pdf_workflows.py` 通过
  - `conda run -n comic python -m unittest discover -s tests -p 'test_*.py'` 通过（8 个测试）
- 新增端到端 PDF 工作流回归：
  1. `batch` 模式：1 个 ZIP / 3 张图 => 输出 PDF `Pages = 3`
  2. `book` 模式：2 个章节 / 共 4 张图 => 输出 PDF `Pages = 4`
  3. `cbz` 模式：2 个章节 / 共 4 张图 => 输出 PDF `Pages = 4`
- 真实样本基准（第二阶段后）：
  - `pack_comics_by_book()` 对 `尖帽子的魔法工坊 Vol.04.zip`
    - wall time: `50.38s -> 44.44s`（约 **11.8%** 改善）
    - peak RSS: `1223900 kB -> 718336 kB`（约 **41.3%** 降低）
  - `convert_cbz_to_pdf()` 对 `Vol.01.cbz`
    - wall time: `59.29s -> 52.84s`（约 **10.9%** 改善）
    - peak RSS: `1145536 kB -> 869624 kB`（约 **24.1%** 降低）
- 结论：第二阶段不仅明显降低了内存峰值，也在真实整卷上带来了双位数的总耗时下降。

## Remaining Risks / Follow-up: performance optimization phase 2
- 当前分块处理会多次打开同一个 ZIP/CBZ；虽然总收益仍为正，但后续仍可考虑复用单个已打开的 `ZipFile` 句柄。
- 多进程预处理仍是“每次 `preprocess_images()` 调用建一个进程池”；若想进一步提速，可探索在整卷范围内复用持久 worker 池。
- ReportLab 侧仍会对传入图片再做解码；若继续追求更高性能，后续需要调查是否能减少这部分重复工作。
- `web_server.py` 依旧是单 worker 模型；本轮继续提升的是单任务性能，不是并发任务吞吐。

## Resume Verification Pass (2026-04-15)
- 在恢复会话后重新读取 `task_plan.md` / `findings.md` / `progress.md`，确认当前任务仍是“漫画转换性能优化（第二阶段）”且计划状态为 `Complete`。
- 重新执行本地验证：
  - `python3 -m py_compile main.py web_server.py tests/test_preprocess.py tests/test_pdf_workflows.py` 通过
  - `conda run -n comic python -m unittest discover -s tests -p 'test_*.py'` 通过（8 个测试）
- 结论：当前工作区中的第二阶段实现与规划文件一致，恢复会话后未发现验证漂移或新增失败。

## Web Multi-worker Upgrade Discovery (2026-04-15)
- `web_server.py` 当前的后台执行模型是：
  1. 全局 `job_queue = queue.Queue()`
  2. 单个 `worker_thread()` 无限循环消费
  3. 模块加载时只启动一个线程：`worker = threading.Thread(...); worker.start()`
- 因此现在即使前端一次创建多个任务，也只会按 FIFO 串行处理，`pending` 任务必须等待唯一 worker 空出来。
- 并发升级的主要技术风险不只是“多开几个线程”，还包括：
  1. `worker_thread()` 内部直接替换全局 `sys.stdout`
  2. `ConsoleCapture` 只写入全局 `console_output`
  3. `cancelled_jobs` 是共享集合，但读写路径没有统一封装
- 在单 worker 模型下，上述问题基本不暴露；一旦并发执行，最容易出现：
  - 日志串台 / 抢占 `sys.stdout`
  - 某个 job 的输出被另一个 job 截走
  - pending/running 取消检查与状态切换时序变脏
- 现有前端契约相对简单：它只依赖 `/api/jobs` 返回任务状态列表，以及 `/api/console-output` 返回“最近控制台输出”；因此后端有空间在不改协议的前提下完成 worker pool 升级。
- 适合本轮的最小可行改造方向：
  - 保留 `job_queue`
  - 把单个后台线程升级为固定数量的后台线程池
  - 引入线程本地的输出路由，而不是在 worker 内直接覆盖整个进程的 `sys.stdout`
  - 通过环境变量控制 worker 数，默认值保持保守

## Web Multi-worker Upgrade Implementation (2026-04-15)
- `web_server.py` 现在新增了可配置 worker pool：
  - `get_web_worker_count()`
  - `start_worker_pool(...)`
  - `shutdown_worker_pool(...)`
  - `process_job(...)`
- 模块启动后不再只保留单个 `worker` 线程对象，而是按配置启动多个后台线程，共享原有 `job_queue`。
- 默认 worker 数为 `max(1, min(2, os.cpu_count() or 1))`，可通过环境变量 `COMICPACKER_WEB_WORKERS` 覆盖。
- 为了避免并发任务互相覆盖输出，`sys.stdout` / `sys.stderr` 改为一次性替换成 `JobScopedOutput`：
  - 非 job 线程：直接透传到原始 stdout/stderr
  - job 线程：根据线程本地 `job_id` 把日志路由到 Web 控制台缓冲
- worker 执行任务时通过 `bind_job_console(job_id)` 绑定当前线程的输出归属，因此两个并行任务的转换日志都会自动带上各自的 job 前缀。
- `jobs_lock` 改为 `threading.RLock()`，并把取消检查统一收敛到 helper 中，降低多线程状态切换时的竞态风险。
- job 元数据新增 `worker` 字段，便于观察某个任务最终由哪个后台 worker 执行。
- `create_job()` 现在在入队前调用 `start_worker_pool()`，避免 worker pool 被显式停掉后再创建任务时无人消费。
- `/api/system-stats` 额外返回：
  - `configured_web_workers`
  - `running_jobs`
  - `pending_jobs`
- `tests/test_web_workers.py` 新增 3 个回归测试，覆盖：
  1. 两个任务可并行进入 `running`
  2. 单 worker 忙碌时，后续 pending 任务仍可取消
  3. 并发日志带有各自 job 前缀，不会串台

## Verification Evidence: Web Multi-worker Upgrade
- 语法检查：
  - `python3 -m py_compile main.py web_server.py tests/test_preprocess.py tests/test_pdf_workflows.py tests/test_web_workers.py` 通过
- 全量测试：
  - `conda run -n comic python -m unittest discover -s tests -p 'test_*.py'` 通过（11 个测试）
- 新增并发行为验证：
  1. `test_jobs_can_run_in_parallel_with_multiple_workers`
     - 结果：两个 job 可同时进入 `running`
     - 且 `job['worker']` 显示为不同 worker
  2. `test_pending_job_can_be_cancelled_while_another_worker_is_busy`
     - 结果：当唯一 worker 忙碌时，第二个 pending job 可在启动前被取消
  3. `test_console_output_keeps_job_prefixes_under_parallel_execution`
     - 结果：并发输出带有对应 job 前缀，未出现交叉归属

## Remaining Risks / Follow-up: Web Multi-worker Upgrade
- 单个漫画转换任务本身已经会做图片预处理并行化；若同时跑多个大任务，CPU / 内存峰值可能上升，需要按机器规模调节 `COMICPACKER_WEB_WORKERS`。
- `/api/console-output` 仍是“全局最近 N 行”视图；虽然现在有 job 前缀，不会串归属，但高并发时它依旧是聚合视图，不是 per-job 独立日志窗口。
- 当前 worker pool 生命周期在单进程 Flask 进程内；如果未来切到多进程 WSGI/反向代理部署，需要重新审视“每个进程各自一套后台线程池”的行为。

## CPU 利用率与单 Job 并行调研（2026-04-15）
- `web_server.py` 当前 Web 层并行仅存在于 job 级：`job_queue` + `worker_threads`；默认 worker 数来自 `get_web_worker_count()`，默认值是 `min(2, os.cpu_count())`，环境变量 `COMICPACKER_WEB_WORKERS` 可覆盖。
- `main.py` 当前真正的 CPU 并行主要发生在 `preprocess_images(...)`，其内部用 `ProcessPoolExecutor` 对单批图片预处理并行；默认 `COMICPACKER_PREPROCESS_WORKERS` 未设置时取 `min(os.cpu_count(), 4, image_count)`。
- 因此现在的并发模型是“两层”：
  1. Web 层：多个 job 可并发；
  2. 单个 job 内：仅图片预处理块可并行，漫画文件（ZIP/CBZ/PDF）之间仍是串行 `for` 循环。
- 已确认单 job 内多本漫画确实是串行：
  - `pack_comics_by_book(...)`：按 `for book_idx, zip_file in enumerate(zip_files, 1)` 逐本处理 ZIP。
  - `convert_cbz_to_pdf(...)`：按 `for idx, cbz_file in enumerate(cbz_files, 1)` 逐本处理 CBZ。
  - `convert_pdf_folder_to_mobi(...)`：按 `for idx, pdf_file in enumerate(pdf_files, 1)` 逐本处理 PDF。
  - `pack_comics_to_pdf(...)` 是按批次串行，但每个批次本身就把多本 ZIP 合并到同一个 PDF，所以不适合同样的“逐本并行”思路。
- 样本数据规模较大：当前 `comic` 下可见 5 个漫画目录，其中 CBZ/ZIP 目录常见每卷 180~230 页，单张图像均值约 0.9MB~2.7MB；这说明任何外层并行都会明显放大内存、磁盘读取与 PDF 写入压力。


## CPU 利用率基线与外层并行原型结果（2026-04-15）
- **代表性样本（CBZ，小图快路径）**：`[相反的你和我][阿賀沢紅茶][Vol.01-Vol.08]`。单卷 smoke test：`Vol.01.cbz -> PDF` 用时 **58.37s**，最大 RSS **878MB**。日志显示每个 32 页块都走 `预处理 32 张图片...`（**没有** `并行进程: 4`），说明 `should_parallelize_preprocess(...)` 对该数据判定为串行。
- **代表性样本（ZIP，大图需缩放）**：`[尖帽子的魔法工坊] Vol.01.zip -> PDF` 用时 **47.81s**，最大 RSS **803MB**。日志显示多数块都走 `预处理 32 张图片... (并行进程: 4)`，说明 book/ZIP 场景里单卷内部已经能吃到图片预处理并行。
- **并行判定探针结果**：
  - `相反的你和我 Vol.01.cbz`：`use_parallel=False`
  - `欺诈游戏 Vol.01.cbz`：`use_parallel=False`
  - `尖帽子的魔法工坊 Vol.01.zip`：`use_parallel=True`
  - `金牌得主 Vol.01.zip`：`use_parallel=True`
- **CBZ 外层按卷并行原型（3 卷）**：对 `Vol.01~03.cbz` 做真实原型测量：
  - 当前串行：**176.39s**，平均 **1.01 cores**，峰值 **1.04 cores**，峰值 RSS **932.9MB**
  - 外层并行 2：**104.54s**，平均 **1.68 cores**，峰值 **2.05 cores**，峰值 RSS **2760.8MB**
  - 外层并行 3：**62.97s**，平均 **2.51 cores**，峰值 **3.06 cores**，峰值 RSS **3679.0MB**
- **推论**：
  1. 对当前 CBZ 样本，瓶颈主要不是 Web worker 数，而是“**单 job 内逐卷串行 + 单卷内部未触发图片预处理并行**”。
  2. 在 12 核机器上，3 个并行 job/卷大致只吃到 ~3 个核心，CPU 明显仍有余量，因此**确实存在继续提高 CPU 占用率的空间**。
  3. 外层按卷并行对 CBZ 场景收益明显：3 卷样本下从 176s 降到 63s，吞吐提升约 **2.8x**；代价是峰值内存从 ~0.9GB 升到 ~3.7GB。
  4. ZIP/book 模式不能直接照搬同样默认值，因为其内层已经会触发 `ProcessPoolExecutor(max_workers=4)`；若外层再按卷并行，必须配合“总并发预算”避免外层 * 内层双重超卖。
  5. `pdf -> mobi` 模式也不应激进并行：从运行中的 `kcc-c2e.py` 进程树可见，KCC 自身会再派生多个子进程，外层并发应更保守。
- **结论**：若目标是“单 job 也能更充分利用多核”，则**值得推进 job 内多漫画并行**，但应优先覆盖 `cbz` / `book` 场景，并采用**可配置且按 mode 自适应的保守默认值**。

## Session Addendum: Codex hook JSON error diagnosis (2026-04-16)
- `~/.codex/hooks.json` 将 `SessionStart` 和 `UserPromptSubmit` 直接配置为执行 shell 脚本：
  - `sh .codex/hooks/session-start.sh ... || sh "$HOME/.codex/hooks/session-start.sh" ...`
  - `sh .codex/hooks/user-prompt-submit.sh ... || sh "$HOME/.codex/hooks/user-prompt-submit.sh" ...`
- 当前项目下没有本地 `.codex/hooks/` 覆盖文件，因此实际回退到了全局 `~/.codex/hooks/*`。
- `~/.codex/hooks/user-prompt-submit.sh` 会在存在 `task_plan.md` 时直接输出纯文本摘要（`echo` + `head` + `tail`），不是 JSON。
- `~/.codex/hooks/session-start.sh` 会先运行 `session-catchup.py`，再继续调用同一个 `user-prompt-submit.sh`；因此它同样会把非 JSON 内容写到 stdout。
- Codex 对 `SessionStart` / `UserPromptSubmit` 的 hook stdout 期望是合法 JSON；当前脚本输出纯文本，所以报：`invalid session start JSON output` / `invalid user prompt submit JSON output`。
- `PreToolUse` / `PostToolUse` / `Stop` 没报同类错误，是因为它们走的是 Python adapter，最终输出 JSON。

## 本地 hook 修复实现（2026-04-16）
- 已在当前仓库创建 `.codex/hooks/`，利用 `~/.codex/hooks.json` 的“本地优先、全局回退”机制覆盖出错 hook。
- 新增 `.codex/hooks/planning-context.sh`：继续生成原有纯文本计划摘要，避免逻辑重复。
- 新增 `.codex/hooks/emit_context_hook.py`：把纯文本摘要包装为合法 JSON：
  - `hookSpecificOutput.hookEventName`
  - `hookSpecificOutput.additionalContext`
- 新增 `.codex/hooks/user-prompt-submit.sh`：输出 `UserPromptSubmit` 所需 JSON。
- 新增 `.codex/hooks/session-start.sh`：保留 `session-catchup.py` 行为，但将 catchup 输出与计划摘要统一 JSON 化后再返回。
- 验证方式：直接按 `~/.codex/hooks.json` 中的命令在当前仓库执行，两个 hook 输出都能被 `json.loads` 成功解析，且 `hookEventName` 分别为 `UserPromptSubmit` / `SessionStart`。
- 该修复仅影响当前仓库；其他仓库若没有本地 `.codex/hooks/` 覆盖，仍会继续命中全局纯文本 hook 并报同样错误。


## UI Refactor Audit Kickoff (2026-04-16)
- 本轮任务范围集中在 `templates/index.html`、`static/app.js`、`static/style.css`，必要时只对 `web_server.py` 做最小接口契约修补。
- 当前前端是单页原生 HTML/CSS/JS，没有构建系统；因此“规范格式和接口”主要体现为：减少内联样式、统一状态更新入口、收紧 API 读取与错误处理、避免 DOM/状态分叉。
- `omx explore` 在当前环境不可用，报错为缺少 `cargo` / explore harness，因此代码审查改为直接读取源码。
- 首轮 UI 文件快速观察：
  - `templates/index.html` 仍存在注释掉的旧 header 结构，且存在部分布局语义可收敛。
  - `static/app.js` 负责大量状态、DOM、接口与轮询逻辑，文件职责偏重，适合先做逻辑分组和重复路径收敛。
  - `static/style.css` 已较长，既有通用面板样式，也有具体组件样式，后续需检查重复规则、响应式缺口和与 HTML 结构的耦合点。

## UI Audit Findings: First Pass (2026-04-16)
- `templates/index.html`
  - 页面主结构当前为：文件浏览器 / 转换配置双栏 + 控制台面板 + 任务历史面板 + 日志弹窗。
  - 存在被整段注释掉的旧 `header`，属于死结构噪音，可在重构中删除或恢复为真实语义头部。
  - `batch-size-group` 仍以内联 `style="display: none;"` 控制初始状态，布局状态与 JS 耦合较紧，适合改为 class/hidden 驱动。
- `static/app.js`
  - 文件承担初始化、DOM 查询、目录浏览、模式检测、任务创建、轮询、弹窗、通知、历史渲染等多重职责，后续应优先做逻辑分组与重复错误处理收敛。
  - 已有较好的 API 入口统一点 `readApiPayload()`，但其余请求流程仍多处重复“fetch + parse + response.ok 判断”模板。
  - 文件浏览器当前采用“单击选中、再次点击同一项进入目录”的交互，逻辑上可用，但实现依赖 `.selected` DOM class，而不是显式选中状态模型。
- `web_server.py`
  - UI 直接依赖的主要接口为 `/api/config`、`/api/config/default-path`、`/api/browse`、`/api/download`、`/api/detect-mode`、`/api/system-stats`、`/api/console-output`、`/api/jobs*`。
  - `analyze_comic_folder()` 与 `create_job()` 构成前端命名预览与任务参数的关键契约，需要在前端重构时保持字段一致性。
- 测试现状
  - 当前已有 `tests/test_web_workers.py`，但覆盖点集中在 worker 并发与日志隔离，还没有覆盖前端契约相关的 Flask API 行为与隐藏状态问题。

## UI Audit Findings: Baseline Diagnostics (2026-04-16)
- 项目当前没有 `tsconfig`，因此 LSP/tsc 级别的前端静态诊断不可用；`static/app.js` 只能依赖 `node --check` 与人工审查。
- 直接用系统 Python 跑 `python3 -m unittest discover -s tests -p 'test_*.py'` 失败，不是代码回归，而是环境缺少依赖：
  - `reportlab`
  - `flask`
- 这说明当前仓库测试需要切到项目既有环境（历史记录显示为 conda `comic` 环境）后再做有效验证。
- 纯语法层面：`python3 -m py_compile web_server.py main.py` 与 `node --check static/app.js` 在系统环境下可通过，问题主要在运行依赖而非语法。
- 切换到 `conda run -n comic` 后，现有 11 个测试全部通过；说明当前代码基线可工作，后续可以在该环境中做回归验证。
- 这也再次确认：系统 Python 报错是环境问题，不是当前代码已损坏。

## UI Contract Regressions Captured by New Tests (2026-04-16)
- 新增 `tests/test_web_ui_api.py` 后，确认了两个此前未被覆盖的隐藏问题：
  1. `/api/jobs` 在 `mode` 非法时仍返回 200 并创建任务，错误会延迟到 worker 线程中才暴露；这属于接口边界未校验。
  2. `/api/jobs/clear` 的 `cleared_count` 计算在 `jobs.clear(); jobs.update(...)` 之后执行，结果永远为 0；这会让 UI 的清理历史反馈与实际不一致。
- 同时 `test_detect_mode_returns_ui_analysis_contract` 已建立当前 UI 命名分析契约基线，便于后续前端重构时保持字段一致。

## UI Refactor Implementation Notes (2026-04-16)
- `templates/index.html`
  - 用真实的 `app-header` 替换了注释掉的旧 header，并把页面组织为 `main-grid + secondary-grid` 两段布局。
  - 将配置表单拆为多个 `form-section`，同时移除了 `batch-size-group` 的内联 `display:none`，改为 `hidden` 驱动。
- `static/style.css`
  - 新增了页面头部、次级网格、表单分区、路径按钮组和历史区动作栏的布局样式。
  - 合并了重复的 `.btn-small` 定义，并移除了多段未再使用的旧 progress 区块样式，减少样式噪音。
  - 新增 `stat-value--good/warn/bad`，把系统指标颜色从 JS 内联样式改为 class 驱动。
- `static/app.js`
  - 新增统一的 `requestJson()`，收敛前端 `fetch + parse + error` 模板代码。
  - 新增 `renderPlaceholder()` / `clearElement()` / `setElementHidden()` / `setStatValue()` 等小型 UI helper，减少重复 DOM 操作。
  - `renderFileList()` 和 `renderJobList()` 改为 DOM API 构建节点，不再把文件名、路径、错误信息直接拼进 `innerHTML`；这修复了 UI 中潜在的 HTML 注入/XSS 风险，并移除了 `onclick` 字符串处理。
  - `startConversion()` 现在在请求进行中会禁用开始按钮，避免重复点击提交同一任务。
- `web_server.py`
  - `/api/jobs` 新增模式白名单校验，非法 mode 现在会在 API 层直接返回 400，而不是进入 worker 后再失败。
  - `/api/jobs/clear` 修复了历史清理数量始终显示为 0 的计数错误。
- `tests/test_web_ui_api.py`
  - 新增了 `detect-mode` 契约、非法 mode 拒绝、clear history 计数三个回归测试，用于保护 UI 依赖的关键后端契约。

## Web Layout / PDF Retention Change Audit (2026-04-16)
- 当前页面结构仍使用 `main-grid + secondary-grid` 两段独立网格；这会导致上下两行列宽不一致，不满足“上下对齐宽度，左右对齐高度”的 2x2 面板要求。
- 当前配置表单中 `mode` 下拉选项文案较短，模式说明通过底部 `help-text` 展示；这与用户要求的“说明直接写进选项 + 右侧 hover 说明按钮”不一致。
- 当前 UI 只有 `convert_to_mobi` 复选框，没有 `keep_pdf`；前端请求体也未发送对应参数，后端转换完成后不会清理 `<输出根>/<漫画名>/pdf`。
- `main.py` 的三种会生成 PDF 的流程（batch/book/cbz）都统一通过 `prepare_output_layout()` 创建 `pdf/` 与 `mobi/` 目录，因此“转换完成后删除 PDF 文件夹”最适合抽成公共清理 helper，而不是分别复制粘贴逻辑。
- 当前 `PDF -> MOBI` 模式也会创建输出布局中的 `pdf/` 目录，但该目录并不承载新生成内容；如果允许 `keep_pdf=false`，删除空 `pdf/` 目录即可满足“只留下 MOBI 文件夹”的结果。
- `templates/index.html` 中“命名来源”一行当前由 `static/app.js` 中的 `namingSourceDisplay` 驱动；如果删除该行，需要同步移除 DOM 查询与状态更新，避免空节点访问。
- 现有测试里 `tests/test_web_ui_api.py` 适合补 API 参数默认值/约束测试；输出目录删除逻辑更适合在 `tests/test_pdf_workflows.py` 或新增轻量单测中直接验证 `main.py` 行为。

## Web Layout / PDF Retention Implementation Findings (2026-04-16)
- 统一四面板布局最稳妥的方式是把原本分开的 `main-grid` 与 `secondary-grid` 合并成单一 `workspace-grid`。CSS Grid 会天然保证同一行左右两块面板等高、同一列上下两块面板等宽，满足“上下对齐宽度，左右对齐高度”。
- “label 和 select 同行”可以通过 `form-row` 的两列栅格实现，不需要引入额外 JS；移动端再退化成单列即可保持自适应。
- `keep_pdf` 的前端状态规则最终定为：
  - 未启用 MOBI 转换时：强制勾选并禁用；
  - 启用 MOBI 转换时：允许取消勾选；
  - `pdf` 模式：`convert_to_mobi` 强制为 true，但 `keep_pdf` 仍可控制是否保留输出布局中的 `pdf/` 子目录。
- `main.py` 中新增 `cleanup_pdf_output_dir()` 后，四种转换路径都能复用同一清理逻辑；这样避免了分别在 batch/book/cbz/pdf 中写四遍 `shutil.rmtree`。
- API 层新增 `coerce_bool()` 后，`keep_pdf` / `convert_to_mobi` 即使以后从非 JSON 场景传入字符串值，也能保持一致布尔语义。
- 新增测试覆盖点：
  - `tests/test_web_ui_api.py`：`keep_pdf` 在 API 层的默认强制/允许关闭逻辑；
  - `tests/test_output_retention.py`：MOBI 生成后是否删除 `pdf/` 子目录。

## Visual Compression Follow-up Findings (2026-04-16)
- 用户提供的页面截图确认：转换配置区虽然功能到位，但仍因多行说明文本和较大的 section padding 显得偏高，尤其是“转换模式”单行子模块。
- 这轮优化采取两条主线：
  1. 把转换配置区所有说明迁移到统一的 `?` tooltip 按钮；
  2. 继续压缩 `form-section`、`form-row`、输入框、输出预览和 checkbox chip 的垂直尺寸。
- 动态说明没有删除，而是改为挂载到 tooltip 内容节点：`comic-name-help`、`output-preview-help`、`format-options-help` 仍由 `static/app.js` 更新，只是不再占用额外行高。
- 本轮未改动后端契约，仅做模板/样式层面的视觉收紧，因此回归风险主要集中在 DOM id 是否仍被 JS 正确引用；测试与语法检查已覆盖基本回归面。
