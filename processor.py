import gpxpy
import logging

logger = logging.getLogger(__name__)

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
