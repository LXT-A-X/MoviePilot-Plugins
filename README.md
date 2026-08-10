# MoviePilot-Plugins

MoviePilot V2 插件库，收录实用插件。

## 插件列表

### Emby 演职人员中文化 (EmbyPeopleLocalize)

利用大模型（LLM）把 Emby 中英文/罗马音/日文人名翻译为正式中文名并写回。

**功能特性：**
- 支持自定义大模型提示词
- 支持按 Emby 服务器和媒体库筛选
- 支持按演职人员类型过滤（Actor/VoiceActor/Director/Writer/Producer）
- 支持定时扫描和入库自动触发
- 人名翻译缓存，避免重复调用 LLM

**安装方式：**
1. 在 MoviePilot 插件市场添加本仓库地址
2. 搜索 "Emby 演职人员中文化" 并安装
3. 配置 LLM（系统设置 → 大模型配置）
4. 选择要扫描的 Emby 媒体库
5. 启用插件并运行

## 仓库地址

```
https://github.com/LXT-A-X/MoviePilot-Plugins
```
