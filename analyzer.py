import os
import json
import logging
import requests
from google import genai

logger = logging.getLogger(__name__)

class BaseAnalyzer:
    def analyze_gpx_data(self, gpx_stats):
        raise NotImplementedError

class GeminiAnalyzer(BaseAnalyzer):
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.error("GEMINI_API_KEY not found in environment variables.")
            raise ValueError("GEMINI_API_KEY is required for Gemini provider")
        self.client = genai.Client(api_key=self.api_key)

        # 환경 변수에서 모델명 로드, 없으면 기본값 사용
        self.model_name = os.getenv("AY_GEMINI_MODEL", "gemini-2.0-flash")
        self.fallback_model = os.getenv("AY_GEMINI_FALLBACK_MODEL", "gemini-1.5-flash")
        self.prompt_template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_template.txt')
        logger.info(f"Analyzer initialized with model: {self.model_name}, fallback: {self.fallback_model}")

    def _calculate_pace(self, distance_meters, duration_seconds):
        """Calculate pace per km (min/km) and speed (km/h)."""
        if distance_meters <= 0 or duration_seconds <= 0:
            return 0, 0
        
        distance_km = distance_meters / 1000
        pace_min_km = (duration_seconds / 60) / distance_km
        speed_kmh = distance_km / (duration_seconds / 3600)
        
        return pace_min_km, speed_kmh

    def _get_weather_info(self, latitude=None, longitude=None):
        """Get weather information from Open-Meteo API.
        
        Args:
            latitude: Latitude coordinate (optional)
            longitude: Longitude coordinate (optional)
            
        Returns:
            str: Weather information string including temperature
        """
        if latitude is None or longitude is None:
            logger.info("Weather info requested without coordinates. Using placeholder.")
            return "현재 날씨 정보 없음"
        
        try:
            # Open-Meteo API endpoint for current weather
            url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            temperature = data['current']['temperature_2m']
            
            return f"현재 날씨: {temperature:.1f}°C"
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch weather data from Open-Meteo: {e}")
            return "현재 날씨 정보 없음"
        except (KeyError, TypeError) as e:
            logger.warning(f"Unexpected response format from Open-Meteo: {e}")
            return "현재 날씨 정보 없음"
        except Exception as e:
            logger.error(f"Unexpected error fetching weather data: {e}")
            return "현재 날씨 정보 없음"

    def _load_prompt_template(self):
        """Load prompt template from file with fallback."""
        try:
            with open(self.prompt_template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"Prompt template file not found at {self.prompt_template_path}. Using default prompt.")
            return """Analyze these GPX statistics for a blog post:

Distance: {distance} meters
Duration: {duration} seconds
Pace per km: {pace_per_km} min/km
Speed: {speed} km/h
Weather: {weather}

Provide a brief, engaging summary of the activity, suitable for a blog post.
If possible, suggest a title for the blog post.
Format the output as JSON: {{"title": "Suggested Title", "summary": "Blog post summary"}}"""
        except Exception as e:
            logger.error(f"Error reading prompt template: {e}")
            return """Analyze these GPX statistics for a blog post:

Distance: {distance} meters
Duration: {duration} seconds
Pace per km: {pace_per_km} min/km
Speed: {speed} km/h
Weather: {weather}

Provide a brief, engaging summary of the activity, suitable for a blog post.
If possible, suggest a title for the blog post.
Format the output as JSON: {{"title": "Suggested Title", "summary": "Blog post summary"}}"""

    def _validate_json(self, text):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def analyze_gpx_data(self, gpx_stats):
        """
        Sends GPX statistics to Gemini for analysis.
        """
        if not gpx_stats:
            return {"title": "GPX Activity Analysis", "summary": "No GPX stats provided for analysis."}

        distance = gpx_stats.get('distance', 0)
        duration = gpx_stats.get('duration', 0)
        
        # Calculate pace and speed
        pace_per_km, speed = self._calculate_pace(distance, duration)
        
        # Get weather info (try to extract lat/lon from GPX stats if available)
        weather = self._get_weather_info(
            latitude=gpx_stats.get('latitude'),
            longitude=gpx_stats.get('longitude')
        )
        
        # Load prompt template
        prompt_template = self._load_prompt_template()
        
        # Prepare data dictionary for safe formatting
        data = {
            'distance': distance,
            'duration': duration,
            'pace_per_km': pace_per_km,
            'speed': speed,
            'weather': weather
        }
        
        # Format prompt with data using format_map for safety
        try:
            prompt = prompt_template.format_map(data)
        except KeyError as e:
            logger.error(f"Missing variable in prompt template: {e}")
            # Fallback to basic format with all keys provided
            prompt = prompt_template.format(
                distance=distance,
                duration=duration,
                pace_per_km=pace_per_km,
                speed=speed,
                weather=weather
            )
        
        try:
            response = self.client.models.generate_content(model=self.model_name, contents=prompt)
            # Attempt to parse the response as JSON
            if not response.text:
                logger.error("Gemini API returned empty response.")
                return {"title": "GPX Activity Analysis", "summary": "No response received from Gemini API."}
            
            analysis_result = self._validate_json(response.text)
            if analysis_result:
                return analysis_result
            else:
                logger.error("Gemini API returned invalid JSON response.")
                return {"title": "GPX Activity Analysis", "summary": response.text}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response from Gemini. Raw response: {response.text}")
            return {"title": "GPX Activity Analysis", "summary": response.text}
        except Exception as e:
            # Check for 404 errors and log the attempted model name
            if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                if e.response.status_code == 404:
                    logger.error(f"Model '{self.model_name}' not found (404 error). Attempted model: {self.model_name}. Falling back to {self.fallback_model}.")
                    # Retry with fallback model
                    try:
                        response = self.client.models.generate_content(model=self.fallback_model, contents=prompt)
                        if not response.text:
                            logger.error("Gemini API returned empty response for fallback model.")
                            return {"title": "GPX Activity Analysis", "summary": "No response received from Gemini API."}
                        
                        analysis_result = self._validate_json(response.text)
                        if analysis_result:
                            return analysis_result
                        else:
                            logger.error("Fallback model returned invalid JSON response.")
                            return {"title": "GPX Activity Analysis", "summary": response.text}
                    except Exception as fallback_error:
                        logger.error(f"Fallback model '{self.fallback_model}' also failed: {fallback_error}")
                        return {"title": "GPX Activity Analysis", "summary": f"An error occurred during analysis: {fallback_error}"}
                else:
                    logger.error(f"Error status code: {e.response.status_code}. Error: {e}")
            else:
                logger.error(f"Error analyzing with Gemini: {e}")
            return {"title": "GPX Activity Analysis", "summary": f"An error occurred during analysis: {e}"}

