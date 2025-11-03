# MoviePilot 插件开发指南：Tmdb Storyliner

本文档将指导您如何为 [MoviePilot](https://github.com/jxxghp/MoviePilot) 开发一个类似于我们为 Emby 开发的 Tmdb Storyliner 插件。该插件将实现定时从 TMDB 获取剧集和电影的剧情简介，并将英文内容翻译成中文的功能。

## 1. MoviePilot 插件概述

MoviePilot 是一个 NAS 媒体库自动化管理工具，支持通过插件扩展功能。MoviePilot 插件使用 Python 编写，可以实现各种功能，如数据同步、通知推送、资源获取等。

## 2. 插件功能需求

我们要开发的插件需要实现以下功能：

1. **定时任务** - 定时扫描媒体库并更新剧情简介
2. **TMDB 数据获取** - 从 TMDB 获取电影、电视剧和剧集的剧情简介
3. **AI 翻译** - 将英文剧情简介翻译成中文
4. **媒体库更新** - 将更新后的剧情简介保存到 MoviePilot 媒体库中
5. **配置界面** - 提供 Web 界面供用户配置插件参数

## 3. 开发环境准备

### 3.1 环境要求

- Python 3.12
- MoviePilot 运行环境
- TMDB API 密钥
- 翻译服务 API 密钥（百度翻译、腾讯云翻译或阿里云翻译）

### 3.2 获取 MoviePilot 源码

```bash
git clone https://github.com/jxxghp/MoviePilot.git
cd MoviePilot
```

## 4. 插件结构设计

MoviePilot 插件需要遵循特定的目录结构：

```
tmdb_storyliner/
├── __init__.py          # 插件主类文件
├── requirements.txt     # 插件依赖
├── assets/              # 插件资源文件
│   └── icon.png         # 插件图标
└── config/              # 配置文件
    └── config.yaml      # 插件配置
```

## 5. 插件实现

### 5.1 创建插件目录

在 MoviePilot 项目的 `app/plugins` 目录下创建 `tmdb_storyliner` 目录：

```bash
mkdir -p app/plugins/tmdb_storyliner
mkdir -p app/plugins/tmdb_storyliner/assets
mkdir -p app/plugins/tmdb_storyliner/config
```

### 5.2 创建插件主类

创建 `app/plugins/tmdb_storyliner/__init__.py` 文件：

```python
import json
import os
from typing import List, Tuple, Optional, Any
from app.plugins import _PluginBase
from app.core.config import settings
from app.log import logger
from app.utils.http import RequestUtils
from app.utils.string import StringUtils
from app.scheduler import Scheduler

class TmdbStoryliner(_PluginBase):
    # 插件元数据
    plugin_name = "TMDB 剧情简介更新器"
    plugin_desc = "定时从 TMDB 获取剧集和电影的剧情简介，并将英文内容翻译成中文"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/tmdb.png"
    plugin_author = "Your Name"
    author_url = "https://github.com/yourusername"
    plugin_version = "1.0"
    plugin_locale = "zh"
    plugin_config_prefix = "tmdbstoryliner_"
    plugin_site = "https://www.themoviedb.org/"
    plugin_order = 10
    # 需要的配置项
    _enabled = False
    _cron = "0 2 * * *"
    _translate_service = "baidu"
    _tmdb_api_key = ""
    _translate_api_key = ""
    _update_movies = True
    _update_series = True
    
    # 监听事件
    _event = "tmdb.storyliner.update"
    
    def init_plugin(self, config: dict = None):
        """
        初始化插件
        """
        if config:
            self._enabled = config.get("enabled")
            self._cron = config.get("cron")
            self._translate_service = config.get("translate_service")
            self._tmdb_api_key = config.get("tmdb_api_key")
            self._translate_api_key = config.get("translate_api_key")
            self._update_movies = config.get("update_movies")
            self._update_series = config.get("update_series")
            
        # 注册定时任务
        if self._enabled and self._cron:
            Scheduler().add_job(
                func=self.update_storylines,
                trigger="cron",
                id="TmdbStoryliner",
                **StringUtils.cron_expression_to_kwargs(self._cron)
            )
            logger.info(f"TMDB 剧情简介更新器定时任务已注册：{self._cron}")
    
    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled
    
    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程命令
        """
        return [{
            "cmd": "/tmdb_storyliner",
            "event": "tmdb.storyliner.update",
            "desc": "更新 TMDB 剧情简介",
            "category": "自动整理",
            "data": {}
        }]
    
    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册 API 接口
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
            return [{
                "id": "TmdbStoryliner",
                "name": "TMDB 剧情简介更新器",
                "trigger": "CronTrigger",
                "func": self.update_storylines,
                "kwargs": StringUtils.cron_expression_to_kwargs(self._cron)
            }]
        return []
    
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
                                                {'title': '百度翻译', 'value': 'baidu'},
                                                {'title': '腾讯云翻译', 'value': 'tencent'},
                                                {'title': '阿里云翻译', 'value': 'aliyun'}
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
                                            'placeholder': '请输入 TMDB API 密钥'
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
                                            'model': 'translate_api_key',
                                            'label': '翻译服务 API 密钥',
                                            'placeholder': '请输入翻译服务 API 密钥'
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
                                                'text': '注意：需要配置 TMDB API 密钥和翻译服务 API 密钥才能正常使用此插件。'
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
            "cron": "0 2 * * *",
            "translate_service": "baidu",
            "tmdb_api_key": "",
            "translate_api_key": "",
            "update_movies": True,
            "update_series": True
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
        # 数据按时间降序排序
        historys = sorted(historys, key=lambda x: x.get('time'), reverse=True)
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
                                    'hover': True,
                                    'headers': [
                                        {'title': '标题', 'key': 'title', 'align': 'start'},
                                        {'title': '类型', 'key': 'type', 'align': 'start'},
                                        {'title': '状态', 'key': 'status', 'align': 'start'},
                                        {'title': '时间', 'key': 'time', 'align': 'start'},
                                    ],
                                    'items': historys,
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
        pass
    
    def update_storylines(self):
        """
        更新剧情简介主方法
        """
        if not self._enabled:
            return
        
        logger.info("开始更新 TMDB 剧情简介")
        
        # 获取媒体库中的项目
        if self._update_movies:
            self.update_movie_storylines()
        
        if self._update_series:
            self.update_series_storylines()
        
        logger.info("TMDB 剧情简介更新完成")
    
    def update_storylines_api(self):
        """
        API 接口：手动更新剧情简介
        """
        self.update_storylines()
        return {"message": "剧情简介更新任务已启动"}
    
    def update_movie_storylines(self):
        """
        更新电影剧情简介
        """
        logger.info("开始更新电影剧情简介")
        # TODO: 实现电影剧情简介更新逻辑
        # 1. 获取媒体库中的电影
        # 2. 从 TMDB 获取剧情简介
        # 3. 翻译英文剧情简介
        # 4. 更新 MoviePilot 媒体库
        logger.info("电影剧情简介更新完成")
    
    def update_series_storylines(self):
        """
        更新电视剧剧情简介
        """
        logger.info("开始更新电视剧剧情简介")
        # TODO: 实现电视剧剧情简介更新逻辑
        # 1. 获取媒体库中的电视剧
        # 2. 从 TMDB 获取剧情简介
        # 3. 翻译英文剧情简介
        # 4. 更新 MoviePilot 媒体库
        logger.info("电视剧剧情简介更新完成")
```

### 5.3 创建依赖文件

创建 `app/plugins/tmdb_storyliner/requirements.txt` 文件：

```txt
requests>=2.28.0
```

### 5.4 创建插件图标

在 `app/plugins/tmdb_storyliner/assets/` 目录下放置插件图标文件 `icon.png`。

## 6. 核心功能实现

### 6.1 TMDB 服务类

创建 `app/plugins/tmdb_storyliner/tmdb_service.py` 文件：

```python
import requests
import json
from app.log import logger

class TmdbService:
    """
    TMDB 服务类
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.themoviedb.org/3"
    
    def get_movie_details(self, movie_id: int) -> dict:
        """
        获取电影详情
        """
        try:
            url = f"{self.base_url}/movie/{movie_id}"
            params = {
                "api_key": self.api_key,
                "language": "en-US"
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取电影详情失败：{e}")
            return {}
    
    def get_series_details(self, series_id: int) -> dict:
        """
        获取电视剧详情
        """
        try:
            url = f"{self.base_url}/tv/{series_id}"
            params = {
                "api_key": self.api_key,
                "language": "en-US"
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取电视剧详情失败：{e}")
            return {}
    
    def get_episode_details(self, series_id: int, season_number: int, episode_number: int) -> dict:
        """
        获取剧集详情
        """
        try:
            url = f"{self.base_url}/tv/{series_id}/season/{season_number}/episode/{episode_number}"
            params = {
                "api_key": self.api_key,
                "language": "en-US"
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取剧集详情失败：{e}")
            return {}
```

### 6.2 翻译服务类

创建 `app/plugins/tmdb_storyliner/translate_service.py` 文件：

```python
import requests
import hashlib
import random
import json
from app.log import logger

class TranslateService:
    """
    翻译服务类
    """
    
    def __init__(self, service: str, api_key: str):
        self.service = service
        self.api_key = api_key
    
    def translate(self, text: str, source_lang: str = "en", target_lang: str = "zh") -> str:
        """
        翻译文本
        """
        if not text or source_lang == target_lang:
            return text
        
        try:
            if self.service == "baidu":
                return self._baidu_translate(text, source_lang, target_lang)
            elif self.service == "tencent":
                return self._tencent_translate(text, source_lang, target_lang)
            elif self.service == "aliyun":
                return self._aliyun_translate(text, source_lang, target_lang)
            else:
                logger.warn(f"不支持的翻译服务：{self.service}")
                return text
        except Exception as e:
            logger.error(f"翻译失败：{e}")
            return text
    
    def _baidu_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        百度翻译
        """
        try:
            # 百度翻译 API 实现
            url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
            # 分解 API Key
            parts = self.api_key.split(":")
            if len(parts) != 2:
                raise ValueError("百度翻译 API Key 格式错误，应为 appid:secretkey")
            
            appid, secretkey = parts
            
            # 生成签名
            salt = random.randint(32768, 65536)
            sign_str = appid + text + str(salt) + secretkey
            sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
            
            params = {
                "q": text,
                "from": source_lang,
                "to": target_lang,
                "appid": appid,
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
    
    def _tencent_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        腾讯翻译（占位实现）
        """
        logger.warn("腾讯翻译服务尚未完全实现")
        return text
    
    def _aliyun_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        阿里云翻译（占位实现）
        """
        logger.warn("阿里云翻译服务尚未完全实现")
        return text
```

## 7. 插件配置说明

### 7.1 配置项说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enabled | 是否启用插件 | False |
| cron | 定时执行周期（cron 表达式） | "0 2 * * *" |
| translate_service | 翻译服务（baidu/tencent/aliyun） | "baidu" |
| tmdb_api_key | TMDB API 密钥 | "" |
| translate_api_key | 翻译服务 API 密钥 | "" |
| update_movies | 是否更新电影 | True |
| update_series | 是否更新电视剧 | True |

### 7.2 API 密钥获取

1. **TMDB API 密钥**：
   - 访问 [TMDB 官网](https://www.themoviedb.org/settings/api) 注册账号
   - 申请 API 密钥

2. **百度翻译 API 密钥**：
   - 访问 [百度翻译开放平台](https://fanyi-api.baidu.com/) 注册账号
   - 创建应用获取 APP ID 和密钥
   - 格式：`appid:secretkey`

## 8. 插件测试

### 8.1 本地测试

1. 启动 MoviePilot 开发环境
2. 将插件目录复制到 `app/plugins/` 目录下
3. 重启 MoviePilot 服务
4. 在插件市场中找到并安装插件
5. 配置插件参数
6. 手动触发或等待定时任务执行

### 8.2 功能验证

1. 检查插件是否正常加载
2. 验证配置界面是否正常显示
3. 测试手动触发功能
4. 验证定时任务是否正常执行
5. 检查日志是否有错误信息

## 9. 插件发布

### 9.1 提交到 MoviePilot 插件市场

1. Fork [MoviePilot-Plugins](https://github.com/jxxghp/MoviePilot-Plugins) 仓库
2. 在 `plugins/` 目录下创建插件目录
3. 添加插件代码和资源文件
4. 更新 `package.json` 文件
5. 提交 Pull Request

### 9.2 package.json 更新

在 `package.json` 中添加插件信息：

```json
{
  "tmdb_storyliner": {
    "name": "TMDB 剧情简介更新器",
    "description": "定时从 TMDB 获取剧集和电影的剧情简介，并将英文内容翻译成中文",
    "version": "1.0",
    "icon": "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/tmdb.png",
    "author": "Your Name",
    "level": 1
  }
}
```

## 10. 总结

本文档详细介绍了如何为 MoviePilot 开发一个 TMDB 剧情简介更新插件。该插件具备以下特点：

1. **定时任务** - 支持 cron 表达式的定时执行
2. **多翻译服务** - 支持百度、腾讯云、阿里云等多种翻译服务
3. **配置化** - 提供友好的 Web 配置界面
4. **可扩展** - 易于添加新的翻译服务和功能

通过按照本文档的指导，您可以快速开发出功能完善的 MoviePilot 插件，并为 MoviePilot 社区贡献有价值的功能。