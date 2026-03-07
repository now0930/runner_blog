import asyncio
import logging
import os
import time
import requests
from telethon import events
from config import ConfigManager
from analyzer import create_analyzer
from processor import GpxProcessor
from telegram_bot import TelegramManager
from wordpress import WordPressPublisher

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances (for simplicity in event handler access)
# These will be initialized in main() and passed implicitly or accessed via closure.
_config = None
_telegram_manager = None
_gpx_processor = None
_gemini_analyzer = None
_wordpress_publisher = None
_target_chat = None
_analyzer = None

# Event handler for new messages
async def handle_new_message(event):
    message = event.message
    # 모든 메시지를 받되, 우리가 원하는 CHAT_ID 가 아니면 즉시 무시
    if message.chat_id != int(_config.CHAT_ID):
        return
    
    if not message.document:
        return

    logger.info(f"Processing GPX from target chat: {message.chat_id}")
    
    gpx_file_path = await _telegram_manager.download_gpx_file(message)
    
    if gpx_file_path:
        logger.info(f"GPX file downloaded to: {gpx_file_path}")
        
        # Process GPX
        gpx_stats = _gpx_processor.process(gpx_file_path)
        
        if gpx_stats:
            logger.info(f"GPX stats processed: {gpx_stats}")
            
            # Analyze with analyzer (using factory-created instance)
            if _analyzer:
                gemini_analysis = _analyzer.analyze_gpx_data(gpx_stats)
                
                if gemini_analysis:
                    logger.info(f"Analyzer completed. Title: {gemini_analysis.get('title')}")
                    
                    # Upload GPX to WordPress Media Library
                    media_id, media_url, source_url = None, None, None
                    if _wordpress_publisher and _wordpress_publisher.is_enabled:
                        media_id, media_url, source_url = await _wordpress_publisher.upload_media(gpx_file_path)
                    else:
                        logger.warning("WordPress publisher not enabled, skipping media upload.")
                    
                    # Copy file to expected local path to avoid WP media library renaming issues
                    # Target path: /var/www/html/wordpress/wp-content/uploads/gpx/{filename}
                    file_name = os.path.basename(gpx_file_path)
                    target_path = f"/var/www/html/wordpress/wp-content/uploads/gpx/{file_name}"
                    
                    if _wordpress_publisher and _wordpress_publisher.is_enabled:
                        _wordpress_publisher.copy_file_to_expected_location(gpx_file_path, target_path)
                    
                    # 파일 생성 확인 대기 루프
                    for i in range(3):
                        if os.path.exists(target_path):
                            logger.info("File confirmed on disk.")
                            break
                        time.sleep(1)
                    else:
                        logger.warning("File check timed out, proceeding anyway.")
                    
                    # Prepare content for WordPress post WITHOUT shortcode
                    post_title = gemini_analysis.get('title', f"GPX Activity: {file_name}")
                    post_summary = gemini_analysis.get('summary', 'No summary generated.')
                    
                    post_content = f"<h2>Activity Summary</h2>"
                    post_content += f"<p>Distance: {gpx_stats.get('distance', 'N/A'):.2f} meters</p>"
                    post_content += f"<p>Duration: {gpx_stats.get('duration', 'N/A'):.2f} seconds</p>"
                    post_content += f"<h3>Analysis:</h3><p>{post_summary}</p>"
                    
                    # Create WordPress post WITHOUT shortcode
                    if _wordpress_publisher and _wordpress_publisher.is_enabled:
                        post_data = _wordpress_publisher.create_post(post_title, post_content, media_id=media_id)
                        
                        if post_data:
                            post_id = post_data.get('id')
                            if post_id:
                                # Prepare content with shortcode
                                shortcode_path = f"/wp-content/uploads/gpx/{file_name}"
                                shortcode = f'[sgpx gpx="{shortcode_path}"]'
                                
                                post_content_with_shortcode = f"<h2>Activity Summary</h2>"
                                post_content_with_shortcode += f"<p>Distance: {gpx_stats.get('distance', 'N/A'):.2f} meters</p>"
                                post_content_with_shortcode += f"<p>Duration: {gpx_stats.get('duration', 'N/A'):.2f} seconds</p>"
                                post_content_with_shortcode += f"<h3>Analysis:</h3><p>{post_summary}</p>"
                                post_content_with_shortcode += f'<p>{shortcode}</p>'
                                
                                # Update post content with shortcode
                                try:
                                    update_url = f"{_wordpress_publisher.base_url.rstrip('/')}/wp-json/wp/v2/posts/{post_id}"
                                    update_response = requests.patch(update_url, auth=_wordpress_publisher._get_auth_headers(), json={'content': post_content_with_shortcode})
                                    if update_response.status_code == 200:
                                        logger.info(f"Successfully updated post {post_id} with shortcode.")
                                    else:
                                        logger.error(f"Failed to update post {post_id}: {update_response.text}")
                                except Exception as e:
                                    logger.error(f"Error updating post {post_id}: {e}")
                            else:
                                logger.warning("No post ID returned from create_post.")
                        else:
                            logger.warning("Failed to create post.")
                    else:
                        logger.warning("WordPress publisher not enabled, skipping post creation.")
                else:
                    logger.warning("Analyzer failed or returned no data.")
            else:
                logger.warning("No analyzer available. Skipping analysis.")
        else:
            logger.warning("Failed to process GPX stats.")
    else:
        logger.warning("Failed to download GPX file.")

async def main():
    global _config, _telegram_manager, _gpx_processor, _analyzer, _wordpress_publisher, _target_chat

    _config = ConfigManager()
    
    _telegram_manager = TelegramManager(_config)
    _gpx_processor = GpxProcessor()
    _analyzer = create_analyzer(_config)
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

    # Register the event handler without chats parameter to avoid ValueError
    _telegram_manager.client.add_event_handler(
        handle_new_message,
        events.NewMessage()
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