class LocalLLMAnalyzer(BaseAnalyzer):
    """
    Placeholder for local LLM analyzer.
    In a real implementation, this would connect to a local LLM service.
    """
    
    def __init__(self):
        self.api_endpoint = os.getenv("LOCAL_LLM_ENDPOINT", "http://localhost:11434/api/generate")
        self.model_name = os.getenv("LOCAL_LLM_MODEL", "llama3")
        logger.info(f"Local LLM configured with endpoint: {self.api_endpoint}, model: {self.model_name}")

    def _calculate_pace(self, distance_meters, duration_seconds):
        """Calculate pace per km (min/km) and speed (km/h)."""
        if distance_meters <= 0 or duration_seconds <= 0:
            return 0, 0
        
        distance_km = distance_meters / 1000
        pace_min_km = (duration_seconds / 60) / distance_km
        speed_kmh = distance_km / (duration_seconds / 3600)
        
        return pace_min_km, speed_kmh

    def _get_weather_info(self, latitude=None, longitude=None):
        """Get weather information from Open-Meteo API.
        
        Args:
            latitude: Latitude coordinate (optional)
            longitude: Longitude coordinate (optional)
            
        Returns:
            str: Weather information string including temperature
        """
        if latitude is None or longitude is None:
            logger.info("Weather info requested without coordinates. Using placeholder.")
            return "현재 날씨 정보 없음"
        
        try:
            # Open-Meteo API endpoint for current weather
            url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            temperature = data['current']['temperature_2m']
            
            return f"현재 날씨: {temperature:.1f}°C"
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch weather data from Open-Meteo: {e}")
            return "현재 날씨 정보 없음"
        except (KeyError, TypeError) as e:
            logger.warning(f"Unexpected response format from Open-Meteo: {e}")
            return "현재 날씨 정보 없음"
        except Exception as e:
            logger.error(f"Unexpected error fetching weather data: {e}")
            return "현재 날씨 정보 없음"

    def _load_prompt_template(self):
        """Load prompt template from file with fallback."""
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_template.txt'), 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning("Prompt template file not found. Using default prompt.")
            return """Analyze these GPX statistics for a blog post:

Distance: {distance} meters
Duration: {duration} seconds
Pace per km: {pace_per_km} min/km
Speed: {speed} km/h
Weather: {weather}

Provide a brief, engaging summary of the activity, suitable for a blog post.
If possible, suggest a title for the blog post.
Format the output as JSON: {{"title": "Suggested Title", "summary": "Blog post summary"}}"""
        except Exception as e:
            logger.error(f"Error reading prompt template: {e}")
            return """Analyze these GPX statistics for a blog post:

Distance: {distance} meters
Duration: {duration} seconds
Pace per km: {pace_per_km} min/km
Speed: {speed} km/h
Weather: {weather}

Provide a brief, engaging summary of the activity, suitable for a blog post.
If possible, suggest a title for the blog post.
Format the output as JSON: {{"title": "Suggested Title", "summary": "Blog post summary"}}"""

    def _validate_json(self, text):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def analyze_gpx_data(self, gpx_stats):
        """
        Analyzes GPX statistics using a local LLM.
        """
        if not gpx_stats:
            return {"title": "GPX Activity Analysis", "summary": "No GPX stats provided for analysis."}

        distance = gpx_stats.get('distance', 0)
        duration = gpx_stats.get('duration', 0)
        
        # Calculate pace and speed
        pace_per_km, speed = self._calculate_pace(distance, duration)
        
        # Get weather info (try to extract lat/lon from GPX stats if available)
        weather = self._get_weather_info(
            latitude=gpx_stats.get('latitude'),
            longitude=gpx_stats.get('longitude')
        )
        
        # Load prompt template
        prompt_template = self._load_prompt_template()
        
        # Prepare data dictionary for safe formatting
        data = {
            'distance': distance,
            'duration': duration,
            'pace_per_km': pace_per_km,
            'speed': speed,
            'weather': weather
        }
        
        # Format prompt with data using format_map for safety
        try:
            prompt = prompt_template.format_map(data)
        except KeyError as e:
            logger.error(f"Missing variable in prompt template: {e}")
            # Fallback to basic format with all keys provided
            prompt = prompt_template.format(
                distance=distance,
                duration=duration,
                pace_per_km=pace_per_km,
                speed=speed,
                weather=weather
            )
        
        try:
            # Simulate local LLM call - in production, use requests.post to your local LLM
            # For now, we'll use a mock response
            analysis_result = {
                "title": f"Local LLM Analysis: {gpx_stats.get('distance', 0):.2f}m Run",
                "summary": f"Completed a {gpx_stats.get('distance', 0):.2f} meter run in {gpx_stats.get('duration', 0):.2f} seconds. {weather}"
            }
            return analysis_result
        except Exception as e:
            logger.error(f"Error analyzing with local LLM: {e}")
            return {"title": "GPX Activity Analysis", "summary": f"An error occurred during local analysis: {e}"}

