"""Run in the same environment as the bot; never publishes or prints the key."""
import argparse
import sys

from gemini_support import AnalysisError, key_fingerprint, settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-only", action="store_true",
                        help="Show model and key fingerprint without an API request")
    args = parser.parse_args()
    try:
        key, model, fallback = settings()
        print("Provider: Gemini Developer API")
        print("Key SHA-256 fingerprint: " + key_fingerprint(key))
        print("Model: " + model)
        print("Fallback: " + (fallback or "disabled"))
        if not args.config_only:
            from analyzer import GeminiAnalyzer
            analyzer = GeminiAnalyzer()
            try:
                analyzer._generate_analysis('Return JSON with title "Test" and summary "OK".')
            finally:
                analyzer.client.close()
            print("PASS: authenticated generation and valid analysis JSON; nothing published.")
        return 0
    except AnalysisError as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
