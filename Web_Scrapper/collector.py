import argparse
import base64
import json
import html
import os
import re
import sqlite3
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urljoin, unquote

import requests
import yt_dlp
from bs4 import BeautifulSoup


class WebDataCollector:
    MEDIA_DOMAINS = {
        "youtube.com",
        "www.youtube.com",
        "youtu.be",
        "pmonradio.nic.in",
        "www.pmonradio.nic.in",
    }

    def __init__(self, db_name="dataset.db", output_dir="dataset", base_dir=None, target_year=2026):
        # Keep all outputs inside this project folder.
        self.base_dir = Path(base_dir or Path(__file__).resolve().parent)
        self.output_dir = self.base_dir / output_dir
        self.audio_dir = self.output_dir / "audio"
        self.text_dir = self.output_dir / "text"
        self.db_path = self.base_dir / db_name
        self.target_year = int(target_year)

        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.text_dir.mkdir(parents=True, exist_ok=True)
        self._setup_database()

    def _setup_database(self):
        """Initialize SQLite database to track files and metadata."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY,
                    title TEXT,
                    source_url TEXT,
                    file_path TEXT,
                    data_type TEXT
                )
                """
            )
            conn.commit()

    def log_to_db(self, title, source_url, file_path, data_type):
        """Log extracted file metadata into the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO logs (title, source_url, file_path, data_type) VALUES (?, ?, ?, ?)",
                (title, source_url, str(file_path), data_type),
            )
            conn.commit()

    def process_link(self, url):
        """Router: decide how to handle the input link."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        query = parsed.query.lower()

        is_known_media_domain = domain in self.MEDIA_DOMAINS
        has_jw_hint = "jwsource" in query or "jwplayer" in query

        if "pmonradio.nic.in" in domain:
            print("[*] PMO Radio link detected. Resolving episode media...")
            pmo_ok = self._extract_pmonradio_media(url)
            if pmo_ok:
                return

            print("[*] PMO-specific extraction failed. Trying generic media extractor...")
            media_ok = self._extract_media(url)
            if not media_ok:
                print("[*] Media extraction failed. Using AI fallback...")
                self._ai_fallback_extraction(url)
            return

        if "nptel.ac.in" in domain and "/courses/" in parsed.path:
            print("[*] NPTEL course page detected. Extracting lecture media and course outline...")
            nptel_ok = self._extract_nptel_course(url)
            if not nptel_ok:
                print("[*] NPTEL course extraction failed. Using AI fallback...")
                self._ai_fallback_extraction(url)
            return

        if "pmindia.gov.in" in domain and "/news_updates/" in parsed.path:
            print("[*] PM India article page detected. Extracting text...")
            article_ok = self._extract_pmindia_article(url)
            if not article_ok:
                print("[*] Article extraction failed. Using AI fallback...")
                self._ai_fallback_extraction(url)
            return

        if is_known_media_domain or has_jw_hint:
            print("[*] Media link detected. Extracting audio and subtitles...")
            media_ok = self._extract_media(url)
            if not media_ok:
                print("[*] Media extraction failed. Using AI fallback...")
                self._ai_fallback_extraction(url)
        else:
            print("[*] Webpage detected. Using AI fallback for dynamic extraction...")
            self._ai_fallback_extraction(url)

    def _extract_media(self, url):
        """Use yt-dlp Python API to download MP3 and VTT subtitles."""
        ffmpeg_location = self._find_ffmpeg_location()
        has_ffmpeg = ffmpeg_location is not None

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(self.audio_dir / "%(id)s_%(title)s.%(ext)s"),
            "restrictfilenames": True,
            "quiet": True,
            "no_warnings": True,
        }

        if has_ffmpeg:
            ydl_opts["ffmpeg_location"] = ffmpeg_location
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            title = info.get("title") or info.get("id") or "unknown_media"
            media_id = info.get("id", "")

            audio_candidates = []
            if media_id:
                audio_candidates = [
                    path for path in sorted(self.audio_dir.glob(f"{media_id}_*"))
                    if path.suffix.lower() not in {".vtt", ".srt"}
                ]
            subtitle_candidates = sorted(self.audio_dir.glob(f"{media_id}_*.vtt")) if media_id else []

            if audio_candidates:
                audio_path = audio_candidates[-1]
                audio_type = "Audio (MP3)" if audio_path.suffix.lower() == ".mp3" else "Audio (Original)"
                self.log_to_db(title, url, audio_path, audio_type)
            else:
                print("[-] Audio file was not found after download.")
                audio_path = None

            if subtitle_candidates:
                for sub_path in subtitle_candidates:
                    moved_sub_path = self._unique_path(self.text_dir / sub_path.name)
                    if sub_path != moved_sub_path:
                        shutil.move(str(sub_path), str(moved_sub_path))
                        sub_path = moved_sub_path
                    self.log_to_db(title, url, sub_path, "Text (Subtitle VTT)")
            else:
                print("[-] No English VTT subtitle was found for this media.")
                if audio_path:
                    self._transcribe_audio(audio_path, title)

            if audio_path:
                if has_ffmpeg:
                    print(f"[+] Success: Downloaded media assets for '{title}'")
                else:
                    print(f"[+] Success: Downloaded raw audio for '{title}' (ffmpeg not installed, so MP3 conversion was skipped)")
                return True

            return False

        except Exception as e:
            print(f"[-] Error processing media: {e}")
            return False

    def _extract_pmonradio_media(self, url):
        """Extract PMO radio episode media through pcvideocode.asp endpoint."""
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            episode_ids = []

            # Only keep the configured year section and stop once the page moves to an older year.
            for block in soup.select("div.blog-post"):
                label_text = block.get_text(" ", strip=True)
                if str(self.target_year) not in label_text:
                    if episode_ids:
                        break
                    continue

                onclick_tag = block.find(attrs={"onclick": True})
                if not onclick_tag:
                    continue

                onclick = onclick_tag.get("onclick", "")
                match = re.search(r"hideallexcept\('([^']+)'\)", onclick)
                if match:
                    episode_ids.append(match.group(1))

            if not episode_ids:
                body = soup.find("body")
                if body and body.get("onload"):
                    match = re.search(r"hideallexcept\('([^']+)'\)", body.get("onload"))
                    if match:
                        episode_ids.append(match.group(1))

            # Preserve order while removing duplicates.
            episode_ids = list(dict.fromkeys(episode_ids))
            if not episode_ids:
                print("[-] No PMO episode IDs found on page.")
                return False

            downloaded = 0
            for ep_id in episode_ids:
                encoded_id = base64.b64encode(ep_id.encode("utf-8")).decode("ascii")
                info_url = urljoin(url, f"pcvideocode.asp?id={encoded_id}")

                info_resp = requests.get(info_url, headers=headers, timeout=30)
                if info_resp.status_code != 200:
                    continue

                media_urls = self._extract_media_urls_from_html(info_resp.text, base_url=url)
                if not media_urls:
                    continue

                for media_url in media_urls:
                    if self._download_direct_media(media_url, source_url=info_url, title_hint=ep_id):
                        downloaded += 1

            if downloaded == 0:
                print("[-] PMO endpoint did not return downloadable media URLs.")
                return False

            print(f"[+] PMO extraction completed. Downloaded files: {downloaded}")
            return True

        except Exception as e:
            print(f"[-] Error processing PMO media page: {e}")
            return False

    def _extract_pmindia_article(self, url):
        """Extract PM India article text and save it as a transcript file."""
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            raw_html = response.text
            soup = BeautifulSoup(raw_html, "html.parser")

            youtube_url = self._find_embedded_youtube_url(raw_html, soup)
            if youtube_url:
                print(f"[*] Embedded YouTube video detected: {youtube_url}")
                media_ok = self._extract_media(youtube_url)
                if not media_ok:
                    print("[-] Embedded YouTube download failed.")

            for unwanted in soup.select("script, style, noscript, .sidebar, .tweet-container, #recent_news_sidebar"):
                unwanted.decompose()

            printable = soup.select_one("div#printable") or soup.select_one("div.content-loaded") or soup.select_one("div.news-bg") or soup.body
            if printable is None:
                print("[-] PM India article container was not found.")
                return False

            title_tag = printable.find("h2") if hasattr(printable, "find") else None
            title = title_tag.get_text(" ", strip=True) if title_tag else (soup.title.get_text(" ", strip=True) if soup.title else "pmindia_article")
            date_tag = printable.select_one(".share_date .date") if hasattr(printable, "select_one") else None
            published_date = date_tag.get_text(" ", strip=True) if date_tag else ""

            paragraph_source = printable.select_one("div.news-bg") if hasattr(printable, "select_one") else None
            if paragraph_source is None:
                paragraph_source = printable

            paragraphs = []
            for paragraph in paragraph_source.find_all("p"):
                text = paragraph.get_text(" ", strip=True)
                if not text:
                    continue
                if text in {"Friends,", "My young friends,"} or text not in paragraphs:
                    paragraphs.append(text)

            if not paragraphs:
                fallback_text = paragraph_source.get_text("\n", strip=True)
                if fallback_text:
                    paragraphs = [line.strip() for line in fallback_text.splitlines() if line.strip()]

            if not paragraphs:
                print("[-] No article text found on PM India page.")
                return False

            raw_text = "\n\n".join(paragraphs)
            translated_text = self._translate_text_with_ai(raw_text)

            safe_title = self._safe_filename(title)
            file_path = self._unique_path(self.text_dir / f"{safe_title}.txt")

            article_text = []
            article_text.append(title)
            if published_date:
                article_text.append(f"Date: {published_date}")
            article_text.append(f"Source: {url}")
            article_text.append("")
            article_text.append(translated_text)

            file_path.write_text("\n\n".join(article_text), encoding="utf-8")
            self.log_to_db(safe_title, url, file_path, "Text (Article)")
            print(f"[+] Success: Saved article transcript '{file_path.name}'")
            return True

        except Exception as e:
            print(f"[-] Error processing PM India article page: {e}")
            return False

    def _extract_nptel_course(self, url):
        """Extract NPTEL course outline and download all lecture videos from embedded YouTube IDs."""
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            raw_html = response.text
            course_outline = self._parse_nptel_course_outline(raw_html)
            if not course_outline:
                print("[-] Could not locate NPTEL course outline data on page.")
                return False

            course_title = course_outline.get("title") or "nptel_course"
            professor = course_outline.get("professor", "")
            institute = course_outline.get("instituteName") or course_outline.get("nocCoordinatingInstitute") or ""

            manifest_path = self._unique_path(self.text_dir / f"{self._safe_filename(course_title)}_outline.txt")
            manifest_lines = [course_title]
            if professor:
                manifest_lines.append(f"Instructor: {professor}")
            if institute:
                manifest_lines.append(f"Institute: {institute}")
            manifest_lines.append(f"Source: {url}")
            manifest_lines.append("")

            downloaded = 0
            for unit in course_outline.get("units", []):
                unit_name = unit.get("name", "Unit")
                manifest_lines.append(unit_name)
                for lesson in unit.get("lessons", []):
                    lesson_name = lesson.get("name", "Lecture")
                    youtube_id = lesson.get("youtube_id")
                    concepts = lesson.get("concepts_covered") or ""
                    manifest_lines.append(f"- {lesson_name}")
                    if concepts:
                        manifest_lines.append(f"  Concepts: {concepts}")

                    if not youtube_id:
                        manifest_lines.append("  Video: unavailable")
                        continue

                    youtube_url = f"https://www.youtube.com/watch?v={youtube_id}"
                    manifest_lines.append(f"  Video: {youtube_url}")
                    if self._extract_media(youtube_url):
                        downloaded += 1

                manifest_lines.append("")

            manifest_path.write_text("\n".join(manifest_lines).strip() + "\n", encoding="utf-8")
            self.log_to_db(self._safe_filename(course_title), url, manifest_path, "Text (Course Outline)")

            if downloaded == 0:
                print("[-] NPTEL course page found, but no lecture videos were downloaded.")
                return False

            print(f"[+] NPTEL course extraction completed. Downloaded lectures: {downloaded}")
            print(f"[+] Course outline saved to '{manifest_path.name}'")
            return True

        except Exception as e:
            print(f"[-] Error processing NPTEL course page: {e}")
            return False

    def _parse_nptel_course_outline(self, raw_html):
        """Extract NPTEL course metadata and lesson videos from the embedded page data."""
        title_match = re.search(r'<h3 class="text-base font-bold">([^<]+)</h3>', raw_html)
        department_match = re.search(r'<div class="department svelte-6dhyy0"><span>(.*?)</span>', raw_html, flags=re.DOTALL)
        institute_match = re.search(r'contentType:"[^"]+",selfPaced:.*?nocCoordinatingInstitute:"([^"]+)"', raw_html, flags=re.DOTALL)

        if not title_match:
            return None

        units = []
        unit_pattern = re.compile(r'name:"(?P<unit>[^"]+)",lessons:\[(?P<lessons>.*?)\]\}', flags=re.DOTALL)
        lesson_pattern = re.compile(
            r'name:"(?P<name>[^"]+)",youtube_id:"(?P<youtube>[^"]+)",concepts_covered:(?P<concepts>null|"(?P<concept_text>(?:\\.|[^"\\])*)")',
            flags=re.DOTALL,
        )

        for unit_match in unit_pattern.finditer(raw_html):
            unit_name = html.unescape(unit_match.group("unit")).strip()
            lessons_blob = unit_match.group("lessons")
            lessons = []

            for lesson_match in lesson_pattern.finditer(lessons_blob):
                lesson_name = html.unescape(lesson_match.group("name")).strip()
                youtube_id = lesson_match.group("youtube").strip()
                concepts_text = lesson_match.group("concept_text")
                concepts = html.unescape(concepts_text).strip() if concepts_text else None
                lessons.append(
                    {
                        "name": lesson_name,
                        "youtube_id": youtube_id,
                        "concepts_covered": concepts,
                    }
                )

            if lessons:
                units.append({"name": unit_name, "lessons": lessons})

        return {
            "title": html.unescape(title_match.group(1)).strip(),
            "professor": html.unescape(department_match.group(1)).strip() if department_match else "",
            "instituteName": html.unescape(institute_match.group(1)).strip() if institute_match else "",
            "nocCoordinatingInstitute": html.unescape(institute_match.group(1)).strip() if institute_match else "",
            "units": units,
        }

    def _find_embedded_youtube_url(self, raw_html, soup):
        """Return a normalized YouTube watch URL if the page embeds a YouTube player."""
        raw_patterns = (
            r"https?://(?:www\.)?youtube\.com/embed/([A-Za-z0-9_-]+)",
            r"https?://(?:www\.)?youtu\.be/([A-Za-z0-9_-]+)",
        )

        for pattern in raw_patterns:
            match = re.search(pattern, raw_html, flags=re.IGNORECASE)
            if match:
                return f"https://www.youtube.com/watch?v={match.group(1)}"

        for iframe in soup.find_all("iframe", src=True):
            iframe_src = iframe["src"].strip()
            if "youtube.com/embed/" not in iframe_src and "youtu.be" not in iframe_src:
                continue

            parsed_src = urlparse(urljoin("https://www.youtube.com", iframe_src))
            if "youtube.com/embed/" in parsed_src.path:
                video_id = parsed_src.path.rstrip("/").split("/")[-1]
                if video_id:
                    return f"https://www.youtube.com/watch?v={video_id}"

            query_dict = parse_qs(parsed_src.query)
            if "v" in query_dict and query_dict["v"]:
                return f"https://www.youtube.com/watch?v={query_dict['v'][0]}"

        return None

    def _find_ffmpeg_location(self):
        """Return an ffmpeg folder path if ffmpeg/ffprobe are installed."""
        if shutil.which("ffmpeg") and shutil.which("ffprobe"):
            return None

        winget_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
        if not winget_root.exists():
            return None

        for ffmpeg_exe in winget_root.rglob("ffmpeg.exe"):
            ffprobe_exe = ffmpeg_exe.parent / "ffprobe.exe"
            if ffprobe_exe.exists():
                return str(ffmpeg_exe.parent)

        return None

    def _extract_media_urls_from_html(self, html, base_url):
        """Find media URLs inside HTML, including encoded hlsurl parameters."""
        candidates = []

        soup = BeautifulSoup(html, "html.parser")
        for iframe in soup.find_all("iframe", src=True):
            iframe_src = urljoin(base_url, iframe["src"].strip())
            parsed_src = urlparse(iframe_src)
            query_dict = parse_qs(parsed_src.query)

            for key in ("hlsurl", "file", "src", "url"):
                for value in query_dict.get(key, []):
                    candidates.append(unquote(value).strip())

        for match in re.finditer(r"hlsurl=([^&\"'\s>]+)", html, flags=re.IGNORECASE):
            candidates.append(unquote(match.group(1)).strip())

        direct_pattern = r"https?://[^\"'\s>]+(?:\.mp3|\.mp4|\.aac|\.wav|\.webm|\.m4a)"
        candidates.extend(re.findall(direct_pattern, html, flags=re.IGNORECASE))

        normalized = []
        seen = set()
        allowed_ext = {".mp3", ".mp4", ".aac", ".wav", ".webm", ".m4a"}

        for item in candidates:
            candidate = item
            if candidate.startswith("//"):
                candidate = f"https:{candidate}"
            elif candidate.startswith("/"):
                candidate = urljoin(base_url, candidate)

            parsed_candidate = urlparse(candidate)
            suffix = Path(parsed_candidate.path).suffix.lower()
            if suffix not in allowed_ext:
                continue

            if candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)

        return normalized

    def _download_direct_media(self, media_url, source_url, title_hint):
        """Download direct media file URL into dataset and log it."""
        try:
            parsed = urlparse(media_url)
            original_name = Path(parsed.path).name or f"{title_hint}.bin"
            safe_base = self._safe_filename(f"{title_hint}_{Path(original_name).stem}")
            suffix = Path(original_name).suffix or ".bin"
            target_path = self._unique_path(self.audio_dir / f"{safe_base}{suffix}")

            src_parsed = urlparse(source_url)
            referer = f"{src_parsed.scheme}://{src_parsed.netloc}/"
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": referer,
            }
            with requests.get(media_url, headers=headers, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(target_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            self.log_to_db(safe_base, source_url, target_path, "Audio (Direct)")
            print(f"[+] Success: Saved direct media '{target_path.name}'")
            self._transcribe_audio(target_path, safe_base)
            return True
        except Exception as e:
            print(f"[-] Failed direct media download from {media_url}: {e}")
            return False

    def _extract_pdfs(self, url):
        """Scrape webpage for PDF links, download them, and log them."""
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            seen_urls = set()
            pdf_count = 0

            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                if ".pdf" not in href.lower():
                    continue

                pdf_url = urljoin(url, href)
                if pdf_url in seen_urls:
                    continue
                seen_urls.add(pdf_url)

                title = link.get_text(strip=True) or Path(urlparse(pdf_url).path).name or "document"
                safe_title = self._safe_filename(title)
                file_path = self._unique_path(self.text_dir / f"{safe_title}.pdf")

                pdf_response = requests.get(pdf_url, headers=headers, timeout=60)
                pdf_response.raise_for_status()

                with open(file_path, "wb") as f:
                    f.write(pdf_response.content)

                self.log_to_db(safe_title, pdf_url, file_path, "Text (PDF)")
                print(f"[+] Success: Saved transcript '{safe_title}'")
                pdf_count += 1

            if pdf_count == 0:
                print("[-] No PDFs found on this page.")
            else:
                print(f"[+] Total PDFs downloaded: {pdf_count}")

        except Exception as e:
            print(f"[-] Error processing web page: {e}")

    def _ai_fallback_extraction(self, url):
        """Use local Ollama model to extract text and media links from unknown webpages."""
        print(f"[*] Analyzing unknown webpage using AI: {url}")
        try:
            # Still extract PDFs if they exist
            self._extract_pdfs(url)

            # Site-Specific API Bypass: If the site's frontend is down but the API works
            import re
            clean_text = ""
            
            bjs_match = re.search(r"bharatiya-jnana-sarita\.info.*?/article/view/([a-f0-9]+)", url)
            if bjs_match:
                article_id = bjs_match.group(1)
                api_url = f"https://bharatiya-jnana-sarita.info/api/getArticle?id={article_id}"
                print(f"[*] Frontend bypass: Fetching directly from API: {api_url}")
                try:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    api_resp = requests.get(api_url, headers=headers, timeout=30)
                    if api_resp.status_code == 200:
                        extracted = self._extract_text_from_json(api_resp.text)
                        if extracted:
                            clean_text = extracted
                except Exception as e:
                    print(f"[-] API bypass failed: {e}")

            if not clean_text:
                # Standard fetch
                headers = {"User-Agent": "Mozilla/5.0"}
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # Strip junk
                for unwanted in soup.select("script, style, noscript, nav, footer, header"):
                    unwanted.decompose()

                clean_text = soup.get_text(separator="\n", strip=True)

                # If the page has very little text, it's likely JS-rendered. Use Playwright.
                if len(clean_text) < 500:
                    print("[*] Page appears to be JavaScript-rendered. Launching headless browser...")
                    clean_text = self._fetch_with_playwright(url)

            if not clean_text or len(clean_text) < 50:
                print("[-] Could not extract meaningful text from this page.")
                return False

            if len(clean_text) > 20000:
                clean_text = clean_text[:20000]

            prompt = (
                "You are an expert web scraper and translator. Analyze the following webpage text. "
                "Your task is to extract the main article, document, or lecture text. "
                "CRITICAL INSTRUCTION: If the extracted text is NOT in English, you MUST translate it into English. "
                "Also, look for any URLs that might be video or audio files. "
                "Return your answer strictly in JSON format without any markdown formatting:\n"
                "{\n"
                '  "title": "Title of the page or article (in English)",\n'
                '  "main_text": "The full text of the article/document translated to English. Leave empty if none found.",\n'
                '  "media_urls": ["url1", "url2"]\n'
                "}\n\n"
                f"Webpage Text:\n{clean_text}"
            )

            api_url = "http://localhost:11434/api/generate"
            payload = {
                "model": "qwen3.5:9b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 8192
                }
            }

            print("[*] Waiting for Ollama (qwen3.5:9b) to process the page...")
            ai_resp = requests.post(api_url, json=payload, timeout=300)
            ai_resp.raise_for_status()

            result_json = ai_resp.json().get("response", "{}").strip()
            
            # Clean up markdown code blocks if the model ignored the format constraint
            if result_json.startswith("```json"):
                result_json = result_json[7:]
            elif result_json.startswith("```"):
                result_json = result_json[3:]
            if result_json.endswith("```"):
                result_json = result_json[:-3]
            result_json = result_json.strip()

            try:
                data = json.loads(result_json)
            except json.JSONDecodeError as e:
                print(f"[-] AI did not return valid JSON. Error: {e}")
                print(f"[-] Raw AI Output: {result_json}")
                return False

            title = data.get("title", "ai_extracted_document")
            main_text = data.get("main_text", "").strip()
            media_urls = data.get("media_urls", [])

            if main_text:
                safe_title = self._safe_filename(title)
                file_path = self._unique_path(self.text_dir / f"{safe_title}.txt")
                
                content = f"{title}\nSource: {url}\n\n{main_text}"
                file_path.write_text(content, encoding="utf-8")
                self.log_to_db(safe_title, url, file_path, "Text (AI Extracted)")
                print(f"[+] Success: Saved AI extracted text '{file_path.name}'")

            for m_url in media_urls:
                if isinstance(m_url, str) and m_url.startswith("http"):
                    print(f"[*] AI found media URL: {m_url}")
                    if not self._download_direct_media(m_url, source_url=url, title_hint=title):
                        self._extract_media(m_url)

            return True

        except requests.exceptions.RequestException as e:
            print(f"[-] Network error during AI fallback: {e}")
        except Exception as e:
            print(f"[-] Error during AI fallback: {e}")
            
        return False

    def _fetch_with_playwright(self, url):
        """Use Playwright headless browser to render JS-heavy pages and extract text.
        Intercepts API responses to capture data that client-side JS fetches."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[-] Playwright is not installed. Please run: pip install playwright && python -m playwright install chromium")
            return ""

        api_texts = []

        def capture_api_response(response):
            """Intercept JSON API responses that contain article/page data."""
            ct = response.headers.get("content-type", "")
            if response.status == 200 and "json" in ct:
                try:
                    body = response.text()
                    if len(body) > 200:
                        api_texts.append(body)
                except Exception:
                    pass

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = context.new_page()
                page.on("response", capture_api_response)
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(8000)

                # Try to extract text from intercepted API responses
                if api_texts:
                    combined = []
                    for raw_json in api_texts:
                        extracted = self._extract_text_from_json(raw_json)
                        if extracted:
                            combined.append(extracted)
                    if combined:
                        clean_text = "\n\n".join(combined)
                        print(f"[+] Intercepted API data. Extracted {len(clean_text)} characters.")
                        context.close()
                        browser.close()
                        return clean_text

                # Fallback: read DOM
                soup = BeautifulSoup(page.content(), "html.parser")
                for unwanted in soup.select("script, style, noscript, nav, footer, header"):
                    unwanted.decompose()
                clean_text = soup.get_text(separator="\n", strip=True)
                print(f"[+] Playwright rendered page. Extracted {len(clean_text)} characters.")
                context.close()
                browser.close()
                return clean_text
        except Exception as e:
            print(f"[-] Playwright rendering failed: {e}")
            return ""

    def _extract_text_from_json(self, raw_json):
        """Recursively extract readable text from a JSON API response."""
        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            return ""

        texts = []
        self._walk_json_for_text(data, texts)
        return "\n\n".join(texts)

    def _walk_json_for_text(self, obj, texts):
        """Walk a JSON object tree and collect text from HTML content fields and long string values."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and len(value) > 100:
                    if "<" in value and ">" in value:
                        # Looks like HTML content
                        soup = BeautifulSoup(value, "html.parser")
                        
                        # Extract media links before they get stripped by get_text()
                        media_links = []
                        for tag in soup.find_all(["iframe", "video", "audio", "source", "a"]):
                            src = tag.get("src") or tag.get("href")
                            if src and ("youtube" in src or "mp4" in src or "mp3" in src or "vimeo" in src):
                                media_links.append(f"[Media Link: {src}]")
                                
                        text = soup.get_text(separator="\n", strip=True)
                        if media_links:
                            text += "\n\n" + "\n".join(media_links)
                            
                        if len(text) > 50:
                            texts.append(text)
                    elif key.lower() in ("content", "text", "body", "description", "summary", "abstract"):
                        texts.append(value)
                elif isinstance(value, (dict, list)):
                    self._walk_json_for_text(value, texts)
        elif isinstance(obj, list):
            for item in obj:
                self._walk_json_for_text(item, texts)

    def _transcribe_audio(self, audio_path, title_hint):
        print(f"[*] Starting transcription for '{title_hint}' using faster-whisper (large-v3)...")
        
        # Windows fix: Add pip-installed NVIDIA CUDA DLL paths to environment so CTranslate2 can find them
        import os
        import site
        from pathlib import Path
        
        for site_pkg in site.getsitepackages() + [site.getusersitepackages()]:
            nvidia_base = Path(site_pkg) / "nvidia"
            if nvidia_base.exists():
                for lib_dir in ["cublas", "cudnn", "cufft", "curand", "cusolver", "cusparse", "nvjitlink"]:
                    bin_dir = nvidia_base / lib_dir / "bin"
                    if bin_dir.exists() and str(bin_dir) not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = f"{bin_dir};{os.environ.get('PATH', '')}"
                        if hasattr(os, "add_dll_directory"):
                            try:
                                os.add_dll_directory(str(bin_dir))
                            except Exception:
                                pass

        try:
            from faster_whisper import WhisperModel
        except ImportError:
            print("[-] faster-whisper is not installed. Please run: pip install faster-whisper")
            return False

        try:
            def _run_transcription(device, compute_type):
                print(f"[*] Initializing Whisper large-v3 on {device.upper()}...")
                model = WhisperModel("large-v3", device=device, compute_type=compute_type)
                segments_gen, info = model.transcribe(str(audio_path), beam_size=5, task="translate")
                print(f"[*] Detected language '{info.language}' with probability {info.language_probability}")
                
                safe_title = self._safe_filename(title_hint)
                txt_path = self._unique_path(self.text_dir / f"{safe_title}.txt")
                vtt_path = self._unique_path(self.text_dir / f"{safe_title}.vtt")

                with open(txt_path, "w", encoding="utf-8") as f_txt, open(vtt_path, "w", encoding="utf-8") as f_vtt:
                    f_vtt.write("WEBVTT\n\n")
                    for segment in segments_gen:
                        f_txt.write(segment.text.strip() + " ")
                        start = self._format_timestamp(segment.start)
                        end = self._format_timestamp(segment.end)
                        f_vtt.write(f"{start} --> {end}\n{segment.text.strip()}\n\n")
                
                return safe_title, txt_path, vtt_path

            try:
                # Attempt GPU transcription
                safe_title, txt_path, vtt_path = _run_transcription("auto", "default")
            except Exception as cuda_err:
                print(f"[-] GPU transcription failed: {cuda_err}")
                print("[*] Automatically falling back to CPU mode (this may take a while)...")
                # Attempt CPU transcription
                safe_title, txt_path, vtt_path = _run_transcription("cpu", "int8")

            self.log_to_db(safe_title, str(audio_path), txt_path, "Text (Whisper Transcript TXT)")
            self.log_to_db(safe_title, str(audio_path), vtt_path, "Text (Whisper Transcript VTT)")
            print(f"[+] Transcription complete. Saved to '{txt_path.name}' and '{vtt_path.name}'")
            return True
        except Exception as e:
            print(f"[-] Error during transcription: {e}")
            return False

    @staticmethod
    def _format_timestamp(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

    def _translate_text_with_ai(self, text):
        """Use local Ollama to translate text to English if needed."""
        print("[*] Checking/Translating text to English using local AI...")
        try:
            prompt = (
                "You are an expert translator. "
                "Translate the following text into English. "
                "If it is already in English, return it exactly as is. "
                "Do NOT add any extra commentary or explanations, just return the translated text.\n\n"
                f"TEXT:\n{text}"
            )
            api_url = "http://localhost:11434/api/generate"
            payload = {
                "model": "qwen3.5:9b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 8192
                }
            }
            response = requests.post(api_url, json=payload, timeout=300)
            response.raise_for_status()
            
            translated_text = response.json().get("response", "").strip()
            return translated_text if translated_text else text
        except Exception as e:
            print(f"[-] Error during text translation, using original text: {e}")
            return text

    @staticmethod
    def _safe_filename(name):
        cleaned = re.sub(r"[^A-Za-z0-9 _.-]", "", name).strip()
        return cleaned or "document"

    @staticmethod
    def _unique_path(path_obj):
        if not path_obj.exists():
            return path_obj

        stem = path_obj.stem
        suffix = path_obj.suffix
        parent = path_obj.parent
        counter = 1

        while True:
            candidate = parent / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1


def parse_args():
    parser = argparse.ArgumentParser(description="Universal Web Media & Text Data Collector")
    parser.add_argument("url", nargs="?", help="YouTube/media link or webpage URL")
    parser.add_argument("--year", type=int, default=2026, help="Target year to keep for year-grouped pages")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    collector = WebDataCollector(target_year=args.year)

    print("=== Universal Web Media & Text Data Collector ===")

    user_url = args.url
    if not user_url:
        if not sys.stdin.isatty():
            print("[-] No URL provided in non-interactive mode.")
            print("[i] Run like: python collector.py \"https://example.com/media\"")
            raise SystemExit(2)

        user_url = input("Enter a link (YouTube, educational, or any media webpage): ").strip()

    if not user_url:
        print("[-] No URL provided.")
        raise SystemExit(1)

    collector.process_link(user_url)
