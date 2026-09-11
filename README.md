# Isaac Helper

一个在本机浏览器中运行的《以撒的结合：重生 / 忏悔+》成就辅助系统。

项目读取本机 Steam 成就缓存和游戏存档，生成仅保存在本地的进度快照，并按角色、挑战、流程与 Boss、收集、每日等解锁方式整理成就。首页以角色为核心，清楚区分已解锁和未解锁目标。

## 当前状态

本地版本已可运行。它会读取 Steam 成就缓存、Steam Schema 和用户选择的 Repentance+ 存档槽，并提供角色、分类和全部成就三个视图。仓库内置 641 条成就资料和本地图标，断网时仍可浏览。已确认的产品与技术设计见：

- [设计规格](docs/superpowers/specs/2026-09-09-isaac-achievement-helper-design.md)

## 使用方式

1. 双击 `启动以撒助手.bat`。这是推荐的启动方式，启动失败时窗口会保留错误信息。
2. 本地服务仅监听 `127.0.0.1`，并在默认浏览器中打开页面。
3. 在“更新数据”中选择 Steam 账户和存档槽。
4. 点击“读取并更新”更新个人进度。系统只读解析本地文件，将进度快照写入 `data/profiles/`。
5. 需要刷新公共成就名称、解锁条件、奖励和图标时，单独点击“更新成就资料”。这个操作不读取账户选择，也不会改动个人进度。
6. 关闭运行 `start.ps1` 的终端即可停止服务。

需要 Python 3.10 或更高版本，不需要安装第三方依赖。

也可以从项目目录用 PowerShell 手动启动：

```powershell
.\start.ps1
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
- 游戏存档的 Secret 状态与 Steam 成就状态单独显示；映射未经多来源确认时会明确标为“未验证”，不会按列表顺序猜测。
- 通关标记的 Repentance+ 二进制位置尚未得到可靠验证，因此界面不会伪造困难模式标记。
- 当前内置目录的 641 条成就均有中文名称和中文解锁条件；若未来更新缺少可靠中文字段，界面仍会回退显示英文原文，并保留明确的缺失原因。

## 信源策略

用户当前解锁状态以本地 Steam/游戏数据为准；本机 Steam Schema 决定成就 ID、Steam 名称、说明和图标；wiki.gg 提供玩法条件和奖励信息；灰机 Wiki 提供中文名称、说明、奖励与 DLC 术语。

合并时按字段应用上述优先级，来源不一致的值会记录为冲突，不会静默覆盖。每个字段还会保留来源链接或 `local_steam_schema` 本地来源，以及可用的抓取时间。Steam 元数据来自本机 Steam Schema；玩法资料引用[The Binding of Isaac: Rebirth Wiki on wiki.gg](https://bindingofisaacrebirth.wiki.gg/wiki/Achievement)；中文资料引用[以撒的结合中文维基（灰机 Wiki）](https://isaac.huijiwiki.com/wiki/%E9%A6%96%E9%A1%B5)。各来源内容权利和署名要求归其原始来源。

## 资料与资源署名

- 目录中的 641 条英文解锁条件来自 [The Binding of Isaac: Rebirth Wiki 的 Achievement 页面](https://bindingofisaacrebirth.wiki.gg/wiki/Achievement)，署名为 **The Binding of Isaac: Rebirth Wiki contributors**。本项目对这些字段进行了抽取、清理和结构化适配；来源页面按 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 提供内容，适用的衍生文本继续遵循相应的署名与相同方式共享条款。
- [以撒的结合中文维基的版权/分享说明](https://isaac.huijiwiki.com/wiki/MediaWiki%3AFooter) 区分了两类内容：部分英文 Wiki 译文采用 CC BY-SA 3.0，部分原创测试等内容采用 CC BY-NC-SA 3.0。当前基线包含灰机成就数据表中的中文名称、解锁条件和可解析的奖励名称；发布 fork 或发行包时仍须按具体页面和字段核对适用条款，并满足署名、相同方式共享及适用时的非商业限制。
- 成就列表可与 [Steam 官方成就页](https://steamcommunity.com/stats/250900/achievements) 核对，游戏信息见 [Steam 官方商店页](https://store.steampowered.com/app/250900/The_Binding_of_Isaac_Rebirth/)。缓存的成就 JPG 图像来自 Steam CDN；游戏和美术相关权利归 Nicalis, Inc.、Edmund McMillen 等官方商店所列的相应权利人。本项目为非官方工具，与 Valve/Steam、Nicalis 或 Edmund McMillen 均无隶属、合作或背书关系。

上述署名及文件随项目收录这一事实本身不授予额外的再分发许可。任何发布 fork 或发行包的人都应自行核对文字与图像的许可；如果无法确认缓存 JPG 的再分发权限，应从发行物中删除这些 JPG，并让使用者在本机通过更新功能重新生成缓存。

仓库已经包含可离线使用的 641 条统一目录 `data/catalog/achievements.json` 和本地图标。维护者可用与网页相同的更新流程刷新它：

```powershell
python tools/update_achievement_catalog.py --schema "D:\steam\appcache\stats\UserGameStatsSchema_250900.bin"
```

刷新会先生成候选目录，完成 641 条唯一 ID、必填字段、映射状态和本地资源校验后才原子替换现有目录。网络失败或候选数据无效时继续使用上一份有效目录；启动应用不会自动联网更新。

灰机 Wiki 可能拒绝直接自动抓取（HTTP 403）。发生这种情况时，更新器会尝试通过只读文本转发读取同一份公开原始数据；如果转发也不可用，则复用上一份目录中的灰机字段，绝不会自动编造中文翻译。实体、道具或挑战模板无法可靠展开时，本次中文更新会失败并保留旧目录，避免发布“击败1次”一类残缺条件。当前随仓库发布的基线包含 641 条中文名称、641 条中文解锁条件、623 条中文奖励名称和 641 个本地图标。

## 测试

```powershell
python -m unittest discover -s tests -v
```

测试包括合成二进制夹具、HTTP 接口、路径安全、目录合并与原子发布、快照原子写入和可选的本机真实数据冒烟验证。测试不会修改游戏文件。

## 常见问题

- **页面提示未找到 Steam**：确认 Steam 根目录中存在 `userdata/<账户>/250900`。本机默认会检查常见安装目录和 `D:\steam`。
- **没有可选档位**：确认 `250900/remote` 中存在 `rep+persistentgamedata1.dat` 至 `rep+persistentgamedata3.dat`。
- **读取失败**：先退出游戏，确认 Steam 已完成云同步，再点击“更新数据”。旧快照不会因一次失败而被覆盖。
- **进度数字与游戏内不同**：Steam 成就和游戏 Secret 是两个独立来源，页面会分别报告，不能直接混为同一个总数。
