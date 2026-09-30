# V2 插件迁移到 V3 — 详细对照

来源：https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/V3_Plugin_Adaptation.md
（last_verified: 2026-02；与原文冲突时以原文为准并回改本文件。）

## 1. 何时需要 V3 专用副本

V3 默认兼容 V2 插件。只有插件使用了 V3 已变更的合同才需要处理：

1. 将 V2 实现复制到 `plugins.v3/<plugin_id_lower>/`，不改原实现。
2. `package.v3.json` 增加条目，声明 `"system_version": ">=3.0.0"`。
3. 原索引同名条目加 `"v3": false`（避免 V3 回退加载旧合同实现）。
4. 版本主进位归零：`2.6.1 -> 3.0.0`。
5. 同步 `plugin_version`、索引 `version`、`history` 置顶，history 按语义版本降序。

不碰媒体身份/链路/宿主数据库/宿主 REST 的插件通常无需 V3 副本；也**不要**为声明兼容批量加 `"v3": true`。

## 2. 旧导入迁移

兼容层是精确映射（登记过的旧路径仍可导入），不是通配转发；未登记模块抛 `ModuleNotFoundError`。
`DEBUG=true` 时宿主输出类似：

```
[兼容导入] 插件 MyPlugin（__init__.py:12）使用旧路径 app.utils.string，已映射到 app.sdk.string；请迁移到 app.sdk.utilities
```

处理顺序：

1. 按警告末尾推荐路径改，不要从内部目标路径反向导入。
2. 只迁移实际使用的符号；不复制宿主实现、不建自己的兼容包。
3. `DEBUG=true` V3 宿主重载，清零警告。
4. 再做功能回归——导入通 ≠ 调用合同没变。
5. 禁止用拼接模块名/非字面量动态导入隐藏警告。

完整映射表以 MoviePilot 主仓 `app/runtime/compat/manifest.py` 为准。

### 常用映射速查

| 旧 | 新 |
|---|---|
| `app.log` | `app.sdk.logging` |
| `app.core.config` | `app.sdk.config` |
| `app.core.event` | `app.sdk.events` |
| `app.core.cache` | `app.sdk.cache` |
| `app.core.module` / `app.core.plugin` | `app.sdk.plugins` |
| `app.core.context` / `app.core.meta*` / `app.core.metainfo` / `app.utils.media` / `app.utils.tokens` | `app.sdk.media` |
| `app.utils.string` / `app.domain.string` / 加密・DOM・反射・OTP・单例・系统・定时工具 | `app.sdk.utilities` |
| `app.utils.http` / `ip` / `url` / `security` / `site` / `web` | `app.sdk.network` |
| 下载器・媒体服务器・通知・规则・存储・系统状态・服务发现 Helper | `app.sdk.services` |
| `app.helper.browser` | `app.sdk.browser` |

具体符号是否公开，以对应 SDK 模块 `__all__` 为准。

## 3. 媒体身份合同

- 主身份 = `media_source + media_id`，不可拆；同时为空或同时有效；空串、非法来源、`"0"` 无效。
- 内置枚举 `from app.schemas.types import MediaSource`（值：`themoviedb`、`douban`、`bangumi`、`anilist`、`imdb`、`tvdb`、`musicbrainz`、`theaudiodb`、`doubanmusic`、`bilibili`、`mangguodiscover`、`migu`、`tencentvideodiscover`）。
- 插件扩展来源：`MediaSource("acmevideo")`；小写字母开头，仅小写字母/数字/点/下划线/短横线，≤64 字符，发布后不可变。不要改宿主枚举源码。
- 枚举名 ≠ 传输值；序列化用 `media_source.value`。
- 通用调用不再接收来源专用参数：

```python
# 旧（V3 已废）
SearchChain().search_by_id(tmdbid="550", doubanid=None)

# 新
media = MediaChain().recognize_media(
    media_source=MediaSource.Douban, media_id="1295644", mtype=MediaType.MOVIE)
contexts = SearchChain().search_by_id(
    media_source=media.media_source, media_id=media.media_id, mtype=media.type)
```

- 身份比较：`left.media_source == right.media_source and str(left.media_id) == str(right.media_id)`。
- `MediaServerItem`（2026-02 宿主 v3 分支实测）：V2 的 `tmdbid`/`imdbid`/`tvdbid` 字段已删除，只有 `media_source + media_id`，由 `ProviderIds` 按优先级（TMDB 最先）选出唯一来源；`WebhookEventInfo` 保留 `tmdb_id` 兼容属性，`MediaServerItem` 没有。读 TMDB ID 必须先判 `media_source == MediaSource.TMDB` 再取 `media_id`。
- 归一/键工具：`resolve_media_identity()`、`build_media_key()`（如 `douban:1295644`）、`parse_media_key()`。
- 跨源转换：`MediaChain().convert_media_identity(target_source=..., media_source=..., media_id=...)`；插件可实现 `ChainEventType.MediaRecognizeConvert` 参与转换。
- 不要自研来源别名、复合键、跨源匹配。

