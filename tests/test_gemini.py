import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from google.genai.errors import ClientError
from analyzer import GeminiAnalyzer, create_analyzer
from gemini_support import AnalysisError, make_client, safe_error, settings


def api_error(code, message="test failure"):
    return ClientError(code, {"error": {"code": code, "message": message}})


class GeminiTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"GEMINI_API_KEY": "test-key",
            "AY_GEMINI_MODEL": "primary", "AY_GEMINI_FALLBACK_MODEL": "fallback"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = Mock()
        self.sleep = patch("gemini_support.time.sleep").start()
        self.addCleanup(patch.stopall)
        with patch("analyzer.make_client", return_value=self.client):
            self.analyzer = GeminiAnalyzer()

    def test_success(self):
        self.client.models.generate_content.return_value.text = '{"title":"Run","summary":"Good","training":["Rest or easy run"]}'
        self.assertEqual(self.analyzer._generate_analysis("test"), {"title":"Run","summary":"Good","training":["Rest or easy run"]})

    def test_billing_auth_quota_never_fallback_or_publishable_result(self):
        for code in (402, 400, 401, 403, 429):
            with self.subTest(code=code):
                self.client.reset_mock()
                self.client.models.generate_content.side_effect = api_error(code, "secret-key")
                with self.assertRaises(AnalysisError) as caught:
                    self.analyzer._generate_analysis("test")
                self.assertNotIn("secret-key", str(caught.exception))
                self.assertEqual(self.client.models.generate_content.call_count, 1)

    def test_server_error_recovers_with_same_model(self):
        self.client.models.generate_content.side_effect = [api_error(503), api_error(503),
            SimpleNamespace(text='{"title":"Run","summary":"Good","training":["Rest or easy run"]}')]
        with patch("gemini_support.random.uniform", return_value=0):
            self.assertEqual(self.analyzer._generate_analysis("test")["title"], "Run")
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [2, 4])
        self.assertEqual([c.kwargs["model"] for c in self.client.models.generate_content.call_args_list],
                         ["primary"] * 3)

    def test_server_errors_stop_after_four_attempts(self):
        for code in (500, 502, 503, 504):
            with self.subTest(code=code):
                self.client.reset_mock()
                self.sleep.reset_mock()
                self.client.models.generate_content.side_effect = api_error(code, "secret-key")
                with self.assertRaises(AnalysisError) as caught:
                    self.analyzer._generate_analysis("test")
                self.assertNotIn("secret-key", str(caught.exception))
                self.assertEqual(self.client.models.generate_content.call_count, 4)
                self.assertEqual(self.sleep.call_count, 3)

    def test_retry_stops_immediately_on_auth_failure(self):
        self.client.models.generate_content.side_effect = [api_error(503), api_error(403)]
        with self.assertRaises(AnalysisError):
            self.analyzer._generate_analysis("test")
        self.assertEqual(self.client.models.generate_content.call_count, 2)
        self.assertEqual(self.sleep.call_count, 1)

    def test_sdk_404_fallback(self):
        self.client.models.generate_content.side_effect = [api_error(404),
            SimpleNamespace(text='{"title":"Run","summary":"Good","training":["Rest or easy run"]}')]
        self.analyzer._generate_analysis("test")
        self.assertEqual([c.kwargs["model"] for c in self.client.models.generate_content.call_args_list],
                         ["primary", "fallback"])

    def test_fallback_billing_error_is_safe(self):
        self.client.models.generate_content.side_effect = [api_error(404), api_error(402, "secret")]
        with self.assertRaises(AnalysisError) as caught:
            self.analyzer._generate_analysis("test")
        self.assertIn("402", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))

    def test_bad_json_is_not_publishable(self):
        for text in (None, "", "not json", "[]", '{"title":"x"}', '{"title":1,"summary":"s"}'):
            self.client.models.generate_content.return_value.text = text
            with self.subTest(text=text), self.assertRaises(AnalysisError):
                self.analyzer._generate_analysis("test")

    def test_429_prepay_distinguished_from_rate_limit(self):
        self.assertIn("결제", safe_error(api_error(429, "Your prepayment credits are depleted")))
        self.assertIn("한도", safe_error(api_error(429, "Quota exhausted")))

    def test_explicit_key_and_backend(self):
        with patch("gemini_support.genai.Client") as client:
            make_client("chosen-key")
            self.assertEqual(client.call_args.kwargs["api_key"], "chosen-key")
            self.assertFalse(client.call_args.kwargs["vertexai"])
            self.assertEqual(client.call_args.kwargs["http_options"]["retry_options"]["attempts"], 1)

    def test_environment_wins_over_dotenv_for_running_container(self):
        with patch("gemini_support.load_dotenv") as loader:
            self.assertEqual(settings(), ("test-key", "primary", "fallback"))
            self.assertFalse(loader.call_args.kwargs["override"])

    def test_factory_defaults_to_gemini(self):
        with patch.dict(os.environ, {'LLM_PROVIDER': 'gemini'}), \
             patch("analyzer.make_client", return_value=self.client):
            self.assertIsInstance(create_analyzer(), GeminiAnalyzer)

    def test_missing_prompt_stops_analysis(self):
        self.analyzer.prompt_template_path = '/missing/running-prompt.txt'
        with self.assertRaises(AnalysisError):
            self.analyzer._load_prompt_template()


class PublicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_error_stops_before_media_or_wordpress(self):
        import main
        manager = SimpleNamespace(download_gpx_file=AsyncMock(return_value="saved.gpx"))
        publisher = Mock()
        analyzer = Mock()
        analyzer.analyze_gpx_data.side_effect = AnalysisError("billing failure")
        with patch.multiple(main, _config=SimpleNamespace(CHAT_ID="123"),
                _telegram_manager=manager, _gpx_processor=Mock(process=Mock(return_value={"distance":1})),
                _analyzer=analyzer, _wordpress_publisher=publisher):
            await main.handle_new_message(SimpleNamespace(message=SimpleNamespace(chat_id=123, document=True)))
        self.assertEqual(publisher.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
