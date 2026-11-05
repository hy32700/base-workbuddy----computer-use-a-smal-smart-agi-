"""MCP tool definitions shared by stdio frontends and the local coordinator."""

import base64
import json
import sys
from pathlib import Path
from mcp.types import Tool, TextContent, ImageContent

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'computer-control-server'))
import screenshot


def tool(name, description, properties=None, required=None):
    return Tool(name=name, description=description, inputSchema={
        'type': 'object', 'properties': properties or {}, 'required': required or [],
        'additionalProperties': False})


STRING = {'type': 'string'}
CHAT = {'type': 'string', 'description': '真实 WorkBuddy 原生聊天 ID；内部登记不会创建聊天。'}
POLL = {'type': 'number', 'minimum': 0, 'maximum': 30, 'default': 25}
TOOLS = [
    tool('register_chat', '绑定已由 WorkBuddy 创建的独立聊天。vision/dispatcher 各一个，每个新任务使用新聊天。',
         {'chat_id': CHAT, 'role': {'type': 'string', 'enum': ['vision', 'dispatcher', 'task']},
          'task_title': STRING}, ['chat_id', 'role']),
    tool('start_monitoring', '调度聊天启动：每15秒截图，每300秒清理本轮截图。视觉分析由独立视觉聊天完成。',
         {'chat_id': CHAT}, ['chat_id']),
    tool('stop_monitoring', '调度聊天停止截图并清理本轮持有的所有截图。', {'chat_id': CHAT}, ['chat_id']),
    tool('end_session', '调度聊天结束本轮，停止、清理截图、解除聊天绑定。', {'chat_id': CHAT}, ['chat_id']),
    tool('get_status', '查看周期、聊天绑定、截图/分析时间及错误。不会开始监控。'),
    tool('authorize_input', 'computer-control 内部使用：仅当前活动任务聊天可以操作桌面。',
         {'chat_id': CHAT}, ['chat_id']),
    tool('next_observation', '仅视觉聊天：等待最新截图，返回实际图片与坐标元数据；分析后必须 submit_analysis。',
         {'chat_id': CHAT, 'timeout_seconds': POLL}, ['chat_id']),
    tool('submit_analysis', '仅视觉聊天：将截图分析提交给调度聊天，不执行任何点击。浅色/蓝色横条都表示已打开。',
         {'chat_id': CHAT, 'observation_id': STRING, 'summary': STRING,
          'targets': {'type': 'array', 'items': {'type': 'object', 'properties': {
              'name': STRING, 'x': {'type': 'number'}, 'y': {'type': 'number'},
              'running_indicator': {'type': 'string', 'enum': ['light', 'blue', 'none', 'unknown']},
              'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1}},
              'required': ['name', 'x', 'y', 'running_indicator', 'confidence']}}},
         ['chat_id', 'observation_id', 'summary', 'targets']),
    tool('assign_task', '仅调度聊天：给新任务的独立原生聊天分配指令，一个任务聊天不可用于第二项任务。',
         {'chat_id': CHAT, 'task_chat_id': CHAT, 'instruction': STRING},
         ['chat_id', 'task_chat_id', 'instruction']),
    tool('receive_messages', '调度/任务聊天长轮询各自消息；下一次传回返回的 cursor。',
         {'chat_id': CHAT, 'after_sequence': {'type': 'integer', 'minimum': 0, 'default': 0},
          'timeout_seconds': POLL}, ['chat_id']),
    tool('report_task', '任务聊天向调度聊天报告进度/完成/阻塞/失败。',
         {'chat_id': CHAT, 'status': {'type': 'string', 'enum': ['progress', 'completed', 'blocked', 'failed']},
          'summary': STRING}, ['chat_id', 'status', 'summary']),
    tool('send_task_update', '调度聊天将视觉结果/同一任务的后续信息转发给指定任务聊天。新任务仍需新聊天。',
         {'chat_id': CHAT, 'task_chat_id': CHAT, 'message': STRING}, ['chat_id', 'task_chat_id', 'message']),
    tool('capture_task_screen', '任务聊天请求截图（含验证截图），仅返回元数据；图片只发给视觉聊天分析，纳入本轮5分钟清理。',
         {'chat_id': CHAT, 'region': {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 4, 'maxItems': 4},
          'monitor': {'type': 'integer', 'minimum': 0, 'default': 0}}, ['chat_id']),
    tool('map_coordinates', '根据本轮截图元数据换算为鼠标物理像素；支持裁剪、缩放。过期截图需重新截取。',
         {'chat_id': CHAT, 'observation_id': STRING, 'x': {'type': 'number'}, 'y': {'type': 'number'},
          'image_width': {'type': 'number', 'exclusiveMinimum': 0},
          'image_height': {'type': 'number', 'exclusiveMinimum': 0}},
         ['chat_id', 'observation_id', 'x', 'y']),
]


def text_result(value):
    return [TextContent(type='text', text=json.dumps(value, ensure_ascii=False))]


def frame_result(frame):
    if frame is None:
        return text_result({'observation': None, 'retry': True})
    return [*text_result({'observation': frame}), ImageContent(type='image', mimeType='image/png',
             data=base64.b64encode(Path(frame['path']).read_bytes()).decode('ascii'))]


async def dispatch(runtime, name, args):
    c = args.get('chat_id')
    if name == 'register_chat':
        result = runtime.register_chat(args['role'], c, args.get('task_title'))
    elif name == 'start_monitoring':
        result = await runtime.start(c)
    elif name == 'end_session':
        result = await runtime.end_session(c)
    elif name == 'stop_monitoring':
        runtime.require_role(c, 'dispatcher')
        result = await runtime.stop()
    elif name == 'authorize_input':
        result = runtime.authorize_input(c)
    elif name == 'get_status':
        result = runtime.status()
    elif name == 'next_observation':
        return frame_result(await runtime.next_observation(c, args.get('timeout_seconds', 25)))
    elif name == 'submit_analysis':
        frame = runtime.frames.get(args['observation_id'])
        if frame is None:
            raise ValueError('Unknown observation; get a new screenshot')
        targets = []
        for target in args['targets']:
            point = screenshot.map_coordinates(frame, target['x'], target['y'])
            targets.append({**target, 'screen_x': point['x'], 'screen_y': point['y'],
                            'is_running': target['running_indicator'] in {'light', 'blue'}})
        result = runtime.submit_analysis(c, args['observation_id'], args['summary'], targets)
    elif name == 'assign_task':
        result = runtime.assign_task(c, args['task_chat_id'], args['instruction'])
    elif name == 'receive_messages':
        result = await runtime.receive_messages(c, args.get('after_sequence', 0), args.get('timeout_seconds', 25))
    elif name == 'report_task':
        result = runtime.report_task(c, args['status'], args['summary'])
    elif name == 'send_task_update':
        result = runtime.send_task_update(c, args['task_chat_id'], args['message'])
    elif name == 'capture_task_screen':
        frame = await runtime.capture_task_screen(c, args.get('region'), args.get('monitor', 0))
        return text_result({'observation': frame, 'analysis_queued': True})
    elif name == 'map_coordinates':
        runtime.require_role(c, 'task')
        frame = runtime.frames.get(args['observation_id'])
        if frame is None:
            raise ValueError('Screenshot has expired; capture a fresh task screenshot')
        if frame.get('task_chat_id') != c:
            raise ValueError('Use a fresh screenshot belonging to this task chat')
        result = screenshot.map_coordinates(frame, args['x'], args['y'],
                                            args.get('image_width'), args.get('image_height'))
    else:
        raise ValueError(f'Unknown tool: {name}')
    return text_result(result)
