import logging

from flask import current_app


logger = logging.getLogger(__name__)
FALLBACK_SUMMARY = (
    "AI summary temporarily unavailable due to network or API constraints, "
    "but web search results are intact."
)


def generate_ai_report(student_text, urls):
    """Generate a Gemini report, returning summary text and unavailable state."""
    if not urls:
        return "No significant internet matches found.", False

    api_key = (current_app.config.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        logger.warning("Gemini report skipped because GEMINI_API_KEY is not configured.")
        return FALLBACK_SUMMARY, True

    model = (current_app.config.get("GEMINI_MODEL") or "").strip()
    if not model:
        logger.error("Gemini report skipped because GEMINI_MODEL is empty.")
        return FALLBACK_SUMMARY, True

    try:
        timeout_ms = max(1, int(current_app.config.get("GEMINI_TIMEOUT_MS", 30000)))
    except (TypeError, ValueError):
        logger.warning("Invalid GEMINI_TIMEOUT_MS; using the 30000 ms default.")
        timeout_ms = 30000

    prompt = (
        f"Act as an expert academic plagiarism investigator. "
        f"A student submitted text that directly matched these exact websites online: {', '.join(urls)}.\n\n"
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
        return FALLBACK_SUMMARY, True

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        summary = getattr(response, "text", None)
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("Gemini returned an empty report.")
        return summary.strip(), False
    except APIError:
        logger.exception("Gemini API request failed while generating a report with model %r.", model)
        return FALLBACK_SUMMARY, True
    except (httpx.TimeoutException, httpx.TransportError, TimeoutError, ConnectionError):
        logger.exception("Gemini request timed out or could not connect using model %r.", model)
        return FALLBACK_SUMMARY, True
    except Exception:
        logger.exception("Unexpected error while generating a Gemini report with model %r.", model)
        return FALLBACK_SUMMARY, True
