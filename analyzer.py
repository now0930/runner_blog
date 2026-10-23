import os
import json
import logging
import requests
import gpxpy
from datetime import datetime
from gemini_support import (AnalysisError, key_fingerprint, make_client,
                            safe_error, settings, status_code, generate_with_retry)

logger = logging.getLogger(__name__)

class BaseAnalyzer:
    def analyze_gpx_data(self, gpx_stats):
        raise NotImplementedError

    def _validated_analysis(self, result):
        if not isinstance(result, dict) or not all(
                isinstance(result.get(field), str) and result[field].strip()
                for field in ('title', 'summary')):
            raise AnalysisError('Model returned empty or invalid analysis JSON; publication skipped.')
        training = result.get('training')
        if (not isinstance(training, list) or not 1 <= len(training) <= 3 or
                not all(isinstance(item, str) and item.strip() for item in training)):
            raise AnalysisError('Model returned no valid training recommendations; publication skipped.')
        return {'title': result['title'].strip(), 'summary': result['summary'].strip(),
                'training': [item.strip() for item in training]}

    def _detail_text(self, stats):
        rows = []
        for split in stats.get('splits') or []:
            seconds = split.get('duration')
            rows.append(f'{split["km"]}구간 {split["distance"] / 1000:.2f}km, '
                        f'{seconds if seconds is not None else "미상"}초, '
                        f'심박 {split.get("heart_rate")}, 케이던스 {split.get("cadence")}, '
                        f'고도 {split.get("elevation")}m')
        return {
            'splits_text': '; '.join(rows) if rows else '구간 기록 없음',
            'heart_rate_text': (f'평균 {stats["heart_rate_avg"]}bpm, 최대 {stats.get("heart_rate_max")}bpm'
                                if stats.get('heart_rate_avg') is not None else '기록 없음'),
            'cadence_text': (f'평균 {stats["cadence_avg"]}spm, 최대 {stats.get("cadence_max")}spm'
                             if stats.get('cadence_avg') is not None else '기록 없음'),
            'elevation_text': (f'최저 {stats["elevation_min"]}m, 최고 {stats.get("elevation_max")}m'
                               if stats.get('elevation_min') is not None else '기록 없음'),
        }

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
        """Load the required running-analysis prompt."""
        try:
            with open(self.prompt_template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except OSError as error:
            raise AnalysisError('러닝 분석 프롬프트를 읽을 수 없어 게시를 중단했습니다.') from error

    def _validate_json(self, text):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

class GeminiAnalyzer(BaseAnalyzer):
    def __init__(self):
        self.api_key, self.model_name, self.fallback_model = settings()
        self.client = make_client(self.api_key)
        logger.info("Gemini Developer API key fingerprint: %s", key_fingerprint(self.api_key))

        self.prompt_template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_template.txt')
        logger.info(f"Analyzer initialized with model: {self.model_name}, fallback: {self.fallback_model}")

    def analyze_gpx_data(self, gpx_stats):
        """
        Sends GPX statistics to Gemini for analysis.
        """
        if not gpx_stats:
            raise AnalysisError("No GPX stats provided for analysis.")

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
        data.update(self._detail_text(gpx_stats))
        
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
        
        return self._generate_analysis(prompt)

    def _generate_analysis(self, prompt):
        models = [self.model_name]
        if self.fallback_model and self.fallback_model != self.model_name:
            models.append(self.fallback_model)
        for index, model in enumerate(models):
            try:
                response = generate_with_retry(self.client,
                    model=model, contents=prompt,
                    config={"response_mime_type": "application/json",
                            "response_schema": {
                                "type": "OBJECT",
                                "properties": {
                                    "title": {"type": "STRING"},
                                    "summary": {"type": "STRING"},
                                    "training": {"type": "ARRAY", "items": {"type": "STRING"}}},
                                "required": ["title", "summary", "training"]}})
            except Exception as error:
                if status_code(error) == 404 and index + 1 < len(models):
                    logger.warning("Model %s unavailable; trying configured fallback %s",
                                   model, models[index + 1])
                    continue
                raise AnalysisError(safe_error(error)) from None
            result = self._validate_json(response.text) if response.text else None
            return self._validated_analysis(result)



def create_analyzer(config=None):
    """Always use Gemini for running analysis and publication."""
    logger.info("Creating GeminiAnalyzer...")
    return GeminiAnalyzer()
