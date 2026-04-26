import os
import json
import logging
import requests
import gpxpy
import textwrap
from datetime import datetime
from google import genai

logger = logging.getLogger(__name__)

class BaseAnalyzer:
    def analyze_gpx_data(self, gpx_stats):
        raise NotImplementedError

    def _calculate_pace(self, distance_meters, duration_seconds):
        """Calculate pace per km (min/km) and speed (km/h)."""
        if distance_meters <= 0 or duration_seconds <= 0:
            return 0.0, 0.0
        
        distance_km = distance_meters / 1000.0
        pace_min_km = (duration_seconds / 60.0) / distance_km
        speed_kmh = distance_km / (duration_seconds / 3600.0)
        
        return round(pace_min_km, 2), round(speed_kmh, 2)

    def _extract_start_coordinates(self, gpx_data):
        """Extract latitude and longitude from the first track point in GPX data.
        
        Args:
            gpx_data: GPX file path or gpxpy.parse() object
            
        Returns:
            tuple: (latitude, longitude) or (None, None) if extraction fails
        """
        # Default coordinates for Gupo
        default_lat = 37.35
        default_lon = 126.93
        
        try:
            if isinstance(gpx_data, str):
                if not gpx_data or not os.path.exists(gpx_data):
                    logger.warning(f"GPX file path is empty or does not exist: {gpx_data}")
                    return (default_lat, default_lon)
                
                with open(gpx_data, 'r', encoding='utf-8') as f:
                    gpx = gpxpy.parse(f)
            else:
                gpx = gpx_data
            
            if gpx is None:
                logger.warning("GPX object is None after parsing.")
                return (default_lat, default_lon)
            
            if gpx.tracks:
                first_track = gpx.tracks[0]
                if first_track.segments:
                    first_segment = first_track.segments[0]
                    if first_segment.points:
                        first_point = first_segment.points[0]
                        return (first_point.latitude, first_point.longitude)
            
            logger.warning("No track points found in GPX data.")
            return (default_lat, default_lon)
            
        except Exception as e:
            logger.error(f"Failed to extract coordinates from GPX data: {e}")
            return (default_lat, default_lon)

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
            return textwrap.dedent(f"""
                Analyze these GPX statistics for a blog post:

                Distance: {{distance}} meters
                Duration: {{duration}} seconds
                Pace per km: {{pace_per_km}} min/km
                Speed: {{speed}} km/h
                Weather: {{weather}}

                Provide a brief, engaging summary of the activity, suitable for a blog post.
                If possible, suggest a title for the blog post.
                Format the output as JSON: {{"title": "Suggested Title", "summary": "Blog post summary"}}
            """)
        except Exception as e:
            logger.error(f"Error reading prompt template: {e}")
            return textwrap.dedent(f"""
                Analyze these GPX statistics for a blog post:

                Distance: {{distance}} meters
                Duration: {{duration}} seconds
                Pace per km: {{pace_per_km}} min/km
                Speed: {{speed}} km/h
                Weather: {{weather}}

                Provide a brief, engaging summary of the activity, suitable for a blog post.
                If possible, suggest a title for the blog post.
                Format the output as JSON: {{"title": "Suggested Title", "summary": "Blog post summary"}}
            """)

    def _validate_json(self, text):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _call_llm(self, prompt, model_name, api_endpoint=None, api_key=None):
        """Call LLM API and return parsed JSON response.
        
        Args:
            prompt: The prompt to send to the LLM
            model_name: The model name to use
            api_endpoint: The API endpoint (for local LLM)
            api_key: API key if required
            
        Returns:
            dict: Parsed JSON response or error message
        """
        try:
            if api_endpoint:
                # Local LLM (e.g., Ollama)
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                
                payload = {
                    "model": model_name,
                    "prompt": prompt,
                    "format": "json"
                }
                
                response = requests.post(api_endpoint, json=payload, headers=headers, timeout=60)
                response.raise_for_status()
                
                result = response.json()
                
                # Ollama returns response in 'response' field
                if 'response' in result:
                    text = result['response']
                elif 'message' in result and 'content' in result['message']:
                    text = result['message']['content']
                else:
                    text = str(result)
                
                return self._validate_json(text)
            else:
                # Remote LLM (e.g., Gemini)
                return None
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to call LLM API: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode LLM response: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling LLM: {e}")
            return None


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
        
        # Extract coordinates from GPX data if available
        gpx_file_path = gpx_stats.get('gpx_file_path')
        
        # Validate gpx_file_path before processing
        if gpx_file_path is None:
            logger.warning("No GPX file path provided in stats. Using default coordinates.")
            latitude, longitude = 37.35, 126.93
        else:
            # Check if file exists and is not empty
            if not gpx_file_path or not os.path.exists(gpx_file_path):
                logger.warning(f"GPX file path is invalid or does not exist: {gpx_file_path}")
                latitude, longitude = 37.35, 126.93
            else:
                latitude, longitude = self._extract_start_coordinates(gpx_file_path)
        
        # Get weather info
        weather = self._get_weather_info(
            latitude=latitude,
            longitude=longitude
        )
        
        # Load prompt template
        prompt_template = self._load_prompt_template()
        
        # Extract date (default to current system date if missing)
        activity_date = gpx_stats.get('date')
        if not activity_date:
            activity_date = datetime.now().strftime("%Y-%m-%d")
            
        # Prepare data dictionary for safe formatting
        data = {
            'distance': distance,
            'duration': duration,
            'pace_per_km': pace_per_km,
            'speed': speed,
            'weather': weather,
            'date': activity_date
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
                weather=weather,
                date=activity_date
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
    Local LLM analyzer that connects to a local LLM service (e.g., Ollama).
    """
    
    def __init__(self):
        self.api_endpoint = os.getenv("LOCAL_LLM_ENDPOINT", "http://ollama:11434/api/generate")
        self.model_name = os.getenv("LOCAL_LLM_MODEL", "gemma4:e4b")
        self.api_key = os.getenv("LOCAL_LLM_API_KEY")
        self.prompt_template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_template.txt')
        logger.info(f"Local LLM configured with endpoint: {self.api_endpoint}, model: {self.model_name}")

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
        
        # Extract coordinates from GPX data if available
        gpx_file_path = gpx_stats.get('gpx_file_path')
        
        # Validate gpx_file_path before processing
        if gpx_file_path is None:
            logger.warning("No GPX file path provided in stats. Using default coordinates.")
            latitude, longitude = 37.35, 126.93
        else:
            # Check if file exists and is not empty
            if not gpx_file_path or not os.path.exists(gpx_file_path):
                logger.warning(f"GPX file path is invalid or does not exist: {gpx_file_path}")
                latitude, longitude = 37.35, 126.93
            else:
                latitude, longitude = self._extract_start_coordinates(gpx_file_path)
        
        # Get weather info
        weather = self._get_weather_info(
            latitude=latitude,
            longitude=longitude
        )
        
        # Load prompt template
        prompt_template = self._load_prompt_template()
        
        # Extract date (default to current system date if missing)
        activity_date = gpx_stats.get('date')
        if not activity_date:
            activity_date = datetime.now().strftime("%Y-%m-%d")
            
        # Prepare data dictionary for safe formatting
        data = {
            'distance': distance,
            'duration': duration,
            'pace_per_km': pace_per_km,
            'speed': speed,
            'weather': weather,
            'date': activity_date
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
                weather=weather,
                date=activity_date
            )
        
        # Call local LLM
        analysis_result = self._call_llm(
            prompt=prompt,
            model_name=self.model_name,
            api_endpoint=self.api_endpoint,
            api_key=self.api_key
        )
        
        if analysis_result:
            return analysis_result
        else:
            logger.error("Local LLM returned invalid or no response.")
            return {"title": "GPX Activity Analysis", "summary": "Local LLM failed to generate a valid response."}

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
