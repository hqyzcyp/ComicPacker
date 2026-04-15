# Task Plan: 关闭 Flask 调试模式并压缩终端日志输出

## Goal
更新 Web 服务启动配置，关闭 Flask debugger/debug 模式，抑制终端中的 HTTP 访问日志，只保留关键任务执行信息，并向用户说明当前 debugger 模式的作用与取消方式。

## Current Phase
Phase 5

## Phases
### Phase 1: Requirements & Discovery
- [x] 理解用户诉求（debugger 模式说明 + 降低终端噪音）
- [x] 检查当前 `web_server.py` 的启动与日志配置
- [x] 记录发现与约束
- **Status:** complete

### Phase 2: Logging Strategy
- [x] 确定需要关闭的日志来源
- [x] 决定保留哪些关键任务日志
- [x] 记录实现决策
- **Status:** complete

### Phase 3: Implementation
- [x] 修改 Flask 启动参数
- [x] 抑制 Werkzeug 请求日志/调试输出
- [x] 保留关键任务日志
- **Status:** complete

### Phase 4: Testing & Verification
- [x] 验证 debug 关闭
- [x] 验证访问日志不再刷屏
- [x] 记录测试结果
- **Status:** complete

### Phase 5: Delivery
- [ ] 总结改动
- [ ] 解释 debugger 模式用途与取消方式
- [ ] 说明剩余风险/后续动作
- **Status:** in_progress

## Key Questions
1. 当前所谓“debugger 模式”是否来自 Flask `debug=True`？
2. 如何关闭 HTTP 请求访问日志，同时不影响任务进度日志输出？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 关闭 `debug=True` 并禁用 reloader | 去掉 debugger/pin/自动重载等开发模式行为 |
| 抑制 `werkzeug` 的 INFO 级别日志 | 屏蔽终端中的逐条 HTTP 请求记录 |
| 收敛应用侧 `[DEBUG]` 打印 | 只保留与任务生命周期相关的日志 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       | 1       |            |

## Notes
- 若当前服务已在运行，需重启服务后新日志策略才会生效。
