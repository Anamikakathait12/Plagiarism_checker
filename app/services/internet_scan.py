from __future__ import annotations

import os
import re
import logging
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from collections import Counter
from difflib import SequenceMatcher
from flask import current_app, has_app_context
from typing import Any, Dict, List
from dotenv import load_dotenv
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

# Sequence similarity keeps a quarter of the raw source score.
SEQUENCE_WEIGHT = 0.25
# Keyword overlap is reduced because shared topics can match without copying.
KEYWORD_WEIGHT = 0.10
# Three-gram overlap rewards exact reuse of short phrases.
NGRAM_3_WEIGHT = 0.25
# Five-gram overlap gives stronger weight to longer exact phrase reuse.
NGRAM_5_WEIGHT = 0.25
# Sentence-level matching retains its existing contribution.
BEST_SENTENCE_WEIGHT = 0.15
# Small common-content baseline removed before score calibration.
BASELINE = 0.08
# The best source contributes 60% of the overall score.
OVERALL_TOP_SOURCE_WEIGHT = 0.60
# The average of up to three best sources contributes 40%.
OVERALL_TOP3_AVERAGE_WEIGHT = 0.40
# Sentence keyword overlap keeps its existing 0.8 multiplier.
SENTENCE_OVERLAP_WEIGHT = 0.80
# Sentence matches require this minimum combined similarity.
SENTENCE_MATCH_THRESHOLD = 0.25
# Calibration's lower transition point remains 0.3.
CALIBRATION_LOW_CUTOFF = 0.30
# Calibration's upper transition point remains 0.6.
CALIBRATION_HIGH_CUTOFF = 0.60
# Scores below the lower transition retain the existing scale.
CALIBRATION_LOW_SCALE = 1.20
# Calibration's middle segment retains its existing starting value.
CALIBRATION_MIDDLE_BASE = 0.36
# Calibration's middle segment retains its existing scale.
CALIBRATION_MIDDLE_SCALE = 1.50
# Calibration's upper segment retains its existing starting value.
CALIBRATION_UPPER_BASE = 0.81
# Calibration's upper segment retains its existing scale.
CALIBRATION_UPPER_SCALE = 0.95
# Source and page prefixes remain capped at 3,000 characters for scoring.
SCORE_TEXT_CHAR_LIMIT = 3000
# Source scoring compares at most ten student sentences.
SCORE_SENTENCE_LIMIT = 10
# Source scoring uses 60-word passages.
SCORE_PASSAGE_WINDOW_WORDS = 60
# Source-scoring passages advance 30 words at a time.
SCORE_PASSAGE_STEP_WORDS = 30
# Source scoring compares at most twenty passages per sentence.
SCORE_MAX_PASSAGES = 20
# Sentence-level matching uses 80-word passages.
SENTENCE_PASSAGE_WINDOW_WORDS = 80
# Sentence-level passage windows advance 40 words at a time.
SENTENCE_PASSAGE_STEP_WORDS = 40
# Embedded source URLs retain their existing minimum score floor.
EMBEDDED_URL_SCORE_FLOOR = 30.0
# A single source at or above this score triggers the high-plagiarism verdict.
HIGH_SOURCE_VERDICT_THRESHOLD = 60.0

# Low-value social pages are not fetched or scored.
DOMAIN_BLOCKLIST = frozenset({
    "facebook.com", "instagram.com", "youtube.com", "tiktok.com",
    "twitter.com", "x.com", "pinterest.com", "linkedin.com",
})


# ─────────────────────────────────────────────
#  STOPWORDS
# ─────────────────────────────────────────────
STOPWORDS: frozenset = frozenset({
    'a','an','the','and','or','but','in','on','at','to','for','of','with',
    'is','are','was','were','be','been','have','has','had','do','does','did',
    'will','would','could','should','may','might','this','that','these',
    'those','it','its','as','by','from','about','which','who','what','when',
    'where','how','not','can','also','more','other','some','than','then',
    'their','there','they','i','you','we','he','she','very','just','after',
    'before','over','under','up','so','if','all','each','into','through',
    'such','no','only',
})

# ─────────────────────────────────────────────
#  TAVILY API KEY (read from the environment at call time)
# ─────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

def _tavily_key() -> str:
    if has_app_context():
        return current_app.config.get("TAVILY_API_KEY", "") or os.getenv("TAVILY_API_KEY", "")
    return os.getenv("TAVILY_API_KEY", "")

