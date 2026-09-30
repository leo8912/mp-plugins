---
name: moviepilot-plugin-v3
description: MoviePilot V3 插件开发、迁移与审核规范。Use when：用户要编写新的 V3 插件（plugins.v3/ + package.v3.json + app.sdk 导入）、把现有 V1/V2 插件迁移到 V3 架构、审核本地插件是否符合 V3 合同（生命周期、导入路径、媒体身份、数据库边界、命令/事件/API/服务），或要求按官方文档更新校正本规范。触发词：MoviePilot插件、写插件、开发插件、V3插件、插件迁移、迁移到v3、插件审核、审查插件、mp插件、插件市场、package.v3.json。
---

# MoviePilot V3 插件开发规范

## Important

- 本规范的唯一权威来源是官方仓库文档（见下节）。与本规范冲突时，以官方文档和 V3 宿主源码为准，并**立即回改本 skill**。
- 新插件一律放 `plugins.v3/<plugin_id_lower>/`，配 `package.v3.json`；不要往 `plugins/` 或 `plugins.v2/` 写新代码。
- 新代码只从 `app.sdk` 与稳定公开入口导入；`app.core.*`、`app.helper.*`、`app.utils.*`、`app.db.models.*`、`app.sdk._legacy` 是禁区。
- 通用媒体身份必须成对使用 `media_source + media_id`，不得只存 `tmdbid`/`doubanid`/裸 `media_id`。
- 审核任何插件时，先走「插件审核清单」（本文件末尾），逐项给出行号证据。

## 1. 权威来源与本 skill 的更新机制

| 文档 | URL |
|---|---|
| 主指南（V3） | https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/Plugin_Development.md |
| V2→V3 迁移 | https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/V3_Plugin_Adaptation.md |
| 插件 API 响应 | https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/V3_API_Response_Adaptation.md |
| 仓库与发布 | https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/Repository_Guide.md |
| FAQ 合集 | https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/FAQ.md |
| 旧导入兼容清单 | https://github.com/jxxghp/MoviePilot/blob/v3/app/runtime/compat/manifest.py |

- **last_verified: 2026-02**（对照上述文档 fetch 校验；宿主本地 origin/ 检出为 v2.8.1，仅可作 V2 行为参照，V3 行为必须查 V3 宿主源码）。
- 任何一次开发/审核开始前，若距离 last_verified 已久或官方文档疑似更新，先按 `references/update-playbook.md` 刷新本 skill，再动手。
- 发现本规范与实际不符：不要在业务代码里绕过，直接修订 SKILL.md 或 references/，并更新 last_verified。

## 2. 仓库结构与索引（V3）

```
MoviePilot-Plugins/
├── plugins.v3/
│   └── myplugin/
│       ├── __init__.py        # 主类 MyPlugin，目录名 = 类名小写
│       ├── pyproject.toml     # 仅有额外 Python 依赖时
│       └── README.md          # 推荐
├── tests/v3/myplugin/test_plugin.py   # 测试不放进插件目录
└── package.v3.json            # 市场元数据，键名 = 插件 ID
```

对应关系（硬性）：

- 插件 ID = 主类类名；目录 = 类名小写；主类在 `__init__.py`。
- `package.v3.json` 中 `version` == 类中 `plugin_version` == `history` 顶部版本，三处一致。
- `system_version: ">=3.0.0"`；版本跃迁按语义化主版本进位（迁移 V2 插件时 `2.x → 3.0.0`）。
- 旧 V2 实现保留在原目录不动，仅在旧索引条目加 `"v3": false`（已有 V3 专用副本时）。

package.v3.json 条目示例：

```json
{
  "MyPlugin": {
    "name": "我的插件",
    "description": "……",
    "labels": "示例",
    "version": "3.0.0",
    "icon": "Myplugin.png",
    "author": "your-name",
    "level": 1,
    "system_version": ">=3.0.0",
    "history": { "v3.0.0": "迁移至 V3。" }
  }
}
```

> 个人仓库诊断要点：V3 宿主优先读 `package.v3.json`；缺失时回退 `package.json` 并要求条目含 `"v3": true`。两者都没有 → V3 宿主**根本发现不了该插件**。这是迁移第一检查项。

## 3. 最小可运行插件（V3 模板）

