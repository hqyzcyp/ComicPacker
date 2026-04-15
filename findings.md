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
