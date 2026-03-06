import os
import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
import gpxpy
import requests
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self):
        # API credentials from environment variables
        self.API_ID = os.getenv("API_ID")
        self.API_HASH = os.getenv("API_HASH")
        self.PHONE_NUMBER = os.getenv("PHONE_NUMBER")

        # Directories for persistence, defaulting to /app paths for Docker context.
        # These will be mapped to host volumes by docker-compose.
        self.DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", "/app/downloads")
        self.SESSION_DIR = os.getenv("SESSION_DIR", "/app/session")

        # Ensure these directories exist, both for Docker and local runs.
        os.makedirs(self.DOWNLOADS_DIR, exist_ok=True)
        os.makedirs(self.SESSION_DIR, exist_ok=True)

        # Define the full path for the Telethon session file.
        self.TELEGRAM_SESSION_FILE = os.path.join(self.SESSION_DIR, "telegram.session")

        print("Hey! Configuration loaded.") # For initial debugging

class GpxProcessor:
    def process(self, file_path):
        try:
            with open(file_path, 'r') as f:
                gpx = gpxpy.parse(f)
            
            total_distance = 0
            total_duration = 0
            
            for track in gpx.tracks:
                for segment in track.segments:
                    total_distance += segment.length_2d()
                    if len(segment.points) > 1:
                        start_time = segment.points[0].time
                        end_time = segment.points[-1].time
                        if start_time and end_time:
                            total_duration += (end_time - start_time).total_seconds()
            
            return {"distance": total_distance, "duration": total_duration}
        except Exception as e:
            logger.error(f"Error processing GPX file: {e}")
            return None

class TelegramManager:
    def __init__(self, config: ConfigManager, download_dir: str, session_file: str):
        self.config = config
        self.download_dir = download_dir
        self.session_file = session_file # Store the session file path

        # Initialize the Telegram client with the session file path
        self.client = TelegramClient(
            self.session_file,
            self.config.API_ID,
            self.config.API_HASH
        )

    async def connect(self):
        await self.client.start(phone=self.config.PHONE_NUMBER)
        print("Hey! Connected to Telegram.")

    async def get_messages(self, chat_name, limit=10):
        try:
            # Get the chat entity
            chat = await self.client.get_entity(chat_name)
            # Fetch messages
            messages = await self.client.get_messages(chat, limit=limit)
            return messages
        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
            return []

    async def download_gpx_file(self, message):
        try:
            # Check if the message has a document
            if message.document:
                file_name = message.document.attributes[0].file_name
                if file_name.endswith('.gpx'):
                    # Download the file
                    file_path = os.path.join(self.download_dir, file_name)
                    await self.client.download_media(message, file_path)
                    print(f"Hey! Downloaded GPX file: {file_path}")
                    return file_path
            return None
        except Exception as e:
            logger.error(f"Error downloading GPX file: {e}")
            return None

async def main():
    config = ConfigManager()
    
    # Get chat name from environment variable or use default
    chat_name = os.getenv("CHAT_NAME", "your_chat_name")
    
    telegram_manager = TelegramManager(config, config.DOWNLOADS_DIR, config.TELEGRAM_SESSION_FILE)
    gpx_processor = GpxProcessor() # Instantiate the processor

    await telegram_manager.connect()

    # Example: Get messages from a specific chat
    messages = await telegram_manager.get_messages(chat_name, limit=5)

    for message in messages:
        file_path = await telegram_manager.download_gpx_file(message)
        if file_path:
            stats = gpx_processor.process(file_path) # Use the processor
            if stats:
                print(f"Processed {file_path}: {stats}")

if __name__ == "__main__":
    asyncio.run(main())
