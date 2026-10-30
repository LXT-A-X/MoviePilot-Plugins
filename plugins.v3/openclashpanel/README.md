# OpenClash 控制面板（OpenClashPanel）

在 MoviePilot 里直接查看和管理 **OpenClash / Mihomo**：状态总览、策略组与节点切换、延迟测速、访问检查、服务管理（需 OpenWrt 登录）、日志查看；支持 TG 按钮命令与仪表盘组件。

## 功能

- **面板方块**：总状态（内核、模式、运行模式、连接、内存、CPU、负载、上下行速率、累计流量）、端口（HTTP/SOCKS/REDIR/MIXED/TPROXY/TUN）、运行模式、代理模式、区域绕过、域名嗅探、DNS 代理、流媒体解锁、快捷操作（关闭连接/重置防火墙/清缓存）、配置文件、流量、资源占用、访问检查、订阅源
- **策略组**：按 OpenClash 配置文件顺序排列（与 zashboard 一致），支持节点切换、单项测速、整组测速（显示进度与成功/超时数量），Smart 智能组只读展示
- **访问检查**：内核（与官方一致）/ MP 网络 / OpenClash 代理三种视角；逐站加载、30 秒自动采集、支持立刻检查
- **日志**：插件日志 + OpenClash 内核实时日志
- **OpenWrt 管理**（可选）：启动 / 停止 / 重启、运行模式（基础 / 增强 TUN / 混合 MIX）、切换配置文件、更新订阅、清 DNS/Smart 缓存、区域绕过/域名嗅探/DNS 代理/流媒体解锁快捷设置
- **TG 命令**：`/oc_status`、`/oc_check`、`/oc_node`（分页按钮选择组和节点）、`/oc_mode`、`/oc_refresh`、`/oc_help`；微信等渠道自动使用纯文本
- **仪表盘**：全宽组件（状态、访问检查、策略组与节点）

## 安装

1. 在 MoviePilot「插件市场」添加仓库地址：`https://github.com/LXT-A-X/MoviePilot-Plugins`
2. 搜索「OpenClash 控制面板」并安装
3. 打开插件设置，填写：
   - **OpenClash API 地址**：`http://<路由器IP>:9090`（external-controller 根地址，不要带 `/ui/...`）
   - **Dashboard 密码**：OpenClash 的 Dashboard 密码（secret）
   - 可选：**OpenWrt 地址 / 用户名 / 密码**，勾选「启用 OpenWrt 管理」后可使用启停、重启、运行模式等操作
4. 保存后刷新插件页

## 使用

### 面板

- 顶部方块区：总状态、端口、运行模式、代理模式、开启/关闭快捷设置、快捷操作、配置文件、流量、资源占用、访问检查、订阅源
- 策略组：点组名切换组，点节点切换；「测本组延迟」批量测速并显示进度
- 访问检查：
  - **内核**：由 OpenClash 内核直接测速（数字与官方访问检查一致）
  - **MP 网络**：由 MoviePilot 容器测速（国内直连、国外走 MP 配置的代理）
  - **OpenClash**：经 OpenClash 混合端口测速
- 日志页：插件日志 / 内核日志切换

### Telegram 命令

| 命令 | 说明 |
|---|---|
| `/oc_status` | 查看状态与全部策略组 |
| `/oc_check` | 访问检查（按设置里的视角） |
| `/oc_node` | 列出策略组；点按钮选择组→节点切换 |
| `/oc_mode` | 列出规则模式；按钮切换 |
| `/oc_refresh` | 刷新订阅节点 |
| `/oc_help` | 命令帮助 |

### 仪表盘

MoviePilot 首页 → 编辑仪表盘 → 添加组件 → 选择「OpenClash 状态」。

## 注意事项

- 启动 / 停止 / 重启 / 切换运行模式 / 切换配置文件都会重启 OpenClash，**全屋网络会短暂中断**，操作前请确认
- OpenWrt 密码仅保存在插件配置中，不会写入日志
- CPU 占用为 OpenClash 瞬时采样，空闲时通常显示 0%
- OpenWrt 管理需要 LuCI 可登录（用户名/密码），登录失败会给出提示

## 依赖

- MoviePilot V3
- OpenClash（Mihomo 内核）并开启 external-controller
