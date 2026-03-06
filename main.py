import os
import asyncio
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
import gpxpy
import requests
from dotenv import load_dotenv
import logging
import google.generativeai as genai

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
        
        # Chat ID to listen to
        self.CHAT_ID = os.getenv("CHAT_ID")
        if not self.CHAT_ID:
            logger.error("CHAT_ID not found in environment variables.")
            raise ValueError("CHAT_ID is required for event handling")

        print("Hey! Configuration loaded.") # For initial debugging

class GeminiAnalyzer:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("GEMINI_API_KEY not found in environment variables.")
            raise ValueError("GEMINI_API_KEY is required")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-pro')

    def analyze_gpx_data(self, gpx_stats):
        """
        Sends GPX statistics to Gemini for analysis.
        """
        prompt = f"Analyze these GPX statistics: {gpx_stats}. Provide a brief summary of the activity."
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error analyzing with Gemini: {e}")
            return None

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
        self.chat_id = config.CHAT_ID # Store the chat_id

        # Initialize the Telegram client with the session file path
        self.client = TelegramClient(
            self.session_file,
            self.config.API_ID,
            self.config.API_HASH
        )

    async def connect(self):
        await self.client.start(phone=self.config.PHONE_NUMBER)
        print("Hey! Connected to Telegram.")

class WordPressPublisher:
    def __init__(self, wordpress_url, username, password):
        self.base_url = wordpress_url
        self.username = username
        self.password = password
        self.api_url = f"{self.base_url}/wp-json/wp/v2/posts"

    def create_post(self, title, content, status='publish'):
        """
        Creates a new post on WordPress.
        """
        auth = (self.username, self.password)
        payload = {
            'title': title,
            'content': content,
            'status': status,
        }
        try:
            response = requests.post(self.api_url, auth=auth, json=payload)
            response.raise_for_status()  # Raise an exception for bad status codes
            post_data = response.json()
            logger.info(f"Successfully created WordPress post: {post_data['link']}")
            return post_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating WordPress post: {e}")
            return None

async def main():
    config = ConfigManager()
    
    telegram_manager = TelegramManager(config, config.DOWNLOADS_DIR, config.TELEGRAM_SESSION_FILE)
    gpx_processor = GpxProcessor()
    gemini_analyzer = GeminiAnalyzer()
    
    # Fetch WordPress credentials from environment variables
    wp_url = os.getenv("WORDPRESS_URL")
    wp_username = os.getenv("WORDPRESS_USERNAME")
    wp_password = os.getenv("WORDPRESS_PASSWORD")

    if not all([wp_url, wp_username, wp_password]):
        logger.error("WordPress credentials (WORDPRESS_URL, WORDPRESS_USERNAME, WORDPRESS_PASSWORD) are required.")
        return # Exit if WordPress credentials are missing

    wordpress_publisher = WordPressPublisher(wp_url, wp_username, wp_password)

    await telegram_manager.connect()

    # Define the event handler function
    async def message_handler(event):
        message = event.message
        
        # Check if the message is from the correct chat and contains a document
        if message.chat_id == int(config.CHAT_ID) and message.document:
            # Check if the document is a GPX file
            if message.document.mime_type == 'application/gpx+xml':
                file_path = await telegram_manager.download_gpx_file(message)
                if file_path:
                    stats = gpx_processor.process(file_path)
                    if stats:
                        print(f"Processed {file_path}: {stats}")
                        
                        analysis = gemini_analyzer.analyze_gpx_data(stats)
                        if analysis:
                            print(f"Gemini Analysis: {analysis}")

                            # Prepare content for WordPress post
                            post_title = f"GPX Activity: {os.path.basename(file_path)}"
                            post_content = f"<h2>Activity Summary</h2>"
                            post_content += f"<p>Distance: {stats.get('distance', 'N/A'):.2f} meters</p>"
                            post_content += f"<p>Duration: {stats.get('duration', 'N/A'):.2f} seconds</p>"
                            post_content += f"<h3>Gemini Analysis:</h3><p>{analysis}</p>"
                            
                            # TODO: Implement logic to upload GPX file to a media server and get its URL
                            # For now, we'll just post the text analysis.
                            # If you upload the file, you'd get a URL like:
                            # gpx_file_url = await upload_gpx_to_media_server(file_path) 
                            # post_content += f'<p><a href="{gpx_file_url}">Download GPX</a></p>'
                            
                            if wordpress_publisher:
                                wordpress_publisher.create_post(post_title, post_content)
                            else:
                                print("Skipping WordPress post: Publisher not initialized due to missing credentials.")
                    else:
                        print("Skipping message: Failed to process GPX file.")
                else:
                    print("Skipping message: Failed to download GPX file.")
            else:
                print("Skipping message: Not a GPX file.")
        else:
            print("Skipping message: Not from target chat or no document.")

    # Register the event handler
    telegram_manager.client.add_event_handler(message_handler, events.NewMessage(chats=[config.CHAT_ID]))

    print(f"Bot started. Listening for GPX files in chat ID: {config.CHAT_ID}")
    # Keep the client running to listen for events
    await telegram_manager.client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