```python
from typing import Any, Optional
from app.plugins import _PluginBase

class MyPlugin(_PluginBase):
    plugin_name = "我的插件"
    plugin_desc = "一个最小可运行的 MoviePilot V3 插件。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "3.0.0"
    plugin_author = "your-name"
    author_url = "https://github.com/your-name"
    plugin_config_prefix = "myplugin_"
    plugin_order = 50
    auth_level = 1

    _enabled = False
    _message = "Hello MoviePilot"

    def init_plugin(self, config: Optional[dict] = None) -> None:
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        self._message = str(config.get("message") or "Hello MoviePilot")

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> list[dict[str, Any]]:
        return []

    def get_api(self) -> list[dict[str, Any]]:
        return []

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        return [
            {"component": "VForm", "content": [
                {"component": "VSwitch", "props": {"model": "enabled", "label": "启用插件"}},
                {"component": "VTextField", "props": {"model": "message", "label": "展示文本"}},
            ]}
        ], {"enabled": False, "message": "Hello MoviePilot"}

    def get_page(self) -> list[dict]:
        return [{"component": "VAlert",
                 "props": {"type": "info", "variant": "tonal", "text": self._message}}]

    def stop_service(self) -> None:
        self._enabled = False
```

生命周期规则：

- `init_plugin()` 必须可重复调用；开头可 `self.stop_service()` 清理上一轮资源。
- `get_state()` 返回是否启用。宿主用它门控 **命令、服务、模块** 的注册——返回恒 True 会让禁用失效（常见 bug）。
- 后台资源在 `init_plugin` 建立、`stop_service` 释放；不得在导入期/类定义期联网、建库、开线程。
- 需要定位自身插件 ID 时用 `self.__class__.__name__`（V3 虚拟分身会重命名运行类），不要硬编码类名。

## 4. 导入规范（V3）

稳定可直接用：`app.plugins`、`app.schemas`、`app.schemas.types`、`app.chain.*`、`app.modules.*`、`app.agent.*`、`app.api.endpoints.plugin`、`app.scheduler`、`app.db.oper.*`、`app.sdk.*`。

迁移映射（旧 → 新）：

| 旧导入 | V3 推荐入口 |
|---|---|
| `app.log` | `app.sdk.logging` |
| `app.core.config` | `app.sdk.config` |
| `app.core.event` | `app.sdk.events` |
| `app.core.cache` | `app.sdk.cache` |
| `app.core.plugin` / `app.core.module` | `app.sdk.plugins` |
| `app.core.context` / `app.core.meta*` / `app.core.metainfo` / `app.utils.media` | `app.sdk.media` |
| `app.utils.string` / `app.domain.string` / 加密・DOM・反射・OTP・单例・定时工具 | `app.sdk.utilities` |
| `app.utils.http` / `ip` / `url` / `security` / `site` / `web` | `app.sdk.network` |
| 下载器・媒体服务器・通知・规则・存储・服务发现类 Helper（`app.helper.*`） | `app.sdk.services` |
| `app.helper.browser` | `app.sdk.browser` |

禁止（新代码）：

- `app.core.*`、`app.helper.*`、`app.utils.*`（兼容层仅承接存量，不欢迎新用）。
- `app.sdk._legacy`。
- `app.db.models.*`（宿主 ORM 不是插件合同）、`SessionFactory` / `AsyncSessionFactory` / `ScopedSession`。
- 重新创建已删除的 `MusicChain`。
- 拼接模块名/非字面量动态导入来隐藏兼容警告。

HTTP：V3 用 `app.sdk.network.AsyncRequestUtils`（底层 HTTPX2）。默认网络错误返回 `None`；需要区分失败时传 `raise_exception=True` 并捕获 `httpx2.RequestError`；4xx/5xx 不会自动抛出，要自己检查 `status_code`。不要调用 `httpx2.alias_httpx()`。

验证：在 `DEBUG=true` 的 V3 宿主加载插件，确认无「兼容导入」警告。

## 5. 配置、数据、依赖、分身