# ─────────────────────────────────────────────
#  VERDICT THRESHOLDS
# ─────────────────────────────────────────────
THRESHOLDS = [
    (60.0, 'High Web Plagiarism',     'danger',  '🔴'),
    (35.0, 'Moderate Web Similarity', 'warning', '🟠'),
    (15.0, 'Low Web Similarity',      'caution', '🟡'),
    ( 0.0, 'No Match Found',          'safe',    '🟢'),
]


# ═════════════════════════════════════════════
#  TEXT UTILITY HELPERS
# ═════════════════════════════════════════════

def _tokenize(text: str) -> List[str]:
    """Lowercase word tokens, length > 1."""
    return [w for w in re.findall(r'[a-z]+', text.lower()) if len(w) > 1]


def _keywords(text: str) -> List[str]:
    """Non-stopword tokens longer than 3 chars."""
    return [w for w in _tokenize(text) if w not in STOPWORDS and len(w) > 3]


def _sentences(text: str) -> List[str]:
    """Split text into sentences, min 20 chars each."""
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)
            if len(s.strip()) > 20]


def _ngrams(text: str, n: int) -> set:
    """Return set of n-grams from tokenized text."""
    words = _tokenize(text)
    return {' '.join(words[i:i + n]) for i in range(len(words) - n + 1)}


def _similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio between two strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _passages(text: str, window: int = 80, step: int = 40) -> List[str]:
    """Sliding-window word passages for deep comparison."""
    words = text.split()
    if len(words) <= window:
        return [text]
    return [' '.join(words[i:i + window])
            for i in range(0, len(words) - window + 1, step)]


def _calibrate(score: float) -> float:
    """
    Spread the 0-1 similarity range so mid-range scores
    are more meaningful and comparable.
    """
    if score <= 0:   return 0.0
    if score >= 1:   return 1.0
    if score < CALIBRATION_LOW_CUTOFF:
        return score * CALIBRATION_LOW_SCALE
    if score < CALIBRATION_HIGH_CUTOFF:
        return CALIBRATION_MIDDLE_BASE + (
            score - CALIBRATION_LOW_CUTOFF
        ) * CALIBRATION_MIDDLE_SCALE
    return min(
        1.0,
        CALIBRATION_UPPER_BASE
        + (score - CALIBRATION_HIGH_CUTOFF) * CALIBRATION_UPPER_SCALE,
    )


# ═════════════════════════════════════════════
#  PAGE FETCHER
# ═════════════════════════════════════════════

def _fetch_via_tavily_extract(urls: List[str]) -> Dict[str, str]:
    """
    Use Tavily Extract API to get full page content for a batch of URLs.
    This bypasses bot-blocking (403s) since Tavily fetches from their servers.
    Returns {url: text} dict.
    """
    if not urls:
        return {}

    batches = [urls[index:index + 5] for index in range(0, len(urls), 5)]
    api_key = _tavily_key()

    def extract_batch(batch: List[str]) -> Dict[str, str]:
        try:
            res = requests.post("https://api.tavily.com/extract", json={
                "api_key": api_key,
                "urls": batch,  # Tavily accepts at most five URLs per request.
            }, timeout=20)
            if res.status_code == 200:
                return {
                    item.get("url", ""): item.get("raw_content", "")
                    for item in res.json().get("results", [])
                    if item.get("url") and item.get("raw_content")
                }
        except Exception as e:
            print(f"  ⚠️  Tavily extract error: {e}")
        return {}

    with ThreadPoolExecutor(max_workers=min(8, len(batches))) as executor:
        extracted_batches = executor.map(extract_batch, batches)
        return {
            url: content
            for batch_result in extracted_batches
            for url, content in batch_result.items()
        }


def _is_blocklisted_url(url: str) -> bool:
    """Match blocked domains and their subdomains, ignoring URL ports."""
    try:
        hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in DOMAIN_BLOCKLIST
    )


