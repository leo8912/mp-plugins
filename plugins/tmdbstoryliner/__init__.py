import json
import hashlib
import random
import requests
import time
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from app.plugins import _PluginBase
from app.log import logger
from app.utils.string import StringUtils
from app.scheduler import Scheduler
from app.core.config import settings
from app.helper.mediaserver import MediaServerHelper
from app.chain.mediaserver import MediaServerChain
from typing import Optional, Dict
from app.schemas import ServiceInfo
from requests import RequestException
from app.utils.common import retry


class TmdbStoryliner(_PluginBase):
    # 插件元数据
    plugin_name = "剧情更新器"
    plugin_desc = "定时从TMDB获取剧集和电影的剧情简介，并将英文内容翻译成中文"
    plugin_icon = "https://raw.githubusercontent.com/leo8912/mp-plugins/main/icons/tmdbstoryliner.png"
    plugin_author = "leo"
    author_url = "https://github.com/leo8912"
    plugin_version = "1.25"
    plugin_locale = "zh"
    plugin_config_prefix = "tmdbstoryliner_"
    plugin_site = "https://www.themoviedb.org/"
    plugin_order = 10
    
    # 插件配置项
    _enabled = False
    _cron = "0 2 * * *"
    _translate_service = "baidu"
    _tmdb_api_key = ""
    _translate_app_id = ""
    _translate_secret_key = ""
    _update_movies = True
    _update_series = True
    _mediaservers = []
    _library_paths = []
    _onlyonce = False
    
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
            self._update_movies = config.get("update_movies")
            self._update_series = config.get("update_series")
            self._mediaservers = config.get("mediaservers") or []
            self._library_paths = config.get("library_paths") or []
            self._onlyonce = config.get("onlyonce", False)
            
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
                "update_movies": self._update_movies,
                "update_series": self._update_series,
                "mediaservers": self._mediaservers,
                "library_paths": self._library_paths,
                "onlyonce": False
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
        return [{
            "path": "/update_storylines",
            "endpoint": self.update_storylines_api,
            "methods": ["GET"],
            "summary": "手动更新剧情简介",
            "description": "手动触发剧情简介更新任务"
        }]
    
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
        # 如果没有配置媒体服务器，则获取所有可用的媒体服务实例
        services = MediaServerHelper().get_services(type_filter=type_filter, 
                                                   name_filters=self._mediaservers if self._mediaservers else None)
        if not services:
            logger.warning("获取媒体服务器实例失败，请检查配置")
            return None

        active_services = {}
        for service_name, service_info in services.items():
            if service_info.instance.is_inactive():
                logger.warning(f"媒体服务{service_name} 未连接，请检查配置")
            else:
                active_services[service_name] = service_info

        if not active_services:
            logger.warning("没有已连接的媒体服务器，请检查配置")
            return None

        return active_services
    
    def _get_library_paths(self) -> List[dict]:
        """
        获取媒体库路径列表
        """
        library_paths = []
        
        # 获取所有配置的媒体服务器
        server_configs = MediaServerHelper().get_configs().values()
        if not server_configs:
            logger.warning("没有配置媒体服务器")
            return library_paths
        
        # 使用MediaServerChain获取真实的媒体库信息
        try:
            mediaserver_chain = MediaServerChain()
            
            # 遍历每个配置的媒体服务器
            for server_config in server_configs:
                server_name = server_config.name
                
                # 检查服务器是否在用户选择的列表中（如果用户有选择）
                if self._mediaservers and server_name not in self._mediaservers:
                    continue
                
                # 获取该服务器的所有媒体库
                libraries = mediaserver_chain.librarys(server_name)
                
                # 遍历每个媒体库
                for library in libraries:
                    library_paths.append({
                        "title": f"{server_name} - {library.name}",
                        "value": f"{server_name}:{library.id}"
                    })
                    
        except Exception as e:
            logger.error(f"获取媒体库信息失败：{e}")
            
            # 如果获取失败，使用示例数据
            for server_config in server_configs:
                server_name = server_config.name
                
                # 检查服务器是否在用户选择的列表中（如果用户有选择）
                if self._mediaservers and server_name not in self._mediaservers:
                    continue
                    
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
        
        return library_paths
    
    def get_iteminfo(self, server: str, server_type: str, itemid: str) -> dict:
        """
        获得媒体项详情
        """
        service_infos = self.service_infos()
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
        service_infos = self.service_infos()
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
                                                {'title': '百度翻译', 'value': 'baidu'}
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
                                            'model': 'translate_app_id',
                                            'label': '百度翻译APP ID',
                                            'placeholder': '请输入百度翻译APP ID'
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
                                            'model': 'translate_secret_key',
                                            'label': '百度翻译密钥',
                                            'placeholder': '请输入百度翻译密钥'
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
                                            'model': 'mediaservers',
                                            'label': '媒体服务',
                                            'items': [{"title": config.name, "value": config.name}
                                                      for config in MediaServerHelper().get_configs().values()]
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
                                            'items': self._get_library_paths()
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
                                            'model': 'update_movies',
                                            'label': '更新电影',
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
                                            'model': 'update_series',
                                            'label': '更新电视剧',
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
                                                'text': '注意：需要配置TMDB API密钥和百度翻译API密钥才能正常使用此插件',
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": self._enabled,
            "cron": self._cron,
            "translate_service": self._translate_service,
            "tmdb_api_key": self._tmdb_api_key,
            "translate_app_id": self._translate_app_id,
            "translate_secret_key": self._translate_secret_key,
            "update_movies": self._update_movies,
            "update_series": self._update_series,
            "mediaservers": self._mediaservers,
            "library_paths": self._library_paths,
            "onlyonce": False
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
        
        # 获取媒体库中的项目
        if self._update_movies:
            self.update_movie_storylines()
        
        if self._update_series:
            self.update_series_storylines()
        
        logger.info("TMDB剧情简介更新完成")
    
    def update_movie_storylines(self):
        """
        更新电影剧情简介
        """
        logger.info("开始更新电影剧情简介")
        
        # 1. 获取媒体库中的电影
        # 获取活动的媒体服务器
        service_infos = self.service_infos()
        if not service_infos:
            logger.warning("没有配置或连接媒体服务器")
            return
        
        # 使用MediaServerChain获取媒体库中的电影
        try:
            mediaserver_chain = MediaServerChain()
            
            # 遍历每个活动的媒体服务器
            for server_name, server_info in service_infos.items():
                # 检查服务器是否在用户选择的列表中（如果用户有选择）
                if self._mediaservers and server_name not in self._mediaservers:
                    continue
                
                # 获取该服务器的所有媒体库
                libraries = mediaserver_chain.librarys(server_name)
                
                # 遍历每个媒体库
                for library in libraries:
                    # 如果用户指定了媒体库路径，则检查是否匹配
                    if self._library_paths and f"{server_name}:{library.id}" not in self._library_paths:
                        continue
                    
                    # 获取媒体库中的电影
                    movies = mediaserver_chain.items(server_name, library.id)
                    
                    # 遍历每部电影
                    for movie in movies:
                        # 检查媒体类型，只处理电影类型
                        if hasattr(movie, 'type') and movie.type != 'Movie':
                            continue
                        if not movie or not hasattr(movie, 'tmdbid') or not movie.tmdbid:
                            logger.warning(f"电影 {movie.title if movie else '未知'} 缺少TMDB ID，跳过处理")
                            continue
                        
                        # 2. 从TMDB获取电影详细信息（带重试机制）
                        movie_details = None
                        for i in range(3):  # 最多重试3次
                            movie_details = self.get_tmdb_movie_details(movie.tmdbid)
                            if movie_details:
                                break
                            logger.warning(f"获取电影 {movie.title} 的TMDB信息失败，正在进行第{i+1}次重试")
                            time.sleep(1)  # 间隔1秒重试
                        
                        if not movie_details:
                            logger.warning(f"无法获取电影 {movie.title} 的TMDB信息")
                            continue
                        
                        # 3. 处理剧情简介
                        overview = movie_details.get('overview', '')
                        if not overview:
                            logger.debug(f"电影 {movie.title} 没有英文剧情简介")
                            continue
                        
                        # 翻译剧情简介
                        translated_overview = overview
                        if self._translate_service and self._translate_app_id and self._translate_secret_key:
                            translated_overview = self.translate_text(overview)
                            if translated_overview != overview:
                                logger.info(f"已翻译电影 {movie.title} 剧情简介")
                            else:
                                logger.info(f"电影 {movie.title} 剧情简介无需翻译或翻译失败")
                        
                        # 4. 更新媒体库
                        # 获取媒体项详情
                        iteminfo = self.get_iteminfo(server_name, server_info.type, movie.itemid)
                        if iteminfo:
                            # 更新剧情简介
                            iteminfo['Overview'] = translated_overview
                            # 保存更新
                            if self.set_iteminfo(server_name, server_info.type, movie.itemid, iteminfo):
                                logger.info(f"已更新电影 {movie.title} 剧情简介")
                            else:
                                logger.error(f"更新电影 {movie.title} 剧情简介失败")
                        else:
                            logger.error(f"获取电影 {movie.title} 详情失败")
                        
                        # 保存更新历史
                        self.save_update_history(movie.title, "电影", "已更新" if translated_overview != overview else "无需翻译")
        except Exception as e:
            logger.error(f"更新电影剧情简介时发生错误：{e}")
        
        logger.info("电影剧情简介更新完成")
    
    def update_series_storylines(self):
        """
        更新电视剧剧情简介
        """
        logger.info("开始更新电视剧剧情简介")
        
        # 1. 获取媒体库中的电视剧
        # 获取活动的媒体服务器
        service_infos = self.service_infos()
        if not service_infos:
            logger.warning("没有配置或连接媒体服务器")
            return
        
        # 使用MediaServerChain获取媒体库中的电视剧
        try:
            mediaserver_chain = MediaServerChain()
            
            # 遍历每个活动的媒体服务器
            for server_name, server_info in service_infos.items():
                # 检查服务器是否在用户选择的列表中（如果用户有选择）
                if self._mediaservers and server_name not in self._mediaservers:
                    continue
                
                # 获取该服务器的所有媒体库
                libraries = mediaserver_chain.librarys(server_name)
                
                # 遍历每个媒体库
                for library in libraries:
                    # 如果用户指定了媒体库路径，则检查是否匹配
                    if self._library_paths and f"{server_name}:{library.id}" not in self._library_paths:
                        continue
                    
                    # 获取媒体库中的电视剧
                    tv_series = mediaserver_chain.items(server_name, library.id)
                    
                    # 遍历每部电视剧
                    for series in tv_series:
                        # 检查媒体类型，只处理电视剧类型
                        if hasattr(series, 'type') and series.type != 'TV':
                            continue
                        if not series or not hasattr(series, 'tmdbid') or not series.tmdbid:
                            logger.warning(f"电视剧 {series.title if series else '未知'} 缺少TMDB ID，跳过处理")
                            continue
                        
                        # 2. 从TMDB获取电视剧详细信息（带重试机制）
                        series_details = None
                        for i in range(3):  # 最多重试3次
                            series_details = self.get_tmdb_series_details(series.tmdbid)
                            if series_details:
                                break
                            logger.warning(f"获取电视剧 {series.title} 的TMDB信息失败，正在进行第{i+1}次重试")
                            time.sleep(1)  # 间隔1秒重试
                        
                        if not series_details:
                            logger.warning(f"无法获取电视剧 {series.title} 的TMDB信息")
                            continue
                        
                        # 获取季数信息
                        seasons = series_details.get('seasons', [])
                        
                        # 遍历每季
                        for season in seasons:
                            season_number = season.get('season_number')
                            if season_number is None:
                                continue
                            
                            # 跳过特殊季（如预告片等）
                            if season_number == 0:
                                continue
                            
                            # 遍历每集
                            episode_count = season.get('episode_count', 0)
                            for episode_number in range(1, episode_count + 1):
                                # 获取剧集详细信息（带重试机制）
                                episode_details = None
                                for i in range(3):  # 最多重试3次
                                    episode_details = self.get_tmdb_episode_details(series.tmdbid, season_number, episode_number)
                                    if episode_details:
                                        break
                                    logger.warning(f"获取 {series.title} S{season_number:02d}E{episode_number:02d} 的TMDB信息失败，正在进行第{i+1}次重试")
                                    time.sleep(1)  # 间隔1秒重试
                                
                                if not episode_details:
                                    logger.warning(f"无法获取 {series.title} S{season_number:02d}E{episode_number:02d} 的TMDB信息")
                                    continue
                                
                                # 3. 处理剧情简介
                                overview = episode_details.get('overview', '')
                                if not overview:
                                    logger.debug(f"{series.title} S{season_number:02d}E{episode_number:02d} 没有英文剧情简介")
                                    continue
                                
                                # 翻译剧情简介
                                translated_overview = overview
                                if self._translate_service and self._translate_app_id and self._translate_secret_key:
                                    translated_overview = self.translate_text(overview)
                                    if translated_overview != overview:
                                        logger.info(f"已翻译 {series.title} S{season_number:02d}E{episode_number:02d} 剧情简介")
                                    else:
                                        logger.info(f"{series.title} S{season_number:02d}E{episode_number:02d} 剧情简介无需翻译或翻译失败")
                                
                                # 4. 更新媒体库
                                # 获取剧集详情
                                iteminfo = self.get_iteminfo(server_name, server_info.type, series.itemid)
                                if iteminfo:
                                    # 更新剧集剧情简介
                                    iteminfo['Overview'] = translated_overview
                                    # 保存更新
                                    if self.set_iteminfo(server_name, server_info.type, series.itemid, iteminfo):
                                        logger.info(f"已更新 {series.title} S{season_number:02d}E{episode_number:02d} 剧情简介")
                                    else:
                                        logger.error(f"更新 {series.title} S{season_number:02d}E{episode_number:02d} 剧情简介失败")
                                else:
                                    logger.error(f"获取 {series.title} S{season_number:02d}E{episode_number:02d} 详情失败")
                                
                                # 保存更新历史
                                self.save_update_history(
                                    f"{series.title} S{season_number:02d}E{episode_number:02d}", 
                                    "电视剧剧集", 
                                    "已更新" if translated_overview != overview else "无需翻译"
                                )
        except Exception as e:
            logger.error(f"更新电视剧剧情简介时发生错误：{e}")
        
        logger.info("电视剧剧情简介更新完成")
    
    def get_tmdb_movie_details(self, movie_id: int) -> dict:
        """
        获取电影详情
        """
        try:
            url = f"https://api.themoviedb.org/3/movie/{movie_id}"
            params = {
                "api_key": self._tmdb_api_key,
                "language": "en-US"
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取电影详情失败：{e}")
            return {}
    
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
        try:
            url = f"https://api.themoviedb.org/3/tv/{series_id}/season/{season_number}/episode/{episode_number}"
            params = {
                "api_key": self._tmdb_api_key,
                "language": "en-US"
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取剧集详情失败：{e}")
            return {}
    
    def translate_text(self, text: str, source_lang: str = "en", target_lang: str = "zh") -> str:
        """
        使用百度翻译文本
        """
        if not text or source_lang == target_lang:
            return text
        
        try:
            if self._translate_service == "baidu":
                return self._baidu_translate(text, source_lang, target_lang)
            else:
                logger.warn(f"不支持的翻译服务：{self._translate_service}")
                return text
        except Exception as e:
            logger.error(f"翻译失败：{e}")
            return text
    
    def _baidu_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        百度翻译
        """
        try:
            url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
            
            # 生成签名
            salt = random.randint(32768, 65536)
            sign_str = (self._translate_app_id or "") + text + str(salt) + (self._translate_secret_key or "")
            sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
            
            params = {
                "q": text,
                "from": source_lang,
                "to": target_lang,
                "appid": self._translate_app_id,
                "salt": salt,
                "sign": sign
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if "trans_result" in result and len(result["trans_result"]) > 0:
                return result["trans_result"][0]["dst"]
            else:
                logger.error(f"百度翻译返回错误：{result}")
                return text
        except Exception as e:
            logger.error(f"百度翻译失败：{e}")
            return text
    
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