- 用户配置：`init_plugin` 读，`update_config({...})` 写；不要直接改宿主配置文件。
- 少量结构化状态：`save_data` / `get_data` / `del_data`（及异步变体）。
- 报告/缓存/大对象：`get_data_path()`；**禁止写回插件源码目录**。
- 需要索引/筛选/大量记录才建插件自有表：SQLAlchemy 2.0 `Mapped`/`mapped_column()` + `db_query`/`db_update`（异步 `async_db_query`/`async_db_update`）；表名加插件前缀；`__table_args__ = {"extend_existing": True}`；`ensure_table()` 只在 `init_plugin` 调用；结构变更要写按版本、可重复执行的迁移。
- 表单控件的值类型陷阱：`VTextField` 一律回传**字符串**，数值比较前先 `int()`/`float()`。
- 类属性不要放可变对象（`[]`、`{}`、`set()`）当默认值——V3 虚拟分身/多实例会共享；在 `init_plugin` 里赋实例属性。
- 第三方依赖：插件目录 `pyproject.toml` 声明 `dependencies`（V1/V2 历史用 `requirements.txt`）；不提交 `uv.lock`，不在代码里跑 pip/uv；不降级宿主核心依赖；可选能力延迟导入。
- 虚拟分身：同一份源码多实例运行，配置/数据/事件/API/定时任务按实例隔离；排他资源（端口、外部账号）需配置区分。

## 6. 页面与表单

- `get_form()` 返回 `(页面JSON, 默认模型)`；`props.model` 对应模型字段。
- `get_page()` 返回详情页 JSON；数据表用 `VTable` 时要么传 `headers + items(纯 dict 行)`，要么用 `thead/tbody + tr/td` 组件——**不要把组件 JSON 塞进 `items`**（渲染为空行）。
- 复杂交互/侧栏全页用 Vue 联邦：`get_render_mode() -> ("vue", "dist/assets")`；联邦产物不得打包 Vuetify/MDI 全局 CSS（门禁脚本 `check_federation_css.py`）。
- `get_form`/`get_page` 会被频繁调用：里面不要做重网络请求、不要刷 info 日志。

## 7. 命令、事件、API、定时服务

远程命令（三者缺一即失效）：

```python
from app.sdk.events import Event, eventmanager
from app.schemas.types import EventType

@staticmethod
def get_command() -> list[dict]:
    return [{"cmd": "/my_plugin_run", "event": EventType.PluginAction,
             "desc": "执行我的插件", "category": "插件命令",
             "data": {"action": "my_plugin_run"}}]

@eventmanager.register(EventType.PluginAction)
def run_command(self, event: Event) -> None:
    if (event.event_data or {}).get("action") != "my_plugin_run":
        return
    ...
```

- `"event"` 必须是 **EventType 枚举成员**；传字符串会在 `send_event` 处报 Unknown event type，命令静默失效。
- 必须有 `@eventmanager.register(...)` 处理器，并按 `action` 过滤，否则发了没人接。

插件 API：

- 路径最终为 `/api/v1/plugin/<PluginID>/<path>`。
- 显式声明 `auth`：页面用 `"bear"`，外部用 `"apikey"`，非公开接口不要匿名。
- 普通 JSON 可直接返回业务模型或显式 `Response[T]`；宿主**不会**隐式包装插件返回值。统一 envelope `{success, message, data}` 只在宿主普通 REST 上生效。
- 有副作用的动作不要用阻塞式 GET 长任务：立即返回 + 后台执行。

定时服务与一次性任务：

```python
def get_service(self) -> list[dict]:
    if not self.get_state():
        return []
    from apscheduler.triggers.cron import CronTrigger
    return [{"id": "MyPlugin.Refresh", "name": "我的插件定时刷新",
             "trigger": CronTrigger.from_crontab("0 */6 * * *"),
             "func": self.refresh, "kwargs": {}}]
```

- 服务 ID 稳定且唯一；宿主按 `get_state()` 门控注册——`get_state()` 恒真 = 禁用后任务照跑。
- 「立即运行一次」/延时一次性任务用 `app.sdk.scheduler.add_plugin_once_job(插件ID, 任务ID, func, 名称, delay_seconds=3)`，不要在 `init_plugin` 里同步跑长任务，也不要自建 BackgroundScheduler；停用时 `remove_plugin_once_job`。
- **宿主兼容（2026-02 实测）**：部分 V3 构建的 `app.sdk.scheduler` 并没有 `add_plugin_once_job`（报 `has no attribute`，文档示例超前于宿主实现）。必须用 `getattr(scheduler_sdk, "add_plugin_once_job", None)` 探测；缺失、返回 False 或抛错时回退 `threading.Timer(delay, fn)`（`daemon=True`、一次性不常驻），并用非阻塞 `threading.Lock` 防止定时/手动/API 触发的任务重入。
- 服务/命令/API 返回值即使没有也写 `return []`，不要 `pass`（返回 None）。

通知用基类 `post_message()`；工作流用 `get_actions()`；Agent 工具用 `get_agent_tools()`。

