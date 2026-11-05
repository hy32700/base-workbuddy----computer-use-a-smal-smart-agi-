"""
Computer Control MCP Server
提供屏幕截图、鼠标控制、键盘控制能力，供 WorkBuddy 调用。

12 个工具：
  screenshot, get_screen_size, get_mouse_position,
  mouse_move, mouse_click, mouse_double_click, mouse_drag, mouse_scroll,
  type_text, key_press, key_hold, wait
"""

import os
import sys
import json
import time
import asyncio

# 确保同目录模块可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

import screenshot as scr
import mouse
import keyboard

# All task screenshots use the shared coordinator's owned-file registry.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'vision-server'))
from bridge import call as coordinator_call

# ── Server ────────────────────────────────────────────
server = Server("computer-control")

INPUT_TOOLS = {'mouse_move', 'mouse_click', 'mouse_double_click', 'mouse_drag',
               'mouse_scroll', 'type_text', 'key_press', 'key_hold'}


@server.list_tools()
async def list_tools() -> list[Tool]:
    result = [
        # ═══ 截图 ═══
        Tool(
            name="screenshot",
            description="任务聊天截图，纳入本轮每5分钟清理。chat_id 必须是已分配任务的原生聊天 ID。返回物理像素尺寸、原点及文件路径。",
            inputSchema={
                "type": "object",
                "properties": {
                    "chat_id": {"type": "string", "description": "已登记并分配任务的原生聊天 ID"},
                    "region": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 4,
                        "maxItems": 4,
                        "description": "可选，截取区域 [x, y, width, height]。不传则截取全屏。",
                    },
                    "monitor": {
                        "type": "integer",
                        "description": "可选，显示器索引（0=主显示器）。默认 0。",
                        "default": 0,
                    },
                },
                "required": ["chat_id"],
            },
        ),
        Tool(
            name="get_screen_size",
            description="获取主显示器的像素尺寸（宽 x 高）。",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_mouse_position",
            description="获取当前鼠标光标的像素坐标 (x, y)。",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        # ═══ 鼠标 ═══
        Tool(
            name="mouse_move",
            description="移动鼠标到指定像素坐标。默认平滑移动（约 200ms），避免触发 UI 悬停检测丢失。",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "description": "目标 X 坐标（像素）",
                    },
                    "y": {
                        "type": "integer",
                        "description": "目标 Y 坐标（像素）",
                    },
                    "speed": {
                        "type": "string",
                        "enum": ["smooth", "instant"],
                        "description": "移动方式：smooth（平滑，默认）或 instant（瞬间）",
                        "default": "smooth",
                    },
                },
                "required": ["x", "y"],
            },
        ),
        Tool(
            name="mouse_click",
            description="在当前鼠标位置点击。支持左键、右键、中键。",
            inputSchema={
                "type": "object",
                "properties": {
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "description": "鼠标按钮：left（左键，默认）、right（右键）、middle（中键）",
                        "default": "left",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="mouse_double_click",
            description="在当前鼠标位置双击左键。",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="mouse_drag",
            description="从 (x1,y1) 拖拽到 (x2,y2)。先移动到起点，按下左键，平滑移动到终点，释放。",
            inputSchema={
                "type": "object",
                "properties": {
                    "x1": {"type": "integer", "description": "拖拽起点 X"},
                    "y1": {"type": "integer", "description": "拖拽起点 Y"},
                    "x2": {"type": "integer", "description": "拖拽终点 X"},
                    "y2": {"type": "integer", "description": "拖拽终点 Y"},
                },
                "required": ["x1", "y1", "x2", "y2"],
            },
        ),
        Tool(
            name="mouse_scroll",
            description="在当前鼠标位置滚动滚轮。",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "滚动方向：up（向上）或 down（向下）",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "滚动格数，默认 3",
                        "default": 3,
                    },
                },
                "required": ["direction"],
            },
        ),
        # ═══ 键盘 ═══
        Tool(
            name="type_text",
            description="模拟键盘输入文字（支持中文、emoji 等 Unicode 字符）。每个字符之间有小延迟，避免输入过快。",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要输入的文字内容",
                    },
                    "delay_ms": {
                        "type": "integer",
                        "description": "每个字符之间的延迟（毫秒），默认 20",
                        "default": 20,
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="key_press",
            description="按下组合键（如 Ctrl+C、Win+R）。支持所有标准键名。修饰键会自动按正确顺序按下和松开。",
            inputSchema={
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 5,
                        "description": "要按下的键列表。例如：[\"ctrl\", \"c\"]、[\"win\", \"r\"]、[\"alt\", \"tab\"]、[\"enter\"]。支持的键名：ctrl/shift/alt/win/enter/space/tab/escape/backspace/delete/insert/home/end/page_up/page_down/up/down/left/right/f1-f24/a-z/0-9 等。",
                    },
                    "hold_ms": {
                        "type": "integer",
                        "description": "按下持续时间（毫秒），默认 80",
                        "default": 80,
                    },
                },
                "required": ["keys"],
            },
        ),
        Tool(
            name="key_hold",
            description="按住修饰键不放，点按另一个键，再松开修饰键。用于需要长按修饰键的场景（如 Ctrl+Shift+Right 多选）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "hold_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 3,
                        "description": "需要按住的修饰键列表，如 [\"ctrl\", \"shift\"]",
                    },
                    "tap_key": {
                        "type": "string",
                        "description": "在按住修饰键期间点按的键",
                    },
                    "hold_ms": {
                        "type": "integer",
                        "description": "点按键的持续时间（毫秒），默认 100",
                        "default": 100,
                    },
                },
                "required": ["hold_keys", "tap_key"],
            },
        ),
        # ═══ 等待 ═══
        Tool(
            name="wait",
            description="等待指定毫秒数。用于等待 UI 动画、页面加载、菜单展开等。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ms": {
                        "type": "integer",
                        "description": "等待的毫秒数，默认 500",
                        "default": 500,
                    },
                },
                "required": [],
            },
        ),
    ]
    for item in result:
        if item.name in INPUT_TOOLS:
            item.inputSchema['properties']['chat_id'] = {
                'type': 'string', 'description': '当前获得桌面控制权的任务聊天 ID'}
            item.inputSchema.setdefault('required', []).append('chat_id')
    return result


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name in INPUT_TOOLS:
            authorization = await asyncio.to_thread(coordinator_call, 'authorize_input',
                                                      {'chat_id': arguments.get('chat_id', '')})
            if authorization.get('isError'):
                return [TextContent(type='text', text=authorization['content'][0]['text'])]
        # ═══ 截图 ═══
        if name == "screenshot":
            region = arguments.get("region")
            monitor = arguments.get("monitor", 0)
            result = await asyncio.to_thread(coordinator_call, 'capture_task_screen',
                {"chat_id": arguments["chat_id"], "region": region, "monitor": monitor}
                if region is not None else {"chat_id": arguments["chat_id"], "monitor": monitor})
            if result.get('isError'):
                return [TextContent(type='text', text=result['content'][0]['text'])]
            meta = json.loads(result['content'][0]['text'])['observation']
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, **meta})
            )]

        elif name == "get_screen_size":
            w, h = scr.get_screen_size()
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "width": w, "height": h})
            )]

        elif name == "get_mouse_position":
            x, y = mouse.get_position()
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "x": x, "y": y})
            )]

        # ═══ 鼠标 ═══
        elif name == "mouse_move":
            x, y = arguments["x"], arguments["y"]
            speed = arguments.get("speed", "smooth")
            mouse.move_to(x, y, speed)
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "x": x, "y": y, "speed": speed})
            )]

        elif name == "mouse_click":
            btn = arguments.get("button", "left")
            mouse.click(btn)
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "button": btn})
            )]

        elif name == "mouse_double_click":
            mouse.double_click()
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "action": "double_click"})
            )]

        elif name == "mouse_drag":
            mouse.drag(arguments["x1"], arguments["y1"],
                       arguments["x2"], arguments["y2"])
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "from": [arguments["x1"], arguments["y1"]],
                                 "to": [arguments["x2"], arguments["y2"]]})
            )]

        elif name == "mouse_scroll":
            direction = arguments["direction"]
            amount = arguments.get("amount", 3)
            mouse.scroll(direction, amount)
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "direction": direction, "amount": amount})
            )]

        # ═══ 键盘 ═══
        elif name == "type_text":
            text = arguments["text"]
            delay_ms = arguments.get("delay_ms", 20)
            keyboard.type_text(text, delay_ms)
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "text": text, "length": len(text)})
            )]

        elif name == "key_press":
            keys = arguments["keys"]
            hold_ms = arguments.get("hold_ms", 80)
            keyboard.press_keys(keys, hold_ms)
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "keys": keys})
            )]

        elif name == "key_hold":
            hold_keys = arguments["hold_keys"]
            tap_key = arguments["tap_key"]
            hold_ms = arguments.get("hold_ms", 100)
            keyboard.hold_and_tap(hold_keys, tap_key, hold_ms)
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "hold": hold_keys, "tap": tap_key})
            )]

        # ═══ 等待 ═══
        elif name == "wait":
            ms = arguments.get("ms", 500)
            time.sleep(ms / 1000.0)
            return [TextContent(
                type="text",
                text=json.dumps({"success": True, "waited_ms": ms})
            )]

        else:
            return [TextContent(type="text", text=f"❌ 未知工具: {name}")]

    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"success": False, "error": f"{type(e).__name__}: {e}"})
        )]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
