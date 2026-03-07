import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self):
        self.API_ID = os.getenv("API_ID")
        self.API_HASH = os.getenv("API_HASH")
        self.PHONE_NUMBER = os.getenv("PHONE_NUMBER")
        self.DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", "/app/downloads")
        self.SESSION_DIR = os.getenv("SESSION_DIR", "/app/session")
        os.makedirs(self.DOWNLOADS_DIR, exist_ok=True)
        os.makedirs(self.SESSION_DIR, exist_ok=True)
        self.TELEGRAM_SESSION_FILE = os.path.join(self.SESSION_DIR, "telegram.session")
        self.CHAT_ID = os.getenv("CHAT_ID")
        if not self.CHAT_ID:
            raise ValueError("CHAT_ID is required")
        self.WORDPRESS_URL = os.getenv("WORDPRESS_URL")
        self.WORDPRESS_USERNAME = os.getenv("WORDPRESS_USERNAME")
        self.WORDPRESS_PASSWORD = os.getenv("WORDPRESS_PASSWORD")
        self.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
