import unittest
import asyncio
import nest_asyncio


def exception_handler(loop, context):
    print('Exception:', context)


class NestTest(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        nest_asyncio.apply(self.loop)
        asyncio.set_event_loop(self.loop)
        self.loop.set_debug(True)
        self.loop.set_exception_handler(exception_handler)

    def tearDown(self):
        self.loop.close()
        del self.loop

    async def coro(self):
        await asyncio.sleep(0.01)
        return 42

    def test_nesting(self):

        async def f1():
            result = self.loop.run_until_complete(self.coro())
            self.assertEqual(result, await self.coro())
            return result

        async def f2():
            result = self.loop.run_until_complete(f1())
            self.assertEqual(result, await f1())
            return result

        result = self.loop.run_until_complete(f2())
        self.assertEqual(result, 42)

    def test_ensure_future_with_run_until_complete(self):

        async def f():
            task = asyncio.ensure_future(self.coro())
            return self.loop.run_until_complete(task)

        result = self.loop.run_until_complete(f())
        self.assertEqual(result, 42)

    def test_ensure_future_with_run_until_complete_with_wait(self):

        async def f():
            task = asyncio.ensure_future(self.coro())
            done, pending = self.loop.run_until_complete(
                asyncio.wait([task], return_when=asyncio.ALL_COMPLETED))
            task = done.pop()
            return task.result()

        result = self.loop.run_until_complete(f())
        self.assertEqual(result, 42)

    def test_timeout(self):

        async def f1():
            await asyncio.sleep(0.1)

        async def f2():
            asyncio.run(asyncio.wait_for(f1(), 0.01))

        with self.assertRaises(asyncio.TimeoutError):
            self.loop.run_until_complete(f2())

    def _test_two_run_until_completes_in_one_outer_loop(self):

        async def f1():
            self.loop.run_until_complete(asyncio.sleep(0.02))
            return 4

        async def f2():
            self.loop.run_until_complete(asyncio.sleep(0.01))
            return 2

        result = self.loop.run_until_complete(
            asyncio.gather(f1(), f2()))
        self.assertEqual(result, [4, 2])


if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        pass
