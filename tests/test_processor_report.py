import tempfile
import unittest
from pathlib import Path

from processor import GpxProcessor
from report import render_report


class GpxReportTests(unittest.TestCase):
    def test_track_extensions_and_splits_reach_report(self):
        source = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1"
 xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
<trk><trkseg>
<trkpt lat="37.0" lon="127.0"><ele>40</ele><time>2026-10-20T07:00:00Z</time><extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>140</gpxtpx:hr><gpxtpx:cad>160</gpxtpx:cad></gpxtpx:TrackPointExtension></extensions></trkpt>
<trkpt lat="37.01" lon="127.0"><ele>50</ele><time>2026-10-20T07:10:00Z</time><extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>160</gpxtpx:hr><gpxtpx:cad>170</gpxtpx:cad></gpxtpx:TrackPointExtension></extensions></trkpt>
<trkpt lat="37.02" lon="127.0"><ele>45</ele><time>2026-10-20T07:20:00Z</time><extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>170</gpxtpx:hr><gpxtpx:cad>175</gpxtpx:cad></gpxtpx:TrackPointExtension></extensions></trkpt>
</trkseg></trk></gpx>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.gpx'
            path.write_text(source)
            stats = GpxProcessor().process(str(path))
        self.assertEqual(stats['date'], '2026-10-20 16:00')
        self.assertEqual(stats['duration'], 1200)
        self.assertEqual(stats['heart_rate_max'], 170)
        self.assertEqual(stats['cadence_max'], 175)
        self.assertEqual(stats['elevation_min'], 40)
        self.assertGreaterEqual(len(stats['splits']), 2)
        html = render_report(stats, {'summary': '<script>bad</script>', 'training': ['Take it easy']}, 'run.gpx')
        self.assertIn('구간별 기록', html)
        self.assertIn('평균 심박', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('[sgpx gpx="/wp-content/uploads/gpx/run.gpx"]', html)

    def test_missing_optional_fields_are_not_invented(self):
        stats = {'distance': 1000, 'duration': 600, 'splits': []}
        html = render_report(stats, {'summary': '기록 확인', 'training': ['천천히 달리기']}, 'run.gpx')
        self.assertNotIn('평균 심박', html)
        self.assertNotIn('최저', html)
        self.assertIn('10:00/km', html)


if __name__ == '__main__':
    unittest.main()
