import asyncio
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vision-server'))
from runtime import DesktopRuntime


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp_root = Path(__file__).parent / '.tmp'
        temp_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temp_root)
        self.t = 1000.0
        self.n = 0

        def capture(output_dir, region=None, monitor=0):
            self.n += 1
            path = Path(output_dir) / f'viewshot_{self.n}.png'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'owned-screenshot')
            return {'path': str(path), 'width': 2560, 'height': 1600,
                    'origin_x': 0, 'origin_y': 0, 'coordinate_space': 'physical_pixels'}

        self.runtime = DesktopRuntime(Path(self.tmp.name), capture, clock=lambda: self.t)
        self.runtime.register_chat('dispatcher', 'native-dispatcher')
        self.runtime.register_chat('vision', 'native-vision')

    async def asyncTearDown(self):
        await self.runtime.stop()
        self.tmp.cleanup()

    async def test_roles_require_separate_native_chats(self):
        with self.assertRaises(ValueError):
            self.runtime.register_chat('task', 'native-vision', 'click terminal')
        with self.assertRaises(ValueError):
            self.runtime.register_chat('vision', 'second-vision')

    async def test_task_chat_cannot_receive_vision_frames(self):
        self.runtime.register_chat('task', 'task-a', 'task A')
        with self.assertRaises(ValueError):
            await self.runtime.next_observation('task-a', timeout_seconds=0)

    async def test_capture_coalesces_backlog_to_latest_frame(self):
        await self.runtime.capture_once()
        latest = await self.runtime.capture_once()
        received = await self.runtime.next_observation('native-vision', timeout_seconds=0)
        self.assertEqual(latest['id'], received['id'])
        self.assertEqual(2, self.n)

    async def test_vision_analysis_routes_to_dispatcher_only(self):
        self.runtime.register_chat('task', 'task-a', 'task A')
        await self.runtime.capture_once()
        frame = await self.runtime.next_observation('native-vision', timeout_seconds=0)
        self.runtime.submit_analysis('native-vision', frame['id'], 'terminal running', [])
        events = await self.runtime.receive_messages('native-dispatcher', 0, 0)
        self.assertEqual('vision_analysis', events['messages'][-1]['type'])
        self.assertEqual('terminal running', events['messages'][-1]['payload']['summary'])
        self.assertEqual([], (await self.runtime.receive_messages('task-a', 0, 0))['messages'])

    async def test_each_task_is_isolated_and_cannot_be_reassigned(self):
        self.runtime.register_chat('task', 'task-a', 'task A')
        self.runtime.register_chat('task', 'task-b', 'task B')
        self.runtime.assign_task('native-dispatcher', 'task-a', 'click terminal')
        received = await self.runtime.receive_messages('task-a', 0, 0)
        self.assertEqual('click terminal', received['messages'][0]['payload']['instruction'])
        self.assertEqual([], (await self.runtime.receive_messages('task-b', 0, 0))['messages'])
        with self.assertRaises(ValueError):
            self.runtime.assign_task('native-dispatcher', 'task-a', 'unrelated new task')

    async def test_cleanup_deletes_only_owned_files_and_protects_pending(self):
        first = await self.runtime.capture_once()
        pending = await self.runtime.capture_once()
        unrelated = self.runtime.run_dir / 'notes.png'
        unrelated.write_bytes(b'user-file')
        external = Path(self.tmp.name) / 'other.png'
        external.write_bytes(b'not-from-this-run')
        deleted = self.runtime.cleanup_once()
        self.assertEqual(1, deleted)
        self.assertFalse(Path(first['path']).exists())
        self.assertTrue(Path(pending['path']).exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(external.exists())

    async def test_cleanup_keeps_inflight_until_analysis_is_submitted(self):
        await self.runtime.capture_once()
        frame = await self.runtime.next_observation('native-vision', timeout_seconds=0)
        await self.runtime.capture_once()
        self.runtime.cleanup_once()
        self.assertTrue(Path(frame['path']).exists())
        self.runtime.submit_analysis('native-vision', frame['id'], 'done', [])
        self.runtime.cleanup_once()
        self.assertFalse(Path(frame['path']).exists())

    async def test_capture_and_cleanup_intervals_are_15_and_300_seconds(self):
        self.assertEqual(15, self.runtime.capture_interval)
        self.assertEqual(300, self.runtime.cleanup_interval)
        await self.runtime.start('native-dispatcher')
        await asyncio.sleep(0.05)
        self.assertEqual(1, self.n)
        self.assertTrue(self.runtime.status()['running'])
        await self.runtime.stop()
        self.assertFalse(self.runtime.status()['running'])

    async def test_start_requires_both_permanent_chats(self):
        other = DesktopRuntime(Path(self.tmp.name), lambda **kw: {})
        other.register_chat('dispatcher', 'd')
        with self.assertRaises(ValueError):
            await other.start('d')

    async def test_rejects_analysis_for_unissued_frame(self):
        frame = await self.runtime.capture_once()
        with self.assertRaises(ValueError):
            self.runtime.submit_analysis('native-vision', frame['id'], 'guessed', [])

    async def test_scheduler_repeats_at_15_second_deadlines(self):
        tick = [0.0]
        delays = []
        async def advance(delay):
            if len(delays) == 3:
                raise asyncio.CancelledError
            delays.append(delay)
            tick[0] += delay
        self.runtime.monotonic = lambda: tick[0]
        self.runtime.timer_sleep = advance
        with self.assertRaises(asyncio.CancelledError):
            await self.runtime._capture_loop()
        self.assertEqual([0, 15, 15], delays)
        self.assertEqual(3, self.n)

    async def test_cleanup_timer_runs_at_300_seconds(self):
        first = await self.runtime.capture_once()
        pending = await self.runtime.capture_once()
        delays = []
        async def advance(delay):
            if delays:
                raise asyncio.CancelledError
            delays.append(delay)
        self.runtime.timer_sleep = advance
        with self.assertRaises(asyncio.CancelledError):
            await self.runtime._cleanup_loop()
        self.assertEqual([300], delays)
        self.assertFalse(Path(first['path']).exists())
        self.assertTrue(Path(pending['path']).exists())

    async def test_task_screenshots_go_to_vision_then_dispatcher(self):
        self.runtime.register_chat('task', 'task-a', 'task A')
        self.runtime.assign_task('native-dispatcher', 'task-a', 'inspect only')
        await self.runtime.start('native-dispatcher')
        frame = await self.runtime.capture_task_screen('task-a')
        self.runtime.cleanup_once()
        self.assertTrue(Path(frame['path']).exists())
        received = await self.runtime.next_observation('native-vision', 0)
        self.assertEqual(frame['id'], received['id'])
        self.runtime.submit_analysis('native-vision', frame['id'], 'verified', [])
        events = await self.runtime.receive_messages('native-dispatcher', 0, 0)
        self.assertEqual('task-a', events['messages'][0]['payload']['task_chat_id'])
        self.runtime.send_task_update('native-dispatcher', 'task-a', 'verified target')
        task_events = await self.runtime.receive_messages('task-a', 0, 0)
        self.assertEqual('task_update', task_events['messages'][-1]['type'])

    async def test_only_one_active_task_until_completed(self):
        self.runtime.register_chat('task', 'task-a', 'task A')
        self.runtime.register_chat('task', 'task-b', 'task B')
        self.runtime.assign_task('native-dispatcher', 'task-a', 'A')
        with self.assertRaises(ValueError):
            self.runtime.assign_task('native-dispatcher', 'task-b', 'B')
        await self.runtime.start('native-dispatcher')
        with self.assertRaises(ValueError):
            self.runtime.authorize_input('task-b')
        self.assertTrue(self.runtime.authorize_input('task-a')['authorized'])
        self.runtime.report_task('task-a', 'completed', 'done')
        self.runtime.assign_task('native-dispatcher', 'task-b', 'B')
        with self.assertRaises(ValueError):
            self.runtime.authorize_input('task-a')

    async def test_end_session_invalidates_previous_long_polls(self):
        waiting_image = asyncio.create_task(self.runtime.next_observation('native-vision', 25))
        waiting_events = asyncio.create_task(self.runtime.receive_messages('native-dispatcher', 0, 25))
        await asyncio.sleep(0)
        await self.runtime.end_session('native-dispatcher')
        # Even reusing a native ID must not revive an old generation's wait.
        self.runtime.register_chat('dispatcher', 'native-dispatcher')
        self.runtime.register_chat('vision', 'native-vision')
        for waiting in (waiting_image, waiting_events):
            with self.assertRaises(ValueError):
                await waiting

    async def test_stop_drains_task_capture_before_final_cleanup(self):
        self.runtime.register_chat('task', 'task-a', 'task A')
        self.runtime.assign_task('native-dispatcher', 'task-a', 'inspect')
        await self.runtime.start('native-dispatcher')
        await asyncio.sleep(0.05)
        original = self.runtime.capture
        started, release = threading.Event(), threading.Event()
        def slow_capture(**kw):
            started.set()
            if not release.wait(timeout=2):
                raise TimeoutError('test release missing')
            return original(**kw)
        self.runtime.capture = slow_capture
        capturing = asyncio.create_task(self.runtime.capture_task_screen('task-a'))
        self.assertTrue(await asyncio.to_thread(started.wait, 1))
        stopping = asyncio.create_task(self.runtime.stop())
        await asyncio.sleep(0.02)
        self.assertFalse(stopping.done())
        release.set()
        await capturing
        await stopping
        self.assertEqual(0, self.runtime.status()['owned_screenshot_count'])
        self.assertEqual([], list(self.runtime.run_dir.glob('*.png')))
        with self.assertRaises(ValueError):
            await self.runtime.capture_task_screen('task-a')

    async def test_start_waits_for_end_session_and_cannot_restart_orphan_loops(self):
        await self.runtime.start('native-dispatcher')
        await asyncio.sleep(0.05)
        # Force end_session to wait while draining a concurrent capture.
        await self.runtime.capture_lock.acquire()
        ending = asyncio.create_task(self.runtime.end_session('native-dispatcher'))
        await asyncio.sleep(0.02)
        starting = asyncio.create_task(self.runtime.start('native-dispatcher'))
        await asyncio.sleep(0.02)
        self.assertFalse(starting.done())
        self.runtime.capture_lock.release()
        await ending
        with self.assertRaises(ValueError):
            await starting
        self.assertFalse(self.runtime.status()['running'])


if __name__ == '__main__':
    unittest.main()
