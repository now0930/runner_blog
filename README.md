# GPX to WordPress Auto-Blogger

This project is an automated bot that processes GPX files (GPS tracking data), analyzes the activity using LLMs (Gemini or Local LLM), fetches relevant weather information, and automatically publishes a blog post to WordPress.

## Key Features
- **GPX Data Analysis**: Parses GPX files to extract distance, duration, and pace.
- **AI-Powered Summarization**: Uses Gemini or Local LLMs to generate engaging blog content based on the activity data.
- **Weather Integration**: Automatically fetches weather data for the activity location.
- **WordPress Automation**: Automatically creates and publishes posts to your WordPress site.
- **Telegram Integration**: Receive and process GPX files directly via Telegram.

## Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Configure Environment Variables**:
   Copy the example file and fill in your credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and credentials
   ```

3. **Run with Docker**:
   Use `docker-compose` to build and start the service:
   ```bash
   docker-compose up --build -d
   ```

## Usage

1. **Start the Bot**: Ensure the container is running.
2. **Send GPX File**: Send a `.gpx` file to the Telegram account associated with the `PHONE_NUMBER` configured in your `.env`.
3. **Processing**: The bot will automatically:
   - Download the file.
   - Parse the GPX data.
   - Generate a summary using the configured LLM.
   - Publish the post to your WordPress site.
