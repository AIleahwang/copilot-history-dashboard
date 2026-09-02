# 🗂️ Copilot History Dashboard

> 把 **GitHub Copilot CLI 与桌面端**本机历史对话变成可视化看板：分类 / 合并 / 搜索 / 一键恢复，外加一个 *Her* 风格的 Mission Queue 作战空间。
>
> Turn your local **GitHub Copilot CLI and desktop** chat history into a visual kanban: categorize, merge, search, one-click resume — plus a *Her*-inspired Mission Queue war room.

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

- 🐙 **GitHub Desktop 入口**：按 `host_type` 自动识别桌面端会话并放入独立模块
- 🧠 **自动分类**：按关键词把其他对话分到「Scout / 技能 / 客户 / 汇报 / 学习 / 工具 / 其他」模块
- 📱 **模块自由排序**：长按模块标题进入抖动模式，拖动后自动让位并记住布局
- 🔗 **拖拽合并**：相似主题对话拖到一起，自动合并成一个任务
- 📂 **改分类**：把任意 chat 拖到别的模块
- ▶️ **一键恢复**：点开任何 chat → 详情页 → 「在 Copilot CLI 继续」按钮
- 🗑️ **彻底清理**：测试/临时对话可删除（含 DB 行 + session-state 文件）
- 🧹 **空白自动清理**：无标题、无有效内容的空壳会话不显示，并在安全缓冲期后清除本地记录
- ✨ **作战空间** `/space`：NOW / NEXT / LOOP / PARKED 四个漂浮 Mission 模块，任务可拖拽流转
- 🏆 **闭环反馈**：每个小 session 都可以 Done，完成后有胜利音效 + 撒花
- ✅ **+Mission 勾选器**：从主看板已有任务中勾选加入 Mission Queue，取消勾选即移除
- ◈ **AI Builder Roadmap** `/ai-roadmap`：Midnight Atlas 世界地图、六个可点击知识区域、Paper Expedition 城市下钻、叙事路线动画、地图/档案双模式、每周高信号 builders、Output Kit 与商业机会雷达
- ◫ **AI Evolution Atlas** `/ai-roadmap?view=history`：用非等距时间轴压缩早期历史、展开最近五年；先以六章大众叙事串起计算机、互联网、云与手机到生成式 AI / Agent，再通过关键人物肖像、机构 Logo 墙、六条技术轨道与权威来源下钻
- 🌐 **公网版本**：[AI Builder Roadmap](https://aileahwang.github.io/copilot-history-dashboard/) 由 GitHub Pages 托管，只发布最终 Roadmap HTML，可直接把网址发给别人

### ◈ 每周 AI Builder Scout

- 默认从 Follow Builders 中央 feed 读取公开 X / podcast / official blog 内容
- 用四维证据标准筛选：真正 Building、原创观点、AI Input 价值与来源质量
- 只有总分 ≥ 70，且 Building ≥ 24、原创性 ≥ 15、AI Input ≥ 15 的账号进入榜单
- X/Twitter 信号直接跳转到原帖，YouTube 与官方历史资料保留各自原始来源；所有链接使用兼容内嵌浏览器的当前页导航
- 每周数据写入 `%USERPROFILE%\.follow-builders\ai-roadmap.json`，按周归档，页面自动读取最新版
- 更新命令：`python scripts\update_ai_roadmap.py --input <weekly-update.json>`
- 公网发布命令：`python scripts\publish_ai_roadmap_pages.py`；本机周五任务会在校验和渲染成功后自动调用

### 🌐 云端分享如何工作

`localhost` 只对当前电脑可见。公网版本采用一条明确的数据边界：

1. 本机 Scout 从公开来源生成并校验每周 JSON。
2. 本机渲染独立 HTML，并移除只适用于本地看板的导航。
3. 发布器仅把最终 HTML 上传到仓库的 `gh-pages` 分支。
4. GitHub Pages 将它托管为固定 HTTPS 地址；每周五覆盖更新，分享链接保持不变。

发布器不会上传 Copilot 对话数据库、Follow Builders 配置或其他本地文件。首次调试可先运行
`python scripts\publish_ai_roadmap_pages.py --check`。

### 🔒 数据隐私（重要）

> 对话看板**只读取你本机** `%USERPROFILE%\.copilot\session-store.db`，所有对话操作都在你自己的电脑完成。
> `server.py` 不上传对话数据。Follow Builders 周更读取公开中央 feed；启用公网发布后，仅最终渲染的 Roadmap HTML 会被明确上传到 GitHub Pages。

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
| 🐙 GitHub Desktop | Detects desktop sessions by source and groups them in a dedicated module |
| 🧠 Auto-categorize | Sorts chats into Scout / Skills / Customer / Reporting / Learning / Tools / Other |
| 📱 Reorder modules | Long-press a module header, then drag; nearby modules shift automatically and the layout persists |
| 🔗 Drag to merge | Combine related chats into one task |
| 📂 Re-categorize | Drag any chat to a different module |
| ▶️ One-click resume | Jump straight back into any past Copilot CLI session |
| 🗑️ Clean delete | Remove test/temp chats fully (DB row + session-state) |
| 🧹 Blank cleanup | Hides empty shells immediately and removes inactive blank records after a safety grace period |
| ✨ Mission Queue | NOW / NEXT / LOOP / PARKED floating modules at `/space` |
| 🏆 Completion FX | Mark session-level subtasks as Done with victory sound + confetti |
| ✅ Add by checkbox | Add/remove existing dashboard tasks into Mission Queue via checkboxes |
| ◈ AI Builder Roadmap | Midnight Atlas knowledge world + weekly qualified builders + direct original sources at `/ai-roadmap` |
| ◫ AI Evolution Atlas | Nonlinear public history from computers and the web to generative AI and agents, with representative people, an organization logo wall, and six technical tracks at `/ai-roadmap?view=history` |
| 🌐 Public Roadmap | Shareable GitHub Pages site at `https://aileahwang.github.io/copilot-history-dashboard/`, refreshed by the Friday scout |

### 🔒 Privacy

The dashboard server is local and has **no telemetry or conversation uploads**. Conversation data stays in `%USERPROFILE%\.copilot\session-store.db`. When public publishing is enabled, only the final rendered Roadmap HTML is uploaded to GitHub Pages; local configuration and databases remain private.

---

## 📁 Files

```
copilot-history-dashboard/
├── server.py                    # Main server (classic kanban + API)
├── space_view.py                # War-room spatial view at /space
├── ai-roadmap.html              # Self-contained roadmap UI template
├── ai_roadmap_view.py           # Local overlay loader + renderer
├── ai_roadmap_seed.json         # Stable AI history baseline
├── scripts/update_ai_roadmap.py # Source-link and score-gate validator
├── scripts/publish_ai_roadmap_pages.py # Static-safe GitHub Pages publisher
├── tests/test_ai_roadmap.py     # Roadmap data and rendering tests
├── 启动看板.bat                 # One-click start
├── 卸载.bat                     # One-click uninstall
├── SKILL.md                     # Copilot CLI skill manifest
├── LICENSE                      # MIT
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
