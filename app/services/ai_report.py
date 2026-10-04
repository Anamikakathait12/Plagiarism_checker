from flask import current_app


def generate_ai_report(student_text, urls):
    """Use Gemini to generate a professional plagiarism investigator report."""
    if not urls:
        return "No significant internet matches found."

    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        return "AI report unavailable: GEMINI_API_KEY is not configured."

    prompt = (
        f"Act as an expert academic plagiarism investigator. "
        f"A student submitted text that directly matched these exact websites online: {', '.join(urls)}.\n\n"
        f"Student Text Snippet: {student_text[:1500]}\n\n"
        f"Write a short, professional 2-sentence report for the teacher stating that the text appears "
        f"to be copied from the internet, and name the specific website URLs."
    )
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=current_app.config["GEMINI_MODEL"],
            contents=prompt,
        )
        return response.text
    except Exception:
        return "AI Report generation failed due to an API error."
