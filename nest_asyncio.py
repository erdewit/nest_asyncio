import sys
import asyncio
import heapq


def apply(loop=None):
    """
    Patch asyncio to make its event loop reentrent.
    """
    loop = loop or asyncio.get_event_loop()
    if hasattr(loop, '_run_until_complete_orig'):
        # already patched
        return
    _patch_asyncio()
    _patch_loop(loop)
    _patch_task()
    _patch_handle()


def _patch_asyncio():
    """
    Patch asyncio module to use pure Python tasks and futures,
    use module level _current_tasks, all_tasks and patch run method.
    """
    def run(future, *, debug=False):
        loop = asyncio.get_event_loop()
        run_orig = asyncio._run_orig  # noqa
        if run_orig and not loop.is_running():
            return run_orig(future, debug=debug)
        else:
            loop.set_debug(debug)
            return loop.run_until_complete(future)

    if sys.version_info >= (3, 6, 0):
        asyncio.Task = asyncio.tasks._CTask = asyncio.tasks.Task = \
            asyncio.tasks._PyTask
        asyncio.Future = asyncio.futures._CFuture = asyncio.futures.Future = \
            asyncio.futures._PyFuture
    if sys.version_info < (3, 7, 0):
        asyncio.tasks._current_tasks = asyncio.tasks.Task._current_tasks  # noqa
        asyncio.all_tasks = asyncio.tasks.Task.all_tasks  # noqa
    if not hasattr(asyncio, '_run_orig'):
        asyncio._run_orig = getattr(asyncio, 'run', None)
        asyncio.run = run


def _patch_loop(loop):
    """
    Patch loop to make it reentrent.
    """
    def run_until_complete(self, future):
        if self.is_running():
            self._check_closed()
            f = asyncio.ensure_future(future)
            if f is not future:
                f._log_destroy_pending = False
            while not f.done():
                run_once(self)
            return f.result()
        else:
            return self._run_until_complete_orig(future)

    def run_once(self):
        self._nesting_level += 1
        if self._nesting_level == 1:
            handle = asyncio.Handle(None, None, self)
            handle.cancel()
            self._bogus_handles = [handle] * len(self._ready)

        while self._scheduled and self._scheduled[0]._cancelled:
            self._timer_cancelled_count -= 1
            handle = heapq.heappop(self._scheduled)
            handle._scheduled = False

        timeout = None
        if self._ready or self._stopping:
            timeout = 0
        elif self._scheduled:
            when = self._scheduled[0]._when
            timeout = max(0, when - self.time())

        event_list = self._selector.select(timeout)
        self._process_events(event_list)

        end_time = self.time() + self._clock_resolution
        while self._scheduled:
            handle = self._scheduled[0]
            if handle._when >= end_time:
                break
            handle = heapq.heappop(self._scheduled)
            handle._scheduled = False
            self._ready.append(handle)

        self._num_handles_todo += len(self._ready)
        while self._num_handles_todo:
            self._num_handles_todo -= 1
            handle = self._ready.popleft()
            if handle._cancelled:
                continue
            handle._run()
        handle = None

        self._nesting_level -= 1
        if self._nesting_level == 0:
            # add bogus handles to keep loop._run_once happy
            self._ready.extend(self._bogus_handles)

    cls = loop.__class__
    cls._run_until_complete_orig = cls.run_until_complete
    cls.run_until_complete = run_until_complete
    loop._num_handles_todo = 0
    loop._nesting_level = 0
    loop._bogus_handles = []


def _patch_task():
    """
    Patch the Task's step and enter/leave methods to make it reentrant.
    """
    def step(task, exc=None):
        curr_task = curr_tasks.get(task._loop)
        try:
            step_orig(task, exc)
        finally:
            if curr_task is None:
                curr_tasks.pop(task._loop, None)
            else:
                curr_tasks[task._loop] = curr_task

    Task = asyncio.Task
    if sys.version_info >= (3, 7, 0):

        def enter_task(loop, task):
            curr_tasks[loop] = task

        def leave_task(loop, task):
            del curr_tasks[loop]

        asyncio.tasks._enter_task = enter_task
        asyncio.tasks._leave_task = leave_task
        curr_tasks = asyncio.tasks._current_tasks
        step_orig = Task._Task__step
        Task._Task__step = step
    else:
        curr_tasks = Task._current_tasks
        step_orig = Task._step
        Task._step = step


def _patch_handle():
    """
    Patch Handle to allow recursive calls.
    """
    def run(self):
        try:
            ctx = self._context.copy()
            ctx.run(self._callback, *self._args)
        except Exception as exc:
            cb = format_helpers._format_callback_source(
                self._callback, self._args)
            msg = 'Exception in callback {}'.format(cb)
            context = {
                'message': msg,
                'exception': exc,
                'handle': self,
            }
            if self._source_traceback:
                context['source_traceback'] = self._source_traceback
            self._loop.call_exception_handler(context)
        self = None

    if sys.version_info >= (3, 7, 0):
        from asyncio import format_helpers
        asyncio.events.Handle._run = run
