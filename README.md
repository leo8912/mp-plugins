# 🤖 mp-plugins 插件库（AI Generated）

欢迎来到 mp-plugins！本仓库所有插件均由 AI 自动生成与优化，致力于为 MoviePilot 用户带来更智能、更高效的下载与媒体管理体验。

---

## ✨ 项目特色

- 🚀 **全自动**：所有插件均由 AI 编写、维护与进化。
- 🛠️ **持续优化**：不断学习社区优秀实践，自动适配 MoviePilot 插件市场。
- 📦 **开箱即用**：结构规范，兼容官方插件市场，易于集成。

---

## 📦 插件列表

### 1. multitrackereditor

> 🧩 **本插件灵感源自 [honue/MoviePilot-Plugins](https://github.com/honue/MoviePilot-Plugins) 的 tracker 替换插件，并在此基础上进行了功能增强：**

- 🔄 **自动读取 MoviePilot 全局下载器配置**
  - 无需手动输入 IP、端口、账号、密码等信息，插件会自动获取并复用 MoviePilot 的全局下载器设置，极大简化配置流程，提升易用性。
- 🗂️ **多下载器批量选择与管理**
  - 支持同时选择多个下载器（如 qBittorrent、Transmission 等）进行 tracker 批量替换，参考了 [jxxghp/MoviePilot-Plugins](https://github.com/jxxghp/MoviePilot-Plugins) 官方仓库的 iyuu 插件设计思路，适合多下载器环境下的统一管理和操作。

### 2. varietyshowsubscriber（综艺订阅助手）

> 📺 **自动为新添加的综艺订阅添加指定站点**

- 🤖 **自动识别综艺类型**
  - 基于 TMDB 媒体类型 ID 自动识别综艺类型（默认 10764、10767），也可自定义配置类型 ID。
- 🌐 **自动添加订阅站点**
  - 当添加综艺订阅时，自动将配置的站点添加到订阅中，无需手动选择。
- 📝 **历史记录追踪**
  - 提供可视化界面查看处理历史，记录每次添加的订阅名称、站点等信息。
- 📢 **通知提醒**
  - 可选开启通知功能，处理完成后发送系统通知告知结果。

---

## 📚 参考与致谢

本项目参考并致敬以下优秀开源仓库：

- [honue/MoviePilot-Plugins](https://github.com/honue/MoviePilot-Plugins)
- [jxxghp/MoviePilot-Plugins](https://github.com/jxxghp/MoviePilot-Plugins)

---

## 🤝 如何参与/贡献

- 欢迎提交 issue、PR 或建议，AI 会自动学习并持续优化插件。
- 你也可以 fork 本仓库，开发属于自己的 AI 插件！

---

## 📄 License

本项目遵循 GPL-3.0 License.

# MoviePilot Plugins Development Environment

This repository contains the development environment for MoviePilot plugins.

## Structure

- `origin/MoviePilot` - Clone of the official MoviePilot repository
- `origin/MoviePilot-Plugins` - Clone of the official MoviePilot-Plugins repository
- `plugins` - Custom plugins being developed

## Automatic Upstream Sync

A scheduled task has been set up to automatically sync with upstream repositories daily at 3 AM.

### Manual Sync

To manually sync with upstream repositories, run:

```powershell
powershell -ExecutionPolicy Bypass -File sync_upstream.ps1
```

### Reschedule Sync Task

To change the sync schedule, modify and run:

```powershell
powershell -ExecutionPolicy Bypass -File schedule_sync.ps1
```

## Development

Custom plugins are developed in the `plugins` directory and can be tested with the MoviePilot instance.

## Git Ignore

The `origin` directory containing the upstream repositories is excluded from Git tracking through the `.gitignore` file. This ensures that:
1. Upstream repository contents are not pushed to your personal repository
2. Your local changes and commits remain clean and focused on your custom plugins
3. You can still sync with upstream repositories without conflicts
