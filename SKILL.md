---
name: copilot-history-dashboard
description: 把 GitHub Copilot CLI 本机历史对话变成可视化看板（分类/合并/搜索/恢复/删除），含 Her 风格作战空间页。WHEN：「看板」「对话历史」「恢复会话」「清理对话」「Copilot 历史」。
---

# Copilot History Dashboard

让用户能可视化、整理、恢复本机 Copilot CLI 对话。

## 触发场景
- 用户说「打开看板」「我的对话历史在哪」「想看历史 chat」
- 用户说「恢复之前那个对话」「继续之前 xxx 的会话」
- 用户说「清理 Copilot 历史」「删除测试对话」
- 用户说「作战空间」「Her 风格界面」

## 启动方式
```powershell
cd "<这个 skill 所在目录>"
python server.py
```
默认监听 `http://localhost:8765`，会自动打开浏览器。

## 关键功能
- `/` 经典看板（六大分类 + 拖拽合并）
- `/space` 作战空间（可拖拽缩放的科技面板）
- `/session?id=<id>` chat 详情页
- `POST /resume` 触发 `copilot --resume=<id>`
- `POST /delete` 删除 DB 行 + session-state 文件
- `POST /sessions/recat` 修改 chat 分类
- `POST /groups/merge` 合并 chat 成一个任务

## 数据源
**只读** `%USERPROFILE%\.copilot\session-store.db`。
分组/分类覆盖写入：
- `%USERPROFILE%\.copilot\session-groups.json`
- `%USERPROFILE%\.copilot\session-overrides.json`

## 隐私
零网络出站，所有操作只在用户本机完成。
