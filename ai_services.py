import google.generativeai as genai


def generate_ai_report(student_text, urls):
    """Use Gemini to generate a professional plagiarism investigator report."""
    if not urls:
        return "No significant internet matches found."

    prompt = (
        f"Act as an expert academic plagiarism investigator. "
        f"A student submitted text that directly matched these exact websites online: {', '.join(urls)}.\n\n"
        f"Student Text Snippet: {student_text[:1500]}\n\n"
        f"Write a short, professional 2-sentence report for the teacher stating that the text appears "
        f"to be copied from the internet, and name the specific website URLs."
    )
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        return response.text
    except Exception:
        return "AI Report generation failed due to an API error."
