import unittest
from unittest.mock import patch

from analyzer import BaseAnalyzer
from report import render_report


class HistoricalWeatherTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = BaseAnalyzer()

    def test_uses_run_date_and_start_hour_not_current_weather(self):
        with patch('analyzer.requests.get') as get:
            get.return_value.json.return_value = {'hourly': {
                'time': ['2026-10-20T16:00', '2026-10-20T17:00'],
                'temperature_2m': [15.2, 13.4],
                'relative_humidity_2m': [62, 65],
                'wind_speed_10m': [5.3, 6.2],
                'precipitation': [0.0, 0.1],
            }}
            weather = self.analyzer._get_weather_info(37.0, 127.0, '2026-10-20 16:12')
            self.assertIn('2026-10-20 16:00 KST', weather)
            self.assertIn('15.2°C', weather)
            self.assertIn('과거 날씨 추정치', weather)
            self.assertEqual(get.call_args.args[0], 'https://archive-api.open-meteo.com/v1/archive')
            params = get.call_args.kwargs['params']
            self.assertEqual(params['start_date'], '2026-10-20')
            self.assertEqual(params['timezone'], 'Asia/Seoul')
            self.assertNotIn('current', params)

    def test_missing_time_or_hour_never_uses_unrelated_weather(self):
        with patch('analyzer.requests.get') as get:
            self.assertEqual(self.analyzer._get_weather_info(None, None, '2026-10-20 16:12'),
                             '운동 당시 날씨 자료 없음')
            self.assertEqual(self.analyzer._get_weather_info(37, 127, None),
                             '운동 당시 날씨 자료 없음')
            get.assert_not_called()
            get.return_value.json.return_value = {'hourly': {'time': []}}
            self.assertEqual(self.analyzer._get_weather_info(37, 127, '2026-10-20 16:12'),
                             '운동 당시 날씨 자료 없음')

    def test_report_records_weather_without_html_injection(self):
        stats = {'distance': 1000, 'duration': 600, 'date': '2026-10-20 16:12'}
        analysis = {'summary': '기록 확인', 'training': ['휴식'], 'weather': '<script>bad</script>'}
        report = render_report(stats, analysis, 'run.gpx')
        self.assertIn('날씨: &lt;script&gt;bad&lt;/script&gt;', report)

    def test_weather_reaches_model_and_published_analysis(self):
        weather = '운동 시작 시간대 과거 날씨 추정치: 기온 15.2°C'
        with patch.object(self.analyzer, '_get_weather_info', return_value=weather), \
             patch.object(self.analyzer, '_generate_analysis', return_value={
                 'title': 'Run', 'summary': '기록 확인', 'training': ['휴식']}) as generate:
            result = self.analyzer.analyze_gpx_data({
                'distance': 1000, 'duration': 600, 'date': '2026-10-20 16:12'})
        self.assertIn(weather, generate.call_args.args[0])
        self.assertEqual(result['weather'], weather)


if __name__ == '__main__':
    unittest.main()
