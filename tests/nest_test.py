import unittest
import asyncio
import nest_asyncio
nest_asyncio.apply()


def exception_handler(loop, context):
    print('Exception:', context)


class NestTest(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(True)
        self.loop.set_exception_handler(exception_handler)

    def tearDown(self):
        self.loop.stop()
        del self.loop

    async def coro(self):
        await asyncio.sleep(0.01)
        return 42

    async def coro2(self):
        result = self.loop.run_until_complete(self.coro())
        self.assertEqual(result, await self.coro())
        return result

    async def coro3(self):
        result = self.loop.run_until_complete(self.coro2())
        self.assertEqual(result, await self.coro2())
        return result

    def test_nesting(self):
        result = self.loop.run_until_complete(self.coro3())
        self.assertEqual(result, 42)

    async def ensure_future_with_run_until_complete(self):
        task = asyncio.ensure_future(self.coro())
        return self.loop.run_until_complete(task)

    def test_ensure_future_with_run_until_complete(self):
        result = self.loop.run_until_complete(
            self.ensure_future_with_run_until_complete())
        self.assertEqual(result, 42)

    async def ensure_future_with_run_until_complete_with_wait(self):
        task = asyncio.ensure_future(self.coro())
        done, pending = self.loop.run_until_complete(
            asyncio.wait([task], return_when=asyncio.ALL_COMPLETED))
        task = done.pop()
        return task.result()

    def test_ensure_future_with_run_until_complete_with_wait(self):
        result = self.loop.run_until_complete(
            self.ensure_future_with_run_until_complete_with_wait())
        self.assertEqual(result, 42)


if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        pass