## 8. 媒体身份（V3 硬合同）

- 通用身份 = `media_source + media_id` 成对：同时为空或同时有效；空串、非法来源、`"0"` 无效。
- 内置来源用枚举 `from app.schemas.types import MediaSource`（`themoviedb`/`douban`/…），插件扩展来源用稳定小写标识 `MediaSource("acmevideo")`。
- 比较、缓存键、历史查询、迁移都必须同时处理来源和 ID；复合键用 `build_media_key()`，解析用 `parse_media_key()`，归一用 `resolve_media_identity()`。
- 通用链路调用改签名：`SearchChain().search_by_id(media_source=..., media_id=...)`，`MediaChain().recognize_media(media_source=..., media_id=..., mtype=...)`；跨源转换用 `MediaChain().convert_media_identity(target_source=..., media_source=..., media_id=...)`。
- **允许保留原生 ID 的边界**：来源专用链（`TmdbChain` 等）、`/tmdb` 等单源 API、NFO `uniqueid`、Emby/Jellyfin `ProviderIds`、`MediaInfo.tmdb_id` 等辅助字段。纯 TMDB 单源插件内部缓存键用 tmdbid 可以，但只要数据可能被通用链路消费，就升级为身份对。
- **`MediaServerItem` 已无 `tmdbid`/`imdbid`/`tvdbid` 字段（2026-02 宿主 v3 分支实测）**：条目身份只有 `media_source + media_id`（由 `ProviderIds` 按固定优先级 TMDB→Douban→… 选出唯一一个）。读 TMDB ID：`media_source` 为 `themoviedb` 时取 `int(media_id)`，否则视为无 TMDB 身份（不要把非 TMDB 来源的 `media_id` 当 tmdbid 用）。`WebhookEventInfo` 另有 `tmdb_id` 兼容属性，`MediaServerItem` 没有。
- 存量数据迁移要幂等：验证新字段 → 回退读旧字段 → 成功后写新删旧 → 可重复执行、不丢数据。

## 9. 数据库边界（V3）

| 数据 | 入口 |
|---|---|
| 插件设置 | `get_config()` / `update_config()` |
| 少量状态 | `save_data()` / `get_data()` / `del_data()` |
| 文件/大对象 | `get_data_path()` |
| 宿主业务数据 | `app.db.oper.<entity>` 或 Chain / SDK |
| 需要索引的自有数据 | 自有表 + `db_query`/`db_update` 装饰器 |

- 宿主 Oper 无会话调用 = 每次调用独立事务；不要假设多次 Oper 调用原子，不要跨任务复用 Session。
- 跨多个宿主写入要原子 → 用宿主 Chain/SDK，不要自行拼事务。
- 装饰器内完成物化（list/标量/字典）再返回，避免会话释放后懒加载。
- 自有表迁移：`checkfirst=True` 只建表不改列；列变更需版本化、可重复迁移，先备份。

## 10. V2 → V3 迁移摘要

详细步骤与代码对照见 `references/v2-to-v3-migration.md`。核心决策流：

1. 插件不碰媒体身份/链路/宿主数据库/宿主 REST → 通常**无需** V3 专用副本，V2 默认兼容 V3。
2. 需要专用实现 → 复制到 `plugins.v3/<id>/`，加 `package.v3.json`（`system_version ">=3.0.0"`），旧索引条目加 `"v3": false`，版本跃迁主版本（`2.6.1 → 3.0.0`）。
3. 导入按第 4 节映射迁到 `app.sdk`；在 `DEBUG=true` V3 宿主清零兼容警告。
4. 身份合同、数据库边界、REST envelope、链职责（无 MusicChain）逐条过 `references/v2-to-v3-migration.md` 的检查表。
5. 旧目录代码不要顺手改。

## 11. 插件审核清单（audit checklist）

审核任何本地插件时逐项检查，结论必须带文件:行号：

**A. 仓库与索引**
1. 是否存在 `plugins.v3/<id>/` 与 `package.v3.json`？缺 → V3 宿主不可见。
2. `plugin_version` / 索引 `version` / `history` 顶部三处一致，语义版本降序。
3. 目录名 == 类名小写；插件 ID == 类名 == 索引键。
4. 图标：索引 `icon` 与仓库 icons/ 文件可对上（URL 形式需在 V3 前端实测）。

