import gpxpy
import logging
import requests

logger = logging.getLogger(__name__)

class GpxProcessor:
    def process(self, file_path):
        """Process GPX file and extract statistics.
        
        Args:
            file_path: Path to the GPX file
            
        Returns:
            dict: GPX statistics including distance, duration, pace, speed, and file path
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                gpx = gpxpy.parse(f)
            
            total_distance = 0.0
            total_duration_seconds = 0.0
            
            for track in gpx.tracks:
                for segment in track.segments:
                    for point in segment.points:
                        # Calculate distance between consecutive points
                        if len(segment.points) > 1:
                            prev_point = segment.points[-2]
                            curr_point = segment.points[-1]
                            
                            # Haversine formula for distance calculation
                            from math import radians, sin, cos, sqrt, atan2
                            
                            lat1, lon1 = radians(prev_point.latitude), radians(prev_point.longitude)
                            lat2, lon2 = radians(curr_point.latitude), radians(curr_point.longitude)
                            
                            dlat = lat2 - lat1
                            dlon = lon2 - lon1
                            
                            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                            c = 2 * atan2(sqrt(a), sqrt(1-a))
                            
                            distance_km = 6371.0 * c
                            total_distance += distance_km * 1000  # Convert to meters
                            
                            # Accumulate duration from point time attributes
                            if hasattr(point, 'time') and hasattr(segment.points[0], 'time'):
                                try:
                                    total_duration_seconds += (point.time - segment.points[0].time).total_seconds()
                                except:
                                    pass
            
            # Calculate pace and speed
            pace_per_km, speed = self._calculate_pace(total_distance, total_duration_seconds)
            
            # Extract start coordinates
            latitude, longitude = self._extract_start_coordinates(gpx)
            
            # Get weather info
            weather = self._get_weather_info(latitude, longitude)
            
            return {
                'distance': total_distance,
                'duration': total_duration_seconds,
                'pace_per_km': pace_per_km,
                'speed': speed,
                'latitude': latitude,
                'longitude': longitude,
                'weather': weather,
                'gpx_file_path': file_path
            }
            
        except FileNotFoundError:
            logger.error(f"GPX file not found: {file_path}")
            return None
        except Exception as e:
            logger.error(f"Error processing GPX file {file_path}: {e}")
            return None
    
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
            gpx_data: GPX object
            
        Returns:
            tuple: (latitude, longitude) or default coordinates if extraction fails
        """
        # Default coordinates for Gupo
        default_lat = 37.35
        default_lon = 126.93
        
        try:
            if gpx_data.tracks:
                first_track = gpx_data.tracks[0]
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
