import requests
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class WordPressPublisher:
    def __init__(self, config):
        self.config = config
        
        # Debug: Check each WordPress credential individually
        self.is_enabled = True
        self.base_url = self.config.WORDPRESS_URL
        self.username = self.config.WORDPRESS_USERNAME
        self.password = self.config.WORDPRESS_PASSWORD
        
        # Safely construct API URLs with rstrip to handle trailing slashes
        self.posts_api_url = f"{self.base_url.rstrip('/')}/wp-json/wp/v2/posts"
        self.media_api_url = f"{self.base_url.rstrip('/')}/wp-json/wp/v2/media"

        # Debug logging for WordPressPublisher initialization
        if not self.config.WORDPRESS_URL:
            logger.error("WordPressPublisher: WORDPRESS_URL is None or empty.")
            self.is_enabled = False
        elif not self.config.WORDPRESS_USERNAME:
            logger.error("WordPressPublisher: WORDPRESS_USERNAME is None or empty.")
            self.is_enabled = False
        elif not self.config.WORDPRESS_PASSWORD:
            logger.error("WordPressPublisher: WORDPRESS_PASSWORD is None or empty.")
            self.is_enabled = False
        else:
            logger.info(f"WordPressPublisher initialized successfully. Base URL: {self.base_url}")

        if not self.is_enabled:
            logger.warning("WordPress publishing is disabled due to missing credentials.")
            return
        
        logger.info("WordPressPublisher is enabled and ready.")

    def _get_auth_headers(self):
        # For WordPress REST API with basic auth, use a tuple for requests
        return (self.username, self.password)

    def get_relative_path(self, media_url):
        """Extracts wp-content/uploads/... path from full URL."""
        parsed = urlparse(media_url)
        path = parsed.path.lstrip('/')
        if 'wp-content/uploads' in path:
            return path[path.find('wp-content/uploads'):]
        return path

    def get_gpx_shortcode_path(self, file_path):
        """
        Converts a local file path to a WordPress relative path for the [sgpx] shortcode.
        """
        file_name = os.path.basename(file_path)
        return f"/wp-content/uploads/gpx/{file_name}"

    def get_gpx_shortcode_url(self, media_url):
        """
        Extracts the full URL from the media upload response for the [sgpx] shortcode.
        """
        if media_url:
            return media_url
        return None

    async def upload_media(self, file_path):
        """
        Uploads a file to WordPress media library and returns its ID and URL.
        Returns: (media_id, media_url, source_url)
        """
        if not self.is_enabled:
            logger.warning("WordPress publisher is not enabled. Cannot upload media.")
            return None, None, None

        file_name = os.path.basename(file_path)
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (file_name, f)}
                # Set Content-Disposition header for WordPress to recognize filename
                headers = {
                    'Content-Disposition': f'attachment; filename="{file_name}"'
                }
                
                logger.info(f"Uploading {file_name} to WordPress media library...")
                response = requests.post(self.media_api_url, auth=self._get_auth_headers(), files=files, headers=headers)
                response.raise_for_status()
                media_data = response.json()
                media_id = media_data.get('id')
                media_url = media_data.get('source_url')
                source_url = media_data.get('source_url')
                logger.info(f"Successfully uploaded media. ID: {media_id}, URL: {media_url}")
                return media_id, media_url, source_url
        except FileNotFoundError:
            logger.error(f"Media file not found at {file_path}")
            return None, None, None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error uploading media to WordPress: {e}")
            if 'response' in locals() and response is not None:
                logger.error(f"WordPress API response: {response.text}")
            return None, None, None
        except Exception as e:
            logger.error(f"An unexpected error occurred during media upload: {e}")
            return None, None, None

    def copy_file_to_expected_location(self, source_path, target_path):
        """
        Copies the uploaded file to the expected location if it doesn't exist there.
        Adjusts permissions if needed.
        """
        try:
            if not os.path.exists(target_path):
                logger.info(f"Copying file from {source_path} to {target_path}")
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(source_path, 'rb') as src:
                    with open(target_path, 'wb') as dst:
                        dst.write(src.read())
                
                # Adjust permissions (readable by web server)
                os.chmod(target_path, 0o644)
                logger.info(f"File copied and permissions adjusted: {target_path}")
                return True
            else:
                logger.info(f"File already exists at {target_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to copy file to expected location: {e}")
            return False

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
            "categories": [1792]  # 여기서 카테고리를 지정합니다
        }
        if media_id:
            payload['featured_media'] = media_id # Link the media as featured image

        try:
            logger.info(f"Creating WordPress post: '{title}'")
            response = requests.post(self.posts_api_url, auth=self._get_auth_headers(), json=payload)
            
            # Log response text if not successful (201 Created)
            if response.status_code != 201:
                logger.error(f"WordPress API error (Status {response.status_code}): {response.text}")
            
            response.raise_for_status()
            post_data = response.json()
            logger.info(f"Successfully created WordPress post: {post_data.get('link', 'N/A')}")
            return post_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating WordPress post: {e}")
            if 'response' in locals() and response is not None:
                logger.error(f"WordPress API response: {response.text}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during post creation: {e}")
            return None
