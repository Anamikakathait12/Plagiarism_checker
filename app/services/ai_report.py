import logging

from flask import current_app


logger = logging.getLogger(__name__)

# Scores below 5% are not reported as significant matched sources.
MIN_REPORTED_SCORE = 5.0


def _fallback_summary(scan_result):
    """Build a deterministic report from internet-scan results."""
    overall = float(scan_result.get("overall_pct", 0.0))
    verdict = scan_result.get("verdict", "No Match Found")
    matches = scan_result.get("matches", [])
    highest_score = max((float(match.get("pct", 0.0)) for match in matches), default=0.0)
    metrics = scan_result.get("metrics", {})
    sources_checked = metrics.get("sources_scored", len(matches))
    summary = f"Internet scan: {overall:.1f}% overall — {verdict}."
    if verdict.strip().lower() == "no match found" or highest_score < MIN_REPORTED_SCORE:
        return (
            f"Internet scan: {overall:.1f}% overall, no significant matches found "
            f"across {sources_checked} sources checked."
        )

    top_matches = [
        match for match in matches
        if float(match.get("pct", 0.0)) >= MIN_REPORTED_SCORE
    ][:2]
    if top_matches:
        sources = ", ".join(
            f"{match.get('url', 'Unknown URL')} ({float(match.get('pct', 0.0)):.1f}%)"
            for match in top_matches
        )
        return f"{summary} Top matched sources: {sources}."
    return (
        f"Internet scan: {overall:.1f}% overall, no significant matches found "
        f"across {sources_checked} sources checked."
    )


def generate_ai_report(student_text, urls):
    """Generate a Gemini report, returning summary text and unavailable state."""
    scan_result = urls if isinstance(urls, dict) else {}
    source_urls = (
        [match.get("url", "") for match in scan_result.get("matches", []) if match.get("url")]
        if scan_result else urls
    )
    fallback = _fallback_summary(scan_result)
    if not source_urls:
        logger.info("AI report summary source: local fallback.")
        return fallback, False

    api_key = (current_app.config.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        logger.warning("Gemini report skipped because GEMINI_API_KEY is not configured.")
        logger.info("AI report summary source: local fallback.")
        return fallback, True

    model = (current_app.config.get("GEMINI_MODEL") or "").strip()
    if not model:
        logger.error("Gemini report skipped because GEMINI_MODEL is empty.")
        logger.info("AI report summary source: local fallback.")
        return fallback, True

    try:
        timeout_ms = min(
            15000,
            max(1, int(current_app.config.get("GEMINI_TIMEOUT_MS", 15000))),
        )
    except (TypeError, ValueError):
        logger.warning("Invalid GEMINI_TIMEOUT_MS; using the 15000 ms default.")
        timeout_ms = 15000

    prompt = (
        f"Act as an expert academic plagiarism investigator. "
        f"A student submitted text that directly matched these exact websites online: {', '.join(source_urls)}.\n\n"
        f"Student Text Snippet: {student_text[:1500]}\n\n"
        f"Write a short, professional 2-sentence report for the teacher stating that the text appears "
        f"to be copied from the internet, and name the specific website URLs."
    )

    try:
        from google import genai
        from google.genai import types
        from google.genai.errors import APIError
        import httpx
    except ImportError:
        logger.exception("Gemini report unavailable because the Gemini SDK dependencies could not be imported.")
        logger.info("AI report summary source: local fallback.")
        return fallback, True

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=timeout_ms,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        summary = getattr(response, "text", None)
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("Gemini returned an empty report.")
        logger.info("AI report summary source: Gemini.")
        return summary.strip(), False
    except APIError:
        logger.exception("Gemini API request failed while generating a report with model %r.", model)
        logger.info("AI report summary source: local fallback.")
        return fallback, True
    except (httpx.TimeoutException, httpx.TransportError, TimeoutError, ConnectionError):
        logger.exception("Gemini request timed out or could not connect using model %r.", model)
        logger.info("AI report summary source: local fallback.")
        return fallback, True
    except Exception:
        logger.exception("Unexpected error while generating a Gemini report with model %r.", model)
        logger.info("AI report summary source: local fallback.")
        return fallback, True
