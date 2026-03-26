# Network Workflow Console

一个本地运行的网络工作流控制台，用来统一查看模式、链路和开发代理验证结果。

## 重要提醒

如果你移动或重命名项目目录，需要重新运行一次快捷方式安装脚本：

```bash
./install_shortcuts.sh
```

桌面上的 `.command` 快捷方式可以随便挪到文件夹里，但它们依赖“安装时记录的项目路径”。

## 当前实现

这一版使用 Python 标准库提供本地 Web 服务，页面在浏览器中以 HTML 形式操作。

原因很简单：

- 当前环境没有 `node` 和 `pnpm`
- 先把 MVP 跑起来比死等前端框架环境更重要

后续如果需要迁到 Next.js，这一版的状态模型、接口边界和验证逻辑仍然可以直接复用。

## 启动方式

```bash
cd /path/to/network-workflow-console
python3 server.py
```

默认地址：

- [http://127.0.0.1:8123](http://127.0.0.1:8123)

安装桌面快捷方式：

```bash
cd /path/to/network-workflow-console
./install_shortcuts.sh
```

默认会安装到桌面。也可以指定目录：

```bash
./install_shortcuts.sh "/path/to/your/folder"
```

也可以自定义端口：

```bash
python3 server.py --port 9000
```

## 配置文件

配置分两层：

- `./config/default.json`
  仓库模板，适合提交到 GitHub
- `./config/local.json`
  本机覆盖，不进 Git，用来放你自己的真实地址

关键字段：

- `profiles.studio.miniHost`
- `profiles.studio.proxy.host`
- `profiles.studio.proxy.port`
- `profiles.studio.proxy.type`
- `profiles.travel.miniHost`
- `profiles.travel.proxy.host`
- `profiles.travel.proxy.port`
- `profiles.travel.proxy.type`
- `expectedRegion`
- `verifyEndpoints`

页面里的配置表单会把修改写到 `./config/local.json`。

推荐填法：

- `studio` 填工作室局域网地址，例如 `192.168.5.135:6152`
- `travel` 填 Tailscale 地址，例如 `100.86.79.63:6152`

## 状态与日志

本地状态文件：

- `./data/state.json`

本地事件日志：

- `./data/events.jsonl`

这些都属于运行态文件，不建议提交到 GitHub。

## 快速验证会做什么

`POST /api/verify` 会做这些检查：

1. 读取当前模式和策略
2. 检查 Tailscale 状态
3. 检查 mini 主机 TCP 可达性
4. 检查代理端口 TCP 可达性
5. 直连访问验证端点，拿直连出口信息
6. 显式通过代理访问验证端点，拿代理出口信息
7. 对比代理出口地区和 `expectedRegion`
8. 生成 `green / yellow / red / fallback / unknown` 结论

默认验证端点已改成更适合当前场景的：

- `https://api.ip.sb/geoip`
- `https://ifconfig.co/json`

## 开发代理模板

切换到 `studio` 或 `travel` 模式时，会生成：

- `~/.network-workflow-console/dev-proxy.env`
- `~/.network-workflow-console/open-proxy-shell.sh`

推荐加载方式：

```bash
source ~/.network-workflow-console/dev-proxy.env
```

或者直接打开一个代理 shell：

```bash
~/.network-workflow-console/open-proxy-shell.sh
```

## 当前限制

- 浏览器代理不由本系统直接管理
- 已打开的终端不会被自动接管
- `NO_PROXY` 的兼容性依赖具体工具
- 代理出口验证依赖本机可用的 `curl`
- Tailscale 状态依赖本机安装了 `tailscale` CLI

## 服务窗口说明

首次启动时会拉起一个 Terminal 窗口运行 `server.py`。

- 这个窗口只是控制台服务本身，不是你的代理
- 如果误关，控制台页面会失效，但网络不会因此坏掉
- 重新双击桌面启动器即可恢复
- 如果你想主动停止控制台，用桌面的“关闭网络工作流控制台”即可

## 应用控制页

控制台的高级区里新增了“应用控制”面板。

它可以显示：

- 控制台服务是否运行
- GUI 代理环境是否已注入
- `Codex` 是否运行
- `Antigravity` 是否运行

它也可以执行：

- 代理启动 `Codex + Antigravity`
- 恢复普通 `Codex + Antigravity`
- 关闭控制台服务

注意：

- GUI 代理动作会重启 `Codex` 和 `Antigravity`
- 如果你当前正在 `Codex` 里对话，点这个动作可能会中断当前会话

## 模式说明

- `normal`: 普通直连
- `studio`: 工作室开发模式，使用 `profiles.studio`
- `studio_direct`: 工作室直连模式，不走 mini 代理，方便手动挂旧 VPN
- `travel`: 外出模式，使用 `profiles.travel`
- `fallback`: 临时保底模式

## 从 0 到 1

1. 双击桌面的 `网络工作流控制台.command`
2. 浏览器会自动打开 `http://127.0.0.1:8123`
3. 平时默认点 `工作室代理`
4. 点一次 `快速验证`
5. 重点看 4 个结果：
   - 顶部结论
   - 当前模式
   - 当前链路路径
   - 代理出口
6. 如果你想绕过 mini，就点 `工作室直连`
7. 如果 GUI 版 `Codex` 或 `Antigravity` 不走代理，再到高级区的“应用控制”里处理
8. 不用了就点桌面的 `关闭网络工作流控制台.command`

最简单的稳定状态判断标准：

- 顶部显示 `稳定模式：日本（mini）`
- `当前模式 = studio`
- `当前链路路径 = proxy`
- `代理出口 = JP / Japan`

## GitHub / 迁移说明

这版已经改成可迁移路径版：

- 项目内部脚本会根据自身所在目录定位项目根目录
- 不再依赖固定的 `/Users/.../network-workflow-console` 路径
- 迁移目录后，只需要重新运行 `./install_shortcuts.sh`

建议推 GitHub 时保留：

- `server.py`
- `web/`
- `config/default.json`
- `install_shortcuts.sh`
- 各类 `*.sh`

运行时文件不会推上去：

- `config/local.json`
- `data/state.json`
- `data/events.jsonl`
- `data/server.log`
- `data/server.pid`

如果你换机器或换目录：

1. clone 仓库
2. 按需编辑 `config/local.json`
3. 运行 `./install_shortcuts.sh`
4. 再启动控制台
