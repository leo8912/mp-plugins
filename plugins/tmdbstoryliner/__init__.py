import json
import requests
import time
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path

from app.plugins import _PluginBase
from app.log import logger
from app.scheduler import Scheduler
from app.helper.mediaserver import MediaServerHelper
from app.chain.mediaserver import MediaServerChain
from app.schemas import ServiceInfo
from app.core.config import settings
from app.core.event import EventManager
from app.schemas.types import EventType, NotificationType, MessageChannel

class TmdbStoryliner(_PluginBase):
    # 插件元数据
    plugin_name = "剧情更新器"
    plugin_desc = "定时从TMDB获取剧集的剧情简介，并将英文内容翻译成中文"
    plugin_icon = "https://raw.githubusercontent.com/leo8912/mp-plugins/main/icons/tmdbstoryliner.png"
    plugin_author = "leo"
    author_url = "https://github.com/leo8912"
    plugin_version = "2.7"
    plugin_locale = "zh"
    plugin_config_prefix = "tmdbstoryliner_"
    plugin_site = "https://www.themoviedb.org/"
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 1
    
    # 插件配置项
    _enabled = False
    _cron = "0 2 * * *"
    _translate_service = "google"
    _tmdb_api_key = ""
    _translate_app_id = ""
    _translate_secret_key = ""
    _update_series = True
    _library_paths = []
    _onlyonce = False
    # 新增配置项
    _update_episode_image = True
    _update_episode_rating = True
    _update_episode_premieredate = True
    _update_episode_credits = True
    # 推送配置
    _enable_notify = True
    # AI翻译配置
    _ai_translate = False
    _siliconflow_api_key = ""
    _siliconflow_model = "Qwen/Qwen2.5-7B-Instruct"
    
    # 添加缓存和历史记录
    _series_status_cache = {}  # 剧集状态缓存
    _update_history = {}       # 更新历史记录
    _start_time = None         # 任务开始时间
    _max_runtime = 3600        # 最大运行时间(秒)，默认1小时
    
    def init_plugin(self, config: Optional[dict] = None):
        """
        初始化插件
        """
        # 停止现有服务
        self.stop_service()
        
        if config:
            self._enabled = config.get("enabled")
            self._cron = config.get("cron")
            self._translate_service = config.get("translate_service")
            self._tmdb_api_key = config.get("tmdb_api_key")
            self._translate_app_id = config.get("translate_app_id")
            self._translate_secret_key = config.get("translate_secret_key")
            # 移除电影更新选项，只保留电视剧更新选项
            self._update_series = config.get("update_series", True)
            self._library_paths = config.get("library_paths") or []
            self._onlyonce = config.get("onlyonce", False)
            # 新增配置项
            self._update_episode_image = config.get("update_episode_image", True)
            self._update_episode_rating = config.get("update_episode_rating", True)
            self._update_episode_premieredate = config.get("update_episode_premieredate", True)
            self._update_episode_credits = config.get("update_episode_credits", True)
            # 推送配置
            self._enable_notify = config.get("enable_notify", True)
            # AI翻译配置
            self._ai_translate = config.get("ai_translate", False)
            self._siliconflow_api_key = config.get("siliconflow_api_key", "")
            self._siliconflow_model = config.get("siliconflow_model", "Qwen/Qwen2.5-7B-Instruct")
            
        # 加载缓存和历史记录
        self._load_cache_and_history()
        
        # 立即运行一次
        if self._onlyonce:
            logger.info("立即运行一次剧情简介更新任务")
            self.update_storylines()
            self._onlyonce = False
            self.update_config({
                "enabled": self._enabled,
                "cron": self._cron,
                "translate_service": self._translate_service,
                "tmdb_api_key": self._tmdb_api_key,
                "translate_app_id": self._translate_app_id,
                "translate_secret_key": self._translate_secret_key,
                "update_series": self._update_series,
                "library_paths": self._library_paths,
                "onlyonce": False,
                # 新增配置项
                "update_episode_image": self._update_episode_image,
                "update_episode_rating": self._update_episode_rating,
                "update_episode_premieredate": self._update_episode_premieredate,
                "update_episode_credits": self._update_episode_credits,
                # 推送配置
                "enable_notify": self._enable_notify,
                # AI翻译配置
                "ai_translate": self._ai_translate,
                "siliconflow_api_key": self._siliconflow_api_key,
                "siliconflow_model": self._siliconflow_model
            })
        
        # 注册定时任务
        if self._enabled and self._cron:
            try:
                # 使用MoviePilot的调度器注册任务
                Scheduler().update_plugin_job("TmdbStoryliner")
                logger.info(f"TMDB剧情简介更新器定时任务已注册：{self._cron}")
            except Exception as e:
                logger.error(f"注册定时任务失败：{e}")
    
    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled if self._enabled is not None else False
    
    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程命令
        """
        return [{
            "cmd": "/tmdb_storyliner",
            "event": "tmdb.storyliner.update",
            "desc": "更新TMDB剧情简介",
            "category": "自动整理",
            "data": {}
        }]
    
    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册API接口
        """
        return [
            {
                "path": "/update_storylines",
                "endpoint": self.update_storylines_api,
                "methods": ["GET"],
                "summary": "手动更新剧情简介",
                "description": "手动触发剧情简介更新任务"
            },

        ]
    

    
    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        """
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
    
    def service_infos(self, type_filter: Optional[str] = None) -> Optional[Dict[str, ServiceInfo]]:
        """
        服务信息
        """
        # 直接使用 MediaServerHelper 获取媒体服务器
        try:
            logger.info("尝试使用MediaServerHelper获取媒体服务器")
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

            logger.info(f"通过MediaServerHelper成功获取到 {len(active_services)} 个活跃媒体服务器")
            return active_services
        except Exception as e:
            logger.error(f"通过MediaServerHelper获取媒体服务器服务失败：{e}")
            return None
    
    def _get_library_paths(self) -> List[dict]:
        """
        获取媒体库路径列表
        """
        library_paths = []
        
        # 使用 run_module 方法获取媒体服务器服务
        try:
            service_infos = self.chain.run_module("mediaserver_services")
            if not service_infos:
                logger.warning("没有已连接的媒体服务器")
            else:
                # 使用MediaServerChain获取真实的媒体库信息
                mediaserver_chain = MediaServerChain()
                
                # 遍历每个配置的媒体服务器
                for server_name, server_info in service_infos.items():
                    # 获取该服务器的所有媒体库
                    try:
                        libraries = mediaserver_chain.librarys(server_name)
                        if libraries:
                            # 遍历每个媒体库
                            for library in libraries:
                                library_paths.append({
                                    "title": f"{server_name} - {library.name}",
                                    "value": f"{server_name}:{library.id}"
                                })
                        else:
                            logger.warning(f"媒体服务器 {server_name} 没有找到媒体库")
                    except Exception as e:
                        logger.error(f"获取媒体服务器 {server_name} 的媒体库信息失败：{e}")
        except Exception as e:
            logger.error(f"通过run_module获取媒体服务器服务失败：{e}")
        
        # 如果通过run_module方式失败，尝试使用MediaServerHelper作为备选方案
        if not library_paths:
            try:
                logger.info("尝试使用MediaServerHelper获取媒体库信息")
                server_configs = MediaServerHelper().get_configs().values()
                if not server_configs:
                    logger.warning("没有配置媒体服务器")
                    return library_paths
                
                # 使用MediaServerChain获取真实的媒体库信息
                mediaserver_chain = MediaServerChain()
                
                # 遍历每个配置的媒体服务器
                for server_config in server_configs:
                    server_name = server_config.name
                    
                    # 获取该服务器的所有媒体库
                    try:
                        libraries = mediaserver_chain.librarys(server_name)
                        if libraries:
                            # 遍历每个媒体库
                            for library in libraries:
                                library_paths.append({
                                    "title": f"{server_name} - {library.name}",
                                    "value": f"{server_name}:{library.id}"
                                })
                        else:
                            # 如果获取失败，使用示例数据
                            library_paths.append({
                                "title": f"{server_name} - 电影库",
                                "value": f"{server_name}:/movies"
                            })
                            library_paths.append({
                                "title": f"{server_name} - 电视剧库",
                                "value": f"{server_name}:/tv"
                            })
                            library_paths.append({
                                "title": f"{server_name} - 纪录片库",
                                "value": f"{server_name}:/documentaries"
                            })
                    except Exception as e:
                        logger.error(f"获取媒体服务器 {server_name} 的媒体库信息失败：{e}")
                        # 如果获取失败，使用示例数据
                        library_paths.append({
                                "title": f"{server_name} - 电影库",
                                "value": f"{server_name}:/movies"
                            })
                        library_paths.append({
                                "title": f"{server_name} - 电视剧库",
                                "value": f"{server_name}:/tv"
                            })
                        library_paths.append({
                                "title": f"{server_name} - 纪录片库",
                                "value": f"{server_name}:/documentaries"
                        })
            except Exception as e:
                logger.error(f"通过MediaServerHelper获取媒体库信息失败：{e}")
        
        return library_paths
    
    def get_iteminfo(self, server: str, server_type: str, itemid: str) -> dict:
        """
        获得媒体项详情
        """
        # 直接使用已获取的service_infos，避免重复获取
        service_infos = self._cached_service_infos if hasattr(self, '_cached_service_infos') else self.service_infos()
        if not service_infos:
            logger.warn(f"未找到媒体服务器实例")
            return {}

        service = service_infos.get(server)
        if not service:
            logger.warn(f"未找到媒体服务器 {server} 的实例")
            return {}

        def __get_emby_iteminfo() -> dict:
            """
            获得Emby媒体项详情
            """
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
            """
            获得Jellyfin媒体项详情
            """
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
            """
            获得Plex媒体项详情
            """
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
        """
        更新媒体项详情
        """
        # 直接使用已获取的service_infos，避免重复获取
        service_infos = self._cached_service_infos if hasattr(self, '_cached_service_infos') else self.service_infos()
        if not service_infos:
            logger.warn(f"未找到媒体服务器实例")
            return False

        service = service_infos.get(server)
        if not service:
            logger.warn(f"未找到媒体服务器 {server} 的实例")
            return False

        def __set_emby_iteminfo():
            """
            更新Emby媒体项详情
            """
            try:
                res = service.instance.post_data(
                    url=f'[HOST]emby/Items/{itemid}?api_key=[APIKEY]&reqformat=json',
                    data=json.dumps(iteminfo),
                    headers={
                        "Content-Type": "application/json"
                    }
                )
                if res and res.status_code in [200, 204]:
                    return True
                else:
                    logger.error(f"更新Emby媒体项详情失败，错误码：{res.status_code}")
                    return False
            except Exception as err:
                logger.error(f"更新Emby媒体项详情失败：{str(err)}")
            return False

        def __set_jellyfin_iteminfo():
            """
            更新Jellyfin媒体项详情
            """
            try:
                res = service.instance.post_data(
                    url=f'[HOST]Items/{itemid}?api_key=[APIKEY]',
                    data=json.dumps(iteminfo),
                    headers={
                        "Content-Type": "application/json"
                    }
                )
                if res and res.status_code in [200, 204]:
                    return True
                else:
                    logger.error(f"更新Jellyfin媒体项详情失败，错误码：{res.status_code}")
                    return False
            except Exception as err:
                logger.error(f"更新Jellyfin媒体项详情失败：{str(err)}")
            return False

        def __set_plex_iteminfo():
            """
            更新Plex媒体项详情
            """
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
    
    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
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
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期',
                                            'placeholder': '0 2 * * *'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'translate_service',
                                            'label': '翻译服务',
                                            'items': [
                                                {'title': 'Google翻译（免账号）', 'value': 'google'},
                                                {'title': 'AI翻译（SiliconFlow）', 'value': 'ai'}
                                            ]
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'tmdb_api_key',
                                            'label': 'TMDB API 密钥',
                                            'placeholder': '请输入TMDB API密钥'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'siliconflow_api_key',
                                            'label': 'SiliconFlow API密钥',
                                            'placeholder': '使用AI翻译时必填'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'clearable': True,
                                            'model': 'library_paths',
                                            'label': '媒体库目录',
                                            'items': library_path_options
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'update_series',
                                            'label': '更新电视剧',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enable_notify',
                                            'label': '启用推送',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'update_episode_image',
                                            'label': '更新剧集图片',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'update_episode_rating',
                                            'label': '更新剧集评分',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'update_episode_premieredate',
                                            'label': '更新播出日期',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'update_episode_credits',
                                            'label': '更新演职人员',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'siliconflow_model',
                                            'label': 'AI模型',
                                            'placeholder': '如: Qwen/Qwen2.5-7B-Instruct'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal'
                                        },
                                        'content': [
                                            {
                                                'component': 'span',
                                                'text': '注意：需要配置TMDB API密钥才能正常使用此插件',
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },

                ]
            }
        ], {
            "enabled": self._enabled,
            "cron": self._cron,
            "translate_service": self._translate_service,
            "tmdb_api_key": self._tmdb_api_key,
            "translate_app_id": self._translate_app_id,
            "translate_secret_key": self._translate_secret_key,
            "update_series": self._update_series,
            "library_paths": self._library_paths,
            "onlyonce": False,
            # 新增配置项
            "update_episode_image": self._update_episode_image,
            "update_episode_rating": self._update_episode_rating,
            "update_episode_premieredate": self._update_episode_premieredate,
            "update_episode_credits": self._update_episode_credits,
            # 推送配置
            "enable_notify": self._enable_notify,
            # AI翻译配置
            "ai_translate": self._ai_translate,
            "siliconflow_api_key": self._siliconflow_api_key,
            "siliconflow_model": self._siliconflow_model
        }
    
    def get_page(self) -> List[dict]:
        """
        拼装插件详情页面，需要返回页面配置，同时附带数据
        """
        # 查询同步详情
        historys = self.get_data('history')
        if not historys:
            return [
                {
                    'component': 'div',
                    'text': '暂无数据',
                    'props': {
                        'class': 'text-center',
                    }
                }
            ]
        # 数据按时间降序排列
        historys = sorted(historys, key=lambda x: x.get('time'), reverse=True)
        # 拼装页面
        contents = [
            {
                'component': 'tr',
                'props': {
                    'class': 'text-sm'
                },
                'content': [
                    {
                        'component': 'td',
                        'props': {
                            'class': 'whitespace-nowrap break-keep text-high-emphasis'
                        },
                        'text': history_item.get("time")
                    },
                    {
                        'component': 'td',
                        'text': history_item.get("title")
                    },
                    {
                        'component': 'td',
                        'text': history_item.get("type")
                    },
                    {
                        'component': 'td',
                        'text': history_item.get("status")
                    }
                ]
            } for history_item in historys
        ]
        
        return [
            {
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {
                            'cols': 12,
                        },
                        'content': [
                            {
                                'component': 'VTable',
                                'props': {
                                    'hover': True,
                                    'headers': [
                                        {'title': '时间', 'key': 'time', 'align': 'start'},
                                        {'title': '标题', 'key': 'title', 'align': 'start'},
                                        {'title': '类型', 'key': 'type', 'align': 'start'},
                                        {'title': '状态', 'key': 'status', 'align': 'start'},
                                    ],
                                    'items': contents,
                                    'class': 'overflow-hidden',
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    
    def stop_service(self):
        """
        退出插件
        """
        try:
            # 通过调度器移除任务
            Scheduler().remove_plugin_job("TmdbStoryliner")
        except Exception as e:
            logger.error(f"停止插件服务失败：{e}")
        finally:
            # 保存缓存和历史记录
            self._save_cache_and_history()
            super().stop_service()
    
    def update_storylines_api(self):
        """
        API接口：手动更新剧情简介
        """
        self.update_storylines()
        return {"message": "剧情简介更新任务已启动"}
    
    def update_storylines(self):
        """
        更新剧情简介主方法
        """
        if not self._enabled:
            return
        
        logger.info("开始更新TMDB剧情简介")
        
        # 设置任务开始时间
        self._start_time = time.time()
        
        # 只更新电视剧，移除电影更新
        if self._update_series:
            self.update_series_storylines()
        
        logger.info("TMDB剧情简介更新完成")
    
    def _check_timeout(self) -> bool:
        """
        检查任务是否超时
        
        :return: True表示超时，False表示未超时
        """
        if self._start_time is None:
            return False
            
        elapsed_time = time.time() - self._start_time
        if elapsed_time > self._max_runtime:
            logger.warning(f"任务执行时间已超过最大运行时间 {self._max_runtime} 秒，停止执行")
            return True
            
        return False
    
    def _check_run_conditions(self) -> bool:
        """
        检查运行条件：插件是否启用以及是否超时
        
        :return: True表示可以继续运行，False表示应该停止
        """
        if not self._enabled:
            logger.info("插件已禁用，停止执行")
            return False
            
        if self._check_timeout():
            return False
            
        return True
    
    def update_series_storylines(self):
        """
        更新电视剧剧情简介
        """
        logger.info("开始更新电视剧剧情简介")
        
        # 检查插件是否应该继续运行
        if not self._check_run_conditions():
            return
            
        # 1. 获取媒体库中的电视剧
        # 获取活动的媒体服务器
        service_infos = self.service_infos()
        # 缓存service_infos以避免重复获取
        self._cached_service_infos = service_infos
        if not service_infos:
            logger.warning("没有配置或连接媒体服务器")
            return
        
        # 使用MediaServerChain获取媒体库中的电视剧
        try:
            mediaserver_chain = MediaServerChain()
            
            # 遍历每个活动的媒体服务器
            for server_name, server_info in service_infos.items():
                # 检查插件是否仍应运行
                if not self._check_run_conditions():
                    return
                    
                # 获取该服务器的所有媒体库
                libraries = mediaserver_chain.librarys(server_name)
                
                # 遍历每个媒体库
                for library in libraries:
                    # 检查插件是否仍应运行
                    if not self._check_run_conditions():
                        return
                        
                    # 如果用户指定了媒体库路径，则检查是否匹配
                    if self._library_paths and f"{server_name}:{library.id}" not in self._library_paths:
                        continue
                    
                    # 获取媒体库中的电视剧
                    tv_series = list(mediaserver_chain.items(server_name, library.id))
                    logger.info(f"在媒体库 {library.name} 中找到 {len(tv_series) if tv_series else 0} 部电视剧")
                    
                    # 遍历每部电视剧
                    for series in tv_series:
                        # 检查插件是否仍应运行
                        if not self._check_run_conditions():
                            return
                            
                        # 检查媒体类型，只处理电视剧类型
                        if hasattr(series, 'type') and series.type != 'TV':
                            continue
                        if not series or not hasattr(series, 'tmdbid') or not series.tmdbid:
                            logger.warning(f"电视剧 {series.title if series else '未知'} 缺少TMDB ID，跳过处理")
                            continue
                        
                        logger.info(f"开始处理电视剧: {series.title}")
                        
                        # 2. 从TMDB获取电视剧详细信息（带重试机制）
                        series_details = None
                        for i in range(3):  # 最多重试3次
                            # 检查插件是否仍应运行
                            if not self._check_run_conditions():
                                return
                                
                            series_details = self.get_tmdb_series_details(series.tmdbid)
                            if series_details:
                                break
                            logger.warning(f"获取电视剧 {series.title} 的TMDB信息失败，正在进行第{i+1}次重试")
                            time.sleep(1)  # 间隔1秒重试
                        
                        if not series_details:
                            logger.warning(f"无法获取电视剧 {series.title} 的TMDB信息")
                            continue
                        
                        # 获取媒体服务器中的剧集信息（按季组织）
                        seasons = list(mediaserver_chain.episodes(server_name, series.item_id))
                        logger.info(f"在电视剧 {series.title} 中找到 {len(seasons)} 个季")
                        
                        # 尝试通过items方法获取具体的剧集信息（只需要获取一次）
                        episode_items = {}
                        try:
                            # 获取季的详细信息，包括item_id
                            season_items = self._get_items(server_name, server_info.type, series.item_id, 'Season')
                            if season_items:
                                for season_item in season_items.get("Items", []):
                                    # 检查插件是否仍应运行
                                    if not self._check_run_conditions():
                                        return
                                        
                                    # 检查季号是否匹配
                                    season_index = season_item.get('IndexNumber')
                                    if season_index is not None:
                                        # 获取该季下的所有剧集
                                        episodes_in_season = self._get_items(server_name, server_info.type, season_item.get('Id'), 'Episode')
                                        if episodes_in_season:
                                            for episode_item in episodes_in_season.get("Items", []):
                                                # 检查插件是否仍应运行
                                                if not self._check_run_conditions():
                                                    return
                                                    
                                                # 以"S{season}E{episode}"格式存储剧集信息
                                                episode_index = episode_item.get('IndexNumber')
                                                if episode_index is not None:
                                                    key = f"S{season_index:02d}E{episode_index:02d}"
                                                    episode_items[key] = episode_item
                        except Exception as e:
                            logger.warning(f"获取剧集项目信息失败: {e}")
                        
                        # 遍历每个季
                        for season in seasons:
                            # 检查插件是否仍应运行
                            if not self._check_run_conditions():
                                return
                                
                            # 获取季信息
                            season_number = getattr(season, 'season', getattr(season, 'Season', None))
                            if season_number is None:
                                if hasattr(season, 'get'):
                                    season_number = season.get('season') or season.get('Season')
                            
                            episodes_list = getattr(season, 'episodes', getattr(season, 'Episodes', None))
                            if episodes_list is None:
                                if hasattr(season, 'get'):
                                    episodes_list = season.get('episodes') or season.get('Episodes')
                            
                            # 检查季信息是否完整
                            if season_number is None:
                                logger.warning(f"季信息不完整: {series.title}, season对象详情: {season}")
                                continue
                            
                            # 不再跳过任何季，包括S00
                            logger.info(f"正在处理 {series.title} 第{season_number}季，共{len(episodes_list) if episodes_list else 0}集")
                            
                            # 遍历该季的每一集
                            if episodes_list:
                                for episode_number in episodes_list:
                                    # 检查插件是否仍应运行
                                    if not self._check_run_conditions():
                                        return
                                        
                                    # 确保集号是数字类型
                                    if not isinstance(episode_number, (int, float)):
                                        logger.warning(f"无效的集号类型 {series.title} 第{season_number}季: {episode_number}")
                                        continue
                                    
                                    episode_number = int(episode_number)
                                    logger.info(f"正在处理 {series.title} S{season_number:02d}E{episode_number:02d}")
                                    
                                    # 获取剧集详细信息（带重试机制）
                                    episode_details = None
                                    for i in range(5):  # 增加重试次数到5次
                                        # 检查插件是否仍应运行
                                        if not self._check_run_conditions():
                                            return
                                            
                                        episode_details = self.get_tmdb_episode_details(series.tmdbid, season_number, episode_number)
                                        if episode_details:
                                            break
                                        logger.warning(f"获取 {series.title} S{season_number:02d}E{episode_number:02d} 的TMDB信息失败，正在进行第{i+1}次重试")
                                        time.sleep(5)  # 增加间隔到5秒重试
                                    
                                    if not episode_details:
                                        logger.warning(f"无法获取 {series.title} S{season_number:02d}E{episode_number:02d} 的TMDB信息")
                                        continue
                                    
                                    # 3. 处理剧情简介和标题
                                    overview = episode_details.get('overview', '').strip()
                                    name = episode_details.get('name', '').strip()
                                    need_translate = episode_details.get('_need_translate', False)
                                    
                                    # 添加判断是否需要翻译的详细日志
                                    overview_len = len(overview) if overview else 0
                                    name_len = len(name) if name else 0
                                    logger.info(f"剧集 {series.title} S{season_number:02d}E{episode_number:02d} - 剧情简介: {'有' if overview else '无'}({overview_len}字符), 标题: {'有' if name else '无'}({name_len}字符)")
                                    
                                    # 添加更详细的调试信息
                                    if overview:
                                        logger.debug(f"剧情简介内容预览: {overview[:100]}...")
                                    if name:
                                        logger.debug(f"标题内容预览: {name[:100]}...")
                                    
                                    if not overview and not name:
                                        logger.debug(f"{series.title} S{season_number:02d}E{episode_number:02d} 没有英文剧情简介和标题")
                                        continue
                                    
                                    # 4. 更新媒体库
                                    # 尝试获取具体的剧集item_id
                                    episode_key = f"S{season_number:02d}E{episode_number:02d}"
                                    episode_item_id = None
                                    if episode_key in episode_items:
                                        episode_item_id = episode_items[episode_key].get('Id')
                                    
                                    # 如果能获取到具体剧集ID，则更新单集信息
                                    if episode_item_id:
                                        # 获取剧集详情
                                        iteminfo = self.get_iteminfo(server_name, server_info.type, episode_item_id)
                                        if iteminfo:
                                            # 检查是否应该跳过此剧集的更新（先比对再翻译）
                                            if self._should_skip_episode(iteminfo, episode_details, series.tmdbid, season_number, episode_number):
                                                logger.info(f"跳过更新 {series.title} S{season_number:02d}E{episode_number:02d} - 内容已是中文或无需更新")
                                                # 更新跳过记录
                                                self._update_history_record(series.tmdbid, season_number, episode_number, "skipped")
                                                # 保存跳过记录
                                                self.save_update_history(
                                                    f"{series.title} S{season_number:02d}E{episode_number:02d}", 
                                                    "电视剧剧集", 
                                                    "已跳过(内容已是中文)"
                                                )
                                                continue
                                            
                                            # 只有在不跳过的情况下才进行翻译
                                            translated_overview = overview
                                            translated_name = name
                                            
                                            if self._translate_service == "google":
                                                logger.debug(f"开始翻译处理 - 服务: {self._translate_service}")
                                                # 检查是否需要翻译（包括英文内容或者中文区返回英文内容的情况）
                                                if overview and (need_translate or not self._is_chinese(overview)):
                                                    logger.info(f"{series.title} S{season_number:02d}E{episode_number:02d} 剧情简介需要翻译: {overview[:50]}...")
                                                    translated_overview = self.translate_text(overview)
                                                    # 将翻译后的内容与原文结合
                                                    translated_overview = self._combine_translation_with_original(translated_overview, overview, False)
                                                    logger.info(f"已翻译 {series.title} S{season_number:02d}E{episode_number:02d} 剧情简介")
                                                else:
                                                    logger.info(f"{series.title} S{season_number:02d}E{episode_number:02d} 剧情简介无需翻译")
                                                
                                                if name and (need_translate or not self._is_chinese(name)):
                                                    logger.info(f"{series.title} S{season_number:02d}E{episode_number:02d} 标题需要翻译: {name}")
                                                    translated_name = self.translate_text(name)
                                                    # 将翻译后的内容与原文结合（标题不需要附加原文）
                                                    translated_name = self._combine_translation_with_original(translated_name, name, True)
                                                    logger.info(f"已翻译 {series.title} S{season_number:02d}E{episode_number:02d} 标题")
                                                else:
                                                    logger.info(f"{series.title} S{season_number:02d}E{episode_number:02d} 标题无需翻译")
                                            elif self._translate_service == "ai":
                                                logger.debug(f"开始AI翻译处理 - 服务: {self._translate_service}")
                                                # 检查是否需要翻译（包括英文内容或者中文区返回英文内容的情况）
                                                if overview and (need_translate or not self._is_chinese(overview)):
                                                    logger.info(f"{series.title} S{season_number:02d}E{episode_number:02d} 剧情简介需要翻译: {overview[:50]}...")
                                                    translated_overview = self.ai_translate_text(overview)
                                                    # 将翻译后的内容与原文结合
                                                    translated_overview = self._combine_translation_with_original(translated_overview, overview, False)
                                                    logger.info(f"已AI翻译 {series.title} S{season_number:02d}E{episode_number:02d} 剧情简介")
                                                else:
                                                    logger.info(f"{series.title} S{season_number:02d}E{episode_number:02d} 剧情简介无需翻译")
                                                
                                                if name and (need_translate or not self._is_chinese(name)):
                                                    logger.info(f"{series.title} S{season_number:02d}E{episode_number:02d} 标题需要翻译: {name}")
                                                    translated_name = self.ai_translate_text(name)
                                                    # 将翻译后的内容与原文结合（标题不需要附加原文）
                                                    translated_name = self._combine_translation_with_original(translated_name, name, True)
                                                    logger.info(f"已AI翻译 {series.title} S{season_number:02d}E{episode_number:02d} 标题")
                                                else:
                                                    logger.info(f"{series.title} S{season_number:02d}E{episode_number:02d} 标题无需翻译")
                                            else:
                                                logger.debug("未满足翻译条件，跳过翻译")
                                                # 即使没有配置翻译服务，也要确保中文内容被正确使用
                                                if overview and not self._is_chinese(overview):
                                                    logger.debug(f"{series.title} S{season_number:02d}E{episode_number:02d} 剧情简介不是中文，但未配置翻译服务")
                                                if name and not self._is_chinese(name):
                                                    logger.debug(f"{series.title} S{season_number:02d}E{episode_number:02d} 标题不是中文，但未配置翻译服务")
                                                        
                                            # 更新剧集信息
                                            if overview:  # 只要原始内容存在就更新
                                                iteminfo['Overview'] = translated_overview
                                            if name:  # 只要原始标题存在就更新
                                                iteminfo['Name'] = translated_name
                                        
                                            # 保存更新
                                            if self.set_iteminfo(server_name, server_info.type, episode_item_id, iteminfo):
                                                logger.info(f"已更新 {series.title} S{season_number:02d}E{episode_number:02d} 标题和剧情简介")
                                                # 更新成功记录
                                                self._update_history_record(series.tmdbid, season_number, episode_number, "updated")
                                                
                                                # 发送推送通知
                                                if self._enable_notify:
                                                    self.post_message(
                                                        mtype=NotificationType.Plugin,
                                                        title="【剧情信息更新啦】🎉",
                                                        text=f"📺 剧集 {series.title} S{season_number:02d}E{episode_number:02d} 已更新\n"
                                                             f"标题：{translated_name}\n"
                                                             f"剧情简介：{translated_overview[:100]}{'...' if len(translated_overview) > 100 else ''}"
                                                    )
                                            else:
                                                logger.error(f"更新 {series.title} S{season_number:02d}E{episode_number:02d} 标题和剧情简介失败")
                                                # 更新失败记录
                                                self._update_history_record(series.tmdbid, season_number, episode_number, "failed")
                                        else:
                                            logger.error(f"获取 {series.title} S{season_number:02d}E{episode_number:02d} 详情失败")
                                            # 更新失败记录
                                            self._update_history_record(series.tmdbid, season_number, episode_number, "failed")
                                    else:
                                        # 如果无法获取具体剧集ID，则尝试通过季来更新
                                        logger.warning(f"缺少具体剧集ID，无法更新 {series.title} S{season_number:02d}E{episode_number:02d} 的标题和剧情简介")
                                    
                                    # 保存更新历史
                                    # 检查是否进行了翻译
                                    has_translation = (translated_overview != overview) or (translated_name != name)
                                    self.save_update_history(
                                        f"{series.title} S{season_number:02d}E{episode_number:02d}", 
                                        "电视剧剧集", 
                                        "已翻译并更新" if has_translation else "已更新原始内容"
                                    )
                            else:
                                # 处理没有剧集列表的季（可能为空季）
                                logger.info(f"电视剧 {series.title} 第{season_number}季没有剧集")
                                
                        # 检查是否有遗漏的季
                        logger.debug(f"检查电视剧 {series.title} 是否有遗漏的季信息")
                        try:
                            all_season_items = self._get_items(server_name, server_info.type, series.item_id, 'Season')
                            if all_season_items and "Items" in all_season_items:
                                found_seasons = set()
                                # 收集已处理的季号
                                for season in seasons:
                                    season_number = getattr(season, 'season', getattr(season, 'Season', None))
                                    if season_number is not None:
                                        found_seasons.add(int(season_number))
                                
                                # 检查是否有未处理的季
                                for season_item in all_season_items.get("Items", []):
                                    season_index = season_item.get('IndexNumber')
                                    if season_index is not None and int(season_index) not in found_seasons:
                                        logger.info(f"发现未处理的季: {series.title} S{season_index:02d}")
                                        # 获取该季下的所有剧集
                                        episodes_in_season = self._get_items(server_name, server_info.type, season_item.get('Id'), 'Episode')
                                        if episodes_in_season and "Items" in episodes_in_season:
                                            logger.info(f"正在处理 {series.title} 第{season_index}季，共{len(episodes_in_season.get('Items', []))}集")
                                            for episode_item in episodes_in_season.get("Items", []):
                                                episode_index = episode_item.get('IndexNumber')
                                                if episode_index is not None:
                                                    # 生成剧集key
                                                    episode_key = f"S{season_index:02d}E{episode_index:02d}"
                                                    episode_items[episode_key] = episode_item
                                                    
                                                    # 处理剧集
                                                    logger.info(f"正在处理 {series.title} S{season_index:02d}E{episode_index:02d}")
                                                    
                                                    # 获取剧集详细信息（带重试机制）
                                                    episode_details = None
                                                    for i in range(5):  # 增加重试次数到5次
                                                        # 如果启用了扩展功能，则获取详细信息
                                                        if (self._update_episode_image or 
                                                            self._update_episode_rating or 
                                                            self._update_episode_premieredate or 
                                                            self._update_episode_credits):
                                                            episode_details = self.get_tmdb_episode_details_ex(series.tmdbid, season_index, episode_index)
                                                        else:
                                                            episode_details = self.get_tmdb_episode_details(series.tmdbid, season_index, episode_index)
                                                            
                                                        if episode_details:
                                                            break
                                                        logger.warning(f"获取 {series.title} S{season_index:02d}E{episode_index:02d} 的TMDB信息失败，正在进行第{i+1}次重试")
                                                        time.sleep(2)  # 增加间隔到2秒重试
                                    
                                                    if not episode_details:
                                                        logger.warning(f"无法获取 {series.title} S{season_index:02d}E{episode_index:02d} 的TMDB信息")
                                                        continue
                                    
                                                    # 3. 处理剧情简介和标题
                                                    overview = episode_details.get('overview', '').strip()
                                                    name = episode_details.get('name', '').strip()
                                                    need_translate = episode_details.get('_need_translate', False)
                                                    
                                                    # 添加判断是否需要翻译的详细日志
                                                    overview_len = len(overview) if overview else 0
                                                    name_len = len(name) if name else 0
                                                    logger.info(f"剧集 {series.title} S{season_index:02d}E{episode_index:02d} - 剧情简介: {'有' if overview else '无'}({overview_len}字符), 标题: {'有' if name else '无'}({name_len}字符)")
                                                    
                                                    # 添加更详细的调试信息
                                                    if overview:
                                                        logger.debug(f"剧情简介内容预览: {overview[:100]}...")
                                                    if name:
                                                        logger.debug(f"标题内容预览: {name[:100]}...")
                                                    
                                                    if not overview and not name:
                                                        logger.debug(f"{series.title} S{season_index:02d}E{episode_index:02d} 没有英文剧情简介和标题")
                                                        continue

                                    
                                                    # 更新媒体库
                                                    episode_item_id = episode_item.get('Id')
                                                    if episode_item_id:
                                                        # 获取剧集详情
                                                        iteminfo = self.get_iteminfo(server_name, server_info.type, episode_item_id)
                                                        if iteminfo:
                                                            # 检查是否应该跳过此剧集的更新
                                                            if self._should_skip_episode(iteminfo, episode_details, series.tmdbid, season_index, episode_index):
                                                                logger.info(f"跳过更新 {series.title} S{season_index:02d}E{episode_index:02d} - 内容已是中文或无需更新")
                                                                # 更新跳过记录
                                                                self._update_history_record(series.tmdbid, season_index, episode_index, "skipped")
                                                                # 保存跳过记录
                                                                self.save_update_history(
                                                                    f"{series.title} S{season_index:02d}E{episode_index:02d}", 
                                                                    "电视剧剧集", 
                                                                    "已跳过(内容已是中文)"
                                                                )
                                                                continue
                                                            
                                                            # 翻译剧情简介
                                                            translated_overview = overview
                                                            translated_name = name
                                                            
                                                            if self._translate_service == "google":
                                                                logger.debug(f"开始翻译处理 - 服务: {self._translate_service}")
                                                                # 检查是否需要翻译（包括英文内容或者中文区返回英文内容的情况）
                                                                if overview and (need_translate or not self._is_chinese(overview)):
                                                                    logger.info(f"{series.title} S{season_index:02d}E{episode_index:02d} 剧情简介需要翻译: {overview[:50]}...")
                                                                    translated_overview = self.translate_text(overview)
                                                                    # 将翻译后的内容与原文结合
                                                                    translated_overview = self._combine_translation_with_original(translated_overview, overview, False)
                                                                    logger.info(f"已翻译 {series.title} S{season_index:02d}E{episode_index:02d} 剧情简介")
                                                                else:
                                                                    logger.info(f"{series.title} S{season_index:02d}E{episode_index:02d} 剧情简介无需翻译")
                                                                    
                                                                if name and (need_translate or not self._is_chinese(name)):
                                                                    logger.info(f"{series.title} S{season_index:02d}E{episode_index:02d} 标题需要翻译: {name}")
                                                                    translated_name = self.translate_text(name)
                                                                    # 将翻译后的内容与原文结合（标题不需要附加原文）
                                                                    translated_name = self._combine_translation_with_original(translated_name, name, True)
                                                                    logger.info(f"已翻译 {series.title} S{season_index:02d}E{episode_index:02d} 标题")
                                                                else:
                                                                    logger.info(f"{series.title} S{season_index:02d}E{episode_index:02d} 标题无需翻译")
                                                            elif self._translate_service == "ai":
                                                                logger.debug(f"开始AI翻译处理 - 服务: {self._translate_service}")
                                                                # 检查是否需要翻译（包括英文内容或者中文区返回英文内容的情况）
                                                                if overview and (need_translate or not self._is_chinese(overview)):
                                                                    logger.info(f"{series.title} S{season_index:02d}E{episode_index:02d} 剧情简介需要翻译: {overview[:50]}...")
                                                                    translated_overview = self.ai_translate_text(overview)
                                                                    # 将翻译后的内容与原文结合
                                                                    translated_overview = self._combine_translation_with_original(translated_overview, overview, False)
                                                                    logger.info(f"已AI翻译 {series.title} S{season_index:02d}E{episode_index:02d} 剧情简介")
                                                                else:
                                                                    logger.info(f"{series.title} S{season_index:02d}E{episode_index:02d} 剧情简介无需翻译")
                                                                
                                                                if name and (need_translate or not self._is_chinese(name)):
                                                                    logger.info(f"{series.title} S{season_index:02d}E{episode_index:02d} 标题需要翻译: {name}")
                                                                    translated_name = self.ai_translate_text(name)
                                                                    # 将翻译后的内容与原文结合（标题不需要附加原文）
                                                                    translated_name = self._combine_translation_with_original(translated_name, name, True)
                                                                    logger.info(f"已AI翻译 {series.title} S{season_index:02d}E{episode_index:02d} 标题")
                                                                else:
                                                                    logger.info(f"{series.title} S{season_index:02d}E{episode_index:02d} 标题无需翻译")
                                                            else:
                                                                logger.debug("未满足翻译条件，跳过翻译")
                                                                # 即使没有配置翻译服务，也要确保中文内容被正确使用
                                                                if overview and not self._is_chinese(overview):
                                                                    logger.debug(f"{series.title} S{season_index:02d}E{episode_index:02d} 剧情简介不是中文，但未配置翻译服务")
                                                                if name and not self._is_chinese(name):
                                                                    logger.debug(f"{series.title} S{season_index:02d}E{episode_index:02d} 标题不是中文，但未配置翻译服务")
                                                            
                                                            # 更新剧集信息
                                                            if overview:  # 只要原始内容存在就更新
                                                                iteminfo['Overview'] = translated_overview
                                                            if name:  # 只要原始标题存在就更新
                                                                iteminfo['Name'] = translated_name
                                                                
                                                            # 更新剧集图片
                                                            if self._update_episode_image and episode_details.get('still_url'):
                                                                # 注意：这里需要根据不同的媒体服务器类型进行适配
                                                                # 当前版本暂不实现图片更新功能
                                                                logger.debug(f"剧集图片更新功能占位符: {episode_details.get('still_url')}")
                                                                
                                                            # 更新剧集评分
                                                            if self._update_episode_rating:
                                                                vote_average = episode_details.get('vote_average', 0)
                                                                vote_count = episode_details.get('vote_count', 0)
                                                                if vote_average > 0:
                                                                    iteminfo['CommunityRating'] = vote_average
                                                                # 注意：vote_count 更新需要特定的字段，根据不同媒体服务器而不同
                                                                
                                                            # 更新播出日期
                                                            if self._update_episode_premieredate and episode_details.get('air_date'):
                                                                air_date = episode_details.get('air_date')
                                                                if air_date:
                                                                    # 格式化日期，根据不同媒体服务器类型可能需要调整
                                                                    iteminfo['PremiereDate'] = air_date
                                                                    iteminfo['ProductionYear'] = air_date[:4] if len(air_date) >= 4 else air_date
                                                                
                                                            # 更新演职人员信息
                                                            if self._update_episode_credits:
                                                                guest_stars = episode_details.get('guest_stars', [])
                                                                crew = episode_details.get('crew', [])
                                                                # 注意：演职人员信息更新比较复杂，需要根据媒体服务器的具体实现
                                                                # 当前版本记录信息但不实际更新
                                                                if guest_stars or crew:
                                                                    logger.debug(f"剧集演职人员信息: guest_stars={len(guest_stars)}, crew={len(crew)}")
                                                                
                                                            # 保存更新
                                                            if self.set_iteminfo(server_name, server_info.type, episode_item_id, iteminfo):
                                                                logger.info(f"已更新 {series.title} S{season_index:02d}E{episode_index:02d} 标题和剧情简介")
                                                                
                                                                # 发送推送通知
                                                                if self._enable_notify:
                                                                    self.post_message(
                                                                        mtype=NotificationType.Plugin,
                                                                        title="【剧情信息更新啦】🎉",
                                                                        text=f"📺 剧集 {series.title} S{season_index:02d}E{episode_index:02d} 已更新\n"
                                                                             f"标题：{translated_name}\n"
                                                                             f"剧情简介：{translated_overview[:100]}{'...' if len(translated_overview) > 100 else ''}"
                                                                    )
                                                            else:
                                                                logger.error(f"更新 {series.title} S{season_index:02d}E{episode_index:02d} 标题和剧情简介失败")
                                                        else:
                                                            logger.error(f"获取 {series.title} S{season_index:02d}E{episode_index:02d} 详情失败")
                        except Exception as e:
                            logger.warning(f"检查遗漏季信息时出错: {e}")
        except Exception as e:
            logger.error(f"更新电视剧剧情简介时发生错误：{e}")
            logger.error(f"错误详情：{str(e)}")
        finally:
            # 清理缓存
            if hasattr(self, '_cached_service_infos'):
                delattr(self, '_cached_service_infos')
        
        logger.info("电视剧剧情简介更新完成")
    
    def get_tmdb_series_details(self, series_id: int) -> dict:
        """
        获取电视剧详情
        """
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
    
    def get_tmdb_episode_details(self, series_id: int, season_number: int, episode_number: int) -> dict:
        """
        获取剧集详情
        """
        # 首先尝试获取中文内容，增加重试机制
        for retry in range(5):  # 增加重试次数到5次
            try:
                url = f"https://api.themoviedb.org/3/tv/{series_id}/season/{season_number}/episode/{episode_number}"
                params = {
                    "api_key": self._tmdb_api_key,
                    "language": "zh-CN"
                }
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                result = response.json()
                
                logger.debug(f"从TMDB获取到的原始数据: {result}")
                
                # 处理返回的内容
                overview = result.get('overview', '')
                # 确保overview不为None并进行处理
                if overview is not None:
                    overview = overview.strip()
                else:
                    overview = ''
                    
                name = result.get('name', '')
                # 确保name不为None并进行处理
                if name is not None:
                    name = name.strip()
                else:
                    name = ''
                
                logger.debug(f"处理后的overview: '{overview}', 长度: {len(overview)}")
                logger.debug(f"处理后的name: '{name}', 长度: {len(name)}")
                
                # 检查是否需要获取英文内容来补充缺失的信息
                need_english_content = False
                if not overview or not name:
                    logger.debug(f"中文区域内容不完整，尝试获取英文内容补充: series_id={series_id}, S{season_number:02d}E{episode_number:02d}")
                    need_english_content = True
                elif (overview and not self._is_chinese(overview)) or (name and not self._is_chinese(name)):
                    logger.debug(f"中文区域返回非中文内容，尝试获取英文内容: series_id={series_id}, S{season_number:02d}E{episode_number:02d}")
                    need_english_content = True
                
                # 如果需要获取英文内容来补充或替换
                if need_english_content:
                    english_result = self._get_english_episode_details(series_id, season_number, episode_number)
                    # 合并中英文内容，优先使用中文内容，缺失的部分用英文补充
                    if not overview and english_result.get('overview'):
                        overview = english_result.get('overview', '')
                    if not name and english_result.get('name'):
                        name = english_result.get('name', '')
                    
                    # 判断是否需要翻译（只要有英文内容就需要翻译）
                    result['_need_translate'] = english_result.get('_need_translate', False) or (
                        (overview and not self._is_chinese(overview)) or 
                        (name and not self._is_chinese(name))
                    )
                else:
                    # 标记是否需要翻译
                    result['_need_translate'] = False
                    
                    # 检查内容是否需要翻译
                    if overview or name:
                        # 如果是纯ASCII字符(英文)，需要翻译
                        if (overview and overview.isascii()) or (name and name.isascii()):
                            logger.debug(f"中文区返回英文内容，需要翻译: {overview[:50]}...")
                            result['_need_translate'] = True
                        # 如果不是中文内容，也需要翻译
                        elif not self._is_chinese(overview) or not self._is_chinese(name):
                            result['_need_translate'] = True
                            logger.debug(f"内容不是中文，需要翻译: overview={overview[:50]}..., name={name[:50]}...")
                
                # 更新结果中的overview和name字段
                result['overview'] = overview
                result['name'] = name
                
                logger.debug(f"最终返回的overview: '{result['overview']}', 长度: {len(result['overview'])}")
                logger.debug(f"最终返回的name: '{result['name']}', 长度: {len(result['name'])}")
                
                return result
            except Exception as e:
                logger.warning(f"第{retry+1}次获取中文剧集详情失败: {e}")
                if retry < 4:  # 不是最后一次尝试，等待后重试
                    time.sleep(5)
                else:
                    # 最后一次尝试也失败了，记录错误并返回空结果
                    logger.error(f"获取剧集详情完全失败：{e}")
                    return {
                        'overview': '',
                        'name': '',
                        '_need_translate': False
                    }
    
    def get_tmdb_episode_details_ex(self, series_id: int, season_number: int, episode_number: int) -> dict:
        """
        获取剧集详细信息（扩展版，包含图片、评分、播出日期、演职人员等）
        """
        try:
            # 获取剧集基础信息
            url = f"https://api.themoviedb.org/3/tv/{series_id}/season/{season_number}/episode/{episode_number}"
            params = {
                "api_key": self._tmdb_api_key,
                "language": "zh-CN",
                # 添加更多字段
                "append_to_response": "credits,images"
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            logger.debug(f"从TMDB获取到的剧集详细数据: {result}")
            
            # 处理返回的内容
            overview = result.get('overview', '')
            if overview is not None:
                overview = overview.strip()
            else:
                overview = ''
                
            name = result.get('name', '')
            if name is not None:
                name = name.strip()
            else:
                name = ''
            
            # 获取额外信息
            # 评分
            vote_average = result.get('vote_average', 0)
            vote_count = result.get('vote_count', 0)
            
            # 播出日期
            air_date = result.get('air_date', '')
            
            # 图片信息
            still_path = result.get('still_path', '')
            if still_path:
                still_url = f"https://image.tmdb.org/t/p/original{still_path}"
            else:
                still_url = ""
            
            # 演职人员信息
            credits_info = result.get('credits', {})
            guest_stars = credits_info.get('guest_stars', [])
            crew = credits_info.get('crew', [])
            
            # 构建返回数据
            extended_result = {
                'overview': overview,
                'name': name,
                'vote_average': vote_average,
                'vote_count': vote_count,
                'air_date': air_date,
                'still_url': still_url,
                'guest_stars': guest_stars,
                'crew': crew,
                '_need_translate': False
            }
            
            # 检查内容是否需要翻译
            if overview or name:
                # 如果是纯ASCII字符(英文)，需要翻译
                if (overview and overview.isascii()) or (name and name.isascii()):
                    logger.debug(f"剧集详情返回英文内容，需要翻译: {overview[:50]}...")
                    extended_result['_need_translate'] = True
                # 如果不是中文内容，也需要翻译
                elif not self._is_chinese(overview) or not self._is_chinese(name):
                    extended_result['_need_translate'] = True
                    logger.debug(f"剧集详情内容不是中文，需要翻译: overview={overview[:50]}..., name={name[:50]}...")
            
            logger.debug(f"处理后的剧集详情: {extended_result}")
            return extended_result
            
        except Exception as e:
            logger.error(f"获取剧集详细信息失败：{e}")
            # 返回基础信息
            return {
                'overview': '',
                'name': '',
                'vote_average': 0,
                'vote_count': 0,
                'air_date': '',
                'still_url': '',
                'guest_stars': [],
                'crew': [],
                '_need_translate': False
            }
    
    def _get_english_episode_details(self, series_id: int, season_number: int, episode_number: int) -> dict:
        """
        获取英文剧集详情
        """
        # 增加重试机制
        for retry in range(5):  # 增加重试次数到5次
            try:
                url = f"https://api.themoviedb.org/3/tv/{series_id}/season/{season_number}/episode/{episode_number}"
                params = {
                    "api_key": self._tmdb_api_key,
                    "language": "en-US"
                }
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                result = response.json()
                logger.debug(f"从TMDB获取到的英文原始数据: {result}")
                # 英文内容肯定需要翻译
                result['_need_translate'] = True
                
                # 对英文内容也进行strip处理
                if 'overview' in result:
                    overview = result['overview']
                    if overview is not None:
                        result['overview'] = overview.strip()
                    else:
                        result['overview'] = ''
                else:
                    result['overview'] = ''
                    
                if 'name' in result:
                    name = result['name']
                    if name is not None:
                        result['name'] = name.strip()
                    else:
                        result['name'] = ''
                else:
                    result['name'] = ''
                    
                logger.debug(f"处理后的英文overview: '{result['overview']}', 长度: {len(result['overview'])}")
                logger.debug(f"处理后的英文name: '{result['name']}', 长度: {len(result['name'])}")
                    
                return result
            except Exception as e:
                logger.warning(f"第{retry+1}次获取英文剧集详情失败: {e}")
                if retry < 4:  # 不是最后一次尝试，等待后重试
                    time.sleep(5)
                else:
                    # 最后一次尝试也失败了
                    logger.error(f"获取英文剧集详情完全失败：{e}")
                    # 返回空的结果而不是{}
                    return {
                        'overview': '',
                        'name': '',
                        '_need_translate': False
                    }
    
    def translate_text(self, text: str, source_lang: str = "en", target_lang: str = "zh") -> str:
        """
        使用Google翻译文本
        """
        if not text or source_lang == target_lang:
            return text
        
        logger.debug(f"调用翻译函数 - 服务: {self._translate_service}, 源语言: {source_lang}, 目标语言: {target_lang}, 文本: {text[:50]}...")
        
        try:
            if self._translate_service == "google":
                return self._google_translate(text, source_lang, target_lang)
            else:
                logger.warn(f"不支持的翻译服务：{self._translate_service}")
                return text
        except Exception as e:
            logger.error(f"翻译失败：{e}")
            return text

    def _google_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        Google翻译（免账号）
        """
        try:
            import urllib.parse
            
            # Google翻译API端点
            url = "https://translate.googleapis.com/translate_a/single"
            
            # 参数
            params = {
                "client": "gtx",
                "sl": source_lang,
                "tl": target_lang,
                "dt": "t",
                "q": text
            }
            
            # 发送请求
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # 解析响应
            result = response.json()
            
            if result and len(result) > 0 and result[0]:
                translated_text = ""
                for item in result[0]:
                    if item and len(item) > 0 and item[0]:
                        translated_text += item[0]
                # 确保返回的文本不为空
                if translated_text.strip():
                    return translated_text
                else:
                    logger.warning("Google翻译返回空结果")
                    return text
            
            logger.error(f"Google翻译返回错误：{result}")
            return text
        except Exception as e:
            logger.error(f"Google翻译失败：{e}")
            return text
    
    def ai_translate_text(self, text: str, source_lang: str = "en", target_lang: str = "zh") -> str:
        """
        使用SiliconFlow AI翻译文本
        """
        if not text or not self._siliconflow_api_key:
            return text
        
        logger.debug(f"调用AI翻译函数 - 模型: {self._siliconflow_model}, 源语言: {source_lang}, 目标语言: {target_lang}")
        logger.debug(f"待翻译文本: {text[:100]}...")
        
        try:
            # 构造优化的提示词，专门针对影视内容翻译
            prompt = f"""你是一位专业的影视翻译人员，请将以下{source_lang}影视内容翻译成{target_lang}：

{text}

翻译要求：
1. 将所有英文内容翻译成中文，包括人名、地名、专有名词等
2. 保持原意不变，语句通顺自然
3. 影视行业术语请使用标准中文译名
4. 保持特殊格式不变（如标点符号、换行等）
5. 仅输出翻译结果，不要添加任何解释或其他内容"""

            # SiliconFlow API端点
            url = "https://api.siliconflow.cn/v1/chat/completions"
            
            # 请求头
            headers = {
                "Authorization": f"Bearer {self._siliconflow_api_key}",
                "Content-Type": "application/json"
            }
            
            # 请求数据
            data = {
                "model": self._siliconflow_model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 4096
            }
            
            # 发送请求，增加超时时间到120秒
            response = requests.post(url, headers=headers, json=data, timeout=120)
            response.raise_for_status()
            
            # 解析响应
            result = response.json()
            
            if "choices" in result and len(result["choices"]) > 0:
                translated_text = result["choices"][0]["message"]["content"].strip()
                logger.debug(f"AI翻译成功，结果: {translated_text[:100]}...")
                return translated_text
            else:
                logger.error(f"AI翻译返回错误：{result}")
                return text
                
        except Exception as e:
            logger.error(f"AI翻译失败：{e}")
            return text
    
    def _get_items(self, server: str, server_type: str, parentid: str, mtype: Optional[str] = None) -> dict:
        """
        获得媒体的所有子媒体项
        """
        # 使用缓存的service_infos，避免重复获取
        service_infos = self._cached_service_infos if hasattr(self, '_cached_service_infos') else self.service_infos()
        if not service_infos:
            logger.warn(f"未找到媒体服务器实例")
            return {}

        service = service_infos.get(server)
        if not service:
            logger.warn(f"未找到媒体服务器 {server} 的实例")
            return {}

        def __get_emby_items() -> dict:
            """
            获得Emby媒体的所有子媒体项
            """
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
            """
            获得Jellyfin媒体的所有子媒体项
            """
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
            """
            获得Plex媒体的所有子媒体项
            """
            items = {}
            try:
                plex = service.instance.get_plex()
                items['Items'] = []
                if parentid:
                    if mtype and 'Season' in mtype:
                        plexitem = plex.library.fetchItem(ekey=parentid)
                        items['Items'] = []
                        for season in plexitem.seasons():
                            item = {
                                'Name': season.title,
                                'Id': season.key,
                                'IndexNumber': season.seasonNumber,
                                'Overview': season.summary
                            }
                            items['Items'].append(item)
                    elif mtype and 'Episode' in mtype:
                        plexitem = plex.library.fetchItem(ekey=parentid)
                        items['Items'] = []
                        for episode in plexitem.episodes():
                            item = {
                                'Name': episode.title,
                                'Id': episode.key,
                                'IndexNumber': episode.episodeNumber,
                                'Overview': episode.summary,
                                'CommunityRating': episode.audienceRating
                            }
                            items['Items'].append(item)
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
    
    def _load_cache_and_history(self):
        """
        加载缓存和历史记录
        """
        try:
            # 加载剧集状态缓存
            series_status_cache = self.get_data('series_status_cache')
            if series_status_cache:
                self._series_status_cache = series_status_cache
            
            # 加载更新历史记录
            update_history = self.get_data('update_history')
            if update_history:
                self._update_history = update_history
        except Exception as e:
            logger.error(f"加载缓存和历史记录失败: {e}")
    
    def _save_cache_and_history(self):
        """
        保存缓存和历史记录
        """
        try:
            # 保存剧集状态缓存
            self.save_data('series_status_cache', self._series_status_cache)
            
            # 保存更新历史记录
            self.save_data('update_history', self._update_history)
        except Exception as e:
            logger.error(f"保存缓存和历史记录失败: {e}")
    
    def _update_history_record(self, series_id: int, season_number: int, episode_number: int, status: str):
        """
        更新剧集的历史记录
        
        :param series_id: 剧集TMDB ID
        :param season_number: 季号
        :param episode_number: 集号
        :param status: 更新状态 (updated, skipped, failed)
        """
        import time
        
        # 构建剧集唯一标识
        episode_key = f"{series_id}_S{season_number:02d}E{episode_number:02d}"
        current_time = time.time()
        
        # 初始化剧集历史记录
        if episode_key not in self._update_history:
            self._update_history[episode_key] = {
                'last_update': 0,
                'update_count': 0,
                'skip_count': 0,
                'fail_count': 0,
                'last_status': ''
            }
        
        # 更新历史记录
        episode_history = self._update_history[episode_key]
        episode_history['last_update'] = current_time
        episode_history['last_status'] = status
        
        if status == "updated":
            episode_history['update_count'] += 1
        elif status == "skipped":
            episode_history['skip_count'] += 1
        elif status == "failed":
            episode_history['fail_count'] += 1
        
        # 保存更新后的历史记录
        self._save_cache_and_history()
    
    def save_update_history(self, title: str, media_type: str, status: str):
        """
        保存更新历史
        """
        # 获取历史记录
        history = self.get_data('history') or []
        
        # 添加新记录
        history.append({
            'title': title,
            'type': media_type,
            'status': status,
            'time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        })
        
        # 保存历史记录
        self.save_data('history', history)
    
    def _is_chinese(self, text: str) -> bool:
        """
        判断文本是否包含中文字符
        """
        if not text:
            return False
        
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':
                return True
        return False
    

    
    def _contains_original_and_matches(self, existing_text: str, tmdb_text: str) -> bool:
        """
        检查本地内容是否已包含原文且与TMDB一致
        
        :param existing_text: 本地已有的文本内容
        :param tmdb_text: TMDB获取的原文内容
        :return: 是否已包含原文且一致
        """
        if not existing_text or not tmdb_text:
            return False
            
        # 检查本地内容是否以特定格式包含原文
        # 格式：翻译后的内容\n\n[原文：原始英文内容]
        original_marker = "\n\n[原文："
        if original_marker in existing_text:
            # 提取原文部分
            try:
                start_idx = existing_text.index(original_marker) + len(original_marker)
                end_idx = existing_text.index("]", start_idx)
                extracted_original = existing_text[start_idx:end_idx]
                
                # 比较提取的原文与TMDB内容是否一致
                if extracted_original == tmdb_text:
                    return True
            except ValueError:
                # 如果解析失败，说明格式不正确
                pass
                
        return False
    
    def _combine_translation_with_original(self, translated_text: str, original_text: str, is_title: bool = False) -> str:
        """
        将翻译后的文本与原文结合
        
        :param translated_text: 翻译后的文本
        :param original_text: 原始英文文本
        :param is_title: 是否为标题（标题不需要附加原文）
        :return: 结合后的文本
        """
        if not original_text:
            return translated_text
            
        # 标题不需要附加原文
        if is_title:
            return translated_text
            
        # 将原文附加到翻译文本后面（仅限剧情简介）
        combined_text = f"{translated_text}\n\n[原文：{original_text}]"
        return combined_text
    
    def _should_skip_episode(self, iteminfo: dict, episode_details: dict, series_id: int, season_number: int, episode_number: int) -> bool:
        """
        判断是否应该跳过剧集更新（智能跳过策略）
        
        :param iteminfo: 媒体服务器中的剧集信息
        :param episode_details: TMDB获取的剧集详情
        :param series_id: 剧集TMDB ID
        :param season_number: 季号
        :param episode_number: 集号
        :return: 是否应该跳过更新
        """
        import time
        from datetime import datetime, timedelta
        
        # 构建剧集唯一标识
        episode_key = f"{series_id}_S{season_number:02d}E{episode_number:02d}"
        current_time = time.time()
        
        # 获取媒体服务器中已有的信息
        existing_overview = iteminfo.get('Overview', '').strip()
        existing_name = iteminfo.get('Name', '').strip()
        
        # 获取TMDB中的信息
        tmdb_overview = episode_details.get('overview', '').strip()
        tmdb_name = episode_details.get('name', '').strip()
        
        # 获取是否需要翻译的标记
        need_translate = episode_details.get('_need_translate', False)
        
        # 添加详细的本地信息日志
        logger.info(f"检查本地剧集信息 {episode_key}:")
        logger.info(f"  本地剧情简介: {'存在' if existing_overview else '不存在'} ({len(existing_overview)} 字符)")
        logger.info(f"  本地标题: {'存在' if existing_name else '不存在'} ({len(existing_name)} 字符)")
        logger.info(f"  TMDB剧情简介: {'存在' if tmdb_overview else '不存在'} ({len(tmdb_overview)} 字符)")
        logger.info(f"  TMDB标题: {'存在' if tmdb_name else '不存在'} ({len(tmdb_name)} 字符)")
        
        # 1. 如果TMDB没有提供任何信息，则跳过
        if not tmdb_overview and not tmdb_name:
            logger.debug(f"TMDB未提供任何信息，跳过更新 {episode_key}")
            # 记录为已完成，下次不再更新
            self._update_history_record(series_id, season_number, episode_number, "updated")
            return True
        
        # 2. 检查本地是否已包含原文且与TMDB一致（增强的跳过逻辑）
        # 情况A: 本地内容已包含原文且与TMDB一致，则跳过更新
        if self._contains_original_and_matches(existing_overview, tmdb_overview) and \
           self._contains_original_and_matches(existing_name, tmdb_name):
            logger.info(f"剧集 {episode_key} 本地内容已包含原文且与TMDB一致，跳过更新")
            # 记录为已完成，下次不再更新
            self._update_history_record(series_id, season_number, episode_number, "updated")
            return True
        
        # 3. 检查本地内容与TMDB内容是否完全一致（适用于中文内容）
        # 情况B: 本地内容与TMDB内容完全一致，则跳过更新
        if existing_overview == tmdb_overview and existing_name == tmdb_name and (tmdb_overview or tmdb_name):
            logger.debug(f"剧集 {episode_key} 现有内容和TMDB内容完全一致，跳过更新")
            # 记录为已完成，下次不再更新
            self._update_history_record(series_id, season_number, episode_number, "updated")
            return True
            
        # 4. 检查TMDB内容是否为中文
        tmdb_overview_is_chinese = self._is_chinese(tmdb_overview)
        tmdb_name_is_chinese = self._is_chinese(tmdb_name)
        
        # 添加中文检测日志
        logger.debug(f"本地内容中文检测 - 剧情简介: {self._is_chinese(existing_overview)}, 标题: {self._is_chinese(existing_name)}")
        logger.debug(f"TMDB内容中文检测 - 剧情简介: {tmdb_overview_is_chinese}, 标题: {tmdb_name_is_chinese}")
        
        # 5. 特殊处理：如果媒体服务器中剧情简介为空，但TMDB有内容，则需要更新
        if not existing_overview and tmdb_overview:
            logger.debug(f"剧集 {episode_key} 媒体服务器中剧情简介为空但TMDB有内容，需要更新")
            return False
            
        # 6. 特殊处理：如果媒体服务器中标题为空，但TMDB有内容，则需要更新
        if not existing_name and tmdb_name:
            logger.debug(f"剧集 {episode_key} 媒体服务器中标题为空但TMDB有内容，需要更新")
            return False
        
        # 7. 如果TMDB内容需要翻译，但媒体服务器中已经是中文，则检查是否需要更新
        # 情况C: TMDB是英文内容，本地已经是中文内容
        existing_overview_is_chinese = self._is_chinese(existing_overview)
        existing_name_is_chinese = self._is_chinese(existing_name)
        
        if need_translate and (existing_overview_is_chinese or existing_name_is_chinese):
            logger.debug(f"剧集 {episode_key} TMDB内容需要翻译但媒体服务器中已有中文内容，检查是否需要更新")
            # 检查本地是否包含原文且与TMDB一致
            if self._contains_original_and_matches(existing_overview, tmdb_overview) and \
               self._contains_original_and_matches(existing_name, tmdb_name):
                logger.info(f"剧集 {episode_key} 本地中文内容包含的原文与TMDB一致，跳过更新")
                # 记录为已完成，下次不再更新
                self._update_history_record(series_id, season_number, episode_number, "updated")
                return True
            # 其他情况需要更新（例如TMDB获取到新内容）
            logger.debug(f"剧集 {episode_key} 需要检查更新")
            return False
        
        # 8. 如果现有内容和TMDB内容都是中文且不为空，则跳过
        # 特别处理：对于中文内容，我们需要检查本地内容和TMDB内容是否一致
        if (existing_overview and existing_overview_is_chinese) and \
           (existing_name and existing_name_is_chinese):
            logger.debug(f"剧集 {episode_key} 媒体服务器中已存在中文内容")
            # 如果TMDB也是中文，检查是否一致
            if (tmdb_overview and tmdb_overview_is_chinese) and \
               (tmdb_name and tmdb_name_is_chinese):
                if existing_overview == tmdb_overview and existing_name == tmdb_name:
                    logger.info(f"剧集 {episode_key} 本地中文内容与TMDB中文内容一致，跳过更新")
                    # 记录为已完成，下次不再更新
                    self._update_history_record(series_id, season_number, episode_number, "updated")
                    return True
                else:
                    logger.debug(f"剧集 {episode_key} 本地中文内容与TMDB中文内容不一致，需要更新")
                    return False
            # 如果TMDB是英文但本地是中文，检查本地是否包含原文
            elif need_translate:
                if self._contains_original_and_matches(existing_overview, tmdb_overview) and \
                   self._contains_original_and_matches(existing_name, tmdb_name):
                    logger.info(f"剧集 {episode_key} 本地中文内容包含的原文与TMDB英文内容一致，跳过更新")
                    # 记录为已完成，下次不再更新
                    self._update_history_record(series_id, season_number, episode_number, "updated")
                    return True
                else:
                    logger.debug(f"剧集 {episode_key} 本地中文内容与TMDB英文内容不匹配，需要更新")
                    return False
            else:
                # 本地是中文，TMDB是非中文且不需要翻译
                logger.debug(f"剧集 {episode_key} 本地是中文内容，TMDB是非中文内容且不需要翻译")
                # 记录为已完成，下次不再更新
                self._update_history_record(series_id, season_number, episode_number, "updated")
                return True
        
        # 9. 检查更新历史记录，实现智能跳过策略
        if episode_key in self._update_history:
            episode_history = self._update_history[episode_key]
            last_update_time = episode_history.get('last_update', 0)
            update_count = episode_history.get('update_count', 0)
            skip_count = episode_history.get('skip_count', 0)
            last_status = episode_history.get('last_status', '')
            
            # 如果上次更新状态是"updated"，说明已经更新过，可以跳过
            if last_status == "updated":
                logger.debug(f"剧集 {episode_key} 上次更新状态为已更新，跳过更新")
                return True
            
            # 判断剧集是否已完结（这里简化处理，实际应该传入剧集详情）
            is_ended = self._series_status_cache.get(series_id, {}).get('ended', False) if series_id in self._series_status_cache else False
            
            # 对于已完结的剧集，采用更长的更新间隔
            if is_ended:
                # 已完结剧集每7天更新一次
                update_interval = 7 * 24 * 3600
            else:
                # 连载中剧集每天更新一次
                update_interval = 24 * 3600
            
            # 如果距离上次更新时间小于更新间隔，则跳过
            if current_time - last_update_time < update_interval:
                logger.debug(f"剧集 {episode_key} 未到更新时间，跳过更新")
                return True
            
            # 如果连续多次更新都没有变化，则增加跳过概率
            if update_count > 3 and skip_count > update_count // 2:
                # 50%概率跳过
                import random
                if random.random() < 0.5:
                    logger.debug(f"剧集 {episode_key} 连续多次更新无变化，随机跳过更新")
                    return True
        
        # 默认不跳过
        logger.debug(f"剧集 {episode_key} 需要更新")
        return False
    
    def _is_series_ended(self, series_details: dict, series_id: int) -> bool:
        """
        判断电视剧是否已完结
        
        :param series_details: TMDB电视剧详情
        :param series_id: 电视剧TMDB ID
        :return: 是否已完结
        """
        import time
        from datetime import datetime, timedelta
        
        # 检查缓存
        current_time = time.time()
        if series_id in self._series_status_cache:
            cached_status = self._series_status_cache[series_id]
            # 缓存有效期为1天
            if current_time - cached_status['timestamp'] < 86400:
                logger.debug(f"使用剧集 {series_id} 的缓存状态: {cached_status['ended']}")
                return cached_status['ended']
            else:
                # 缓存过期，删除旧缓存
                del self._series_status_cache[series_id]
        
        # 获取状态信息
        status = series_details.get('status', '').lower()
        if status in ['ended', 'cancelled']:
            result = True
        else:
            # 检查是否有下一集播出信息
            next_episode = series_details.get('next_episode_to_air')
            if not next_episode:
                # 检查最后播出日期
                last_air_date = series_details.get('last_air_date')
                if last_air_date:
                    try:
                        # 如果最后播出日期距离现在超过1年，认为已完结
                        last_date = datetime.strptime(last_air_date, '%Y-%m-%d')
                        now = datetime.now()
                        if (now - last_date).days > 365:
                            result = True
                        else:
                            result = False
                    except Exception as e:
                        logger.warning(f"解析最后播出日期失败: {e}")
                        result = False
                else:
                    result = False
            else:
                result = False
        
        # 缓存结果
        self._series_status_cache[series_id] = {
            'ended': result,
            'timestamp': current_time
        }
        
        # 保存缓存
        self._save_cache_and_history()
        
        logger.debug(f"剧集 {series_id} 状态判断结果: {'已完结' if result else '连载中'}")
        return result