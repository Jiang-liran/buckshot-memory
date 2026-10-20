# Buckshot Memory · 恶魔轮盘实时膛线助手

一个本地运行的 Windows 桌面记忆辅助工具，用于《Buckshot Roulette》的**单人模式**。
自动记录已知子弹信息，减少记忆负担。无需登录、无需网页服务，也无需逐发手动录入。

> 实验性、版本绑定的社区项目，并非官方产品。需要自行购买并安装游戏。
> 仓库不包含游戏本体、资源、完整游戏脚本或预先修改的游戏副本。

## 能显示什么

- 当前剩余子弹总数、实弹数和空包弹数。
- 放大镜和手机揭示过的弹型；未知位置仍然显示 `?`。
- 每次射击或退弹后，已知位置自动前移。
- 下一发实弹概率；未知弹被逆转器翻转时显示可能数量和估计范围。
- 置顶小窗口，游戏内约 160 ms 导出一次、助手每 100 ms 检查一次。
- 相同内容不重复重建弹序控件，避免高频闪烁；短暂文件写入冲突有有限容错。

这是记忆辅助，不是完整隐藏弹序查看器。逆转器后的概率范围是简化估计，
不是完整贝叶斯推断；游戏道具函数触发时就会同步，可能略早于对应播报或动画。
桥接仅接入单人脚本，不提供多人联机支持。

## 工作原理

不是视觉识别，也不扫描进程内存。

安装工具使用玩家自己的原版游戏，在本机临时提取三个脚本，并插入本项目的桥接代码，
生成另一个 `Buckshot Roulette Memory.exe`。Steam 原版文件保持不变。
桥接副本把已知信息写入本地 JSON，Python/Tkinter 桌面程序读取并显示它。

状态文件位于：

```text
%APPDATA%\Godot\app_userdata\Buckshot Roulette\buckshot_memory_state.json
```

助手和桥接代码没有网络上传、账号登录、遥测或云端同步功能。
这不代表原游戏或 Steam 自身没有网络功能。

## 支持范围

当前仅验证 Windows 版游戏 **v2.2.0.6**，以原始 EXE 的 SHA-256 为最终兼容依据：

```text
df2f8a31bd469438a1a29f831945ccea7b26963ab735f73b32936792207b1663
```

不同版本、已修改游戏、其它平台会被安装工具拒绝，不会强行打补丁。
游戏更新后，需要重新验证兼容性；旧桥接副本不会随 Steam 自动更新。
不要将旧副本当作当前官方版本继续使用。

开发环境：Windows、Python 3.12（包含 Tcl/Tk）；安装桥接还需要
[GDRE Tools 2.6.0 官方发行包](https://github.com/GDRETools/gdsdecomp/releases/tag/v2.6.0)。
完整解压工具发行包，保留 `gdre_tools.exe`、配套 `.pck` 和 DLL 在同一目录。
GDRE Tools 不随本项目分发，也不会被自动下载。

## 从源码开始

当前发布的是源码。以下命令在 PowerShell 中、项目根目录运行。
示例中的游戏和 GDRE 路径需要换成你自己的真实路径。

### 1. 准备 Python

安装带 Tcl/Tk 的 Python 3.12，然后：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

运行助手本身只使用 Python 标准库，不需要安装第三方 Python 包。

### 2. 生成本机桥接副本

关闭游戏。建议先自行备份游戏存档：桥接副本与原版使用相同的游戏数据目录，
正常游玩仍可能修改存档。生成副本需要数 GB 空闲临时空间。

先只检查版本，不写入文件：

```powershell
.\.venv\Scripts\python.exe tools\install_bridge.py --game "C:\Games\Buckshot Roulette\Buckshot Roulette.exe" --check-only
```

通过后安装：

```powershell
.\.venv\Scripts\python.exe tools\install_bridge.py --game "C:\Games\Buckshot Roulette\Buckshot Roulette.exe" --gdre "C:\Tools\GDRE\gdre_tools.exe"
```

默认在原游戏旁生成 `Buckshot Roulette Memory.exe`。工具会校验原版和脚本哈希，
重新提取生成文件进行逐项核验，再复制到目标位置；已有文件一律拒绝覆盖。
如果提示文件已存在，可手动备份旧桥接副本，或用 `--output` 指定不同文件名。
请勿上传或分享生成的游戏副本，也不要把临时提取脚本加入仓库。

### 3. 启动助手

```powershell
.\.venv\Scripts\python.exe src\buckshot_bridge_ui.py
```

助手会从 Steam 注册表和库配置寻找桥接副本，尝试启动它。
进入单人牌桌后开始同步。如果是非标准安装位置或自定义副本名称：

```powershell
$env:BUCKSHOT_MEMORY_GAME = "C:\Games\Buckshot Roulette\Buckshot Roulette Memory.exe"
.\.venv\Scripts\python.exe src\buckshot_bridge_ui.py
```

不要同时运行 Steam 原版和桥接副本；从 Steam 直接启动原版不会输出桥接状态。

## 打包成本地 EXE

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe tools\build.py
```

输出为 `dist\BuckshotMemory.exe`，双击即可运行助手，不需要接收者安装 Python。
它**只包含助手**，不会打包游戏或 GDRE。用户仍需在自己的电脑上生成桥接副本。
目前没有代码签名；请审查来源，不要为了运行它而关闭系统安全防护。

## 常见问题

**一直等待游戏状态？** 确认启动的是桥接副本、处于单人牌桌，且游戏版本通过检查。
状态超过约 1.8 秒未更新时会显示等待，不会把过期数据继续冒充实时数据。

**不支持新版游戏？** 请提交游戏版本及原版 EXE 的 SHA-256，不要上传游戏文件、存档或提取脚本。
报告问题不需要提供你的 Steam 登录信息。

**手机位置不固定？** 序号始终相对于当前剩余弹序；前面的子弹被消耗后，记录会自动前移。

**如何恢复原版？** 关闭桥接副本，使用 Steam 启动原版即可。
不再需要时可自行删除生成的 `Buckshot Roulette Memory.exe` 和助手文件。
不要删除整个 Godot 用户数据目录，里面可能还有存档。

## 项目结构

```text
src/buckshot_bridge_ui.py     桌面界面与状态读取
bridge/memory_bridge.gd.inc   原创桥接片段，不是完整游戏脚本
tools/install_bridge.py      版本校验、本地生成与验证
tools/build.py               Windows 助手打包
tests/test_helper.py         状态、渲染去重和安装防护测试
```

欢迎通过 Issue 或 Pull Request 改进安装体验、可访问性、测试与版本兼容。
提交前运行 `python -m unittest discover -s tests -v`。

## License / English summary

Original helper and bridge code: [MIT](LICENSE). Game names and third-party software
belong to their respective owners and are not covered by this project's license.
This is an unofficial community project, not affiliated with the game developers or publisher.

Buckshot Memory is a local Windows/Tkinter memory aid for **single-player** Buckshot Roulette.
It tracks remaining rounds and item-revealed information, without revealing the full hidden sequence.
It is not OCR or a process-memory reader. A local, version-checked installer builds a separate
bridge-enabled copy from a game you own. The original game stays untouched, but both copies share
the game's save-data directory. Only the exact executable hash above is supported.
No game binaries, full extracted scripts, assets, accounts or telemetry are included.
Run the tests, install the bridge with your own GDRE Tools copy, then launch
`python src/buckshot_bridge_ui.py`. Use `python tools/build.py` for a standalone assistant EXE.
