# 🗂️ Copilot History Dashboard

> 把 **GitHub Copilot CLI** 本机历史对话变成可视化看板：分类 / 合并 / 搜索 / 一键恢复，外加一个 *Her* 风格的「作战空间」视图。
>
> Turn your local **GitHub Copilot CLI** chat history into a visual kanban: categorize, merge, search, one-click resume — plus a *Her*-inspired spatial "war room" view.

![Python](https://img.shields.io/badge/python-3.8%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Platform](https://img.shields.io/badge/platform-Windows-lightgrey) ![No Cloud](https://img.shields.io/badge/cloud-zero-success)

---

## 🇨🇳 中文版

### 🚀 三步启动

1. **克隆**这个仓库到任意位置
   ```bash
   git clone https://github.com/AIleahwang/copilot-history-dashboard.git
   ```
2. 确保已安装 **Python 3.8+**（`python --version`）
3. **双击 `启动看板.bat`** —— 浏览器自动打开 `http://localhost:8765`

> 看板会读取 `%USERPROFILE%\.copilot\session-store.db`（Copilot CLI 自己生成的对话数据库）。如果你从未用过 Copilot CLI，看板会显示空。

### ✨ 能做什么

- 🧠 **自动分类**：按关键词把对话分到「技能 / 客户 / 数据 / 学习 / 工具 / 其他」六大模块
- 🔗 **拖拽合并**：相似主题对话拖到一起，自动合并成一个任务
- 📂 **改分类**：把任意 chat 拖到别的模块
- ▶️ **一键恢复**：点开任何 chat → 详情页 → 「在 Copilot CLI 继续」按钮
- 🗑️ **彻底清理**：测试/临时对话可删除（含 DB 行 + session-state 文件）
- ✨ **作战空间** `/space`：黑金科技风第三空间，模块可拖拽缩放，模拟电影 *Her* 式工作面板

### 🔒 数据隐私（重要）

> 看板**只读取你本机** `%USERPROFILE%\.copilot\session-store.db`，所有操作都在你自己的电脑完成。
> **零网络请求、零数据上传**。作者和任何其他人都看不到你的对话。

可自行打开 `server.py` 搜索 `requests` / `urllib` / `http.client` 验证——除了 `localhost:8765` 本机 HTTP 服务，没有任何外部网络调用。

### 🗑️ 卸载

双击 `卸载.bat`。**不会动你的 Copilot CLI 数据库**。

### ❓ 常见问题

- **端口 8765 被占用？** 编辑 `server.py` 最后几行的 `PORT = 8765`
- **看板看不到最新对话？** 退出 Copilot CLI 让它写完 DB，再刷新
- **想恢复默认分类？** 删除 `%USERPROFILE%\.copilot\session-overrides.json` 和 `session-groups.json`

---

## 🇺🇸 English

### 🚀 Quick Start

1. Clone this repo
   ```bash
   git clone https://github.com/AIleahwang/copilot-history-dashboard.git
   ```
2. Install **Python 3.8+**
3. Run `python server.py` (or double-click `启动看板.bat`) → browser opens `http://localhost:8765`

### ✨ Features

| Feature | Description |
|---|---|
| 🧠 Auto-categorize | Sorts chats into 6 modules by keyword |
| 🔗 Drag to merge | Combine related chats into one task |
| 📂 Re-categorize | Drag any chat to a different module |
| ▶️ One-click resume | Jump straight back into any past Copilot CLI session |
| 🗑️ Clean delete | Remove test/temp chats fully (DB row + session-state) |
| ✨ Spatial view | A *Her*-style "war room" canvas at `/space` |

### 🔒 Privacy

100% local. The dashboard reads only your own `%USERPROFILE%\.copilot\session-store.db`. **No telemetry, no uploads, no cloud.** Grep `server.py` for `requests`/`urllib`/`http.client` to verify — the only network listener is `localhost:8765`.

---

## 📁 Files

```
copilot-history-dashboard/
├── server.py        # Main server (classic kanban + API)
├── space_view.py    # War-room spatial view at /space
├── 启动看板.bat     # One-click start
├── 卸载.bat         # One-click uninstall
├── SKILL.md         # Copilot CLI skill manifest
├── LICENSE          # MIT
└── README.md
```

---

## 🛠️ Use as a Copilot CLI Skill

复制整个目录到 `~/.copilot/skills/copilot-history-dashboard/`，Copilot CLI 会自动识别。之后在 CLI 里说「打开看板」/「我的对话历史」等即可触发。

---

## 🌟 Star History

If this helps you stay focused, give it a star — that's how I know to keep building.

## 📝 License

MIT © [AIleahwang](https://github.com/AIleahwang)
