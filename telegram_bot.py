from telethon import TelegramClient
import logging
import os

logger = logging.getLogger(__name__)

class TelegramManager:
    def __init__(self, config):
        self.config = config
        
        self.client = TelegramClient(
            self.config.TELEGRAM_SESSION_FILE,
            self.config.API_ID,
            self.config.API_HASH
        )
        self.target_chat_id = int(self.config.CHAT_ID) # Ensure it's an integer

    async def connect(self):
        # 1. Establish connection to Telegram servers
        await self.client.connect()

        # 2. Check if the session is already authorized
        if await self.client.is_user_authorized():
            logger.info("Telegram client connected and already authorized.")
        else:
            # 3. Only start the auth flow if not authorized
            logger.info("Telegram client not authorized. Starting auth flow...")
            await self.client.start(phone=self.config.PHONE_NUMBER)
            logger.info("Telegram client authorized successfully.")

    async def download_gpx_file(self, message):
        if not message.document:
            logger.warning("No document found in message.")
            return None
        
        # Check if it's a GPX file
        if message.document.mime_type not in ('application/gpx+xml', 'application/xml') and not message.document.attributes[0].file_name.lower().endswith('.gpx'):
            logger.warning(f"Skipping non-GPX file: {message.document.attributes[0].file_name}")
            return None

        file_name = message.document.attributes[0].file_name
        file_path = os.path.join(self.config.DOWNLOADS_DIR, file_name)
        
        try:
            logger.info(f"Downloading {file_name} to {self.config.DOWNLOADS_DIR}.")
            await message.download_media(file=file_path)
            logger.info(f"Successfully downloaded {file_name}.")
            return file_path
        except Exception as e:
            logger.error(f"Failed to download file {file_name}: {e}")
            return None
