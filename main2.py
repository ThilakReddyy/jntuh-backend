from messaging.consumer import consume_messages
import asyncio


async def main():
    await consume_messages()


asyncio.run(main())

