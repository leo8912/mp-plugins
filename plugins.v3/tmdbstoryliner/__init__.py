import json
import threading
import time
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path

import requests

from app.plugins import _PluginBase
from app.sdk.logging import logger
from app.scheduler import Scheduler
from app.sdk.services import MediaServerHelper
from app.chain.mediaserver import MediaServerChain
from app.schemas import ServiceInfo
from app.sdk.events import Event, eventmanager
from app.sdk import scheduler as scheduler_sdk
from app.schemas.types import EventType, NotificationType


class tmdbstoryliner(_PluginBase):
    # 插件元数据
    plugin_name = "剧情更新器"
    plugin_desc = "定时从TMDB获取剧集的剧情简介，并将英文内容翻译成中文"
    plugin_icon = "https://raw.githubusercontent.com/leo8912/mp-plugins/main/icons/tmdbstoryliner.png"
    plugin_author = "leo"
    author_url = "https://github.com/leo8912"
    plugin_version = "3.0.5"
    plugin_locale = "zh"
    plugin_config_prefix = "tmdbstoryliner_"
    plugin_site = "https://www.themoviedb.org/"
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 1

    def __init__(self):
        super().__init__()
        # 插件配置项
        self._enabled = False
        self._cron = "0 2 * * *"
        self._translate_service = "google"
        self._tmdb_api_key = ""
        self._translate_app_id = ""
        self._translate_secret_key = ""
        self._update_series = True
        self._library_paths: List[str] = []
        self._onlyonce = False
        self._update_episode_image = True
        self._update_episode_rating = True
        self._update_episode_premieredate = True
        self._update_episode_credits = True
        # 推送配置
        self._enable_notify = True
        # AI翻译配置
        self._ai_translate = False
        self._siliconflow_api_key = ""
        self._siliconflow_model = "Qwen/Qwen2.5-7B-Instruct"
        # OpenAI兼容渠道 Base URL（留空默认 SiliconFlow）
        self._ai_base_url = ""
        # 缓存与历史（实例属性，避免多实例共享）
        self._series_status_cache: Dict[str, dict] = {}
        self._update_history: Dict[str, dict] = {}
        self._cached_service_infos: Optional[Dict[str, ServiceInfo]] = None
        # 防止定时/手动触发的任务重入
        self._run_guard = threading.Lock()

    # ------------------------------------------------------------------
    # 配置与生命周期
    # ------------------------------------------------------------------
    def _config_dict(self) -> dict:
        """组装当前配置（onlyonce 恒存 False）"""
        return {
            "enabled": self._enabled,
            "cron": self._cron,
            "translate_service": self._translate_service,
            "tmdb_api_key": self._tmdb_api_key,
            "translate_app_id": self._translate_app_id,
            "translate_secret_key": self._translate_secret_key,
            "update_series": self._update_series,
            "library_paths": self._library_paths,
            "onlyonce": False,
            "update_episode_image": self._update_episode_image,
            "update_episode_rating": self._update_episode_rating,
            "update_episode_premieredate": self._update_episode_premieredate,
            "update_episode_credits": self._update_episode_credits,
            "enable_notify": self._enable_notify,
            "ai_translate": self._ai_translate,
            "siliconflow_api_key": self._siliconflow_api_key,
            "siliconflow_model": self._siliconflow_model,
            "ai_base_url": self._ai_base_url,
        }

    @staticmethod
    def _load_legacy_config() -> Optional[dict]:
        """一次性迁移：读取旧类名 TmdbStoryliner 时期的插件配置键。

        插件 ID 曾为类名 TmdbStoryliner，配置存于 plugin.TmdbStoryliner；
        类名改为 tmdbstoryliner 后新键为空时回读旧键，避免配置丢失。
        """
        try:
            from app.db.oper.systemconfig import SystemConfigOper
            legacy = SystemConfigOper().get("plugin.TmdbStoryliner")
            if legacy:
                logger.info("已从旧配置键 plugin.TmdbStoryliner 迁移配置")
                return legacy
        except Exception as e:
            logger.warning(f"读取旧配置键失败（如为首次使用可忽略）：{e}")
        return None

    def init_plugin(self, config: Optional[dict] = None):
        """初始化插件（可重复调用）"""
        self.stop_service()

        if not config:
            config = self._load_legacy_config()

        if config:
            self._enabled = bool(config.get("enabled"))
            self._cron = config.get("cron") or "0 2 * * *"
            self._translate_service = config.get("translate_service") or "google"
            self._tmdb_api_key = config.get("tmdb_api_key") or ""
            self._translate_app_id = config.get("translate_app_id") or ""
            self._translate_secret_key = config.get("translate_secret_key") or ""
            self._update_series = config.get("update_series", True)
            self._library_paths = config.get("library_paths") or []
            self._onlyonce = config.get("onlyonce", False)
            self._update_episode_image = config.get("update_episode_image", True)
            self._update_episode_rating = config.get("update_episode_rating", True)
            self._update_episode_premieredate = config.get("update_episode_premieredate", True)
            self._update_episode_credits = config.get("update_episode_credits", True)
            self._enable_notify = config.get("enable_notify", True)
            self._ai_translate = config.get("ai_translate", False)
            self._siliconflow_api_key = config.get("siliconflow_api_key") or ""
            self._siliconflow_model = config.get("siliconflow_model") or "Qwen/Qwen2.5-7B-Instruct"
            self._ai_base_url = (config.get("ai_base_url") or "").strip()

        # 加载缓存和历史记录
        self._load_cache_and_history()

        # 立即运行一次：交给宿主调度器异步执行，不阻塞初始化
        if self._onlyonce:
            logger.info("立即运行一次剧情简介更新任务")
            self._onlyonce = False
            self._dispatch_run("onlyonce_run", "剧情更新器立即运行", delay_seconds=3)
            self.update_config(self._config_dict())

    def _dispatch_run(self, job_id: str, name: str, delay_seconds: int = 1) -> bool:
        """将一次性的更新任务交给宿主调度器执行。

        部分宿主构建的 app.sdk.scheduler 未提供 add_plugin_once_job，
        此时回退为延迟守护线程执行一次（一次性，不常驻）。
        """
        if not self._enabled:
            return False
        add_once = getattr(scheduler_sdk, "add_plugin_once_job", None)
        if add_once:
            try:
                if add_once(self.__class__.__name__, job_id, self.update_storylines, name,
                            delay_seconds=delay_seconds):
                    return True
                logger.warning("调度器未接受一次性任务，回退为线程执行")
            except Exception as e:
                logger.error(f"加入一次性任务失败：{e}，回退为线程执行")
        # 兼容回退：延迟守护线程执行
        try:
            timer = threading.Timer(delay_seconds, self.update_storylines)
            timer.daemon = True
            timer.start()
            logger.info(f"已通过回退线程派发任务：{name}")
            return True
        except Exception as e:
            logger.error(f"启动回退线程失败：{e}")
            return False

    def get_state(self) -> bool:
        """返回插件是否启用（宿主用它门控命令/服务注册）"""
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """定义远程命令"""
        return [{
            "cmd": "/tmdb_storyliner",
            "event": EventType.PluginAction,
            "desc": "更新TMDB剧情简介",
            "category": "自动整理",
            "data": {"action": "tmdb_storyliner_update"},
        }]

    @eventmanager.register(EventType.PluginAction)
    def run_command(self, event: Event) -> None:
        """处理远程命令，异步派发更新任务"""
        if (event.event_data or {}).get("action") != "tmdb_storyliner_update":
            return
        if self._dispatch_run("run_once", "剧情更新器命令触发"):
            logger.info("已接收命令，剧情更新任务稍后执行")

    def get_api(self) -> List[Dict[str, Any]]:
        """注册API接口"""
        return [
            {
                "path": "/update_storylines",
                "endpoint": self.update_storylines_api,
                "methods": ["GET", "POST"],
                "summary": "手动更新剧情简介",
                "description": "手动触发剧情简介更新任务（异步执行）",
                "auth": "apikey",
            },
        ]

    def update_storylines_api(self):
        """API接口：手动更新剧情简介（异步派发，不阻塞请求）"""
        if not self._enabled:
            return {"message": "插件未启用", "started": False}
        started = self._dispatch_run("run_once", "剧情更新器API触发")
        if started is False:
            return {"message": "任务加入失败：插件未启用或调度器未运行", "started": False}
        return {"message": "剧情简介更新任务已加入队列", "started": True}

    def get_service(self) -> List[Dict[str, Any]]:
        """注册插件公共服务"""
        if self._enabled and self._cron:
            try:
                from apscheduler.triggers.cron import CronTrigger
                return [{
                    "id": "TmdbStoryliner",
                    "name": "TMDB剧情简介更新器",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.update_storylines,
                    "kwargs": {}
                }]
            except Exception as e:
                logger.error(f"注册公共服务失败：{e}")
        return []

    def stop_service(self):
        """退出插件：取消任务并保存缓存，不禁用插件"""
        try:
            Scheduler().remove_plugin_job(self.__class__.__name__)
            remove_once = getattr(scheduler_sdk, "remove_plugin_once_job", None)
            if remove_once:
                remove_once(self.__class__.__name__, "run_once")
                remove_once(self.__class__.__name__, "onlyonce_run")
        except Exception as e:
            logger.error(f"停止插件服务失败：{e}")
        finally:
            self._save_cache_and_history()

    # ------------------------------------------------------------------
    # 表单与详情页
    # ------------------------------------------------------------------
    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """拼装插件配置页面"""
        # 获取媒体库路径选项
        library_path_options = []
        try:
            library_path_options = self._get_library_paths()
        except Exception as e:
            logger.error(f"获取媒体库路径选项失败：{e}")

        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'enabled', 'label': '启用插件'},
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'onlyonce', 'label': '立即运行一次'},
                                }]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VTextField',
                                    'props': {'model': 'cron', 'label': '执行周期', 'placeholder': '0 2 * * *'},
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VSelect',
                                    'props': {
                                        'model': 'translate_service',
                                        'label': '翻译服务',
                                        'items': [
                                            {'title': 'Google翻译（免账号）', 'value': 'google'},
                                            {'title': 'AI翻译（OpenAI兼容渠道）', 'value': 'ai'},
                                        ]
                                    },
                                }]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VTextField',
                                    'props': {'model': 'tmdb_api_key', 'label': 'TMDB API 密钥',
                                              'placeholder': '请输入TMDB API密钥'},
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VTextField',
                                    'props': {'model': 'siliconflow_api_key', 'label': 'AI翻译 API密钥',
                                              'placeholder': 'OpenAI兼容渠道Key（SiliconFlow/OpenRouter等），用AI翻译时必填'},
                                }]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [{
                                    'component': 'VSelect',
                                    'props': {
                                        'multiple': True,
                                        'chips': True,
                                        'clearable': True,
                                        'model': 'library_paths',
                                        'label': '媒体库目录',
                                        'items': library_path_options,
                                    },
                                }]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'update_series', 'label': '更新电视剧'},
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'enable_notify', 'label': '启用推送'},
                                }]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'update_episode_image', 'label': '更新剧集图片（暂未实现）'},
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'update_episode_rating', 'label': '更新剧集评分'},
                                }]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'update_episode_premieredate', 'label': '更新播出日期'},
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VSwitch',
                                    'props': {'model': 'update_episode_credits', 'label': '更新演职人员（暂未实现）'},
                                }]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VTextField',
                                    'props': {'model': 'siliconflow_model', 'label': 'AI模型',
                                              'placeholder': '如: Qwen/Qwen2.5-7B-Instruct 或 meta-llama/llama-3.3-70b-instruct:free'},
                                }]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [{
                                    'component': 'VTextField',
                                    'props': {'model': 'ai_base_url', 'label': 'AI API地址（Base URL）',
                                              'placeholder': '如: https://api.openrouter.ai/v1，留空默认SiliconFlow'},
                                }]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [{
                                    'component': 'VAlert',
                                    'props': {'type': 'info', 'variant': 'tonal'},
                                    'content': [{
                                        'component': 'span',
                                        'text': '注意：需要配置TMDB API密钥才能正常使用此插件',
                                    }]
                                }]
                            },
                        ]
                    },
                ]
            }
        ], self._config_dict()

    def get_page(self) -> List[dict]:
        """拼装插件详情页面"""
        historys = self.get_data('history')
        if not historys or not isinstance(historys, list):
            return [{
                'component': 'div',
                'text': '暂无数据',
                'props': {'class': 'text-center'},
            }]

        # 数据按时间降序排列，并转换为 VTable 纯字典行
        historys = sorted(historys, key=lambda x: x.get('time') or "", reverse=True)
        items = [{
            'time': h.get('time'),
            'title': h.get('title'),
            'type': h.get('type'),
            'status': h.get('status'),
        } for h in historys]

        return [{
            'component': 'VRow',
            'content': [{
                'component': 'VCol',
                'props': {'cols': 12},
                'content': [{
                    'component': 'VTable',
                    'props': {
                        'hover': True,
                        'headers': [
                            {'title': '时间', 'key': 'time', 'align': 'start'},
                            {'title': '标题', 'key': 'title', 'align': 'start'},
                            {'title': '类型', 'key': 'type', 'align': 'start'},
                            {'title': '状态', 'key': 'status', 'align': 'start'},
                        ],
                        'items': items,
                        'class': 'overflow-hidden',
                    },
                }]
            }]
        }]

    # ------------------------------------------------------------------
    # 媒体服务器访问
    # ------------------------------------------------------------------
    def service_infos(self, type_filter: Optional[str] = None) -> Optional[Dict[str, ServiceInfo]]:
        """获取已连接的媒体服务器"""
        try:
            services = MediaServerHelper().get_services(type_filter=type_filter)
            if not services:
                logger.warning("MediaServerHelper未能获取到媒体服务器实例")
                return None

            active_services = {}
            for service_name, service_info in services.items():
                if service_info.instance.is_inactive():
                    logger.warning(f"媒体服务{service_name}未连接")
                else:
                    active_services[service_name] = service_info

            if not active_services:
                logger.warning("没有已连接的媒体服务器")
                return None

            logger.debug(f"获取到 {len(active_services)} 个活跃媒体服务器")
            return active_services
        except Exception as e:
            logger.error(f"获取媒体服务器服务失败：{e}")
            return None

    def _get_library_paths(self) -> List[dict]:
        """获取媒体库路径列表（仅返回真实媒体库，不伪造数据）"""
        library_paths = []

        # 优先通过 run_module 获取媒体服务器服务
        try:
            service_infos = self.chain.run_module("mediaserver_services")
            if service_infos:
                mediaserver_chain = MediaServerChain()
                for server_name in service_infos:
                    try:
                        libraries = mediaserver_chain.librarys(server_name)
                        for library in libraries or []:
                            library_paths.append({
                                "title": f"{server_name} - {library.name}",
                                "value": f"{server_name}:{library.id}",
                            })
                    except Exception as e:
                        logger.error(f"获取媒体服务器 {server_name} 的媒体库信息失败：{e}")
        except Exception as e:
            logger.error(f"通过run_module获取媒体服务器服务失败：{e}")

        # 备选：MediaServerHelper 配置列表
        if not library_paths:
            try:
                server_configs = MediaServerHelper().get_configs().values()
                mediaserver_chain = MediaServerChain()
                for server_config in server_configs:
                    try:
                        libraries = mediaserver_chain.librarys(server_config.name)
                        for library in libraries or []:
                            library_paths.append({
                                "title": f"{server_config.name} - {library.name}",
                                "value": f"{server_config.name}:{library.id}",
                            })
                    except Exception as e:
                        logger.error(f"获取媒体服务器 {server_config.name} 的媒体库信息失败：{e}")
            except Exception as e:
                logger.error(f"通过MediaServerHelper获取媒体库信息失败：{e}")

        if not library_paths:
            logger.warning("未能获取到任何媒体库选项")
        return library_paths

    def get_iteminfo(self, server: str, server_type: str, itemid: str) -> dict:
        """获得媒体项详情"""
        service_infos = self._cached_service_infos or self.service_infos()
        if not service_infos:
            logger.warning("未找到媒体服务器实例")
            return {}

        service = service_infos.get(server)
        if not service:
            logger.warning(f"未找到媒体服务器 {server} 的实例")
            return {}

        def __get_emby_iteminfo() -> dict:
            try:
                url = f'[HOST]emby/Users/[USER]/Items/{itemid}?' \
                      f'Fields=ChannelMappingInfo&api_key=[APIKEY]'
                res = service.instance.get_data(url=url)
                if res:
                    return res.json()
            except Exception as err:
                logger.error(f"获取Emby媒体项详情失败：{str(err)}")
            return {}

        def __get_jellyfin_iteminfo() -> dict:
            try:
                url = f'[HOST]Users/[USER]/Items/{itemid}?Fields=ChannelMappingInfo&api_key=[APIKEY]'
                res = service.instance.get_data(url=url)
                if res:
                    result = res.json()
                    if result:
                        result['FileName'] = Path(result['Path']).name
                    return result
            except Exception as err:
                logger.error(f"获取Jellyfin媒体项详情失败：{str(err)}")
            return {}

        def __get_plex_iteminfo() -> dict:
            iteminfo = {}
            try:
                plexitem = service.instance.get_plex().library.fetchItem(ekey=itemid)
                if 'movie' in plexitem.METADATA_TYPE:
                    iteminfo['Type'] = 'Movie'
                    iteminfo['IsFolder'] = False
                elif 'episode' in plexitem.METADATA_TYPE:
                    iteminfo['Type'] = 'Series'
                    iteminfo['IsFolder'] = False
                    if 'show' in plexitem.TYPE:
                        iteminfo['ChildCount'] = plexitem.childCount
                iteminfo['Name'] = plexitem.title
                iteminfo['Id'] = plexitem.key
                iteminfo['ProductionYear'] = plexitem.year
                iteminfo['ProviderIds'] = {}
                for guid in plexitem.guids:
                    idlist = str(guid.id).split(sep='://')
                    if len(idlist) < 2:
                        continue
                    iteminfo['ProviderIds'][idlist[0]] = idlist[1]
                for location in plexitem.locations:
                    iteminfo['Path'] = location
                    iteminfo['FileName'] = Path(location).name
                iteminfo['Overview'] = plexitem.summary
                iteminfo['CommunityRating'] = plexitem.audienceRating
                return iteminfo
            except Exception as err:
                logger.error(f"获取Plex媒体项详情失败：{str(err)}")
            return {}

        if server_type == "emby":
            return __get_emby_iteminfo()
        elif server_type == "jellyfin":
            return __get_jellyfin_iteminfo()
        else:
            return __get_plex_iteminfo()

    def set_iteminfo(self, server: str, server_type: str, itemid: str, iteminfo: dict):
        """更新媒体项详情"""
        service_infos = self._cached_service_infos or self.service_infos()
        if not service_infos:
            logger.warning("未找到媒体服务器实例")
            return False

        service = service_infos.get(server)
        if not service:
            logger.warning(f"未找到媒体服务器 {server} 的实例")
            return False

        def __set_emby_iteminfo():
            try:
                res = service.instance.post_data(
                    url=f'[HOST]emby/Items/{itemid}?api_key=[APIKEY]&reqformat=json',
                    data=json.dumps(iteminfo),
                    headers={"Content-Type": "application/json"}
                )
                if res and res.status_code in [200, 204]:
                    return True
                logger.error(f"更新Emby媒体项详情失败，错误码：{res.status_code if res else '无响应'}")
            except Exception as err:
                logger.error(f"更新Emby媒体项详情失败：{str(err)}")
            return False

        def __set_jellyfin_iteminfo():
            try:
                res = service.instance.post_data(
                    url=f'[HOST]Items/{itemid}?api_key=[APIKEY]',
                    data=json.dumps(iteminfo),
                    headers={"Content-Type": "application/json"}
                )
                if res and res.status_code in [200, 204]:
                    return True
                logger.error(f"更新Jellyfin媒体项详情失败，错误码：{res.status_code if res else '无响应'}")
            except Exception as err:
                logger.error(f"更新Jellyfin媒体项详情失败：{str(err)}")
            return False

        def __set_plex_iteminfo():
            try:
                plexitem = service.instance.get_plex().library.fetchItem(ekey=itemid)
                plexitem.editSummary(iteminfo['Overview']).reload()
                return True
            except Exception as err:
                logger.error(f"更新Plex媒体项详情失败：{str(err)}")
            return False

        if server_type == "emby":
            return __set_emby_iteminfo()
        elif server_type == "jellyfin":
            return __set_jellyfin_iteminfo()
        else:
            return __set_plex_iteminfo()

    def _get_items(self, server: str, server_type: str, parentid: str, mtype: Optional[str] = None) -> dict:
        """获得媒体的所有子媒体项"""
        service_infos = self._cached_service_infos or self.service_infos()
        if not service_infos:
            logger.warning("未找到媒体服务器实例")
            return {}

        service = service_infos.get(server)
        if not service:
            logger.warning(f"未找到媒体服务器 {server} 的实例")
            return {}

        def __get_emby_items() -> dict:
            try:
                if parentid:
                    url = f'[HOST]emby/Users/[USER]/Items?ParentId={parentid}&api_key=[APIKEY]'
                else:
                    url = '[HOST]emby/Users/[USER]/Items?api_key=[APIKEY]'
                res = service.instance.get_data(url=url)
                if res:
                    return res.json()
            except Exception as err:
                logger.error(f"获取Emby媒体的所有子媒体项失败：{str(err)}")
            return {}

        def __get_jellyfin_items() -> dict:
            try:
                if parentid:
                    url = f'[HOST]Users/[USER]/Items?ParentId={parentid}&api_key=[APIKEY]'
                else:
                    url = '[HOST]Users/[USER]/Items?api_key=[APIKEY]'
                res = service.instance.get_data(url=url)
                if res:
                    return res.json()
            except Exception as err:
                logger.error(f"获取Jellyfin媒体的所有子媒体项失败：{str(err)}")
            return {}

        def __get_plex_items() -> dict:
            items = {}
            try:
                plex = service.instance.get_plex()
                items['Items'] = []
                if parentid:
                    if mtype and 'Season' in mtype:
                        plexitem = plex.library.fetchItem(ekey=parentid)
                        for season in plexitem.seasons():
                            items['Items'].append({
                                'Name': season.title,
                                'Id': season.key,
                                'IndexNumber': season.seasonNumber,
                                'Overview': season.summary,
                            })
                    elif mtype and 'Episode' in mtype:
                        plexitem = plex.library.fetchItem(ekey=parentid)
                        for episode in plexitem.episodes():
                            items['Items'].append({
                                'Name': episode.title,
                                'Id': episode.key,
                                'IndexNumber': episode.episodeNumber,
                                'Overview': episode.summary,
                                'CommunityRating': episode.audienceRating,
                            })
                    else:
                        plexitems = plex.library.sectionByID(sectionID=parentid)
                        for plexitem in plexitems.all():
                            item = {}
                            if 'movie' in plexitem.METADATA_TYPE:
                                item['Type'] = 'Movie'
                                item['IsFolder'] = False
                            elif 'episode' in plexitem.METADATA_TYPE:
                                item['Type'] = 'Series'
                                item['IsFolder'] = False
                            item['Name'] = plexitem.title
                            item['Id'] = plexitem.key
                            items['Items'].append(item)
                else:
                    plexitems = plex.library.sections()
                    for plexitem in plexitems:
                        item = {}
                        if 'Directory' in plexitem.TAG:
                            item['Type'] = 'Folder'
                            item['IsFolder'] = True
                        elif 'movie' in plexitem.METADATA_TYPE:
                            item['Type'] = 'Movie'
                            item['IsFolder'] = False
                        elif 'episode' in plexitem.METADATA_TYPE:
                            item['Type'] = 'Series'
                            item['IsFolder'] = False
                        item['Name'] = plexitem.title
                        item['Id'] = plexitem.key
                        items['Items'].append(item)
                return items
            except Exception as err:
                logger.error(f"获取Plex媒体的所有子媒体项失败：{str(err)}")
            return {}

        if server_type == "emby":
            return __get_emby_items()
        elif server_type == "jellyfin":
            return __get_jellyfin_items()
        else:
            return __get_plex_items()


    # ------------------------------------------------------------------
    # 更新主流程
    # ------------------------------------------------------------------
    def update_storylines(self):
        """更新剧情简介主方法"""
        if not self._enabled:
            logger.info("插件已禁用，停止执行")
            return
        # 防止定时/手动/API触发的任务重入
        if not self._run_guard.acquire(blocking=False):
            logger.info("已有更新任务在执行，跳过本次触发")
            return
        try:
            logger.info("开始更新TMDB剧情简介")
            try:
                if self._update_series:
                    self.update_series_storylines()
            finally:
                self._save_cache_and_history()
            logger.info("TMDB剧情简介更新完成")
        finally:
            self._run_guard.release()

    def _check_run_conditions(self) -> bool:
        """检查运行条件：插件是否启用"""
        if not self._enabled:
            logger.info("插件已禁用，停止执行")
            return False
        return True

    @staticmethod
    def _is_tv_item(series) -> bool:
        """判断媒体服务器项目是否为电视剧。

        MediaServerItem.item_type 取值跨服务器不一致：
        Emby/Jellyfin 为 "Series"，Plex 为 "show"。
        """
        item_type = str(getattr(series, 'item_type', '') or '')
        if not item_type:
            # 未提供类型时按电视剧处理（本插件只处理剧集）
            return True
        return item_type.lower() in ('series', 'show', 'tv')

    @staticmethod
    def _get_tmdb_id(series) -> Optional[int]:
        """读取条目的 TMDB ID。

        V3 的 MediaServerItem 移除了 tmdbid 字段，改为统一身份对
        media_source + media_id（仅保留一个来源，TMDB 优先级最高）；
        兼容仍带旧 tmdbid 字段的数据。
        """
        legacy = getattr(series, 'tmdbid', None)
        if legacy:
            try:
                return int(legacy)
            except (TypeError, ValueError):
                return None
        source = getattr(series, 'media_source', None)
        if source is None:
            return None
        # MediaSource 枚举的 str() 为传输值 themoviedb；也兼容直接是字符串的情况
        if str(getattr(source, 'value', source)) != 'themoviedb':
            return None
        media_id = getattr(series, 'media_id', None)
        if not media_id:
            return None
        try:
            return int(str(media_id).strip())
        except ValueError:
            return None

    @staticmethod
    def _parse_episode_key(key: str) -> Optional[Tuple[int, int]]:
        """解析 "S01E02" 形式的剧集 key"""
        try:
            season_part, episode_part = key[1:].split('E', 1)
            return int(season_part), int(episode_part)
        except Exception:
            return None

    def _collect_episode_items(self, server_name: str, server_type: str,
                               series_item_id: str) -> Dict[str, dict]:
        """从媒体服务器收集该剧所有剧集，返回 {SxxEyy: item} 映射"""
        episode_items: Dict[str, dict] = {}
        try:
            season_items = self._get_items(server_name, server_type, series_item_id, 'Season')
            for season_item in (season_items or {}).get("Items", []):
                season_index = season_item.get('IndexNumber')
                if season_index is None:
                    continue
                episodes_in_season = self._get_items(server_name, server_type,
                                                     season_item.get('Id'), 'Episode')
                for episode_item in (episodes_in_season or {}).get("Items", []):
                    episode_index = episode_item.get('IndexNumber')
                    if episode_index is None:
                        continue
                    key = f"S{int(season_index):02d}E{int(episode_index):02d}"
                    episode_items[key] = episode_item
        except Exception as e:
            logger.warning(f"获取剧集项目信息失败: {e}")
        return episode_items

    def update_series_storylines(self):
        """更新电视剧剧情简介"""
        logger.info("开始更新电视剧剧情简介")
        if not self._check_run_conditions():
            return

        service_infos = self.service_infos()
        self._cached_service_infos = service_infos
        if not service_infos:
            logger.warning("没有配置或连接媒体服务器")
            return

        try:
            mediaserver_chain = MediaServerChain()
            for server_name, server_info in service_infos.items():
                if not self._check_run_conditions():
                    return
                libraries = mediaserver_chain.librarys(server_name)
                for library in libraries or []:
                    if not self._check_run_conditions():
                        return
                    # 如果用户指定了媒体库路径，则检查是否匹配
                    if self._library_paths and f"{server_name}:{library.id}" not in self._library_paths:
                        continue

                    tv_series = [item for item in mediaserver_chain.items(server_name, library.id) if item]
                    logger.info(f"媒体库 {library.name} 中找到 {len(tv_series)} 个项目")

                    for series in tv_series:
                        if not self._check_run_conditions():
                            return
                        if not self._is_tv_item(series):
                            continue
                        tmdb_id = self._get_tmdb_id(series)
                        if not tmdb_id:
                            logger.warning(f"项目 {getattr(series, 'title', '未知')} 缺少TMDB ID，跳过处理")
                            continue
                        self._process_series(mediaserver_chain, server_name, server_info, series, tmdb_id)
        except Exception as e:
            logger.error(f"更新电视剧剧情简介时发生错误：{e}")
        finally:
            self._cached_service_infos = None

        logger.info("电视剧剧情简介更新完成")

    def _process_series(self, mediaserver_chain, server_name: str, server_info,
                        series, tmdb_id: int) -> None:
        """处理单部电视剧：拉取TMDB信息并逐集更新"""
        logger.info(f"开始处理电视剧: {series.title}")

        # 1. 从TMDB获取电视剧详情（带重试）
        series_details = None
        for i in range(3):
            if not self._check_run_conditions():
                return
            series_details = self.get_tmdb_series_details(tmdb_id)
            if series_details:
                break
            logger.warning(f"获取电视剧 {series.title} 的TMDB信息失败，正在进行第{i + 1}次重试")
            time.sleep(1)

        if not series_details:
            logger.warning(f"无法获取电视剧 {series.title} 的TMDB信息")
            return

        # 2. 填充完结状态缓存（供跳过间隔判断使用）
        try:
            self._is_series_ended(series_details, tmdb_id)
        except Exception as e:
            logger.debug(f"判断剧集完结状态失败: {e}")

        # 3. 收集媒体服务器中的剧集ID映射
        episode_items = self._collect_episode_items(server_name, server_info.type, series.item_id)
        logger.debug(f"电视剧 {series.title} 媒体服务器共 {len(episode_items)} 集")

        # 4. 合并工作集：chain.episodes 提供的季集 + 媒体服务器实际存在的剧集
        work_keys = set()
        try:
            seasons = mediaserver_chain.episodes(server_name, series.item_id) or []
            for season in seasons:
                season_number = getattr(season, 'season', None)
                episodes_list = getattr(season, 'episodes', None) or []
                if season_number is None:
                    logger.warning(f"季信息不完整: {series.title}，跳过该季")
                    continue
                for episode_number in episodes_list:
                    if isinstance(episode_number, (int, float)):
                        work_keys.add((int(season_number), int(episode_number)))
        except Exception as e:
            logger.warning(f"获取剧集信息失败: {e}")

        for key in episode_items:
            parsed = self._parse_episode_key(key)
            if parsed:
                work_keys.add(parsed)

        # 5. 扩展信息开关（图片/评分/播出日期/演职人员）对所有路径统一生效
        use_extended = (self._update_episode_image or self._update_episode_rating
                        or self._update_episode_premieredate or self._update_episode_credits)

        for season_number, episode_number in sorted(work_keys):
            if not self._check_run_conditions():
                return
            key = f"S{season_number:02d}E{episode_number:02d}"
            item_id = (episode_items.get(key) or {}).get('Id')
            self._update_one_episode(server_name, server_info.type, series, tmdb_id,
                                     season_number, episode_number, item_id, use_extended)

    def _update_one_episode(self, server_name: str, server_type: str, series,
                            tmdb_id: int, season_number: int, episode_number: int,
                            item_id: Optional[str], use_extended: bool) -> None:
        """更新单集的标题与剧情简介（所有路径共用的唯一实现）"""
        episode_label = f"{series.title} S{season_number:02d}E{episode_number:02d}"

        if not item_id:
            logger.warning(f"缺少媒体服务器剧集ID，跳过 {episode_label}")
            self.save_update_history(episode_label, "电视剧剧集", "失败(缺少剧集ID)")
            return

        # 1. 获取TMDB剧集详情（带重试）
        episode_details = None
        for i in range(5):
            if not self._check_run_conditions():
                return
            episode_details = self.get_tmdb_episode_details(
                tmdb_id, season_number, episode_number, extended=use_extended)
            if episode_details:
                break
            logger.warning(f"获取 {episode_label} 的TMDB信息失败，正在进行第{i + 1}次重试")
            time.sleep(5)

        if not episode_details:
            logger.warning(f"无法获取 {episode_label} 的TMDB信息")
            self.save_update_history(episode_label, "电视剧剧集", "失败(无TMDB信息)")
            return

        overview = episode_details.get('overview', '').strip()
        name = episode_details.get('name', '').strip()
        need_translate = episode_details.get('_need_translate', False)

        if not overview and not name:
            logger.debug(f"{episode_label} 没有剧情简介和标题")
            self._update_history_record(tmdb_id, season_number, episode_number, "skipped")
            return

        # 2. 获取媒体服务器中的现有信息并判断是否跳过
        iteminfo = self.get_iteminfo(server_name, server_type, item_id)
        if not iteminfo:
            logger.error(f"获取 {episode_label} 详情失败")
            self._update_history_record(tmdb_id, season_number, episode_number, "failed")
            return

        if self._should_skip_episode(iteminfo, episode_details, tmdb_id,
                                     season_number, episode_number):
            logger.info(f"跳过更新 {episode_label} - 内容一致或未到更新时间")
            self._update_history_record(tmdb_id, season_number, episode_number, "skipped")
            self.save_update_history(episode_label, "电视剧剧集", "已跳过")
            return

        # 3. 翻译
        translated_overview, translated_name = self._translate_fields(
            overview, name, need_translate, episode_label)

        # 4. 更新字段
        if overview:
            iteminfo['Overview'] = translated_overview
        if name:
            iteminfo['Name'] = translated_name

        if use_extended:
            self._apply_extended_fields(iteminfo, episode_details, episode_label)

        # 5. 保存
        if self.set_iteminfo(server_name, server_type, item_id, iteminfo):
            logger.info(f"已更新 {episode_label} 标题和剧情简介")
            self._update_history_record(tmdb_id, season_number, episode_number, "updated")

            if self._enable_notify:
                self.post_message(
                    mtype=NotificationType.Plugin,
                    title="【剧情信息更新啦】🎉",
                    text=f"📺 剧集 {episode_label} 已更新\n"
                         f"标题：{translated_name}\n"
                         f"剧情简介：{translated_overview[:100]}"
                         f"{'...' if len(translated_overview) > 100 else ''}"
                )
        else:
            logger.error(f"更新 {episode_label} 标题和剧情简介失败")
            self._update_history_record(tmdb_id, season_number, episode_number, "failed")

        has_translation = (translated_overview != overview) or (translated_name != name)
        self.save_update_history(
            episode_label, "电视剧剧集",
            "已翻译并更新" if has_translation else "已更新原始内容")

    def _apply_extended_fields(self, iteminfo: dict, episode_details: dict,
                               episode_label: str) -> None:
        """应用扩展字段：评分/播出日期（图片与演职人员暂未实现）"""
        # 更新剧集图片（占位：Emby/Jellyfin 需要单独的图片上传接口，暂不实现）
        if self._update_episode_image and episode_details.get('still_url'):
            logger.debug(f"{episode_label} 剧集图片更新暂未实现: {episode_details.get('still_url')}")

        # 更新播出评分
        if self._update_episode_rating:
            vote_average = episode_details.get('vote_average') or 0
            if vote_average and vote_average > 0:
                iteminfo['CommunityRating'] = vote_average

        # 更新播出日期
        if self._update_episode_premieredate and episode_details.get('air_date'):
            air_date = episode_details.get('air_date')
            iteminfo['PremiereDate'] = air_date
            iteminfo['ProductionYear'] = air_date[:4] if len(air_date) >= 4 else air_date

        # 更新演职人员（占位：需按媒体服务器分别实现，暂不写入）
        if self._update_episode_credits:
            guest_stars = episode_details.get('guest_stars') or []
            crew = episode_details.get('crew') or []
            if guest_stars or crew:
                logger.debug(f"{episode_label} 演职人员信息更新暂未实现: "
                             f"guest_stars={len(guest_stars)}, crew={len(crew)}")

    def _translate_fields(self, overview: str, name: str, need_translate: bool,
                          episode_label: str) -> Tuple[str, str]:
        """按配置的翻译服务处理简介与标题"""
        translated_overview = overview
        translated_name = name

        if self._translate_service == "google":
            translator = self.translate_text
        elif self._translate_service == "ai":
            translator = self.ai_translate_text
        else:
            logger.debug(f"{episode_label} 未配置翻译服务，跳过翻译")
            return translated_overview, translated_name

        if overview and (need_translate or not self._is_chinese(overview)):
            logger.info(f"{episode_label} 剧情简介需要翻译: {overview[:50]}...")
            translated_overview = self._combine_translation_with_original(
                translator(overview), overview, False)

        if name and (need_translate or not self._is_chinese(name)):
            logger.info(f"{episode_label} 标题需要翻译: {name}")
            translated_name = self._combine_translation_with_original(
                translator(name), name, True)

        return translated_overview, translated_name

    # ------------------------------------------------------------------
    # TMDB 访问
    # ------------------------------------------------------------------
    def get_tmdb_series_details(self, series_id: int) -> dict:
        """获取电视剧详情"""
        try:
            url = f"https://api.themoviedb.org/3/tv/{series_id}"
            params = {
                "api_key": self._tmdb_api_key,
                "language": "en-US"
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取电视剧详情失败：{e}")
            return {}

    def get_tmdb_episode_details(self, series_id: int, season_number: int,
                                 episode_number: int, extended: bool = False) -> dict:
        """获取剧集详情（zh-CN 优先，缺失时回退英文并标记需翻译）。

        :param extended: 是否附带评分/播出日期/图片/演职人员等扩展字段
        """
        append_to_response = "credits,images" if extended else None

        for retry in range(5):
            try:
                url = (f"https://api.themoviedb.org/3/tv/{series_id}"
                       f"/season/{season_number}/episode/{episode_number}")
                params = {
                    "api_key": self._tmdb_api_key,
                    "language": "zh-CN",
                }
                if append_to_response:
                    params["append_to_response"] = append_to_response
                response = requests.get(url, params=params, timeout=30)
                if response.status_code == 404:
                    # TMDB 不存在该集（本地季集编号与 TMDB 不一致），属永久失败，不重试
                    logger.info(f"TMDB 无此集 {series_id} S{season_number:02d}E{episode_number:02d}，跳过")
                    return {'overview': '', 'name': '', '_need_translate': False,
                            '_not_found': True}
                response.raise_for_status()
                result = response.json()

                # 中文内容处理
                overview = (result.get('overview') or '').strip()
                name = (result.get('name') or '').strip()

                # 中文不完整或非中文时，回退英文内容补充
                need_english_content = False
                if not overview or not name:
                    need_english_content = True
                elif (overview and not self._is_chinese(overview)) or \
                        (name and not self._is_chinese(name)):
                    need_english_content = True

                if need_english_content:
                    english_result = self._get_english_episode_details(
                        series_id, season_number, episode_number)
                    if not overview and english_result.get('overview'):
                        overview = english_result['overview']
                    if not name and english_result.get('name'):
                        name = english_result['name']
                    result['_need_translate'] = english_result.get('_need_translate', False) or (
                        (overview and not self._is_chinese(overview)) or
                        (name and not self._is_chinese(name))
                    )
                else:
                    result['_need_translate'] = (
                        (overview and overview.isascii()) or
                        (name and name.isascii()) or
                        (overview and not self._is_chinese(overview)) or
                        (name and not self._is_chinese(name))
                    )

                result['overview'] = overview
                result['name'] = name

                # 扩展字段
                if extended:
                    result.update(self._extract_extended_fields(result))

                return result
            except Exception as e:
                logger.warning(f"第{retry + 1}次获取剧集详情失败: {e}")
                if retry < 4:
                    time.sleep(5)
                else:
                    logger.error(f"获取剧集详情完全失败：{e}")
                    return {'overview': '', 'name': '', '_need_translate': False}

    @staticmethod
    def _extract_extended_fields(result: dict) -> dict:
        """从TMDB响应中提取扩展字段"""
        still_path = result.get('still_path') or ''
        credits_info = result.get('credits') or {}
        return {
            'vote_average': result.get('vote_average') or 0,
            'vote_count': result.get('vote_count') or 0,
            'air_date': result.get('air_date') or '',
            'still_url': f"https://image.tmdb.org/t/p/original{still_path}" if still_path else "",
            'guest_stars': credits_info.get('guest_stars') or [],
            'crew': credits_info.get('crew') or [],
        }

    def _get_english_episode_details(self, series_id: int, season_number: int,
                                     episode_number: int) -> dict:
        """获取英文剧集详情"""
        for retry in range(5):
            try:
                url = (f"https://api.themoviedb.org/3/tv/{series_id}"
                       f"/season/{season_number}/episode/{episode_number}")
                params = {
                    "api_key": self._tmdb_api_key,
                    "language": "en-US"
                }
                response = requests.get(url, params=params, timeout=30)
                if response.status_code == 404:
                    return {'overview': '', 'name': '', '_need_translate': False,
                            '_not_found': True}
                response.raise_for_status()
                result = response.json()
                result['_need_translate'] = True
                result['overview'] = (result.get('overview') or '').strip()
                result['name'] = (result.get('name') or '').strip()
                return result
            except Exception as e:
                logger.warning(f"第{retry + 1}次获取英文剧集详情失败: {e}")
                if retry < 4:
                    time.sleep(5)
                else:
                    logger.error(f"获取英文剧集详情完全失败：{e}")
                    return {'overview': '', 'name': '', '_need_translate': False}

    # ------------------------------------------------------------------
    # 翻译
    # ------------------------------------------------------------------
    def translate_text(self, text: str, source_lang: str = "en", target_lang: str = "zh") -> str:
        """使用配置的翻译服务翻译文本"""
        if not text or source_lang == target_lang:
            return text
        try:
            if self._translate_service == "google":
                return self._google_translate(text, source_lang, target_lang)
            logger.warning(f"不支持的翻译服务：{self._translate_service}")
            return text
        except Exception as e:
            logger.error(f"翻译失败：{e}")
            return text

    def _google_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Google翻译（免账号）"""
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx",
                "sl": source_lang,
                "tl": target_lang,
                "dt": "t",
                "q": text
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result and len(result) > 0 and result[0]:
                translated_text = ""
                for item in result[0]:
                    if item and len(item) > 0 and item[0]:
                        translated_text += item[0]
                if translated_text.strip():
                    return translated_text
                logger.warning("Google翻译返回空结果")
                return text

            logger.error(f"Google翻译返回错误：{result}")
            return text
        except Exception as e:
            logger.error(f"Google翻译失败：{e}")
            return text

    def ai_translate_text(self, text: str, source_lang: str = "en", target_lang: str = "zh") -> str:
        """使用SiliconFlow AI翻译文本"""
        if not text or not self._siliconflow_api_key:
            return text

        try:
            prompt = f"""你是一位专业的影视翻译人员，请将以下{source_lang}影视内容翻译成{target_lang}：

{text}

翻译要求：
1. 将所有英文内容翻译成中文，包括人名、地名、专有名词等
2. 保持原意不变，语句通顺自然
3. 影视行业术语请使用标准中文译名
4. 保持特殊格式不变（如标点符号、换行等）
5. 仅输出翻译结果，不要添加任何解释或其他内容"""

            # OpenAI兼容渠道：支持 SiliconFlow / OpenRouter / 任意兼容端点
            base_url = (self._ai_base_url or "https://api.siliconflow.cn/v1").strip().rstrip("/")
            if base_url.endswith("/chat/completions"):
                url = base_url
            else:
                url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self._siliconflow_api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": self._siliconflow_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 4096
            }
            response = requests.post(url, headers=headers, json=data, timeout=120)
            response.raise_for_status()
            result = response.json()

            if "choices" in result and len(result["choices"]) > 0:
                translated_text = result["choices"][0]["message"]["content"].strip()
                logger.debug(f"AI翻译成功，结果: {translated_text[:100]}...")
                return translated_text
            logger.error(f"AI翻译返回错误：{result}")
            return text
        except Exception as e:
            logger.error(f"AI翻译失败：{e}")
            return text

    # ------------------------------------------------------------------
    # 缓存与历史
    # ------------------------------------------------------------------
    def _load_cache_and_history(self):
        """加载缓存和历史记录"""
        try:
            series_status_cache = self.get_data('series_status_cache')
            if series_status_cache:
                # JSON 反序列化后键为字符串，统一为 str
                self._series_status_cache = {str(k): v for k, v in series_status_cache.items()}
            update_history = self.get_data('update_history')
            if update_history:
                self._update_history = {str(k): v for k, v in update_history.items()}
        except Exception as e:
            logger.error(f"加载缓存和历史记录失败: {e}")

    def _save_cache_and_history(self):
        """保存缓存和历史记录"""
        try:
            self.save_data('series_status_cache', self._series_status_cache)
            self.save_data('update_history', self._update_history)
        except Exception as e:
            logger.error(f"保存缓存和历史记录失败: {e}")

    def _update_history_record(self, series_id: int, season_number: int,
                               episode_number: int, status: str):
        """更新剧集的历史记录（不立即落库，由任务结束时统一保存）"""
        episode_key = f"{series_id}_S{season_number:02d}E{episode_number:02d}"
        current_time = time.time()

        episode_history = self._update_history.setdefault(episode_key, {
            'last_update': 0,
            'update_count': 0,
            'skip_count': 0,
            'fail_count': 0,
            'last_status': ''
        })

        episode_history['last_update'] = current_time
        episode_history['last_status'] = status

        if status == "updated":
            episode_history['update_count'] += 1
        elif status == "skipped":
            episode_history['skip_count'] += 1
        elif status == "failed":
            episode_history['fail_count'] += 1

    def save_update_history(self, title: str, media_type: str, status: str):
        """保存更新历史（限制容量，避免无限增长）"""
        history = self.get_data('history') or []
        if not isinstance(history, list):
            history = []
        if len(history) > 500:
            history = history[-499:]

        history.append({
            'title': title,
            'type': media_type,
            'status': status,
            'time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        })
        self.save_data('history', history)

    # ------------------------------------------------------------------
    # 跳过策略与文本工具
    # ------------------------------------------------------------------
    def _is_chinese(self, text: str) -> bool:
        """判断文本是否包含中文字符"""
        if not text:
            return False
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':
                return True
        return False

    def _contains_original_and_matches(self, existing_text: str, tmdb_text: str) -> bool:
        """检查本地内容是否已包含原文且与TMDB一致"""
        if not existing_text or not tmdb_text:
            return False

        original_marker = "\n\n[原文："
        if original_marker in existing_text:
            try:
                start_idx = existing_text.index(original_marker) + len(original_marker)
                end_idx = existing_text.index("]", start_idx)
                extracted_original = existing_text[start_idx:end_idx]
                if extracted_original == tmdb_text:
                    return True
            except ValueError:
                pass
        return False

    def _combine_translation_with_original(self, translated_text: str,
                                           original_text: str, is_title: bool = False) -> str:
        """将翻译后的文本与原文结合（标题不附加原文）"""
        if not original_text or is_title:
            return translated_text
        return f"{translated_text}\n\n[原文：{original_text}]"

    def _should_skip_episode(self, iteminfo: dict, episode_details: dict,
                             series_id: int, season_number: int,
                             episode_number: int) -> bool:
        """判断是否应该跳过剧集更新（智能跳过策略）"""
        episode_key = f"{series_id}_S{season_number:02d}E{episode_number:02d}"
        current_time = time.time()

        existing_overview = (iteminfo.get('Overview') or '').strip()
        existing_name = (iteminfo.get('Name') or '').strip()
        tmdb_overview = (episode_details.get('overview') or '').strip()
        tmdb_name = (episode_details.get('name') or '').strip()

        # 1. TMDB没有提供任何信息：跳过，但不把状态记为已更新
        #    （否则TMDB后续补充内容时会被永久跳过）
        if not tmdb_overview and not tmdb_name:
            logger.debug(f"TMDB未提供任何信息，跳过更新 {episode_key}")
            return True

        # 2. 本地已包含原文且与TMDB一致
        if self._contains_original_and_matches(existing_overview, tmdb_overview) and \
           self._contains_original_and_matches(existing_name, tmdb_name):
            logger.debug(f"剧集 {episode_key} 本地内容已包含原文且与TMDB一致，跳过更新")
            return True

        # 3. 本地内容与TMDB内容完全一致
        if existing_overview == tmdb_overview and existing_name == tmdb_name and \
                (tmdb_overview or tmdb_name):
            logger.debug(f"剧集 {episode_key} 现有内容和TMDB内容完全一致，跳过更新")
            return True

        # 4. 本地为空而TMDB有内容：需要更新
        if not existing_overview and tmdb_overview:
            return False
        if not existing_name and tmdb_name:
            return False

        # 5. 按更新间隔跳过（已完结剧集7天，连载剧集1天）
        if episode_key in self._update_history:
            episode_history = self._update_history[episode_key]
            last_update_time = episode_history.get('last_update', 0)
            last_status = episode_history.get('last_status', '')

            if last_status == "updated":
                is_ended = self._series_status_cache.get(str(series_id), {}).get('ended', False)
                update_interval = 7 * 24 * 3600 if is_ended else 24 * 3600
                if current_time - last_update_time < update_interval:
                    logger.debug(f"剧集 {episode_key} 未到更新间隔，跳过更新")
                    return True

        # 默认不跳过
        return False

    def _is_series_ended(self, series_details: dict, series_id: int) -> bool:
        """判断电视剧是否已完结（结果按天缓存）"""
        cache_key = str(series_id)
        current_time = time.time()

        cached_status = self._series_status_cache.get(cache_key)
        if cached_status and current_time - cached_status.get('timestamp', 0) < 86400:
            return cached_status.get('ended', False)

        status = (series_details.get('status') or '').lower()
        if status in ['ended', 'cancelled']:
            result = True
        else:
            next_episode = series_details.get('next_episode_to_air')
            if not next_episode:
                last_air_date = series_details.get('last_air_date')
                if last_air_date:
                    try:
                        from datetime import datetime
                        last_date = datetime.strptime(last_air_date, '%Y-%m-%d')
                        result = (datetime.now() - last_date).days > 365
                    except Exception as e:
                        logger.warning(f"解析最后播出日期失败: {e}")
                        result = False
                else:
                    result = False
            else:
                result = False

        self._series_status_cache[cache_key] = {
            'ended': result,
            'timestamp': current_time
        }
        logger.debug(f"剧集 {series_id} 状态判断结果: {'已完结' if result else '连载中'}")
        return result

