import time
from typing import List, Tuple, Dict, Any, Optional

from apscheduler.triggers.cron import CronTrigger

from app.sdk.logging import logger
from app.sdk.events import Event, eventmanager
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.schemas.types import EventType
from app.sdk.services import DownloaderHelper


class multitrackereditor(_PluginBase):
    # 常量定义
    QBITTORRENT = "qbittorrent"
    TRANSMISSION = "transmission"

    # 插件元信息
    plugin_name = "多下载器tracker替换"
    plugin_desc = "批量替换多下载器的tracker，支持周期性巡检"
    plugin_icon = "https://raw.githubusercontent.com/leo8912/mp-plugins/main/icons/multitrackereditor.png"
    plugin_version = "3.0.0"
    plugin_author = "leo"
    author_url = "https://github.com/leo8912"
    plugin_config_prefix = "multitrackereditor_"
    plugin_order = 30
    # 可使用的用户级别
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._enabled = False
        self._notify = 1  # 默认仅有替换任务时通知
        self._onlyonce = False
        self._run_con_enable = False
        self._run_con = ""
        self._tracker_config = ""
        self._downloaders = []

    def init_plugin(self, config: Optional[dict] = None):
        if config:
            self._enabled = config.get("enabled", False)
            self._notify = config.get("notify", 1)
            self._onlyonce = config.get("onlyonce", False)
            self._run_con_enable = config.get("run_con_enable", False)
            self._run_con = config.get("run_con", "")
            self._tracker_config = config.get("tracker_config", "")
            self._downloaders = config.get("downloaders", [])
        if self._onlyonce:
            logger.info("tracker替换任务：立即运行一次")
            self.task()
            self._onlyonce = False
            self.__update_config()

    def update_config(self, config: dict):
        # 彻底过滤onlyonce字段
        if "onlyonce" in config:
            config = dict(config)
            config.pop("onlyonce")
        super().update_config(config)

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        downloader_list = self.get_downloader_list()
        logger.debug(f"[get_form] get_downloader_list: {downloader_list}")
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
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
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'notify',
                                            'label': '发送通知',
                                            'items': [
                                                {'title': '每次运行都通知', 'value': 0},
                                                {'title': '仅有替换任务时通知', 'value': 1},
                                                {'title': '不通知', 'value': 2}
                                            ],
                                            'placeholder': '请选择通知模式'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
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
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'run_con',
                                            'label': 'cron表达式',
                                            'placeholder': '* * * * *'
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
                                            'model': 'run_con_enable',
                                            'label': '启用周期性巡检',
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
                                            'model': 'downloaders',
                                            'label': '下载器',
                                            'items': downloader_list,
                                            'multiple': True,
                                            'chips': True,
                                            'placeholder': '选择下载器'
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
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'tracker_config',
                                            'label': 'tracker替换配置',
                                            'rows': 6,
                                            'placeholder': '每一行一个配置，中间以|分隔\n待替换文本|替换的文本',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                ]
            }
        ], {
            "enabled": self._enabled,
            "notify": self._notify if self._notify is not None else 1,
            "onlyonce": False,
            "run_con_enable": self._run_con_enable,
            "run_con": self._run_con,
            "tracker_config": self._tracker_config,
            "downloaders": self._downloaders or [],
        }

    def __update_config(self):
        self.update_config({
            "enabled": self._enabled,
            "notify": self._notify,
            "onlyonce": False,
            "run_con_enable": self._run_con_enable,
            "run_con": self._run_con,
            "tracker_config": self._tracker_config,
            "downloaders": self._downloaders or [],
        })

    def task(self):
        """
        执行tracker替换任务
        """
        logger.info(f"tracker替换任务执行，下载器：{self._downloaders}")
        logger.debug(f"tracker_config: {self._tracker_config}")

        if not self._downloaders:
            logger.warning("未配置下载器，跳过任务执行")
            return
        if not self._tracker_config:
            logger.warning("未配置tracker替换规则，跳过任务执行")
            return
        tracker_rules = self._parse_tracker_config()
        if not tracker_rules:
            logger.warning("tracker配置解析失败，跳过任务执行")
            return
        logger.info(f"解析到 {len(tracker_rules)} 条tracker替换规则")
        services = DownloaderHelper().get_services(name_filters=self._downloaders)
        if not services:
            logger.warning("获取下载器服务失败")
            return

        total_torrents = 0
        updated_torrents = 0
        failed_torrents = 0
        per_downloader_stats = {}

        for service_name, service_info in services.items():
            torrents, _ = service_info.instance.get_torrents()
            per_downloader_stats[service_name] = {'total': 0, 'updated': 0, 'failed': 0}
            for torrent in torrents:
                per_downloader_stats[service_name]['total'] += 1
                total_torrents += 1
                current_trackers = self._get_torrent_trackers(torrent, service_info.type)
                updated_trackers = self._check_and_replace_trackers(current_trackers, tracker_rules)
                if updated_trackers != current_trackers:
                    logger.info('-------------------------------')
                    name = torrent.get("name", "Unknown")
                    torrent_hash = self._get_torrent_hash(torrent, service_info.type)
                    logger.info(f'🎬 种子：{name}')
                    logger.info(f'🔑 Hash: {torrent_hash}')
                    logger.info(f'🌐 当前tracker: {current_trackers[0] if current_trackers else "无"}')
                    logger.info(f'➡️ 替换后tracker: {updated_trackers[0] if updated_trackers else "无"}')
                    success = self._update_torrent_trackers(service_info.instance, torrent, torrent_hash, updated_trackers, service_info.type)
                    if success:
                        per_downloader_stats[service_name]['updated'] += 1
                        updated_torrents += 1
                        logger.info('✅ 替换成功')
                    else:
                        per_downloader_stats[service_name]['failed'] += 1
                        failed_torrents += 1
                        logger.warning('❌ 替换失败')
                    logger.info('-------------------------------')

        # 统计需修改的种子数
        need_update = updated_torrents + failed_torrents
        # 通知逻辑
        notify_mode = self._notify
        has_update = need_update > 0
        if notify_mode == 0 or (notify_mode == 1 and has_update):
            msg_lines = ["🎯 Tracker替换任务完成"]
            for d, stat in per_downloader_stats.items():
                msg_lines.append(f"📦 {d}：总种子数 {stat['total']}，需修改 {stat['updated']+stat['failed']}，成功 {stat['updated']}，失败 {stat['failed']}")
            msg_lines.append(f"🔢 总计：{total_torrents}，需修改 {need_update}，成功 {updated_torrents}，失败 {failed_torrents}")
            self.send_site_message("Tracker替换任务完成 🚀", "\n".join(msg_lines))
        logger.info(f"Tracker替换任务完成，总种子数：{total_torrents}，成功替换：{updated_torrents}，失败：{failed_torrents}")

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [{
            "cmd": "/tracker_replace",
            "event": EventType.PluginAction,
            "desc": "Tracker替换",
            "category": "下载管理",
            "data": {
                "action": "tracker_replace"
            }
        }]

    @eventmanager.register(EventType.PluginAction)
    def run_command(self, event: Event) -> None:
        """处理远程命令 /tracker_replace"""
        if (event.event_data or {}).get("action") != "tracker_replace":
            return
        self.task()

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        if self._run_con_enable and self._run_con:
            logger.info(f"{'*' * 30}TrackerEditor: 注册公共调度服务{'*' * 30}")
            return [
                {
                    "id": "TrackerChangeRun",
                    "name": "启用周期性Tracker替换",
                    "trigger": CronTrigger.from_crontab(self._run_con),
                    "func": self.task,
                    "kwargs": {}
                }]
        return []

    def get_page(self) -> List[dict]:
        return []

    def get_state(self) -> bool:
        return self._enabled

    def stop_service(self):
        """插件无后台资源需要释放"""
        pass

    def send_site_message(self, title, message):
        self.post_message(
            mtype=NotificationType.SiteMessage,
            title=title,
            text=message
        )

    def get_downloader_list(self) -> List[Dict[str, Any]]:
        try:
            configs = DownloaderHelper().get_configs()
            if configs:
                return [{"title": config.name, "value": config.name} for config in configs.values()]
            else:
                logger.warning("获取下载器列表失败")
                return []
        except Exception as e:
            logger.error(f"获取下载器列表异常: {e}")
            return []

    def _parse_tracker_config(self) -> List[Tuple[str, str]]:
        rules = []
        if not self._tracker_config:
            return rules
        for line in self._tracker_config.strip().split('\n'):
            line = line.strip()
            if not line or '|' not in line:
                continue
            parts = line.split('|', 1)
            if len(parts) == 2:
                old_tracker = parts[0].strip()
                new_tracker = parts[1].strip()
                if old_tracker and new_tracker:
                    rules.append((old_tracker, new_tracker))
        return rules

    def _get_torrent_hash(self, torrent, dl_type: str) -> str:
        try:
            if dl_type == self.QBITTORRENT:
                return torrent.get("hash")
            elif dl_type == self.TRANSMISSION:
                return torrent.hashString
            else:
                logger.error(f"未知下载器类型: {dl_type}")
                return ""
        except Exception as e:
            logger.error(f"获取种子hash失败：{e}")
            return ""

    def _get_torrent_trackers(self, torrent, dl_type: str) -> List[str]:
        try:
            if dl_type == self.QBITTORRENT:
                trackers = torrent.get("trackers", [])
                if not trackers:
                    tracker = torrent.get("tracker", "")
                    if tracker:
                        trackers = [tracker]
                tracker_urls = []
                for tracker in trackers:
                    if isinstance(tracker, dict):
                        if tracker.get("url"):
                            tracker_urls.append(tracker.get("url"))
                    elif isinstance(tracker, str):
                        tracker_urls.append(tracker)
                return tracker_urls
            elif dl_type == self.TRANSMISSION:
                trackers = torrent.trackers
                tracker_urls = []
                if hasattr(trackers, 'announce'):
                    tracker_urls.append(trackers.announce)
                elif isinstance(trackers, list):
                    for tracker in trackers:
                        if hasattr(tracker, 'announce'):
                            tracker_urls.append(tracker.announce)
                elif hasattr(trackers, '__iter__'):
                    try:
                        for tracker in trackers:
                            if hasattr(tracker, 'announce'):
                                tracker_urls.append(tracker.announce)
                    except Exception as e:
                        logger.error(f"Transmission _get_torrent_trackers - 迭代tracker时出错：{e}")
                return tracker_urls
            else:
                logger.error(f"未知下载器类型: {dl_type}")
                return []
        except Exception as e:
            logger.error(f"获取种子tracker失败：{e}")
            logger.error(f"tracker对象类型：{type(torrent.trackers) if hasattr(torrent, 'trackers') else 'No trackers'}")
            return []

    def _check_and_replace_trackers(self, current_trackers: List[str], rules: List[Tuple[str, str]]) -> List[str]:
        updated_trackers = current_trackers.copy()
        for old_tracker, new_tracker in rules:
            for i, tracker in enumerate(updated_trackers):
                if old_tracker in tracker:
                    updated_trackers[i] = tracker.replace(old_tracker, new_tracker)
                    logger.info(f"Tracker替换：{tracker} -> {updated_trackers[i]}")
        return updated_trackers

    def _update_torrent_trackers(self, downloader, torrent, torrent_hash: str, new_trackers: List[str], dl_type: str) -> bool:
        try:
            if dl_type == self.QBITTORRENT:
                try:
                    logger.info(f"qBittorrent 使用edit_tracker方法进行逐个替换")
                    torrent_obj = torrent
                    current_trackers = self._get_torrent_trackers(torrent_obj, dl_type)
                    success_count = 0
                    total_replace_count = len([1 for old, new in zip(current_trackers, new_trackers) if old != new])
                    for i, (old_tracker, new_tracker) in enumerate(zip(current_trackers, new_trackers)):
                        if old_tracker != new_tracker:
                            try:
                                logger.info(f"qBittorrent 替换tracker: {old_tracker} -> {new_tracker}")
                                result = torrent_obj.edit_tracker(orig_url=old_tracker, new_url=new_tracker)
                                # 增加重试和延迟机制，最多重试3次，每次间隔1秒
                                for retry in range(3):
                                    time.sleep(1)
                                    torrents_after, _ = downloader.get_torrents()
                                    updated_torrent_obj = None
                                    for t in torrents_after:
                                        if t.get("hash") == torrent_hash:
                                            updated_torrent_obj = t
                                            break
                                    if updated_torrent_obj:
                                        updated_tracker_list = self._get_torrent_trackers(updated_torrent_obj, dl_type)
                                        # 只要新tracker文本出现在tracker列表中即判定为成功
                                        if any(new_tracker in tracker for tracker in updated_tracker_list):
                                            logger.info(f"tracker替换最终验证成功: {old_tracker} -> {new_tracker}")
                                            success_count += 1
                                            break
                                        else:
                                            logger.warning(f"tracker替换最终验证失败: {old_tracker} -> {new_tracker}，当前tracker列表: {updated_tracker_list}，重试{retry+1}")
                                    else:
                                        logger.warning(f"未能重新获取到hash={torrent_hash}的最新种子对象，无法验证，重试{retry+1}")
                                else:
                                    logger.warning(f"tracker替换最终验证失败: {old_tracker} -> {new_tracker}，重试已达上限")
                            except Exception as e:
                                logger.error(f"qBittorrent edit_tracker异常: {old_tracker} -> {new_tracker}, 错误: {e}")
                    logger.info(f"qBittorrent 总共需要替换{total_replace_count}个tracker，调用成功{success_count}个")
                    return success_count > 0
                except Exception as e:
                    logger.error(f"qBittorrent edit_tracker方法失败：{e}")
                    return False
            elif dl_type == self.TRANSMISSION:
                try:
                    logger.info(f"Transmission 尝试使用update_tracker方法，参数：{new_trackers}")
                    tracker_list = [[tracker] for tracker in new_trackers]
                    logger.info(f"Transmission 使用二维数组格式：{tracker_list}")
                    result = downloader.update_tracker(torrent_hash, tracker_list)
                    logger.info(f"Transmission update_tracker调用成功，结果：{result}")
                    if result is True:
                        return True
                    else:
                        logger.warning(f"Transmission update_tracker返回False")
                        return False
                except Exception as e:
                    logger.error(f"Transmission update_tracker方法失败：{e}")
                    return False
            else:
                logger.error(f"未知下载器类型: {dl_type}")
                return False
        except Exception as e:
            logger.error(f"更新种子tracker失败：{e}")
            return False
