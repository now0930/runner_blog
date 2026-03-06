import os
import asyncio
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
import gpxpy
import requests
from requests import post
from dotenv import load_dotenv
import logging
from google import genai

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
            logger.error("CHAT_ID not found in environment variables.")
            raise ValueError("CHAT_ID is required for event handling")

        self.WORDPRESS_URL = os.getenv("WORDPRESS_URL")
        self.WORDPRESS_USERNAME = os.getenv("WORDPRESS_USERNAME")
        self.WORDPRESS_PASSWORD = os.getenv("WORDPRESS_PASSWORD")

        if not all([self.WORDPRESS_URL, self.WORDPRESS_USERNAME, self.WORDPRESS_PASSWORD]):
            logger.warning("WordPress credentials not fully set. WordPress publishing will be disabled.")

        logger.info("Configuration loaded successfully.")

class GeminiAnalyzer:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("GEMINI_API_KEY not found in environment variables.")
            raise ValueError("GEMINI_API_KEY is required")
        
        self.client = genai.Client(api_key=self.api_key)

    def analyze_gpx_data(self, gpx_stats):
        """
        Sends GPX statistics to Gemini for analysis.
        """
        if not gpx_stats:
            return "No GPX stats provided for analysis."

        prompt = f"""Analyze these GPX statistics:
Distance: {gpx_stats.get('distance', 'N/A'):.2f} meters
Duration: {gpx_stats.get('duration', 'N/A'):.2f} seconds

Provide a brief, engaging summary of the activity, suitable for a blog post.
If possible, suggest a title for the blog post.
Format the output as JSON: {{"title": "Suggested Title", "summary": "Blog post summary"}}"""
        
        try:
            response = self.client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
            # Attempt to parse the response as JSON
            import json
            analysis_result = json.loads(response.text)
            return analysis_result
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response from Gemini. Raw response: {response.text}")
            return {"title": "GPX Activity Analysis", "summary": response.text} # Fallback to raw text
        except Exception as e:
            logger.error(f"Error analyzing with Gemini: {e}")
            return {"title": "GPX Activity Analysis", "summary": f"An error occurred during analysis: {e}"}

class GpxProcessor:
    def process(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                gpx = gpxpy.parse(f)
            
            total_distance = 0
            total_duration_seconds = 0
            
            for track in gpx.tracks:
                for segment in track.segments:
                    total_distance += segment.length_2d()
                    if len(segment.points) > 1:
                        start_time = segment.points[0].time
                        end_time = segment.points[-1].time
                        if start_time and end_time:
                            total_duration_seconds += (end_time - start_time).total_seconds()
            
            return {"distance": total_distance, "duration": total_duration_seconds}
        except FileNotFoundError:
            logger.error(f"GPX file not found at {file_path}")
            return None
        except gpxpy.gpx.GPXParseException as e:
            logger.error(f"Error parsing GPX file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred processing GPX file {file_path}: {e}")
            return None

class TelegramManager:
    def __init__(self, config: ConfigManager):
        self.config = config
        
        self.client = TelegramClient(
            self.config.TELEGRAM_SESSION_FILE,
            self.config.API_ID,
            self.config.API_HASH
        )
        self.target_chat_id = int(self.config.CHAT_ID) # Ensure it's an integer

    async def connect(self):
        await self.client.start(phone=self.config.PHONE_NUMBER)
        if not await self.client.is_user_authorized():
            logger.error("Telegram client is not authorized. Please check your phone number and session file.")
            # Potentially prompt for code/password here if not handled by client.start logic
        else:
            logger.info("Telegram client connected and authorized.")

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

class WordPressPublisher:
    def __init__(self, config: ConfigManager):
        self.config = config
        if not all([self.config.WORDPRESS_URL, self.config.WORDPRESS_USERNAME, self.config.WORDPRESS_PASSWORD]):
            self.is_enabled = False
            logger.warning("WordPress publishing is disabled due to missing credentials.")
            return
        
        self.is_enabled = True
        self.base_url = self.config.WORDPRESS_URL
        self.username = self.config.WORDPRESS_USERNAME
        self.password = self.config.WORDPRESS_PASSWORD
        self.posts_api_url = f"{self.base_url}/wp-json/wp/v2/posts"
        self.media_api_url = f"{self.base_url}/wp-json/wp/v2/media"

    def _get_auth_headers(self):
        # For WordPress REST API with basic auth, use a tuple for requests
        return (self.username, self.password)

    async def upload_media(self, file_path):
        """
        Uploads a file to WordPress media library and returns its ID and URL.
        """
        if not self.is_enabled:
            logger.warning("WordPress publisher is not enabled. Cannot upload media.")
            return None, None

        file_name = os.path.basename(file_path)
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (file_name, f)}
                # Set Content-Disposition header for WordPress to recognize filename
                headers = {
                    'Content-Disposition': f'attachment; filename="{file_name}"'
                }
                
                logger.info(f"Uploading {file_name} to WordPress media library...")
                response = post(self.media_api_url, auth=self._get_auth_headers(), files=files, headers=headers)
                response.raise_for_status()
                media_data = response.json()
                media_id = media_data.get('id')
                media_url = media_data.get('source')
                logger.info(f"Successfully uploaded media. ID: {media_id}, URL: {media_url}")
                return media_id, media_url
        except FileNotFoundError:
            logger.error(f"Media file not found at {file_path}")
            return None, None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error uploading media to WordPress: {e}")
            if response is not None:
                logger.error(f"WordPress API response: {response.text}")
            return None, None
        except Exception as e:
            logger.error(f"An unexpected error occurred during media upload: {e}")
            return None, None

    def create_post(self, title, content, status='publish', media_id=None):
        """
        Creates a new post on WordPress, optionally associating media.
        """
        if not self.is_enabled:
            logger.warning("WordPress publisher is not enabled. Cannot create post.")
            return None

        payload = {
            'title': title,
            'content': content,
            'status': status,
        }
        if media_id:
            payload['featured_media'] = media_id # Link the media as featured image

        try:
            logger.info(f"Creating WordPress post: '{title}'")
            response = post(self.posts_api_url, auth=self._get_auth_headers(), json=payload)
            response.raise_for_status()
            post_data = response.json()
            logger.info(f"Successfully created WordPress post: {post_data.get('link', 'N/A')}")
            return post_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating WordPress post: {e}")
            if response is not None:
                logger.error(f"WordPress API response: {response.text}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during post creation: {e}")
            return None

