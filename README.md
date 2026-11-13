# MoviePilot 插件仓库（LXT-A-X）

> 适配 **MoviePilot V2 / V3** 的插件合集：字体与字幕处理、Emby 演职人员中文化、OpenClash 控制面板、MKV 工具箱。
> 每个插件都有独立的详细使用手册，见下方「插件列表」与各插件目录下的 `README.md`。

**仓库地址：** <https://github.com/LXT-A-X/MoviePilot-Plugins>

---

## 目录

- [仓库结构](#仓库结构)
- [快速安装](#快速安装)
- [插件列表](#插件列表)
- [插件详情](#插件详情)
  - [字幕字体代理 FontInAssProxy](#字幕字体代理-fontinassproxy)
  - [Emby 演职人员中文化 EmbyPeopleLocalize](#emby-演职人员中文化-embypeoplelocalize)
  - [字体分类管家 Zitifenlei](#字体分类管家-zitifenlei)
  - [OpenClash 控制面板 OpenClashPanel](#openclash-控制面板-openclashpanel)
  - [MKV 工具箱 MkvToolkit](#mkv-工具箱-mkvtoolkit)
- [通用说明](#通用说明)
- [常见问题](#常见问题)
- [致谢与声明](#致谢与声明)

---

## 仓库结构

```text
MoviePilot-Plugins/
├── package.v2.json        # V2 插件市场索引（MoviePilot V2 读取）
├── package.v3.json        # V3 插件市场索引（MoviePilot V3 读取）
├── icons/                 # 插件市场卡片图标
├── plugins.v2/            # 适用于 MoviePilot V2 的插件源码
│   ├── embypeoplelocalize/
│   └── zitifenlei/
└── plugins.v3/            # 适用于 MoviePilot V3 的插件源码（含前端 dist）
    ├── embypeoplelocalize/
    ├── fontinassproxy/
    ├── mkvtoolkit/
    ├── openclashpanel/
    └── zitifenlei/
```

- **V3 插件**：依赖 MoviePilot V3 稳定 SDK（`app.sdk.*`），前端使用 Module Federation 联邦加载，安装时由宿主自动安装 `pyproject.toml` 声明的依赖。
- **V2 插件**：面向旧版 MoviePilot V2，功能相近但界面与配置项不同；V3 宿主请安装 `plugins.v3/` 对应版本。

## 快速安装

1. 打开 **MoviePilot → 插件市场 / 插件仓库**，添加本仓库地址：
   `https://github.com/LXT-A-X/MoviePilot-Plugins`
2. 在插件市场中搜索插件名称（如「字体分类管家」），确认版本与你的 MoviePilot 主版本匹配（V2 / V3）后安装。
3. 安装完成后进入插件「设置」页按手册配置目录/服务地址等参数，保存并**启用插件**。
4. 部分插件需要容器内的外部工具或端口（如字体插件的 7z/unar 解压、字幕代理的 8097 反代端口、MKV 工具箱的 mkvmerge），具体见各插件手册的「前置条件」。

> **更新**：插件更新同样在插件市场完成。GitHub raw 索引有 CDN 缓存，刚发布的版本可能需要等待 1~5 分钟或重启 MoviePilot 后才会出现在市场里。

## 插件列表

| 插件 | 一句话说明 | V2 版本 | V3 版本 | 详细手册 |
| --- | --- | --- | --- | --- |
| **字幕字体代理** FontInAssProxy | 反代 Emby/Jellyfin 字幕流，实时子集化字体并内嵌进 ASS | — | ✅ 3.1.2 | [V3 手册](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v3/fontinassproxy/README.md) |
| **Emby 演职人员中文化** EmbyPeopleLocalize | 用 LLM 把 Emby 演职人员姓名与角色名翻译成简体中文并写回 nfo | ✅ 1.3.11 | ✅ 4.7.13 | [V3 手册](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v3/embypeoplelocalize/README.md) |
| **字体分类管家** Zitifenlei | 字体归档整理 + ASS 字幕缺字体检查 + 字体子集化内嵌 | ✅ 1.2.24 | ✅ 3.4.0 | [V3 手册](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v3/zitifenlei/README.md) · [V2 手册](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v2/zitifenlei/%E4%BD%BF%E7%94%A8%E6%89%8B%E5%86%8C.md) |
| **OpenClash 控制面板** OpenClashPanel | MoviePilot 内查看/管理 OpenClash·Mihomo：状态、策略组、测速、访问检查、OpenWrt 管理 | — | ✅ 1.12.0 | [V3 手册](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v3/openclashpanel/README.md) |
| **MKV 工具箱** MkvToolkit | MKV 容器层编辑：字幕内封、音轨增删排序、字体附件、章节标题，支持队列/历史回滚 | — | ✅ 0.1.51 | [V3 手册](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v3/mkvtoolkit/README.md) |

> 版本号与 `package.v2.json` / `package.v3.json` 索引保持一致；「—」表示该版本暂无此插件。

---

## 插件详情

### 字幕字体代理 FontInAssProxy

**V3 3.1.2 · 适用 MoviePilot V3**

反代 Emby/Jellyfin 的字幕请求：取到字幕后解析它引用的字体，从字体库中做**子集化**并把子集以内嵌 `[Fonts]` 段写回 ASS 返回。播放端不需要安装任何字体，电视盒子/NAS 播放器上的特效字幕也能正常显示。

**核心特性**

- **实时子集化注入**：播放时按需内嵌，不改变原字幕文件；已含 `[Fonts]` 的字幕直接透传。
- **uharfbuzz 子集化引擎**：C 实现高速子集化，失败自动回退 fontTools。
- **内置反代端口**：默认 `8097`，不依赖 nginx；支持 WebSocket 透传。
- **精准字体匹配**：字体内部名优先、文件名兜底；容器格式 ttf > ttc > otf > otc；中/日/拼音多编码别名识别。
- **双层缓存**：内存 LRU + 磁盘缓存（默认保留 1 天、每 4 小时清理），限制总量防止占满磁盘。
- **安全边界**：只做字幕读取与字体库读取，不改媒体文件；匿名入口已移除，仅内置反代提供服务。

**安装要点**：插件市场安装后在设置页填写 Emby/Jellyfin 地址、字体库目录与反代端口，保存启用即可。依赖 `uharfbuzz` 由插件自动安装。

📖 **完整手册（配置项 / 接口 / FAQ）：** [plugins.v3/fontinassproxy/README.md](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v3/fontinassproxy/README.md)

---

### Emby 演职人员中文化 EmbyPeopleLocalize

**V2 1.3.11 / V3 4.7.13 · 适用 MoviePilot V2 / V3**

用大模型（LLM）把 Emby 里的**演职人员姓名**（演员/声优/导演/编剧/制片）与**角色名**翻译成规范简体中文，并写回媒体库的 `nfo` 文件。它不是"翻一次就完"，而是一套带账本、可对账、可回滚的流水线。

**核心特性**

- **NFO 本地文件模式**：直接读写 `tvshow.nfo` / `movie.nfo` / `episode.nfo`，不依赖 Emby API 逐条回写。
- **人名池全局复用**：同一个人名只翻译一次，跨作品复用，显著节省 AI 额度。
- **人工修正优先**：手工改过的译文重跑扫描不会被 AI 覆盖。
- **多条自动入口**：Webhook 入库、NFO 扫描/探测库、拉取人名、人工修改，入口互不重复。
- **失效观察期**：目录/剧集消失先进观察期（默认 24h），期间重新入库按稳定身份恢复且不重复问 AI。
- **限流与熔断**：请求间隔 + TPM 预算限速，限速/配额/认证分级暂停与自动恢复。
- **可选 TMDB 辅助**：中文别名补译、credits 回填第二排角色名，不依赖 AI。
- **精细范围控制**：演员/客串/导演/编剧/制片分别开关 + 每个文件翻前 N 人；第一排/第二排分别控制。
- **完整账本**：翻译记录可查、可导出/导入、可批量写回、单条重扫/重翻/人工编辑。

**安装要点**：配置 LLM（或复用 MoviePilot 系统 LLM）与要处理的媒体库（含 Emby 路径 → 本机路径映射），先在仪表盘点「NFO 扫描」跑一次，再按需开启 Webhook 自动翻译。

📖 **完整手册（V3）：** [plugins.v3/embypeoplelocalize/README.md](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v3/embypeoplelocalize/README.md)
V2 版安装 `plugins.v2/embypeoplelocalize` 对应版本，功能相近，设置页与界面以 V2 版为准。

---

### 字体分类管家 Zitifenlei

**V2 1.2.24 / V3 3.4.0 · 适用 MoviePilot V2 / V3**

字体归档整理与 ASS 字幕字体处理插件：把散落的字体扫描/上传进字体库，按「厂商 → 格式 → 名称」自动归档；检查每部剧的字幕缺不缺字体；并用 HarfBuzz（V3）/ assfonts（V2）把字幕用到的字体**子集化内嵌**进字幕，让任何播放器都能正确显示。

**核心特性**

- **字体归档**：支持 ttf/otf/ttc/otc/woff/woff2，自动识别厂商（思源/Google、森泽 MO、华文 ST、方正等），同名去重、索引自动增量更新。
- **字幕检查**：解析 ASS 实际引用的字体，按字形级（cmap）对照字体库，区分「字体齐全 / 已内嵌 / 缺字体」；检查记录按压缩包/上传批次/字幕目录分组。
- **子集化**：只内嵌用到的字形，支持 HDR 字幕亮度压暗；V3 内置 uharfbuzz 独立工作进程，病态字体不影响主进程。
- **目录监控**：字体监控目录、ASS 字幕检查目录、ASS 自动子集化目录三条链路，**填了哪个目录就监控哪个（无总开关）**；字体监控目录支持字体压缩包（zip/7z/rar）自动解压归档，ASS 字幕目录支持字幕压缩包自动解压检查/子集化；字幕包可按 **SC/TC/自定义关键词** 只处理想要的字幕。可选「解压整理后自动清理压缩包」（移到对应目录的「已处理压缩包/」或删除，默认关），放错目录/待定/失败一律保留并提醒。
- **种子字体收集**：只读轮询下载器已完成种子，从文件清单截取字体/字体包（zip/7z/rar）自动入库，不删种子、不扫下载目录。
- **MoviePilot 入库联动**：剧集入库后自动检查字幕或自动子集化（二选一），按需发送系统通知。
- **缺失字体闭环**：检查/子集化发现的缺失字体统一收集，上传后严格校验（名称命中 + 字形覆盖）→ 一键归类入库 → 索引重建 → 重试子集化。
- **兼容性**：V3 版支持解压工具一键安装（容器内 apt/apk 装 unar）；对残缺 TTC 自动拆 face/修复 cmap。

**安装要点**：V3 版在设置页配置「字体库目录 / 字体监控目录 / ASS 字幕目录」后启用；先点字体库页「全量检查」归档存量字体，再点子集化页「全部重建」构建索引。

📖 **完整手册（V3）：** [plugins.v3/zitifenlei/README.md](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v3/zitifenlei/README.md)
V2 版手册：[plugins.v2/zitifenlei/使用手册.md](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v2/zitifenlei/%E4%BD%BF%E7%94%A8%E6%89%8B%E5%86%8C.md)

---

### OpenClash 控制面板 OpenClashPanel

**V3 1.12.0 · 适用 MoviePilot V3**

在 MoviePilot 里直接查看和管理 **OpenClash / Mihomo**：状态总览、策略组与节点切换、延迟测速、访问检查（内核 / MP / OpenClash 三视角）、插件与内核日志，可选 OpenWrt 服务管理；支持 Telegram 分页按钮命令与仪表盘全宽组件。

**核心特性**

- **状态总览**：内核版本、规则模式、运行模式、连接数、内存/CPU/负载、上下行速率与累计流量。
- **策略组**：按 OpenClash 配置文件顺序排列（与 zashboard 一致），支持节点切换、单项/整组测速（进度与成功/超时统计），Smart 智能组只读。
- **访问检查**：内核视角（与官方一致）/ MP 网络视角 / OpenClash 代理视角，逐站加载、30 秒自动采集。
- **OpenWrt 管理（可选）**：填 LuCI 地址/用户名/密码后，可启动/停止/重启、切换运行模式（基础/增强 TUN/混合 MIX）、切换配置、更新订阅、清缓存、区域绕过/域名嗅探/DNS 代理/流媒体解锁等。
- **TG 命令**：`/oc_status`、`/oc_check`、`/oc_node`（分页按钮选组/节点）、`/oc_mode`、`/oc_refresh`、`/oc_help`。
- **仪表盘组件**：全宽卡片（状态 + 访问检查 + 策略组/节点）。
- **日志**：插件日志 + 内核实时日志。

**安装要点**：填写 OpenClash API 地址（`http://<路由器IP>:9090`）与 Dashboard 密码；需要服务管理时再填 OpenWrt LuCI 地址与账号。修改类操作需要 MoviePilot 管理员权限。

📖 **完整手册（配置项 / 接口 / FAQ）：** [plugins.v3/openclashpanel/README.md](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v3/openclashpanel/README.md)

---

### MKV 工具箱 MkvToolkit

**V3 0.1.51 · 要求 MoviePilot ≥ 3.2.0**

在 MoviePilot 里做 **MKV 容器层编辑**：字幕内封、音轨增删/排序/标签、字体附件、章节与标题修改。基于 `mkvmerge` + `mkvpropedit`（可选 `ffmpeg` 引擎），带预览确认、任务队列、历史回滚与手机端操作。

**核心特性**

- **字幕内封**：把外挂字幕（ASS/SRT 等）封装进 MKV，支持多字幕轨、语言/标题/默认轨标记、编码与延迟设置。
- **音轨编辑**：音轨增删、排序、语言/名称/默认轨/强制轨标记、同步偏移。
- **字体附件**：把字体文件作为 MKV 附件写入，供内嵌 ASS 字幕使用。
- **章节与标题**：读取/编辑章节与容器标题。
- **预览与确认**：执行前生成操作计划（命令 + 输出 + 备份 + 磁盘空间检查）供确认，避免误操作。
- **队列与历史**：批量任务队列、并发控制、失败重试；历史记录支持回滚与中断恢复。
- **多套引擎**：自动探测/一键安装 mkvmerge、mkvpropedit；支持 apt / AppImage / 手动路径三种安装方式。
- **手机端可用**：文件树、文件选择与轨道编辑界面适配移动端。

**安装要点**：插件要求 MoviePilot **≥ 3.2.0**（`system_version` 限制），并在容器内准备 `mkvmerge`/`mkvpropedit`（可在插件设置页一键安装或指定路径）。文件操作限于配置的媒体路径白名单内，修改前会生成备份。

📖 **完整手册（配置项 / 场景 / FAQ）：** [plugins.v3/mkvtoolkit/README.md](https://github.com/LXT-A-X/MoviePilot-Plugins/blob/main/plugins.v3/mkvtoolkit/README.md)

---

## 通用说明

### 依赖安装

- V3 插件在安装时会按插件目录的 `pyproject.toml`（或 `requirements.txt`）自动安装 Python 依赖；安装失败时可到插件「仪表盘 → 依赖」里点「重新安装」。
- 需要系统工具/外部二进制的插件（字体插件的 7z/unar、MKV 工具箱的 mkvmerge、OpenClash 的 API 等）请参照各自手册的「前置条件」；字体插件与 MKV 工具箱均提供设置页一键安装入口。

### 权限与数据

- 修改类接口（保存配置、清库、安装依赖、改文件等）需要 **MoviePilot 管理员** 权限；只读查看接口登录即可。
- 插件数据保存在 MoviePilot 的 `config/plugins/<插件ID>/` 下（数据库、日志、临时文件等），备份 MoviePilot 配置目录即可一并备份。
- 插件不会主动上传/收集用户数据；日志可能包含本地文件路径等排障信息，反馈问题前请注意脱敏。

### 隐私与安全

- 仓库内不含任何个人账号、密码、令牌、内网地址等敏感信息。
- 插件所需的 Emby/Jellyfin/OpenClash/LuCI 账号密码、LLM API Key 等均保存在 MoviePilot 自身的配置中，不会写进插件代码或日志明文（具体存储方式见各插件手册的「安全与权限」）。
- 请勿在公开场合贴出包含真实地址、账号或令牌的插件日志。

## 常见问题

**Q：插件市场里搜不到 / 看不到新版本？**
确认已在插件市场添加本仓库地址；GitHub raw 索引有 CDN 缓存，新版本发布后可能需要等待几分钟，或重启 MoviePilot 再刷新市场。

**Q：V2 和 V3 版本怎么选？**
看你的 MoviePilot 主版本：V2 宿主装 `plugins.v2/` 对应版本，V3 宿主装 `plugins.v3/` 对应版本；两代插件不通用。

**Q：依赖安装失败怎么办？**
到插件「仪表盘 → 依赖」查看失败项并点「重新安装」；容器网络受限时请配置 MoviePilot 的 pip 代理（`PIP_PROXY`）。系统工具类依赖请按各插件手册操作。

**Q：插件更新后页面还是旧界面？**
前端为联邦模块，浏览器/PWA 有缓存：强制刷新页面，或关闭 PWA 后重新打开；必要时重启 MoviePilot。

## 致谢与声明

- 感谢 [MoviePilot](https://github.com/jxxghp/MoviePilot) 提供插件框架与插件市场。
- 各插件使用的第三方组件（如 uharfbuzz、fontTools、assfonts、mkvmerge、7-Zip/unar、Emby/Jellyfin 等）版权归其各自作者所有，使用时请遵守对应许可证。
- 本仓库插件代码由 **LXT-A-X** 编写与维护，仅供个人学习与自用；使用中产生的媒体文件与数据请自行备份。
- 问题反馈与功能建议：<https://github.com/LXT-A-X/MoviePilot-Plugins/issues>

---

> 各插件的详细配置、接口、FAQ 与更新日志，请进入对应插件目录查看 `README.md`。
