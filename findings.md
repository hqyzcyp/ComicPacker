# Findings & Decisions

## Requirements
- 用户想知道当前“debugger 模式”的作用。
- 用户希望确认这种模式是否可以取消。
- 用户不想在终端看到逐条 HTTP 访问日志。
- 用户只想保留关键任务执行信息。

## Research Findings
- `web_server.py` 当前使用 `app.run(..., debug=True, threaded=True)`。
- 这会启用 Flask/Werkzeug 的开发模式：自动重载、交互式 debugger、PIN、额外调试输出。
- 终端中大量 `GET /... 200` 日志来自 `werkzeug` 请求访问日志。
- 当前代码中还有一些 `[DEBUG]` 打印，它们属于应用级日志，不是 Werkzeug 访问日志。
- 将 `werkzeug` logger 级别提高到 `ERROR` 后，请求访问日志和启动 banner 都不会刷屏。
- 将 `debug=False`、`use_reloader=False` 后，不会再出现 `Debugger is active`、PIN、自动重载信息。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 将 `debug` 改为 `False`，并显式关闭 `use_reloader` | 避免再次进入 debugger 模式 |
| 将 `werkzeug` logger 级别提升并关闭传播 | 屏蔽访问日志，同时尽量不影响应用自己的 `print` 输出 |
| monkey patch `flask.cli.show_server_banner` | 进一步减少启动噪音，只保留自定义启动提示 |
| 将应用中的 `[DEBUG]` 打印收敛成关键 `[JOB]`/`[WORKER]` 事件 | 只保留任务相关的重要信息 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 5000 端口已被现有服务占用，无法直接在默认端口复测 | 使用单独的 5050/5051 测试端口做无侵入验证 |

## Resources
- `web_server.py`
- `start_web.sh`
- Flask/Werkzeug 当前运行输出

## Visual/Browser Findings
- 无