### 允许保留来源专用 ID 的边界

- 来源专用链原子方法（`TmdbChain`、`DoubanChain`、`BangumiChain`、`AniListChain` …）。
- `/tmdb`、`/douban`、`/bangumi`、`/anilist` 等单源 API 及 TMDB 剧集/剧集组/排期固定能力。
- NFO `uniqueid`、Emby/Jellyfin/Plex `ProviderIds`、外部服务 URL。
- `MediaInfo.tmdb_id`/`imdb_id` 等辅助字段（不能替代主身份对）。
- 搜索策略字段（如 IMDb 关键字搜索开关）。

### 不参与统一的用户格式

- 自定义识别词强制标签：`{[tmdbid=xxx;type=movie/tv;s=xxx;e=xxx]}` 等。
- 重命名 Jinja2 变量：`tmdbid`、`imdbid`、`doubanid` 等。

## 4. 插件存量数据迁移

新数据只存 `media_source`/`media_id`。幂等迁移步骤：

1. `resolve_media_identity()` 验证统一字段。
2. 无效则按历史优先级回读旧字段（`doubanid`、`tmdbid` …）。
3. 取得完整有效身份后写新字段、删旧字段。
4. 复合 key 用 `build_media_key()`；换 key 先写新再删旧。
5. 找不到回填来源 → 保留原记录。
6. 可重复执行；覆盖 `None`、空白、`"0"`、非法来源、半对、目标已存在；合法扩展来源原样保留。

## 5. 数据库迁移

| V2 写法 | V3 写法 |
|---|---|
| 直接导入 `app.db.models.*` 操作宿主表 | `app.db.oper.<entity>`，优先 Chain/SDK |
| `Model.get(id)` / `model.update(payload)` 无会话调用 | 改用 Oper 公开方法 |
| 导入 `SessionFactory` / `AsyncSessionFactory` / `ScopedSession` | 删除；由 Oper/装饰器管理会话 |
| `@db_query`/`@db_update` 操作宿主 Model | 装饰器只用于插件自有表 |
| SQLAlchemy 1.x 注解 | 自有表用 2.0 `Mapped`/`mapped_column()` |
| 返回会话绑定对象后读懒加载字段 | 装饰器结束前物化为 list/标量/DTO |

宿主 Oper 无会话调用 = 每次调用独立事务；多写入要原子 → 用宿主 Chain/SDK 或在主仓加应用服务，不自行拼事务。

## 6. 链职责变化

- `MusicChain` 已删除，不重建兼容包装。
- 识别 → `MediaChain.recognize_media()` / async 版；音乐搜索/专辑/艺术家 → `MediaChain.search_music()` 等。
- 本地音乐识别 → `MediaChain.recognize_music_by_path()`。
- 站点搜索 → `SearchChain`；榜单/探索 → `RecommendChain`；刮削 → `ScrapingChain.scrape_metadata()`。
- 歌词源：`get_module()` 注册 `music_lyrics_candidates(music)`，从 `app.sdk.media` 导入 `MetaMusic/MusicInfo/MusicLyrics`，返回 `list[MusicLyrics]`（未命中 `[]`），不注册额外 HTTP 路由。
- `MediaChain.scrape_metadata(...)` 旧调用改 `ScrapingChain`。

## 7. REST 响应合同

- 宿主普通 JSON 统一 `{success, message, data}`；Python 客户端从 `data` 读业务数据，错误看 HTTP 状态码 + `message`。
- 插件 `get_api()` 路由**不**被宿主隐式包装：可直接返回业务模型或显式 `app.schemas.Response[T]`，`response_model` 必须一致。
- 接宿主数据页（探索/推荐等）的接口要显式 envelope。
- Vue 远程组件用宿主注入的 `api` props（或 `window.MoviePilotAPI`，baseURL 已含 `/api/v1/`）；错误 Toast 宿主统一处理，别重复弹。

## 8. 迁移发布前检查（补充主 skill 第 12 节）

- 通用方法/事件/任务/插件数据只用成对身份。
- `DEBUG=true` V3 宿主零兼容警告；不新增旧路径。
- 不直接访问宿主 Model / 裸 Session。
- 已移除 `MusicChain`；REST 按 envelope。
- V3 副本在 `plugins.v3/`、主版本跃迁、`system_version` 声明。
- 旧目录代码未被顺手修改；旧索引仅加 `"v3": false`。
- 验证命令：

```bash
python3 -m compileall plugins.v3/myplugin
python3 .github/scripts/check_plugin_versions.py package.json package.v2.json package.v3.json
git diff --check
```

涉及存量数据迁移、事件载荷、Vue 远程组件时，补 V3 宿主聚焦测试与真实加载验证。
