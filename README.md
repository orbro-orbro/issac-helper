# Isaac Helper

一个在本机浏览器中运行的《以撒的结合：重生 / 忏悔+》成就辅助系统。

项目计划读取本机 Steam 成就缓存和游戏存档，生成仅保存在本地的进度快照，并按角色、挑战、流程与 Boss、收集、每日等解锁方式整理成就。首页将以角色为核心，清楚区分已解锁和未解锁目标。

## 当前状态

本地 MVP 已可运行。它会读取 Steam 成就缓存、Steam Schema 和用户选择的 Repentance+ 存档槽，并提供角色、分类和全部成就三个视图。已确认的产品与技术设计见：

- [设计规格](docs/superpowers/specs/2026-09-09-isaac-achievement-helper-design.md)

## 使用方式

1. 双击或在 PowerShell 中运行 `start.ps1`。
2. 本地服务仅监听 `127.0.0.1`，并在默认浏览器中打开页面。
3. 在“更新数据”中选择 Steam 账户和存档槽。
4. 点击“读取并更新”。系统只读解析本地文件，将进度快照写入 `data/profiles/`。
5. 关闭运行 `start.ps1` 的终端即可停止服务。

需要 Python 3.10 或更高版本，不需要安装第三方依赖。

也可以从项目目录手动启动：

```powershell
python -m app.server --open
```

## 隐私与安全

- 不修改、恢复或删除游戏存档。
- 不上传 Steam 成就缓存、游戏存档或个人进度快照。
- `data/profiles/`、原始存档文件及本机配置已由 `.gitignore` 排除。
- 仓库中的测试数据将使用脱敏的最小夹具。

## 技术方向

- Python 标准库本地服务
- 原生 HTML、CSS 和 JavaScript
- 无构建步骤、无数据库、无需桌面打包
- 黑色、简明、以角色为主的界面

## 当前能力边界

- Steam 成就状态与解锁时间来自本地 Steam 缓存。
- 游戏存档的 Secret 数量单独显示；在映射表未经确认前，不猜测其与 Steam 成就的一一对应关系。
- 通关标记的 Repentance+ 二进制位置尚未得到可靠验证，因此界面不会伪造困难模式标记。
- 角色中文名和界面已中文化；641 条玩法条件来自项目内的 wiki.gg 快照。目前尚未逐条补齐中文成就名与中文解锁说明，缺失时显示英文原文。

## 信源策略

用户当前解锁状态以本地 Steam/游戏数据为准；Steam Schema 用于成就 ID 与元数据；玩法条件优先交叉核对 wiki.gg，并使用灰机 Wiki 提供中文术语和说明。

仓库已经包含可离线使用的 wiki.gg 成就条件快照。只有维护目录时才需要联网刷新：

```powershell
python -m tools.update_wiki_catalog
```

刷新命令会拒绝少于 600 条的异常响应，并使用临时文件原子替换 `data/catalog/wiki_achievements.json`；普通使用不需要执行它。

## 测试

```powershell
python -m unittest discover -s tests -v
```

测试包括合成二进制夹具、HTTP 接口、路径安全、快照原子写入和可选的本机真实数据冒烟验证。测试不会修改游戏文件。

## 常见问题

- **页面提示未找到 Steam**：确认 Steam 根目录中存在 `userdata/<账户>/250900`。本机默认会检查常见安装目录和 `D:\steam`。
- **没有可选档位**：确认 `250900/remote` 中存在 `rep+persistentgamedata1.dat` 至 `rep+persistentgamedata3.dat`。
- **读取失败**：先退出游戏，确认 Steam 已完成云同步，再点击“更新数据”。旧快照不会因一次失败而被覆盖。
- **进度数字与游戏内不同**：Steam 成就和游戏 Secret 是两个独立来源，页面会分别报告，不能直接混为同一个总数。
