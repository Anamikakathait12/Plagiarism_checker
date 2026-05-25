"""
plagiarism_checker.py
=====================
Advanced Web Plagiarism Checker — drop this file in the same
folder as app.py and import check_internet_similarity from it.

Usage in app.py:
    from plagiarism_checker import check_internet_similarity
"""

from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Dict, List


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
#  TAVILY API KEY  ← paste yours here
# ─────────────────────────────────────────────
TAVILY_API_KEY = "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"

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
    if score < 0.3:  return score * 1.2
    if score < 0.6:  return 0.36 + (score - 0.3) * 1.5
    return min(1.0,  0.81 + (score - 0.6) * 0.95)


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
    try:
        res = requests.post("https://api.tavily.com/extract", json={
            "api_key": TAVILY_API_KEY,
            "urls": urls[:5],  # max 5 per call
        }, timeout=20)
        if res.status_code == 200:
            result_map = {}
            for r in res.json().get("results", []):
                url = r.get("url", "")
                raw = r.get("raw_content", "")
                if url and raw:
                    result_map[url] = raw
            return result_map
    except Exception as e:
        print(f"  ⚠️  Tavily extract error: {e}")
    return {}


def _fetch_page_text(url: str) -> str:
    """
    Fetch a single URL using direct HTTP.
    Falls back gracefully — Tavily extract is preferred (called in batch).
    """
    try:
        res = requests.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }, allow_redirects=True)
        if res.status_code == 200 and len(res.text) > 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header",
                              "aside", "form", "noscript", "iframe"]):
                tag.decompose()
            main = soup.find("main") or soup.find("article") or soup.find(id="content") or soup
            text = main.get_text(separator=" ", strip=True)
            if len(text) > 300:
                return text
    except Exception as e:
        print(f"  ⚠️  Could not fetch {url}: {e}")
    return ""


# ═════════════════════════════════════════════
#  MULTI-SIGNAL SCORER
# ═════════════════════════════════════════════

def _score_against_page(student_text: str, page_text: str) -> float:
    """
    4-signal calibrated similarity score (returns 0-1):
      1. Overall sequence match         (25%)
      2. Keyword overlap                (25%)
      3. 3-gram fingerprint overlap     (20%)
      4. 5-gram fingerprint overlap     (15%)
      5. Best sentence-level match      (15%)
    """
    if not page_text.strip():
        return 0.0

    src_cap = student_text[:3000].lower()
    ref_cap = page_text[:3000].lower()

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
    for sentence in _sentences(student_text)[:10]:          # cap for speed
        for passage in _passages(page_text, window=60, step=30)[:20]:
            sc      = _similarity(sentence, passage)
            sw      = set(_keywords(sentence))
            pw      = set(_keywords(passage))
            overlap = len(sw & pw) / max(len(sw), 1) if sw else 0.0
            combined = max(sc, overlap * 0.8)
            if combined > best_sent:
                best_sent = combined

    raw = (
        seq_score   * 0.25 +
        kw_overlap  * 0.25 +
        ng3         * 0.20 +
        ng5         * 0.15 +
        best_sent   * 0.15
    )
    return _calibrate(raw)


# ═════════════════════════════════════════════
#  SENTENCE-LEVEL MATCH DETECTOR
# ═════════════════════════════════════════════

def _sentence_level_matches(student_text: str,
                             snippets: List[Dict]) -> List[Dict[str, Any]]:
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
            for passage in _passages(ref, window=80, step=40):
                sc      = _similarity(sentence, passage)
                sw      = set(_keywords(sentence))
                pw      = set(_keywords(passage))
                overlap = len(sw & pw) / max(len(sw), 1) if sw else 0.0
                combined = max(sc, overlap * 0.80)
                if combined > best_score:
                    best_score = combined
                    best_match = passage[:200]
                    best_url   = snip.get('url', '')

        if best_score >= 0.25:
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
    print(" 🔬  Running advanced plagiarism scan...")

    clean_text = re.sub(r'\s+', ' ', text).strip()

    if len(clean_text.split()) < 10:
        return {
            'matches': [], 'sentence_matches': [],
            'overall_pct': 0.0,
            'verdict': 'Text Too Short',
            'level': 'caution', 'icon': '⚠️',
        }

    # ── Detect embedded source domains in the text ────────
    # Catches GFG/Wikipedia links embedded directly in the docx content
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

    # ── Call Tavily for each query, deduplicate results ────
    tavily_results = []
    seen_urls: set = set()

    for query in queries:
        print(f" 👉  Query: {query}")
        try:
            res = requests.post("https://api.tavily.com/search", json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced",
                "max_results": 5
            })
            res.raise_for_status()
            for r in res.json().get("results", []):
                if r.get("url") and r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    tavily_results.append(r)
        except Exception as e:
            print(f"  ❌  Tavily error on query '{query}': {e}")

    if not tavily_results:
        return {
            'matches': [], 'sentence_matches': [],
            'overall_pct': 0.0,
            'verdict': 'No Match Found',
            'level': 'safe', 'icon': '🟢',
        }

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

    # ── Batch-fetch page content via Tavily Extract ──────
    all_urls = [r.get("url","") for r in tavily_results if r.get("url")]
    tavily_extracted = _fetch_via_tavily_extract(all_urls)
    print(f"  ✅  Tavily Extract got content for {len(tavily_extracted)}/{len(all_urls)} URLs")

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
        fetched = tavily_extracted.get(url) or _fetch_page_text(url)

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

        pct = round(_score_against_page(student_clean, reference) * 100, 1) if reference else 0.0

        # Boost score for embedded URLs: if this URL was directly in the
        # student text, it is a near-certain source — apply a minimum floor.
        url_in_text = url.split("?")[0].rstrip("/") 
        if url_in_text in clean_text and pct < 30.0:
            pct = max(pct, 30.0)
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
    overall    = round(sum(top_scores) / len(top_scores), 1) if top_scores else 0.0

    # ── Sentence-level breakdown ───────────────────────────
    sent_matches = _sentence_level_matches(clean_text, snippets)

    # ── Verdict ───────────────────────────────────────────
    verdict, level, icon = 'No Match Found', 'safe', '🟢'
    for threshold, lbl, lv, ic in THRESHOLDS:
        if overall >= threshold:
            verdict, level, icon = lbl, lv, ic
            break

    return {
        'matches':          matches,
        'sentence_matches': sent_matches,
        'overall_pct':      overall,
        'verdict':          verdict,
        'level':            level,
        'icon':             icon,
    }