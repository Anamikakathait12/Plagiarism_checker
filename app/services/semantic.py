from sklearn.metrics.pairwise import cosine_similarity

_model = None


def _get_model():
    """Load the sentence-transformer model on first use (keeps app start-up fast)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        print("Loading paraphrase-detection model... (first use only)")
        # 'all-MiniLM-L6-v2' is lightweight and good at catching paraphrasing
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def calculate_similarity(documents):
    """
    Takes a list of document texts, converts them to semantic vectors,
    and returns a matrix of their cosine-similarity scores.
    """
    if not documents:
        return []

    embeddings = _get_model().encode(documents)
    return cosine_similarity(embeddings)
