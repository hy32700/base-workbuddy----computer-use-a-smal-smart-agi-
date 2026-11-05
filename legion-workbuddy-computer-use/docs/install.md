# 安装与连接 WorkBuddy

## 准备源码和 Python

解压 Release 的源码 ZIP。用资源管理器打开包含 `README.md` 的目录，在地址栏输入 `powershell` 并回车。使用 [Python 官方下载页](https://www.python.org/downloads/windows/)安装 Python 3.13 x64。下面的命令使用 Windows Python 启动器 `py`。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

查看你的电脑机型和 Windows 版本。

```powershell
Get-ItemProperty -LiteralPath 'HKLM:\HARDWARE\DESCRIPTION\System\BIOS' |
  Select-Object SystemManufacturer, SystemProductName, SystemFamily
winver
```

## 添加两个 MCP 服务

在同一个 PowerShell 窗口运行以下命令，生成含本机路径的配置。它输出 JSON，适用于目录名含空格的情况。

```powershell
$repoPath = (Get-Location).Path
$legionPython = Join-Path $repoPath '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $legionPython -PathType Leaf)) {
    throw '请在源码目录创建 .venv 后再生成配置。'
}
$legionMcpConfig = @{
    mcpServers = [ordered]@{
        'desktop-coordinator' = @{
            type = 'stdio'
            command = $legionPython
            args = @((Join-Path $repoPath 'vision-server\server.py'))
            defer_loading = $false
        }
        'computer-control' = @{
            type = 'stdio'
            command = $legionPython
            args = @((Join-Path $repoPath 'computer-control-server\server.py'))
            defer_loading = $false
        }
    }
} | ConvertTo-Json -Depth 6
$legionMcpConfig
```

1. 在 WorkBuddy 打开 **插件 → MCP 服务器 → 配置 MCP**。优先配置到用于本项目的工作区，三个聊天使用同一套服务配置。
2. 将输出中 `mcpServers` 下的两项合并进现有配置。如果配置是空的，可以粘贴整个 JSON。也可以对照 [JSON 示例](../examples/mcp.example.json)手动添加并替换三个路径。
3. 保存后，打开本项目的 WorkBuddy 聊天。若服务未出现，重启 WorkBuddy，再检查两个服务是否启用。部分旧版安装曾通过本地插件加载这两项服务。如果你的界面不同，请参考当前版本的官方说明。 [WorkBuddy MCP 配置](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)
4. 在 WorkBuddy 输入 `请调用 desktop-coordinator 的 get_status，只报告 running、chats 和 owned_screenshot_count。` 能看到状态就说明协调服务已连接。再调用 `computer-control.get_screen_size`，核对显示器宽高。两条调用都无需开始截图。

默认运行目录是仓库下的 `.runtime/`，两个服务要指向同一份源码。若设置了 `VIEW_STATE_DIR`，请给两个服务设置同一个仅自己可访问的绝对路径。

## 本地验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

在 Windows 已登录且桌面可见时，可额外运行真机截图测试。测试会截取真实桌面，大约等待 15 秒核对周期，随后清理本轮截图。请先打开空白桌面或无敏感内容的窗口。

```powershell
.\.venv\Scripts\python.exe tests\live_mcp_check.py
```

成功时输出含 `"passed": true` 的 JSON。它验证服务协议，WorkBuddy 真聊天和微信需要按各自的流程验收。

## 常见问题

| 现象 | 检查方法 |
| --- | --- |
| 聊天里找不到工具 | 核对配置级别、两个绝对路径和服务启用状态。已有工具时用 `get_status` 验证。 |
| 提示模块找不到 | 用 MCP 配置的同一个 Python 安装 `requirements.txt`。 |
| 截图是黑屏或位置偏了 | 确认 Windows 桌面已登录、未锁定。先用内屏试验，按本次截图尺寸、原点、缩放和显示器索引换算。 |
| 键鼠工具拒绝动作 | 检查任务聊天的真实 ID 和 `active_task_chat_id` 是否一致。请调度完成派发后再执行。 |
| 截图持续产生 | 在登记的调度聊天执行 `end_session`，再用 `get_status` 核对。 |
| 无法启动协调进程 | 查看 `.runtime/coordinator.log`，排查依赖和工作目录写权限。公开反馈前先删除日志里的本机路径和身份信息。 |
