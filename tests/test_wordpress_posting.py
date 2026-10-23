import unittest
from unittest.mock import Mock, AsyncMock, patch
from types import SimpleNamespace
from gemini_support import AnalysisError
import main
from wordpress import WordPressPublisher


class WordPressPostingPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_gpx_processing_and_posting(self):
        """GPX 수신 시 분석 및 워드프레스 포스팅 생성이 정상적으로 호출되는지 검증"""
        manager = SimpleNamespace(download_gpx_file=AsyncMock(return_value="/tmp/test.gpx"))
        gpx_processor = Mock()
        gpx_processor.process.return_value = {
            "distance": 5200.0,
            "duration": 1800.0,
            "gpx_file_path": "/tmp/test.gpx"
        }
        analyzer = Mock()
        analyzer.analyze_gpx_data.return_value = {
            "title": "Evening Run",
            "summary": "A pleasant evening run."
        }
        publisher = Mock()
        publisher.is_enabled = True
        publisher.upload_media = AsyncMock(return_value=(101, "https://example.com/wp-content/uploads/gpx/test.gpx", "https://example.com/wp-content/uploads/gpx/test.gpx"))
        publisher.copy_file_to_expected_location.return_value = True
        publisher.create_post.return_value = {"id": 1234, "link": "https://example.com/2026/04/evening-run"}

        with patch.multiple(
            main,
            _config=SimpleNamespace(CHAT_ID="12345"),
            _telegram_manager=manager,
            _gpx_processor=gpx_processor,
            _analyzer=analyzer,
            _wordpress_publisher=publisher
        ), patch("os.path.exists", return_value=True):
            fake_event = SimpleNamespace(
                message=SimpleNamespace(
                    chat_id=12345,
                    document=SimpleNamespace(mime_type="application/gpx+xml")
                )
            )
            await main.handle_new_message(fake_event)

        publisher.create_post.assert_called_once()
        call_kwargs = publisher.create_post.call_args.kwargs
        self.assertEqual(call_kwargs["title"], "Evening Run")
        self.assertIn("Evening Run", call_kwargs["title"])
        self.assertIn("A pleasant evening run.", call_kwargs["content"])
        self.assertIn('[sgpx gpx="/wp-content/uploads/gpx/test.gpx"]', call_kwargs["content"])
        self.assertIsNone(call_kwargs["featured_media_id"])

    async def test_wordpress_disabled_skips_posting(self):
        """워드프레스 설정이 비활성화된 경우 create_post를 호출하지 않는지 검증"""
        manager = SimpleNamespace(download_gpx_file=AsyncMock(return_value="/tmp/test.gpx"))
        gpx_processor = Mock()
        gpx_processor.process.return_value = {"distance": 1000.0, "duration": 600.0}
        analyzer = Mock()
        analyzer.analyze_gpx_data.return_value = {"title": "Short Walk", "summary": "Walk"}

        publisher = Mock()
        publisher.is_enabled = False

        with patch.multiple(
            main,
            _config=SimpleNamespace(CHAT_ID="12345"),
            _telegram_manager=manager,
            _gpx_processor=gpx_processor,
            _analyzer=analyzer,
            _wordpress_publisher=publisher
        ):
            fake_event = SimpleNamespace(
                message=SimpleNamespace(
                    chat_id=12345,
                    document=SimpleNamespace(mime_type="application/gpx+xml")
                )
            )
            await main.handle_new_message(fake_event)

        publisher.create_post.assert_not_called()

    async def test_analysis_error_aborts_posting(self):
        """GPX 분석 실패 시 포스팅 단계로 진행하지 않는지 검증"""
        manager = SimpleNamespace(download_gpx_file=AsyncMock(return_value="/tmp/test.gpx"))
        gpx_processor = Mock()
        gpx_processor.process.return_value = {"distance": 1000.0, "duration": 600.0}
        analyzer = Mock()
        analyzer.analyze_gpx_data.side_effect = AnalysisError("API quota exceeded")
        publisher = Mock()

        with patch.multiple(
            main,
            _config=SimpleNamespace(CHAT_ID="12345"),
            _telegram_manager=manager,
            _gpx_processor=gpx_processor,
            _analyzer=analyzer,
            _wordpress_publisher=publisher
        ):
            fake_event = SimpleNamespace(
                message=SimpleNamespace(
                    chat_id=12345,
                    document=SimpleNamespace(mime_type="application/gpx+xml")
                )
            )
            await main.handle_new_message(fake_event)

        publisher.create_post.assert_not_called()


class WordPressPublisherUnitTests(unittest.TestCase):
    def test_create_post_payload_without_featured_media(self):
        """create_post 호출 시 featured_media가 payload에 포함되지 않는지 검증"""
        config = SimpleNamespace(
            WORDPRESS_URL="https://myblog.com",
            WORDPRESS_USERNAME="admin",
            WORDPRESS_PASSWORD="app-password"
        )
        wp = WordPressPublisher(config)

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"id": 999, "link": "https://myblog.com/post-999"}
            mock_post.return_value = mock_response

            result = wp.create_post(
                title="Test Title",
                content="<p>Test Content</p>",
                status="publish",
                featured_media_id=None
            )

            self.assertIsNotNone(result)
            self.assertEqual(result["id"], 999)

            called_payload = mock_post.call_args.kwargs["json"]
            self.assertNotIn("featured_media", called_payload)
            self.assertEqual(called_payload["title"], "Test Title")


if __name__ == "__main__":
    unittest.main()