**B. 导入**
5. 是否有 `app.core/helper/utils` 旧路径、`app.db.models.*`、裸 SessionFactory？
6. `DEBUG=true` V3 宿主加载是否有兼容导入警告？

**C. 生命周期**
7. `init_plugin` 可重复调用、不阻塞（无同步长任务/`onlyonce` 直跑）。
8. `get_state()` 返回真实启用状态（不是恒 True/恒 False）。
9. `stop_service` 释放线程/任务/连接；不误清配置。
10. 类属性无共享可变默认值。

**D. 命令/事件/API/服务**
11. `get_command` 的 event 是 EventType 枚举？有对应 `@eventmanager.register` 处理器并按 action 过滤？
12. `get_api` 显式 `auth`；副作用操作非阻塞 GET；返回结构与声明一致。
13. `get_service` 先 `get_state()` 门控；ID 唯一；一次性任务走 `add_plugin_once_job`。
14. 各方法返回 `[]` 而非 `None`。

**E. 业务合同**
15. 通用身份是否成对 `media_source+media_id`（或有依据归入单源边界）？
16. 未使用已删除 `MusicChain`、旧链签名（`search_by_id(tmdbid=...)`）。
17. 数据分层正确（配置/状态/文件/Oper/自有表），无宿主 Model 直查。
18. 宿主 REST 调用按 envelope `{success, message, data}` 解析。

**F. 健壮性**
19. 表单数值字段有 `int()` 转换；网络调用有超时/重试/失败降级。
20. 历史/缓存有上限或清理策略；JSON 反序列化后键类型（int→str）仍可命中。
21. 明确列出的占位/未实现功能（搜索注释：`占位`、`暂不实现`、`TODO`）。

**G. 验证**
22. `python -m compileall plugins.v3/<id>` 通过。
23. 版本门禁脚本通过；`git diff --check` 干净。
24. 真实 V3 宿主加载一次：安装、启停、重载无残留，命令/API/服务只注册一次。

## 12. 发布前清单（V3）

- 新插件在 `plugins.v3/`，`package.v3.json` 完整，三处版本一致。
- 只用稳定 SDK / 稳定公开入口；无新增不必要宿主内部依赖。
- 宿主数据只经 Oper/Chain/SDK；事务装饰器只碰自有表。
- 配置初始化可重复；停用/重载释放后台资源；运行数据不写源码目录。
- 身份用 `media_source+media_id`；REST 按 API 专题合同。
- Vue 联邦完成 typecheck/build，且未打包 Vuetify/MDI 全局 CSS。
- 常用验证命令：

```bash
python -m compileall plugins.v3/myplugin
# 官方仓的 check_plugin_versions.py（.github 下）校验索引与插件类版本一致
python <官方仓>/.github/check_plugin_versions.py package.json package.v2.json package.v3.json
git diff --check
# 有测试时
python -m pytest tests/v3/myplugin
```

## 13. Troubleshooting

| 症状 | 原因 | 修复 |
|---|---|---|
| 日志 `app.sdk.scheduler has no attribute add_plugin_once_job` | 宿主构建未提供该接口（文档超前于实现） | `getattr` 探测 + `threading.Timer(daemon)` 回退 + 防重入锁 |
| V3 宿主市场看不到插件 | 无 package.v3.json 且 package.json 条目无 `"v3": true` | 建 plugins.v3/ + package.v3.json |
| 远程命令无反应 | `"event"` 传了字符串，或缺处理器 | 改 EventType 枚举 + `@eventmanager.register` |
| 禁用后定时任务还跑 | `get_state()` 恒 True | 返回真实 `_enabled` |
| 配置页数值比较报 TypeError | VTextField 回传字符串 | `int(config.get(...))` |
| 详情页表格空白 | 组件 JSON 塞进 VTable `items` | 改 headers+纯 dict 或 thead/tbody |
| DEBUG 有兼容导入警告 | 旧路径导入 | 按警告末尾推荐路径迁到 app.sdk |
| 装完插件 ImportError | 缺依赖未声明 | 插件目录 pyproject.toml 声明 |
| 更新历史/缓存读不到 | JSON 序列化 int 键变 str | 读取时统一 str(key) 或存 str |
| 日志每个项目都“缺少TMDB ID，跳过处理” | V3 `MediaServerItem` 已删 `tmdbid` 字段 | 读 `media_source == themoviedb` 时的 `media_id`（见 §8） |

详细迁移对照与更新流程：`references/v2-to-v3-migration.md`、`references/update-playbook.md`。
