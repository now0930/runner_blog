import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from processor import GpxProcessor
from report import render_walking_report
import main


def gpx_track(activity_type='', step=0.0007, interval=60):
    points = []
    for index in range(11):
        minute, second = divmod(index * interval, 60)
        points.append(f'<trkpt lat="0" lon="{index * step:.5f}">'
                      f'<time>2026-10-20T07:{minute:02d}:{second:02d}Z</time></trkpt>')
    kind = f'<type>{activity_type}</type>' if activity_type else ''
    return ('<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">'
            f'<trk>{kind}<trkseg>{"".join(points)}</trkseg></trk></gpx>')


class WalkingClassificationTests(unittest.TestCase):
    def process(self, activity_type='', step=0.0007, interval=60):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'activity.gpx'
            path.write_text(gpx_track(activity_type, step, interval))
            return GpxProcessor().process(str(path))

    def test_walking_from_moving_speed(self):
        stats = self.process()
        self.assertEqual(stats['activity_type'], 'walking')
        self.assertGreater(stats['distance'], 500)

    def test_declared_running_overrides_slow_speed(self):
        self.assertEqual(self.process(activity_type='running')['activity_type'], 'running')

    def test_declared_walking_overrides_fast_speed(self):
        self.assertEqual(self.process(activity_type='walking', step=0.002)['activity_type'], 'walking')

    def test_fast_unknown_activity_remains_running(self):
        self.assertEqual(self.process(step=0.002)['activity_type'], 'running')

    def test_walking_report_only_has_totals(self):
        title, content = render_walking_report({'distance': 1500, 'duration': 1200})
        self.assertIn('걷기 기록', title)
        self.assertIn('총 거리: 1.50km', content)
        self.assertIn('총 시간: 20분 0초', content)
        self.assertNotIn('페이스', content)
        self.assertNotIn('훈련', content)


class WalkingPublicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_walk_skips_model_weather_and_media(self):
        manager = SimpleNamespace(download_gpx_file=AsyncMock(return_value='/tmp/walk.gpx'))
        processor = Mock(process=Mock(return_value={
            'activity_type': 'walking', 'distance': 1500, 'duration': 1200}))
        analyzer = Mock()
        publisher = Mock(is_enabled=True, create_post=Mock(return_value={'id': 123}))
        with patch.multiple(main, _config=SimpleNamespace(CHAT_ID='123'),
                            _telegram_manager=manager, _gpx_processor=processor,
                            _analyzer=analyzer, _wordpress_publisher=publisher):
            await main.handle_new_message(SimpleNamespace(message=SimpleNamespace(chat_id=123, document=True)))
        analyzer.analyze_gpx_data.assert_not_called()
        publisher.upload_media.assert_not_called()
        publisher.create_post.assert_called_once()
        content = publisher.create_post.call_args.kwargs['content']
        self.assertEqual(content, '<p>총 거리: 1.50km</p>\n<p>총 시간: 20분 0초</p>')

    async def test_missing_walking_duration_is_not_published(self):
        manager = SimpleNamespace(download_gpx_file=AsyncMock(return_value='/tmp/walk.gpx'))
        publisher = Mock(is_enabled=True)
        with patch.multiple(main, _config=SimpleNamespace(CHAT_ID='123'),
                            _telegram_manager=manager, _gpx_processor=Mock(process=Mock(return_value={
                                'activity_type': 'walking', 'distance': 1500, 'duration': 0})),
                            _analyzer=Mock(), _wordpress_publisher=publisher):
            await main.handle_new_message(SimpleNamespace(message=SimpleNamespace(chat_id=123, document=True)))
        publisher.create_post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