# Global instances (for simplicity in event handler access)
# These will be initialized in main() and passed implicitly or accessed via closure.
_config = None
_telegram_manager = None
_gpx_processor = None
_gemini_analyzer = None
_wordpress_publisher = None
_target_chat = None

# Event handler for new messages
async def handle_new_message(event):
    message = event.message
    logger.debug(f"Received message from chat ID: {message.chat_id}")

    # Ensure the message is from the target chat and contains a document
    if message.chat_id == int(_config.target_chat_id) and message.document:
        logger.info(f"Processing message with document from chat {_config.CHAT_ID}.")
        
        gpx_file_path = await _telegram_manager.download_gpx_file(message)
        
        if gpx_file_path:
            logger.info(f"GPX file downloaded to: {gpx_file_path}")
            
            # Process GPX
            gpx_stats = _gpx_processor.process(gpx_file_path)
            
            if gpx_stats:
                logger.info(f"GPX stats processed: {gpx_stats}")
                
                # Analyze with Gemini
                gemini_analysis = _gemini_analyzer.analyze_gpx_data(gpx_stats)
                
                if gemini_analysis:
                    logger.info(f"Gemini analysis completed. Title: {gemini_analysis.get('title')}")
                    
                    # Upload GPX to WordPress Media Library
                    media_id, media_url = None, None
                    if _wordpress_publisher and _wordpress_publisher.is_enabled:
                        media_id, media_url = await _wordpress_publisher.upload_media(gpx_file_path)
                    else:
                        logger.warning("WordPress publisher not enabled, skipping media upload.")
                    
                    # Prepare content for WordPress post
                    post_title = gemini_analysis.get('title', f"GPX Activity: {os.path.basename(gpx_file_path)}")
                    post_summary = gemini_analysis.get('summary', 'No summary generated.')
                    
                    post_content = f"<h2>Activity Summary</h2>"
                    post_content += f"<p>Distance: {gpx_stats.get('distance', 'N/A'):.2f} meters</p>"
                    post_content += f"<p>Duration: {gpx_stats.get('duration', 'N/A'):.2f} seconds</p>"
                    post_content += f"<h3>Analysis:</h3><p>{post_summary}</p>"
                    
                    if media_url:
                        post_content += f'<p><a href="{media_url}">View GPX File</a></p>'
                    
                    # Create WordPress post
                    if _wordpress_publisher and _wordpress_publisher.is_enabled:
                        _wordpress_publisher.create_post(post_title, post_content, media_id=media_id)
                    else:
                        logger.warning("WordPress publisher not enabled, skipping post creation.")
                else:
                    logger.warning("Gemini analysis failed or returned no data.")
            else:
                logger.warning("Failed to process GPX stats.")
        else:
            logger.warning("Failed to download GPX file.")
    # else:
        # logger.debug("Message ignored: not from target chat or not a document.")

async def main():
    global _config, _telegram_manager, _gpx_processor, _gemini_analyzer, _wordpress_publisher, _target_chat

    _config = ConfigManager()
    
    _telegram_manager = TelegramManager(_config)
    _gpx_processor = GpxProcessor()
    _gemini_analyzer = GeminiAnalyzer()
    _wordpress_publisher = WordPressPublisher(_config)

    await _telegram_manager.connect()

    # Force cache dialogs immediately after connection to ensure server-side chat info is available
    await _telegram_manager.client.get_dialogs()

    # Fetch the chat entity immediately after client is connected
    try:
        chat_id_str = int(_config.CHAT_ID)
        target_chat = await _telegram_manager.client.get_entity(chat_id_str)
        logger.info(f"Successfully fetched chat entity: {target_chat.title} (ID: {target_chat.id})")
        _target_chat = target_chat
    except Exception as e:
        logger.error(f"Error fetching chat entity: {e}. Please ensure the chat ID is correct and accessible.")
        logger.critical("Cannot start bot without valid chat entity. Exiting.")
        return # Exit if the chat entity cannot be found.

    # Register the event handler with the chat entity object
    _telegram_manager.client.add_event_handler(
        handle_new_message,
        events.NewMessage(chats=[_target_chat.id]) # Use the fetched entity object here
    )

    logger.info(f"Bot started. Listening for GPX files in chat ID: {_config.CHAT_ID}")
    
    # Keep the client running to listen for events
    await _telegram_manager.client.run_until_disconnected()
    logger.info("Bot disconnected.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
    except Exception as e:
        logger.critical(f"An unhandled critical error occurred: {e}", exc_info=True)
