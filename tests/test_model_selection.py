import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from analyzer import GeminiAnalyzer, LocalLLMAnalyzer, OpenAIAnalyzer, create_analyzer
from gemini_support import AnalysisError


VALID = '{"title":"Run","summary":"Measured run","training":["Easy next run"]}'


class ModelSelectionTests(unittest.TestCase):
    def test_factory_selects_only_configured_provider(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key', 'OPENAI_API_KEY': 'test-key'}), \
             patch('analyzer.make_client', return_value=Mock()):
            self.assertIsInstance(create_analyzer(SimpleNamespace(LLM_PROVIDER='gemini')), GeminiAnalyzer)
            self.assertIsInstance(create_analyzer(SimpleNamespace(LLM_PROVIDER='openai')), OpenAIAnalyzer)
            self.assertIsInstance(create_analyzer(SimpleNamespace(LLM_PROVIDER='local')), LocalLLMAnalyzer)
            with self.assertRaises(AnalysisError):
                create_analyzer(SimpleNamespace(LLM_PROVIDER='unknown'))

    def test_missing_openai_key_does_not_fallback_to_gemini(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            with self.assertRaises(AnalysisError):
                create_analyzer(SimpleNamespace(LLM_PROVIDER='openai'))

    def test_openai_uses_configured_model_and_validates_response(self):
        payload = {'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': VALID}]}]}
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key', 'OPENAI_MODEL': 'custom-model'}), \
             patch('analyzer.requests.post') as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = payload
            result = OpenAIAnalyzer()._generate_analysis('synthetic prompt')
            self.assertEqual(result['training'], ['Easy next run'])
            self.assertEqual(post.call_args.kwargs['json']['model'], 'custom-model')
            self.assertFalse(post.call_args.kwargs['json']['store'])

    def test_openai_invalid_analysis_blocks_publication(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}), \
             patch('analyzer.requests.post') as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {'status': 'completed', 'output': [
                {'type': 'message', 'content': [{'type': 'output_text', 'text': '{"title":"Run"}'}]}]}
            with self.assertRaises(AnalysisError):
                OpenAIAnalyzer()._generate_analysis('synthetic prompt')

    def test_local_uses_configured_model_and_validates_response(self):
        with patch.dict(os.environ, {'LOCAL_LLM_ENDPOINT': 'http://localhost:11434/api/generate',
                                     'LOCAL_LLM_MODEL': 'custom-local'}), \
             patch('analyzer.requests.post') as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {'done': True, 'response': VALID}
            result = LocalLLMAnalyzer()._generate_analysis('synthetic prompt')
            self.assertEqual(result['title'], 'Run')
            self.assertEqual(post.call_args.kwargs['json']['model'], 'custom-local')
            self.assertFalse(post.call_args.kwargs['json']['stream'])

    def test_shared_prompt_reaches_selected_model(self):
        with patch.dict(os.environ, {'LOCAL_LLM_MODEL': 'custom-local'}), \
             patch.object(LocalLLMAnalyzer, '_get_weather_info', return_value='현재 날씨 정보 없음'), \
             patch.object(LocalLLMAnalyzer, '_generate_analysis', return_value={'title': 'Run'}) as generate:
            LocalLLMAnalyzer().analyze_gpx_data({'distance': 1000, 'duration': 600,
                                                  'date': '2026-10-24'})
            self.assertIn('1000.00 m', generate.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
