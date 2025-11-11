---
trigger: always_on
alwaysApply: true
---

# 代码版本管理规则

## 版本更新规范
1. 每次代码修改后必须更新插件版本号，确保MoviePilot能正确识别新版本并完成更新
2. 插件版本号必须同时在__init__.py文件的plugin_version变量和package.json文件中同步更新

## 备份规范
当代码版本有新进度时，需要总结对话内容并保存到对话.md中

## 压缩规范
修改正确代码后需更新init中版本号并主动运行compress_plugin_simple.ps1脚本