def create_analyzer(config):
    """
    Factory function to create the appropriate analyzer based on LLM_PROVIDER.
    
    Args:
        config: ConfigManager instance containing LLM_PROVIDER setting
        
    Returns:
        BaseAnalyzer instance (GeminiAnalyzer or LocalLLMAnalyzer)
        
    Raises:
        ValueError: If LLM_PROVIDER is not supported
    """
    provider = config.LLM_PROVIDER
    
    if provider == 'gemini':
        try:
            logger.info("Creating GeminiAnalyzer...")
            return GeminiAnalyzer()
        except ValueError as e:
            logger.error(f"Failed to create GeminiAnalyzer: {e}")
            logger.warning("Falling back to LocalLLMAnalyzer (if available).")
            return LocalLLMAnalyzer()
    elif provider == 'local':
        try:
            logger.info("Creating LocalLLMAnalyzer...")
            return LocalLLMAnalyzer()
        except Exception as e:
            logger.error(f"Failed to create LocalLLMAnalyzer: {e}")
            logger.warning("No analyzer available. Analysis will be skipped.")
            return None
    else:
        logger.error(f"Unsupported LLM_PROVIDER: {provider}")
        logger.warning("Falling back to GeminiAnalyzer (if API key available).")
        try:
            return GeminiAnalyzer()
        except ValueError:
            logger.error("No valid LLM provider available. Analysis will be skipped.")
            return None
