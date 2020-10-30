import asyncio
import exception_group

async def t1():
    await asyncio.sleep(0.5)
    1 / 0

async def t2():
    async with asyncio.TaskGroup() as tg:
        tg.create_task(t21())
        tg.create_task(t22())

async def t21():
    await asyncio.sleep(0.3)
    raise ValueError

async def t22():
    await asyncio.sleep(0.7)
    raise TypeError

async def main():
    async with asyncio.TaskGroup() as tg:
        tg.create_task(t1())
        tg.create_task(t2())


def run(*args):
    try:
        asyncio.run(*args)
    except exception_group.ExceptionGroup as e:
        print('============')
        exception_group.ExceptionGroup.render(e)
        print('^^^^^^^^^^^^')
        raise


run(main())
