"""Extract measured running statistics from GPX tracks."""
import logging
from statistics import mean
from zoneinfo import ZoneInfo

import gpxpy

logger = logging.getLogger(__name__)

WALKING_TYPES = {'walking', 'walk', 'hiking', 'hike', '걷기', '산책', '등산'}
RUNNING_TYPES = {'running', 'run', 'jogging', '러닝', '달리기'}


def _activity_type(gpx, segments, cadence):
    """Prefer GPX activity metadata; use moving speed only when absent."""
    declared = [(track.type or '').strip().lower() for track in gpx.tracks]
    if any(value in RUNNING_TYPES for value in declared):
        return 'running'
    if any(value in WALKING_TYPES for value in declared):
        return 'walking'

    moving_distance = moving_seconds = 0.0
    for segment in segments:
        for first, second in zip(segment.points, segment.points[1:]):
            if not first.time or not second.time:
                continue
            seconds = (second.time - first.time).total_seconds()
            meters = first.distance_2d(second) or 0
            speed = meters / seconds * 3.6 if seconds > 0 else 0
            if meters >= 2 and 1 <= speed <= 15:
                moving_distance += meters
                moving_seconds += seconds
    if moving_distance >= 100 and moving_seconds > 0:
        moving_speed = moving_distance / moving_seconds * 3.6
        if moving_speed <= 6.5 and (cadence is None or cadence <= 140):
            return 'walking'
    return 'running'


def _extension(point, name):
    for extension in point.extensions:
        for child in extension:
            if child.tag.rsplit('}', 1)[-1] == name:
                try:
                    value = float(child.text)
                    return value if value > 0 else None
                except (TypeError, ValueError):
                    return None
    return None


def _average(values):
    return round(mean(values), 1) if values else None


class GpxProcessor:
    def process(self, file_path):
        try:
            with open(file_path, encoding='utf-8') as source:
                gpx = gpxpy.parse(source)
            segments = [segment for track in gpx.tracks for segment in track.segments
                        if segment.points]
            if not segments:
                logger.warning('GPX contains no track points: %s', file_path)
                return None

            points = [point for segment in segments for point in segment.points]
            times = [point.time for point in points if point.time]
            elevations = [point.elevation for point in points if point.elevation is not None]
            heart_rates = [_extension(point, 'hr') for point in points]
            cadences = [_extension(point, 'cad') for point in points]
            cadence_avg = _average([v for v in cadences if v is not None])
            distance = sum(segment.length_2d() for segment in segments)
            duration = sum(max(0, (segment.points[-1].time - segment.points[0].time).total_seconds())
                           for segment in segments if len(segment.points) > 1
                           and segment.points[0].time and segment.points[-1].time)

            # Interpolate each kilometre crossing between adjacent GPS samples.
            splits = []
            travelled = 0.0
            next_boundary = 1000.0
            split_start = points[0].time
            split_hr, split_cad, split_elev = [], [], []
            for segment in segments:
                for first, second in zip(segment.points, segment.points[1:]):
                    step = first.distance_2d(second) or 0.0
                    hr, cad = _extension(first, 'hr'), _extension(first, 'cad')
                    if hr is not None:
                        split_hr.append(hr)
                    if cad is not None:
                        split_cad.append(cad)
                    if first.elevation is not None:
                        split_elev.append(first.elevation)
                    before = travelled
                    travelled += step
                    while step > 0 and travelled >= next_boundary:
                        crossing = (first.time + (second.time - first.time) *
                                    ((next_boundary - before) / step)) if first.time and second.time else None
                        seconds = (crossing - split_start).total_seconds() if crossing and split_start else None
                        splits.append({'km': len(splits) + 1, 'distance': 1000.0,
                                       'duration': round(seconds, 1) if seconds and seconds > 0 else None,
                                       'heart_rate': _average(split_hr), 'cadence': _average(split_cad),
                                       'elevation': _average(split_elev)})
                        split_start = crossing
                        split_hr, split_cad, split_elev = [], [], []
                        next_boundary += 1000.0
            remainder = distance - len(splits) * 1000.0
            if remainder > 1 and split_start and times:
                seconds = (times[-1] - split_start).total_seconds()
                splits.append({'km': len(splits) + 1, 'distance': round(remainder, 1),
                               'duration': round(seconds, 1) if seconds > 0 else None,
                               'heart_rate': _average(split_hr), 'cadence': _average(split_cad),
                               'elevation': _average(split_elev)})

            started = min(times) if times else None
            ended = max(times) if times else None
            return {
                'distance': distance, 'duration': duration, 'gpx_file_path': file_path,
                'date': started.astimezone(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M') if started else None,
                'end_date': ended.astimezone(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M') if ended else None,
                'point_count': len(points), 'splits': splits,
                'activity_type': _activity_type(gpx, segments, cadence_avg),
                'heart_rate_avg': _average([v for v in heart_rates if v is not None]),
                'heart_rate_max': max((v for v in heart_rates if v is not None), default=None),
                'cadence_avg': cadence_avg,
                'cadence_max': max((v for v in cadences if v is not None), default=None),
                'elevation_min': round(min(elevations), 1) if elevations else None,
                'elevation_max': round(max(elevations), 1) if elevations else None,
                'elevation_start': round(points[0].elevation, 1) if points[0].elevation is not None else None,
                'elevation_end': round(points[-1].elevation, 1) if points[-1].elevation is not None else None,
            }
        except (OSError, gpxpy.gpx.GPXParseException) as error:
            logger.error('Failed to process GPX %s: %s', file_path, error)
            return None
