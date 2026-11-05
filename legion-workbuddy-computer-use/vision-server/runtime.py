"""Local capture scheduler and routing; WorkBuddy supplies the native chats and analysis."""

import asyncio
import time
import uuid
from collections import deque
from pathlib import Path


class DesktopRuntime:
    capture_interval = 15
    cleanup_interval = 300

    def __init__(self, screenshot_root, capture, clock=time.time,
                 monotonic=time.monotonic, timer_sleep=asyncio.sleep):
        self.run_id = uuid.uuid4().hex
        self.run_dir = Path(screenshot_root).resolve() / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.capture = capture
        self.clock = clock
        self.monotonic = monotonic
        self.timer_sleep = timer_sleep
        self.chats = {}
        self.assignments = set()
        self.active_task_chat_id = None
        self.generation = 0
        self.frames = {}
        self.owned_files = set()
        self.pending = None
        self.pending_tasks = deque()
        self.inflight = None
        self.frame_event = asyncio.Event()
        self.message_event = asyncio.Condition()
        self.capture_lock = asyncio.Lock()
        self.lifecycle_lock = asyncio.Lock()
        self.accepting_captures = True
        self.messages = deque(maxlen=1000)
        self.sequence = 0
        self.jobs = []
        self.last_capture_error = None
        self.last_cleanup_error = None
        self.last_capture_at = None
        self.last_cleanup_at = None
        self.last_analysis_at = None
        self.deleted_count = 0

    def register_chat(self, role, chat_id, task_title=None):
        if role not in {'dispatcher', 'vision', 'task'}:
            raise ValueError('role must be dispatcher, vision or task')
        if not isinstance(chat_id, str) or not chat_id.strip():
            raise ValueError('A real WorkBuddy native chat ID is required')
        existing = self.chats.get(chat_id)
        entry = {'role': role, 'chat_id': chat_id, 'task_title': task_title}
        if existing:
            if existing != entry:
                raise ValueError('Each role/task must use a separate native chat')
            return existing
        if role != 'task' and any(c['role'] == role for c in self.chats.values()):
            raise ValueError(f'Only one {role} chat may be registered')
        if role == 'task' and (not isinstance(task_title, str) or not task_title.strip()):
            raise ValueError('A task chat needs its own task_title')
        self.chats[chat_id] = entry
        return entry

    def require_role(self, chat_id, role):
        if self.chats.get(chat_id, {}).get('role') != role:
            raise ValueError(f'chat_id must be the registered {role} chat')

    def role_id(self, role):
        return next((c['chat_id'] for c in self.chats.values() if c['role'] == role), None)

    def publish(self, destination, kind, payload):
        self.sequence += 1
        message = {'sequence': self.sequence, 'destination': destination,
                   'type': kind, 'payload': payload, 'created_at': self.clock()}
        self.messages.append(message)
        # Called from the event-loop thread. Wake all long-polling chats.
        async def wake():
            async with self.message_event:
                self.message_event.notify_all()
        asyncio.get_running_loop().create_task(wake())
        return message

    def assign_task(self, dispatcher_id, task_chat_id, instruction):
        self.require_role(dispatcher_id, 'dispatcher')
        self.require_role(task_chat_id, 'task')
        if task_chat_id in self.assignments:
            raise ValueError('Create a NEW native chat for each new task')
        if self.active_task_chat_id is not None:
            raise ValueError('Another task owns the desktop; wait for its completion/failure')
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError('instruction is required')
        self.assignments.add(task_chat_id)
        self.active_task_chat_id = task_chat_id
        return self.publish(task_chat_id, 'task_assignment', {'instruction': instruction})

    def report_task(self, task_chat_id, status, summary):
        self.require_role(task_chat_id, 'task')
        if task_chat_id not in self.assignments:
            raise ValueError('This chat has no assigned task')
        if status not in {'progress', 'completed', 'blocked', 'failed'}:
            raise ValueError('Invalid task status')
        if status in {'completed', 'failed'} and self.active_task_chat_id == task_chat_id:
            self.active_task_chat_id = None
        return self.publish(self.role_id('dispatcher'), 'task_report',
                            {'chat_id': task_chat_id, 'status': status, 'summary': summary})

    def send_task_update(self, dispatcher_id, task_chat_id, message):
        self.require_role(dispatcher_id, 'dispatcher')
        self.require_role(task_chat_id, 'task')
        if task_chat_id not in self.assignments:
            raise ValueError('Task must be assigned first')
        return self.publish(task_chat_id, 'task_update', {'message': message})

    async def receive_messages(self, chat_id, after_sequence=0, timeout_seconds=25):
        if self.chats.get(chat_id, {}).get('role') not in {'dispatcher', 'task'}:
            raise ValueError('Only dispatcher/task chats receive routed messages')
        if not isinstance(after_sequence, int) or after_sequence < 0:
            raise ValueError('after_sequence must be a nonnegative integer')
        if not 0 <= timeout_seconds <= 30:
            raise ValueError('timeout_seconds must be between 0 and 30')
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        generation = self.generation
        async with self.message_event:
            while True:
                if generation != self.generation or self.chats.get(chat_id, {}).get('role') not in {'dispatcher', 'task'}:
                    raise ValueError('Chat session ended; do not reuse its message poll')
                rows = [m for m in self.messages if m['sequence'] > after_sequence
                        and m['destination'] == chat_id]
                remaining = deadline - asyncio.get_running_loop().time()
                if rows or remaining <= 0:
                    return {'messages': rows, 'cursor': self.sequence,
                            'history_truncated': bool(self.messages and after_sequence
                                and after_sequence < self.messages[0]['sequence'] - 1)}
                try:
                    await asyncio.wait_for(self.message_event.wait(), remaining)
                except asyncio.TimeoutError:
                    return {'messages': [], 'cursor': self.sequence, 'history_truncated': False}

    async def _capture(self, region=None, monitor=0):
        async with self.capture_lock:
            if not self.accepting_captures:
                raise ValueError('Monitoring is stopped; start it before requesting screenshots')
            worker = asyncio.create_task(asyncio.to_thread(
                self.capture, output_dir=self.run_dir, region=region, monitor=monitor))
            cancelled = False
            try:
                meta = await asyncio.shield(worker)
            except asyncio.CancelledError:
                # A native screen grab cannot be cancelled mid-thread. Register its
                # output before stopping, so the final cleanup cannot miss the file.
                meta = await worker
                cancelled = True
            path = Path(meta['path']).resolve()
            if path.parent != self.run_dir or path.is_symlink():
                raise ValueError('Capture must stay inside the current run directory')
            self.owned_files.add(path)
            frame = {**meta, 'id': uuid.uuid4().hex, 'run_id': self.run_id,
                     'created_at': self.clock()}
            self.frames[frame['id']] = frame
            if cancelled:
                raise asyncio.CancelledError
            return frame

    async def capture_once(self):
        frame = await self._capture()
        self.pending = frame['id']  # Latest frame replaces unconsumed backlog.
        self.last_capture_at = frame['created_at']
        self.last_capture_error = None
        self.frame_event.set()
        return frame

    async def capture_task_screen(self, chat_id, region=None, monitor=0):
        self.require_role(chat_id, 'task')
        if chat_id not in self.assignments:
            raise ValueError('Task must be assigned before it captures the screen')
        if not self.jobs:
            raise ValueError('Start monitoring before requesting task screenshots')
        self.authorize_input(chat_id)
        frame = await self._capture(region, monitor)
        frame['task_chat_id'] = chat_id
        self.pending_tasks = deque(i for i in self.pending_tasks
                                   if self.frames[i].get('task_chat_id') != chat_id)
        self.pending_tasks.append(frame['id'])
        self.frame_event.set()
        return frame

    async def next_observation(self, chat_id, timeout_seconds=25):
        self.require_role(chat_id, 'vision')
        if not 0 <= timeout_seconds <= 30:
            raise ValueError('timeout_seconds must be between 0 and 30')
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        generation = self.generation
        while True:
            if generation != self.generation:
                raise ValueError('Vision session ended; do not reuse its observation poll')
            self.require_role(chat_id, 'vision')
            if self.inflight:
                return self.frames[self.inflight]
            if self.pending_tasks:
                self.inflight = self.pending_tasks.popleft()
                return self.frames[self.inflight]
            if self.pending:
                self.inflight, self.pending = self.pending, None
                self.frame_event.clear()
                return self.frames[self.inflight]
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return None
            self.frame_event.clear()
            try:
                await asyncio.wait_for(self.frame_event.wait(), remaining)
            except asyncio.TimeoutError:
                return None

    def submit_analysis(self, chat_id, observation_id, summary, targets):
        self.require_role(chat_id, 'vision')
        if observation_id != self.inflight:
            raise ValueError('Analysis must refer to the issued, in-flight observation')
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError('summary is required')
        frame = self.frames[observation_id]
        event = self.publish(self.role_id('dispatcher'), 'vision_analysis',
                             {'observation_id': observation_id, 'captured_at': frame['created_at'],
                              'summary': summary, 'targets': targets,
                              'coordinate_space': frame.get('coordinate_space'),
                              'width': frame['width'], 'height': frame['height'],
                              'origin_x': frame.get('origin_x', 0),
                              'origin_y': frame.get('origin_y', 0),
                              'task_chat_id': frame.get('task_chat_id')})
        self.inflight = None
        self.last_analysis_at = self.clock()
        return event

    def cleanup_once(self, keep_current=True):
        protected_ids = {self.pending, self.inflight, *self.pending_tasks} if keep_current else set()
        protected = {Path(self.frames[i]['path']).resolve()
                     for i in protected_ids if i in self.frames}
        deleted = 0
        for path in tuple(self.owned_files):
            # Never glob Temp or remove a directory; only exact owned PNG paths.
            if path in protected:
                continue
            if path.parent != self.run_dir or path.is_symlink():
                self.owned_files.discard(path)
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError as error:
                self.last_cleanup_error = f'{type(error).__name__}: {error}'
                continue
            self.owned_files.discard(path)
            deleted += 1
        self.frames = {i: f for i, f in self.frames.items()
                       if Path(f['path']).resolve() in self.owned_files}
        if not keep_current:
            self.pending = self.inflight = None
            self.pending_tasks.clear()
        self.deleted_count += deleted
        self.last_cleanup_at = self.clock()
        return deleted

    async def _capture_loop(self):
        deadline = self.monotonic()
        while True:
            await self.timer_sleep(max(0, deadline - self.monotonic()))
            try:
                await self.capture_once()
            except Exception as error:
                self.last_capture_error = f'{type(error).__name__}: {error}'
                self.publish(self.role_id('dispatcher'), 'capture_error',
                             {'error': self.last_capture_error})
            deadline += self.capture_interval
            if deadline < self.monotonic():
                deadline = self.monotonic() + self.capture_interval

    async def _cleanup_loop(self):
        while True:
            await self.timer_sleep(self.cleanup_interval)
            self.last_cleanup_error = None
            self.cleanup_once()
            if self.last_cleanup_error:
                self.publish(self.role_id('dispatcher'), 'cleanup_error',
                             {'error': self.last_cleanup_error})

    async def start(self, dispatcher_id):
        async with self.lifecycle_lock:
            self.require_role(dispatcher_id, 'dispatcher')
            if not self.role_id('vision'):
                raise ValueError('Create and register the dedicated vision chat first')
            if not self.jobs:
                self.accepting_captures = True
                self.jobs = [asyncio.create_task(self._capture_loop()),
                             asyncio.create_task(self._cleanup_loop())]
            return self.status()

    def authorize_input(self, chat_id):
        self.require_role(chat_id, 'task')
        if chat_id != self.active_task_chat_id or not self.jobs:
            raise ValueError('Only the active task may control the desktop while monitoring is running')
        return {'authorized': True, 'chat_id': chat_id}

    async def end_session(self, dispatcher_id):
        async with self.lifecycle_lock:
            self.require_role(dispatcher_id, 'dispatcher')
            await self._stop()
            self.generation += 1
            self.chats.clear()
            self.assignments.clear()
            self.active_task_chat_id = None
            self.messages.clear()
            self.frame_event.set()
            async with self.message_event:
                self.message_event.notify_all()
            return self.status()

    async def stop(self):
        async with self.lifecycle_lock:
            return await self._stop()

    async def _stop(self):
        self.accepting_captures = False
        jobs, self.jobs = self.jobs, []
        for job in jobs:
            job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        # Drain task RPC captures as well as periodic captures before final cleanup.
        async with self.capture_lock:
            self.cleanup_once(keep_current=False)
        return self.status()

    def status(self):
        return {'running': bool(self.jobs) and all(not j.done() for j in self.jobs),
                'run_id': self.run_id, 'screenshot_dir': str(self.run_dir),
                'capture_interval_seconds': self.capture_interval,
                'cleanup_interval_seconds': self.cleanup_interval,
                'chats': list(self.chats.values()), 'pending_observation': self.pending,
                'active_task_chat_id': self.active_task_chat_id,
                'pending_task_observations': list(self.pending_tasks),
                'inflight_observation': self.inflight, 'last_capture_at': self.last_capture_at,
                'last_analysis_at': self.last_analysis_at, 'last_cleanup_at': self.last_cleanup_at,
                'last_capture_error': self.last_capture_error,
                'last_cleanup_error': self.last_cleanup_error,
                'owned_screenshot_count': len(self.owned_files),
                'deleted_screenshot_count': self.deleted_count}
