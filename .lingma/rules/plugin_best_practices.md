---
trigger: model_decision
name: plugin_best_practices_rule
description: 插件开发最佳实践规则
---

# 插件开发最佳实践规则

## 媒体服务器服务调用
获取MoviePilot媒体服务器服务时，应使用self.chain.run_module("mediaserver_services")方法。PluginChain对象不再提供media_infos属性，也不应尝试访问不存在的mediaserver属性。通过run_module机制调用对应模块是兼容且推荐的方式，并建议添加异常处理以确保调用稳定性。

## 插件结构规范
MoviePilot插件开发需包含__init__.py（主程序）、README.md（说明文档）、config.json（配置文件）三个基础文件，插件目录放置于plugins/下

## API调用规范
项目API文档位于 d:\code\mp-plugins\origin\openapi.json，需要调用API时应该参考此文档来获取正确的方法和路径。MoviePilot官方API地址: https://api.movie-pilot.org/ 可用于插件开发时调用官方API获取数据。

## 仓库同步规范
项目需要定期同步官方MoviePilot和MoviePilot-Plugins仓库的更新，通过sync_upstream.ps1脚本实现同步，并设置Windows定时任务每天首次开发插件时自动执行。