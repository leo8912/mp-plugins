from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import json
import time

from app.plugins import _PluginBase
from app.schemas.types import EventType
from app.log import logger
from app.core.event import eventmanager
from app.core.config import settings
from app.helper.sites import SitesHelper
from app.db import get_db
from app.db.models.site import Site
from app.db.subscribe_oper import SubscribeOper
from sqlalchemy.orm import Session


class varietyshowsubscriber(_PluginBase):
    # 插件名称
    plugin_name = "综艺订阅助手"
    # 插件描述
    plugin_desc = "自动为新添加的综艺订阅添加指定站点"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/leo8912/mp-plugins/main/icons/showsubscriber.png"
    # 插件版本
    plugin_version = "2.20"
    # 插件作者
    plugin_author = "leo"
    # 作者主页
    author_url = "https://github.com/leo8912"
    # 插件配置项ID前缀
    plugin_config_prefix = "showsubscriber_"
    # 加载顺序
    plugin_order = 21
    # 可使用的用户级别
    auth_level = 1

    # 配置属性
    _enabled: bool = False
    _notify: bool = False
    _sites: List[int] = []
    _variety_genre_ids: List[int] = [10764, 10767]
    
    # 处理记录，避免重复处理
    _processed_subscriptions = set()
    
    def init_plugin(self, config: dict = None):
        # 停止现有任务
        self.stop_service()

        # 初始化配置
        if config:
            self._enabled = config.get("enabled")
            self._notify = config.get("notify")
            self._sites = config.get("sites") or []
            variety_genre_ids_str = config.get("variety_genre_ids", "10764,10767")
            self._variety_genre_ids = self._parse_genre_ids(variety_genre_ids_str)
        else:
            # 如果没有配置，则使用默认值
            self._variety_genre_ids = [10764, 10767]
        
        # 清理处理记录
        self._processed_subscriptions.clear()
        
        # 记录初始化信息
        logger.info(f"ShowSubscriber插件初始化完成，启用状态: {self._enabled}")
        logger.info(f"配置的站点列表: {self._sites}")
        logger.info(f"配置的综艺类型ID: {self._variety_genre_ids}")
        logger.info("========================================")

    def get_state(self) -> bool:
        logger.info("ShowSubscriber插件get_state被调用")
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        logger.info("ShowSubscriber插件get_command被调用")
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        logger.info("ShowSubscriber插件get_api被调用")
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """获取配置表单"""
        logger.info("ShowSubscriber插件get_form被调用")
        # 获取站点列表
        site_options = self._get_site_options()
        
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
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '发送通知',
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
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'sites',
                                            'label': '订阅站点',
                                            'items': site_options,
                                            'multiple': True,
                                            'chips': True,
                                            'clearable': True
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
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'variety_genre_ids',
                                            'label': '综艺类型ID',
                                            'placeholder': '10764,10767'
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
                                'props': {'cols': 12},
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
                                                'text': '说明：默认综艺类型ID为10764和10767。如果需要添加其他ID，请用逗号分隔，例如：10764,10767,10769'
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
            "enabled": False,
            "notify": False,
            "sites": [],
            "variety_genre_ids": "10764,10767"
        }

    def get_page(self) -> List[dict]:
        """获取页面"""
        logger.info("ShowSubscriber插件get_page被调用")
        # 获取历史记录
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

        if not isinstance(historys, list):
            historys = [historys]

        # 按照时间倒序
        historys = sorted(historys, key=lambda x: x.get("time") or 0, reverse=True)

        # 表格内容
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
                        'text': history.get("time")
                    },
                    {
                        'component': 'td',
                        'text': history.get("name")
                    },
                    {
                        'component': 'td',
                        'text': history.get("sites")
                    },
                    {
                        'component': 'td',
                        'text': history.get("type")
                    }
                ]
            } for history in historys
        ]

        # 拼装页面
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
                                    'hover': True
                                },
                                'content': [
                                    {
                                        'component': 'thead',
                                        'content': [
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '执行时间'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '订阅名称'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '添加站点'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '操作类型'
                                            }
                                        ]
                                    },
                                    {
                                        'component': 'tbody',
                                        'content': contents
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数
        }]
        """
        logger.info("ShowSubscriber插件get_service被调用")
        pass

    def stop_service(self):
        """
        退出插件
        """
        logger.info("ShowSubscriber插件stop_service被调用")
        pass

    @eventmanager.register(EventType.SubscribeAdded)
    def handle_subscribe_added(self, event):
        """处理订阅添加事件"""
        logger.info("ShowSubscriber插件收到订阅添加事件 <<<<<<<<< 关键日志")
        
        # 获取事件数据
        event_data = event.event_data
        if not event_data:
            logger.warn("ShowSubscriber插件未收到事件数据，跳过处理")
            return
            
        # 检查插件是否启用
        if not self._enabled:
            logger.info("ShowSubscriber插件未启用，跳过处理")
            return
            
        # 获取媒体信息
        media_info = event_data.get("media_info") or event_data.get("mediainfo") or {}
        if not media_info:
            logger.warn("ShowSubscriber插件未收到媒体信息，跳过处理")
            return
            
        media_title = media_info.get("title", "未知媒体")
        logger.info(f"处理媒体: {media_title}")
            
        # 检查是否为综艺
        if not self._is_variety_show(media_info):
            logger.info(f"媒体 {media_title} 不是综艺类型，跳过处理")
            return
            
        logger.info(f"检测到综艺: {media_title}")
            
        # 获取订阅信息
        subscribe_info = event_data.get("subscribe_info") or event_data.get("subscribe") or {}
        
        # 尝试从不同字段获取订阅ID
        subscribe_id = (subscribe_info.get("id") or 
                       event_data.get("subscribe_id") or 
                       event_data.get("sub_id"))
        
        # 如果仍然没有订阅ID，尝试从媒体信息中获取
        if not subscribe_id:
            subscribe_id = media_info.get("subscribe_id") or media_info.get("sub_id")
            
        # 检查是否已经处理过该订阅
        if subscribe_id and subscribe_id in self._processed_subscriptions:
            logger.debug(f"订阅 {subscribe_id} 已经处理过，跳过")
            return
            
        # 添加订阅站点
        if subscribe_id:
            logger.info(f"开始为综艺 {media_title} 添加订阅站点，订阅ID: {subscribe_id}")
            # 记录已处理的订阅
            self._processed_subscriptions.add(subscribe_id)
            added_sites = self._add_subscription_sites(subscribe_id, media_title)
            
            # 获取站点名称
            site_names = []
            if added_sites:
                try:
                    db = next(get_db())
                    for site_id in added_sites:
                        site = Site.get(db, site_id)
                        if site:
                            site_names.append(site.name)
                        else:
                            site_names.append(str(site_id))
                except Exception as e:
                    logger.debug(f"获取站点名称失败: {e}")
                    site_names = [str(site_id) for site_id in added_sites]
                finally:
                    try:
                        db.close()
                    except:
                        pass
            
            # 保存处理历史
            history_content = {
                "added_sites": added_sites,
                "configured_sites": self._sites
            }
            
            # 读取历史记录
            history = self.get_data('history') or []
            
            # 添加新记录
            history.append({
                'name': media_title,
                'sites': "、".join(site_names) if site_names else "无",
                'type': '综艺订阅站点添加',
                'content': json.dumps(history_content),
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
            })
            
            # 保存历史记录
            self.save_data(key="history", value=history)
            
            # 发送通知
            if self._notify and added_sites:
                sites_text = "、".join(site_names)
                self.post_message(
                    title="【综艺订阅助手】",
                    text=f"🎉 检测到综艺《{media_title}》\n"
                         f"✅ 已自动添加订阅站点：{sites_text}"
                )
            elif self._notify and not added_sites:
                self.post_message(
                    title="【综艺订阅助手】",
                    text=f"🎉 检测到综艺《{media_title}》\n"
                         f"ℹ️ 订阅站点无需变更"
                )
        else:
            logger.warn(f"未找到订阅ID，无法为综艺 {media_title} 添加订阅站点")

    def _is_variety_show(self, media_info: dict) -> bool:
        """判断是否为综艺"""
        genre_ids = media_info.get("genre_ids", [])
        logger.debug(f"检查媒体类型，genre_ids: {genre_ids}")
        
        if not genre_ids:
            logger.debug("未找到genre_ids，不是综艺类型")
            return False
            
        # 检查是否有匹配的综艺类型ID
        variety_ids_set = set(self._variety_genre_ids)
        media_genre_set = set(genre_ids)
        
        result = bool(variety_ids_set.intersection(media_genre_set))
        logger.debug(f"是否为综艺类型: {result}")
        return result

    def _add_subscription_sites(self, subscribe_id: int, media_title: str) -> List[int]:
        """为综艺添加订阅站点"""
        logger.info(f"开始为订阅ID {subscribe_id} 添加站点: {self._sites}")
        
        # 获取当前订阅信息
        subscribe = SubscribeOper().get(subscribe_id)
        if not subscribe:
            logger.error(f"未找到订阅信息，订阅ID: {subscribe_id}")
            return []
            
        # 获取当前订阅的站点列表
        current_sites = subscribe.sites or []
        logger.info(f"当前站点列表: {current_sites} (类型: {type(current_sites)})")
        
        # 处理当前站点列表
        if isinstance(current_sites, str):
            current_sites = current_sites.split(',') if current_sites else []
        elif not isinstance(current_sites, list):
            current_sites = []
            
        # 确保所有站点ID都是整数类型
        processed_current_sites = []
        for site in current_sites:
            if isinstance(site, str) and site.isdigit():
                processed_current_sites.append(int(site))
            elif isinstance(site, (int, float)):
                processed_current_sites.append(int(site))
                
        logger.info(f"处理后的当前站点列表: {processed_current_sites}")
                
        # 处理插件配置的站点列表
        logger.info(f"插件配置的站点原始数据: {self._sites} (类型: {type(self._sites)})")
        processed_plugin_sites = []
        for site in self._sites:
            if isinstance(site, str) and site.isdigit():
                processed_plugin_sites.append(int(site))
            elif isinstance(site, (int, float)):
                processed_plugin_sites.append(int(site))
                
        logger.info(f"处理后的插件站点列表: {processed_plugin_sites}")
        
        try:
            # 合并站点列表，确保是整数列表
            new_sites = list(set(processed_current_sites + processed_plugin_sites))
            logger.info(f"合并后的站点列表: {new_sites}")
            
            # 只有当有新站点需要添加时才更新
            if new_sites and set(new_sites) != set(processed_current_sites):
                # 更新订阅信息 - 使用正确的参数格式
                SubscribeOper().update(subscribe_id, {
                    "sites": new_sites
                })
                
                # 记录日志
                logger.info(f"为订阅 {media_title}({subscribe_id}) 添加站点成功: {new_sites}")
                
                # 返回新增的站点
                added_sites = list(set(new_sites) - set(processed_current_sites))
                return added_sites
            else:
                logger.info(f"订阅 {media_title}({subscribe_id}) 无需更新站点")
                return []
                
        except Exception as e:
            logger.error(f"添加订阅站点失败: {str(e)}", exc_info=True)
            return []
            
    def _get_site_options(self) -> List[Dict[str, Any]]:
        """获取站点选项列表"""
        logger.info("ShowSubscriber插件_get_site_options被调用")
        try:
            # 获取数据库会话
            db: Session = next(get_db())
            
            # 获取所有站点
            sites = Site.list_order_by_pri(db)
            
            # 构造选项列表
            site_options = [
                {
                    'title': site.name,
                    'value': site.id
                }
                for site in sites if site and site.name
            ]
            
            return site_options
        except Exception as e:
            logger.error(f"获取站点列表失败: {str(e)}")
            return []
        finally:
            try:
                db.close()
            except:
                pass

    def _parse_genre_ids(self, genre_ids_str: str) -> List[int]:
        """解析类型ID字符串"""
        try:
            return [int(x.strip()) for x in genre_ids_str.split(",") if x.strip().isdigit()]
        except Exception as e:
            logger.error(f"解析类型ID失败: {str(e)}")
            return [10764, 10767]