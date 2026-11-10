# MKV 工具箱（MkvToolkit）

MoviePilot V3 插件：对 `.mkv` 做**容器层编辑**（不转码、不剪片）。

## 功能

- **字幕**：内封外挂 `srt/ass/ssa/vtt`（编码自动探测，可强制 GBK/BIG5）、改语言/轨道名/default/forced、删除
- **音轨**：查看/保留/删除/排序、改语言/轨道名/default/forced、从音频文件新增（`aac/flac/mka/ac3/dts/mp3/m4a` 等）、`--sync` 延迟校正
- **附件**：只允许字体（`ttf/otf/ttc`），走 mkvpropedit 原地添加/删除
- **容器**：改标题、章节保留/清空/导入（OGM XML 与 ffmetadata）
- **素材来源**：优先「从目录选择」（复用媒体根目录，不复制文件）；也支持上传（≤50MB，前后端双重校验）
- **执行安全**：先 `/plan` 预览命令与差异 → 确认 → 入队；默认输出到独立目录，也可备份后原地替换；临时文件 + 原子替换 + 完成后校验轨道数与时长
- **队列**：并发可配（1~3）、暂停/继续、置顶/重排、失败重试、重启后等待任务恢复
- **历史**：成功/失败/取消记录，替换模式可回滚
- **界面**：Vue 联邦页面，桌面左右分栏 + 手机抽屉/卡片；「退出」走宿主 `emit('close')`

## 运行要求

- MoviePilot V3（`>=3.2.0`），官方镜像自带 `ffmpeg/ffprobe`
- 需要 **MKVToolNix**（`mkvmerge` / `mkvpropedit` / `mkvextract`）：
  - 插件内「一键安装（apt）」：Debian 13 源自带 92.0
  - 或「AppImage 解包」：下载官方 AppImage 到插件数据目录，免 root
  - 或「手动指定路径」：填 `mkvmerge` 绝对路径，其余工具自动在相邻目录查找
- 未安装 MKVToolNix 时只能探测/预览，默认禁止执行；可在设置里开启「ffmpeg 降级执行」（能力减配）

## 数据目录

全部运行数据在 `/config/plugins/MkvToolkit/`：

| 目录 | 用途 |
|---|---|
| `output/` | 默认输出目录（可改） |
| `backup/` | 原地替换前的备份（保留份数可配） |
| `uploads/` | 上传的字幕/字体/音频 |
| `work/` | 执行中的临时文件 |
| `bin/` | 手动放入或 AppImage 解包生成的工具 |

插件日志与任务记录统一写在 MoviePilot 约定路径的同一个文件里（启动/停止、任务命令、成功/失败都记录在一起）：

- `/config/logs/plugins/mkvtoolkit.log`

## 安装

见仓库根目录 [README](../../README.md) 与 [docs/INSTALL.md](../../docs/INSTALL.md)。

## 注意

- 只处理 `.mkv`；输出为同容器 copy，不改变视频/音频编码
- 删除轨道、清空章节等操作不可逆（请确认输出文件无误后再替换源文件）
- 「从目录选择」只能浏览配置的媒体根目录，不能越权访问系统路径
- 音频文件通常超过 nginx 50MB 上传上限，请使用目录选择
