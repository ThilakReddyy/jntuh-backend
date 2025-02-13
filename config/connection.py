from prisma import Prisma
from utils.logger import database_logger


class PrismaConnection:
    def __init__(self):
        self.prisma = Prisma()

    async def connect(self):
        await self.prisma.connect()
        database_logger.info("Database Connected!!")

    async def disconnect(self):
        await self.prisma.disconnect()
        database_logger.info("Database disConnected!!")


prismaConnection = PrismaConnection()
