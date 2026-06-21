# Universal Web Media & Text Data Collector

A powerful Python tool designed to scrape, extract, download, and translate media (audio/video), transcripts, documents, and articles from arbitrary webpages. Built with fallbacks to handle dynamic JavaScript-rendered sites, custom domain routing, and offline AI processing.

## Features
- **Media Extraction**: Supports direct media downloads, YouTube, and embedded players via `yt-dlp`.
- **Text & Article Scraping**: Extracts main content from static and JavaScript-heavy pages using `BeautifulSoup` and `Playwright`.
- **AI-Powered Fallback & Translation**: Integrates with local `Ollama` models (e.g., `qwen3.5:9b`) to identify article content, translate foreign texts to English, and handle edge-case pages where standard scraping fails.
- **Audio Transcription**: Leverages `faster-whisper` for fast and accurate local audio/video transcription, outputting standard `.txt` and subtitle `.vtt` formats.
- **Database Tracking**: Logs all downloaded artifacts locally in a unified SQLite database (`dataset.db`).

## Prerequisites
Ensure you have Python 3.8+ installed. The following external software is recommended or required for full functionality:
- **FFmpeg**: Required for media processing and audio extraction.
- **Ollama**: Required for local AI text translation and fallback scraping extraction.
- **Playwright Chromium**: Required for scraping JavaScript-rendered websites.

## Installation

1. Clone or download the repository.
2. Install the Python dependencies:
   ```bash
   pip install requests yt-dlp beautifulsoup4 faster-whisper playwright
   ```
3. Initialize Playwright browsers:
   ```bash
   playwright install chromium
   ```
4. Ensure Ollama is installed and running locally with the target model:
   ```bash
   ollama pull qwen3.5:9b
   ```
   *(Note: You can change the model inside `collector.py` if needed)*

## Usage

You can run the collector interactively or provide a URL directly via the command line.

### Interactive Mode
```bash
python collector.py
```
*You will be prompted to paste a link.*

### Command-Line Mode
```bash
python collector.py "https://example.com/some-media-article"
```

### Options
- `--year YYYY`: Specific to certain archive routines (e.g., PMO Radio), restricts scraping to the provided year (default is `2026`).

## Output Structure
Artifacts are automatically organized into a local `dataset` directory inside the project folder:
```text
Web_Scrapping/
├── dataset.db           # SQLite database tracking file metadata
└── dataset/
    ├── audio/           # Downloaded media files
    └── text/            # Transcripts, translated articles, PDFs, and .vtt subtitles
```

## How It Works
1. **Link Analysis**: Parses the domain to see if it's a known handler (e.g. NPTEL, YouTube).
2. **Extraction**: Downloads videos and converts to MP3 if possible. For articles, it parses HTML directly.
3. **Transcription**: If audio is downloaded, `faster-whisper` automatically generates English transcripts.
4. **AI Fallback**: If standard rules fail, Playwright intercepts API responses and dynamically renders the DOM. The extracted text is then passed to a local LLM to reliably extract and translate the main article or document.
5. **Storage**: All data is recorded into the database and saved onto the disk.
