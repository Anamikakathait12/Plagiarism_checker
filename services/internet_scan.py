import re
import requests
from google import genai
from flask import current_app


def check_internet_similarity(text: str) -> list:
    """
    Send the first meaningful sentence to the Tavily search API.
    Returns a list of URLs where the text was found online.
    """
    print("Checking internet plagiarism via Tavily API...")
    try:
        clean_text = re.sub(r'\s+', ' ', text)
        sentences = [s.strip() for s in re.split(r'[.!?]', clean_text) if len(s.strip()) > 60]

        if not sentences:
            return []

        query = '"' + " ".join(sentences[0].split()[:30]) + '"'
        print(f"Searching Tavily for: {query}")

        api_key = current_app.config.get('TAVILY_API_KEY')
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
            },
            timeout=10,
        )
        response.raise_for_status()

        links = []
        for result in response.json().get("results", []):
            url = result.get("url")
            if url and url not in links:
                links.append(url)

        print("Found URLs:", links)
        return links

    except Exception as e:
        print("Tavily API error:", e)
        return []


def generate_ai_report(student_text: str, urls: list) -> str:
    """
    Use Gemini to write a short investigator report for the teacher
    based on matching URLs found online.
    """
    if not urls:
        return "No significant internet matches found."

    try:
        api_key = current_app.config.get('GEMINI_API_KEY')

        # New google-genai SDK (replaces deprecated google.generativeai)
        client = genai.Client(api_key=api_key)

        prompt = (
            "Act as an expert academic plagiarism investigator. "
            f"A student submitted text that directly matched these exact websites online: {', '.join(urls)}.\n\n"
            f"Student Text Snippet: {student_text[:1500]}\n\n"
            "Write a short, professional 2-sentence report for the teacher stating that the text "
            "appears to be copied from the internet, and name the specific website URLs."
        )

        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        return response.text

    except Exception as e:
        print("Gemini AI report error:", e)
        return "AI Report generation failed due to an API error."