def _fetch_page_text_with_status(url: str) -> tuple[str, str]:
    """
    Fetch a single URL using direct HTTP.
    Falls back gracefully — Tavily extract is preferred (called in batch).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    for attempt in range(2):
        try:
            res = requests.get(url, timeout=6, headers=headers, allow_redirects=True)
        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            ConnectionResetError,
        ) as e:
            if attempt == 0:
                continue
            status = "timeout" if isinstance(e, requests.exceptions.Timeout) else "failed"
            print(f"  ⚠️  Could not fetch {url}: {e}")
            return "", status
        except Exception as e:
            print(f"  ⚠️  Could not fetch {url}: {e}")
            return "", "failed"

        if res.status_code == 200 and len(res.text) > 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header",
                              "aside", "form", "noscript", "iframe"]):
                tag.decompose()
            main = soup.find("main") or soup.find("article") or soup.find(id="content") or soup
            text = main.get_text(separator=" ", strip=True)
            if len(text) > 300:
                return text, "ok"
            return "", "empty"
        if res.status_code == 200:
            return "", "empty"
        if res.status_code == 403:
            return "", "403"
        return "", "failed"
    return "", "failed"


def _fetch_page_text(url: str) -> str:
    """Compatibility wrapper returning only the extracted page text."""
    text, _ = _fetch_page_text_with_status(url)
    return text


# ═════════════════════════════════════════════
#  MULTI-SIGNAL SCORER
# ═════════════════════════════════════════════

def _score_against_page(student_text: str, page_text: str,
                        metrics: Dict[str, Any] | None = None) -> float:
    """
    4-signal calibrated similarity score (returns 0-1):
      1. Overall sequence match         (25%)
      2. Keyword overlap                (10%)
      3. 3-gram fingerprint overlap     (25%)
      4. 5-gram fingerprint overlap     (25%)
      5. Best sentence-level match      (15%)
    """
    if not page_text.strip():
        return 0.0

    src_cap = student_text[:SCORE_TEXT_CHAR_LIMIT].lower()
    ref_cap = page_text[:SCORE_TEXT_CHAR_LIMIT].lower()

    # Signal 1 — sequence similarity
    seq_score = SequenceMatcher(None, src_cap, ref_cap).ratio()

    # Signal 2 — keyword overlap
    src_kw    = set(_keywords(student_text))
    ref_kw    = set(_keywords(page_text))
    kw_overlap = len(src_kw & ref_kw) / max(len(src_kw), 1) if src_kw else 0.0

    # Signal 3 — 3-gram overlap
    src_3  = _ngrams(student_text, 3)
    ref_3  = _ngrams(page_text,    3)
    ng3    = len(src_3 & ref_3) / max(len(src_3), 1) if src_3 else 0.0

    # Signal 4 — 5-gram overlap
    src_5  = _ngrams(student_text, 5)
    ref_5  = _ngrams(page_text,    5)
    ng5    = len(src_5 & ref_5) / max(len(src_5), 1) if src_5 else 0.0

    # Signal 5 — best sentence-level match
    best_sent = 0.0
    for sentence in _sentences(student_text)[:SCORE_SENTENCE_LIMIT]:
        for passage in _passages(
            page_text,
            window=SCORE_PASSAGE_WINDOW_WORDS,
            step=SCORE_PASSAGE_STEP_WORDS,
        )[:SCORE_MAX_PASSAGES]:
            if metrics is not None:
                metrics["sliding_window_chunks_compared"] += 1
            sc      = _similarity(sentence, passage)
            sw      = set(_keywords(sentence))
            pw      = set(_keywords(passage))
            overlap = len(sw & pw) / max(len(sw), 1) if sw else 0.0
            combined = max(sc, overlap * SENTENCE_OVERLAP_WEIGHT)
            if combined > best_sent:
                best_sent = combined

    raw = (
        seq_score   * SEQUENCE_WEIGHT +
        kw_overlap  * KEYWORD_WEIGHT +
        ng3         * NGRAM_3_WEIGHT +
        ng5         * NGRAM_5_WEIGHT +
        best_sent   * BEST_SENTENCE_WEIGHT
    )
    return _calibrate(max(0.0, raw - BASELINE))


# ═════════════════════════════════════════════
#  SENTENCE-LEVEL MATCH DETECTOR
# ═════════════════════════════════════════════

def _sentence_level_matches(student_text: str,
                             snippets: List[Dict],
                             metrics: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """
    For each sentence in the student's text, find the best matching
    passage across all fetched sources. Returns top 8 suspicious sentences.
    """
    results = []
    for sentence in _sentences(student_text):
        best_score, best_match, best_url = 0.0, '', ''
        for snip in snippets:
            ref = snip.get('full_text') or snip.get('text', '')
            if not ref:
                continue
            for passage in _passages(
                ref,
                window=SENTENCE_PASSAGE_WINDOW_WORDS,
                step=SENTENCE_PASSAGE_STEP_WORDS,
            ):
                if metrics is not None:
                    metrics["sliding_window_chunks_compared"] += 1
                sc      = _similarity(sentence, passage)
                sw      = set(_keywords(sentence))
                pw      = set(_keywords(passage))
                overlap = len(sw & pw) / max(len(sw), 1) if sw else 0.0
                combined = max(sc, overlap * SENTENCE_OVERLAP_WEIGHT)
                if combined > best_score:
                    best_score = combined
                    best_match = passage[:200]
                    best_url   = snip.get('url', '')

        if best_score >= SENTENCE_MATCH_THRESHOLD:
            results.append({
                'source':     sentence,
                'matched':    best_match,
                'score':      round(_calibrate(best_score) * 100, 1),
                'source_url': best_url,
            })

    return sorted(results, key=lambda x: -x['score'])[:8]


# ═════════════════════════════════════════════
#  MAIN PUBLIC FUNCTION
# ═════════════════════════════════════════════

def check_internet_similarity(text: str) -> Dict[str, Any]:
    """
    Advanced internet plagiarism check.

    Returns a dict:
    {
        'matches': [
            {
                'url':     str,
                'title':   str,
                'snippet': str,
                'pct':     float,   ← per-source similarity %
            },
            ...
        ],
        'sentence_matches': [
            {
                'source':     str,   ← student sentence
                'matched':    str,   ← best matching passage
                'score':      float, ← similarity %
                'source_url': str,
            },
            ...
        ],
        'overall_pct': float,   ← weighted top-3 average
        'verdict':     str,     ← e.g. 'High Web Plagiarism'
        'level':       str,     ← 'danger' | 'warning' | 'caution' | 'safe'
        'icon':        str,     ← emoji
    }
    """
    scan_started = time.perf_counter()
    metrics: Dict[str, Any] = {
        "total_scan_seconds": 0.0,
        "document_word_count": 0,
        "search_queries_fired": 0,
        "unique_urls_returned": 0,
        "pages_fetched_ok": 0,
        "pages_blocked": 0,
        "pages_rescued_by_extract": 0,
        "urls_skipped_blocklist": 0,
        "pages_blocked_or_failed": 0,
        "pages_403": 0,
        "pages_timeout": 0,
        "pages_empty": 0,
        "pages_other_failed": 0,
        "sources_scored": 0,
        "query_build_seconds": 0.0,
        "tavily_search_seconds": 0.0,
        "search_seconds": 0.0,
        "extract_seconds": 0.0,
        "fetch_seconds": 0.0,
        "page_fetch_seconds": 0.0,
        "scoring_seconds": 0.0,
        "sliding_window_chunks_compared": 0,
    }

    def finish(result: Dict[str, Any]) -> Dict[str, Any]:
        metrics["total_scan_seconds"] = round(time.perf_counter() - scan_started, 6)
        metrics["page_fetch_seconds"] = metrics["extract_seconds"] + metrics["fetch_seconds"]
        for key in (
            "query_build_seconds", "tavily_search_seconds",
            "search_seconds", "extract_seconds", "fetch_seconds",
            "page_fetch_seconds", "scoring_seconds",
        ):
            metrics[key] = round(metrics[key], 6)
        result["metrics"] = dict(metrics)
        logger.info("Internet scan metrics: %s", result["metrics"])
        return result

    print(" 🔬  Running advanced plagiarism scan...")

    clean_text = re.sub(r'\s+', ' ', text).strip()
    metrics["document_word_count"] = len(clean_text.split())

    if metrics["document_word_count"] < 10:
        return finish({
            'matches': [], 'sentence_matches': [],
            'overall_pct': 0.0,
            'verdict': 'Text Too Short',
            'level': 'caution', 'icon': '⚠️',
        })

    # ── Detect embedded source domains in the text ────────
    # Catches GFG/Wikipedia links embedded directly in the docx content
    query_build_started = time.perf_counter()
    url_domains = re.findall(
        r'https?://(?:www\.)?([a-zA-Z0-9.-]+\.[a-z]{2,})', clean_text
    )
    dominant_domain = None
    if url_domains:
        from collections import Counter as _Counter
        dominant_domain = _Counter(url_domains).most_common(1)[0][0]
        print(f" 🌐  Detected embedded domain: {dominant_domain}")

    # ── Build multiple smart queries ───────────────────────
    sents = [s.strip() for s in re.split(r'[.!?]', clean_text) if len(s.strip()) > 60]

    queries = []

    # Query 1: site-specific if a domain was detected in embedded links
    if dominant_domain:
        q_words = sents[0].split()[:20] if sents else clean_text.split()[:20]
        queries.append(f'site:{dominant_domain} ' + ' '.join(q_words))

    # Query 2: exact phrase from beginning (catches copy-paste from any site)
    if sents:
        queries.append('"' + ' '.join(sents[0].split()[:20]) + '"')

    # Query 3: exact phrase from middle (more distinctive than intro)
    if len(sents) > 2:
        mid = len(sents) // 2
        queries.append('"' + ' '.join(sents[mid].split()[:20]) + '"')

    # Query 4: exact phrase from near the end
    if len(sents) > 4:
        queries.append('"' + ' '.join(sents[-2].split()[:20]) + '"')

    # Query 5: top keywords combined — catches paraphrased content too
    keywords = _keywords(clean_text)
    from collections import Counter as _KCounter
    top_kw = [w for w, _ in _KCounter(keywords).most_common(10)]
    if top_kw:
        queries.append(' '.join(top_kw))

    # Fallback if nothing was built
    if not queries:
        queries.append('"' + ' '.join(clean_text.split()[:20]) + '"')
    metrics["query_build_seconds"] = time.perf_counter() - query_build_started

    # ── Call Tavily for each query, deduplicate results ────
    tavily_results = []
    seen_urls: set = set()

    def search_query(query: str) -> List[Dict[str, Any]]:
        try:
            res = requests.post("https://api.tavily.com/search", json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": 5
            }, timeout=20)
            res.raise_for_status()
            return res.json().get("results", [])
        except Exception as e:
            print(f"  ❌  Tavily error on query '{query}': {e}")
            return []

    search_started = time.perf_counter()
    api_key = _tavily_key()
    metrics["search_queries_fired"] = len(queries)
    for query in queries:
        print(f" 👉  Query: {query}")
    # Search queries run concurrently; executor.map keeps query order stable.
    with ThreadPoolExecutor(max_workers=len(queries)) as executor:
        for query_results in executor.map(search_query, queries):
            for r in query_results:
                if r.get("url") and r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    tavily_results.append(r)
    metrics["tavily_search_seconds"] = time.perf_counter() - search_started
    metrics["search_seconds"] = metrics["tavily_search_seconds"]
    metrics["unique_urls_returned"] = len(seen_urls)

    if not tavily_results:
        return finish({
            'matches': [], 'sentence_matches': [],
            'overall_pct': 0.0,
            'verdict': 'No Match Found',
            'level': 'safe', 'icon': '🟢',
        })

    # ── Extract URLs directly embedded in the student text ──
    embedded_urls = re.findall(
        r'https?://[^ \t\n\)\]\'"<>]+', clean_text
    )
    # Deduplicate and limit to 5 embedded URLs
    seen_embedded: set = set()
    unique_embedded = []
    for u in embedded_urls:
        u = u.rstrip('.,)')
        if u not in seen_embedded:
            seen_embedded.add(u)
            unique_embedded.append(u)
        if len(unique_embedded) >= 5:
            break

    # Add embedded URLs as synthetic Tavily results so they get scored
    embedded_seen_urls = {r.get("url") for r in tavily_results}
    for eu in unique_embedded:
        if eu not in embedded_seen_urls:
            tavily_results.append({
                "url":     eu,
                "title":   eu,
                "content": "",
            })
            print(f"  🔗  Added embedded URL for scoring: {eu}")

    # Count and remove social-network URLs before either extraction or scoring.
    allowed_results = []
    for result in tavily_results:
        if _is_blocklisted_url(result.get("url", "")):
            metrics["urls_skipped_blocklist"] += 1
        else:
            allowed_results.append(result)
    tavily_results = allowed_results

    # ── Batch-fetch page content via Tavily Extract ──────
    all_urls = [r.get("url","") for r in tavily_results if r.get("url")]
    extract_started = time.perf_counter()
    tavily_extracted = _fetch_via_tavily_extract(all_urls)
    metrics["extract_seconds"] = time.perf_counter() - extract_started
    print(f"  ✅  Tavily Extract got content for {len(tavily_extracted)}/{len(all_urls)} URLs")

    # Direct HTTP fallbacks run concurrently, capped at eight workers.
    direct_urls = [url for url in all_urls if not tavily_extracted.get(url)]
    fetch_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=min(8, len(direct_urls)) or 1) as executor:
        direct_fetches = dict(zip(direct_urls, executor.map(
            _fetch_page_text_with_status, direct_urls
        )))
    metrics["fetch_seconds"] = time.perf_counter() - fetch_started

    # ── Score each result ──────────────────────────────────
    matches:  List[Dict[str, Any]] = []
    snippets: List[Dict[str, str]] = []

    for result in tavily_results:
        url     = result.get("url", "")
        title   = result.get("title", "")
        snippet = result.get("content", "") or result.get("snippet", "")

        if not url:
            continue

        # Priority: Tavily Extract > direct HTTP > snippet
        fetched = tavily_extracted.get(url, "")
        if fetched:
            metrics["pages_fetched_ok"] += 1
            metrics["pages_rescued_by_extract"] += 1
        else:
            fetched, fetch_status = direct_fetches.get(url, ("", "failed"))
            if fetched:
                metrics["pages_fetched_ok"] += 1
            else:
                metrics["pages_blocked"] += 1
                metrics["pages_blocked_or_failed"] += 1
                if fetch_status == "403":
                    metrics["pages_403"] += 1
                elif fetch_status == "timeout":
                    metrics["pages_timeout"] += 1
                elif fetch_status == "empty":
                    metrics["pages_empty"] += 1
                else:
                    metrics["pages_other_failed"] += 1

        # If fetch was blocked, use Tavily snippet as reference text.
        # Also strip embedded markdown URLs from student text before scoring
        # so the URL strings themselves don't inflate the score.
        student_clean = re.sub(r'https?://\S+', ' ', clean_text)
        student_clean = re.sub(r'\s+', ' ', student_clean).strip()

        if fetched and len(fetched) > 300:
            reference = fetched
        elif snippet and len(snippet) > 50:
            # Expand snippet by repeating key phrases — gives scorer more signal
            reference = (snippet + " ") * 3
        else:
            reference = snippet or ""

        if reference:
            metrics["sources_scored"] += 1
            score_started = time.perf_counter()
            pct = round(_score_against_page(student_clean, reference, metrics) * 100, 1)
            metrics["scoring_seconds"] += time.perf_counter() - score_started
        else:
            pct = 0.0

        # Boost score for embedded URLs: if this URL was directly in the
        # student text, it is a near-certain source — apply a minimum floor.
        url_in_text = url.split("?")[0].rstrip("/") 
        if url_in_text in clean_text and pct < EMBEDDED_URL_SCORE_FLOOR:
            pct = max(pct, EMBEDDED_URL_SCORE_FLOOR)
            print(f"  🔗  {url} — embedded in text, boosted to {pct}%")
        else:
            print(f"  📊  {url} → {pct}%")

        display_title = title if (title and title != url) else (
            url.split('/')[-1].replace('-', ' ').replace('_', ' ').title() or url
        )

        matches.append({
            'url':     url,
            'title':   display_title,
            'snippet': snippet[:300] if snippet else url,
            'pct':     pct,
        })
        snippets.append({
            'url':       url,
            'text':      snippet,
            'full_text': fetched,
        })

    # ── Sort + overall score ───────────────────────────────
    matches.sort(key=lambda x: -x['pct'])
    top_scores = [m['pct'] for m in matches[:3]]
    if top_scores:
        top3_average = sum(top_scores) / len(top_scores)
        overall = round(
            top_scores[0] * OVERALL_TOP_SOURCE_WEIGHT
            + top3_average * OVERALL_TOP3_AVERAGE_WEIGHT,
            1,
        )
    else:
        overall = 0.0

    # ── Sentence-level breakdown ───────────────────────────
    score_started = time.perf_counter()
    sent_matches = _sentence_level_matches(clean_text, snippets, metrics)
    metrics["scoring_seconds"] += time.perf_counter() - score_started

    # ── Verdict ───────────────────────────────────────────
    verdict, level, icon = 'No Match Found', 'safe', '🟢'
    if matches and matches[0]['pct'] >= HIGH_SOURCE_VERDICT_THRESHOLD:
        verdict, level, icon = 'High Web Plagiarism', 'danger', '🔴'
    else:
        for threshold, lbl, lv, ic in THRESHOLDS:
            if overall >= threshold:
                verdict, level, icon = lbl, lv, ic
                break

    return finish({
        'matches':          matches,
        'sentence_matches': sent_matches,
        'overall_pct':      overall,
        'verdict':          verdict,
        'level':            level,
        'icon':             icon,
    })