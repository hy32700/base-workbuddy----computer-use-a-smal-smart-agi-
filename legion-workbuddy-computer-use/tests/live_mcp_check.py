"""Explicit live test: independent MCP processes, shared state, capture only (no input)."""

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import AsyncExitStack
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'vision-server'))


def decoded(result):
    assert not result.isError, result.content
    return json.loads(next(c.text for c in result.content if c.type == 'text'))


async def main():
    state = PROJECT / 'tests' / '.tmp' / ('live-' + uuid.uuid4().hex)
    state.mkdir(parents=True)
    env = {**os.environ, 'VIEW_STATE_DIR': str(state)}
    log = (state / 'broker.log').open('wb')
    backend = subprocess.Popen([sys.executable, str(PROJECT / 'vision-server' / 'broker.py')],
                               env=env, stdout=log, stderr=log,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for _ in range(100):
            if (state / 'endpoint.json').exists():
                break
            if backend.poll() is not None:
                raise RuntimeError((state / 'broker.log').read_text(errors='replace'))
            await asyncio.sleep(0.1)
        else:
            raise TimeoutError('Test coordinator did not start')
        async with AsyncExitStack() as stack:
            clients = []
            for _ in range(2):
                r, w = await stack.enter_async_context(stdio_client(StdioServerParameters(
                    command=sys.executable, args=[str(PROJECT / 'vision-server' / 'server.py')], env=env)))
                c = await stack.enter_async_context(ClientSession(r, w))
                await c.initialize()
                clients.append(c)
            dispatcher, vision = clients
            for client, args in [(dispatcher, {'role': 'dispatcher', 'chat_id': 'test-dispatcher'}),
                                 (vision, {'role': 'vision', 'chat_id': 'test-vision'})]:
                decoded(await client.call_tool('register_chat', args))
            status = decoded(await dispatcher.call_tool('get_status', {}))
            assert len(status['chats']) == 2, status
            decoded(await dispatcher.call_tool('start_monitoring', {'chat_id': 'test-dispatcher'}))
            response = await vision.call_tool('next_observation', {'chat_id': 'test-vision'})
            frame = decoded(response)['observation']
            assert any(c.type == 'image' for c in response.content)
            assert frame['coordinate_space'] == 'physical_pixels'
            decoded(await vision.call_tool('submit_analysis', {
                'chat_id': 'test-vision', 'observation_id': frame['id'],
                'summary': 'protocol verification only; no model inference', 'targets': []}))
            events = decoded(await dispatcher.call_tool('receive_messages', {
                'chat_id': 'test-dispatcher', 'timeout_seconds': 0}))
            assert events['messages'][0]['type'] == 'vision_analysis'
            second = decoded(await vision.call_tool('next_observation', {'chat_id': 'test-vision'}))['observation']
            interval = second['created_at'] - frame['created_at']
            assert 13 <= interval <= 18, interval
            for task_id in ('test-task-a', 'test-task-b'):
                decoded(await dispatcher.call_tool('register_chat', {
                    'role': 'task', 'chat_id': task_id, 'task_title': task_id}))
            decoded(await dispatcher.call_tool('assign_task', {
                'chat_id': 'test-dispatcher', 'task_chat_id': 'test-task-a', 'instruction': 'inspect only'}))
            assert not decoded(await vision.call_tool('receive_messages', {
                'chat_id': 'test-task-b', 'timeout_seconds': 0}))['messages']
            task_response = await dispatcher.call_tool('capture_task_screen', {
                'chat_id': 'test-task-a', 'region': [100, 100, 300, 200]})
            assert not any(c.type == 'image' for c in task_response.content)
            task_frame = decoded(task_response)['observation']
            point = decoded(await dispatcher.call_tool('map_coordinates', {
                'chat_id': 'test-task-a', 'observation_id': task_frame['id'], 'x': 25, 'y': 40}))
            assert (point['x'], point['y']) == (125, 140), point
            # A separate computer-control stdio process must use the same owned-image pool.
            r, w = await stack.enter_async_context(stdio_client(StdioServerParameters(
                command=sys.executable, args=[str(PROJECT / 'computer-control-server' / 'server.py')], env=env)))
            control = await stack.enter_async_context(ClientSession(r, w))
            await control.initialize()
            control_frame = decoded(await control.call_tool('screenshot', {'chat_id': 'test-task-a'}))
            assert Path(control_frame['path']).parent == Path(status['screenshot_dir'])
            stopped = decoded(await dispatcher.call_tool('end_session', {'chat_id': 'test-dispatcher'}))
            assert not stopped['running'] and stopped['owned_screenshot_count'] == 0
            assert not list(Path(status['screenshot_dir']).glob('*.png'))
            print(json.dumps({'passed': True, 'independent_mcp_processes': 3,
                              'observed_capture_interval_seconds': round(interval, 2),
                              'image_size': [frame['width'], frame['height']],
                              'task_isolation': True, 'crop_coordinate_mapping': True,
                              'shared_screenshot_cleanup': True}))
    finally:
        backend.terminate()
        backend.wait(timeout=5)
        log.close()


if __name__ == '__main__':
    asyncio.run(main())
