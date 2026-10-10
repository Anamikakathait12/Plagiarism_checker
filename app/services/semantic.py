_model = None
_use_embeddings = None


def _get_model():
    """Load the sentence-transformer model on first use.
    Returns None if sentence-transformers isn't installed (lightweight deploys)."""
    global _model, _use_embeddings
    if _use_embeddings is None:
        try:
            from sentence_transformers import SentenceTransformer
            print("Loading paraphrase-detection model... (first use only)")
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            _use_embeddings = True
        except ImportError:
            print("sentence-transformers not installed: using TF-IDF similarity")
            _use_embeddings = False
    return _model


def calculate_similarity(documents):
    """
    Takes a list of document texts and returns a matrix of cosine-similarity
    scores. Uses sentence embeddings when available, otherwise TF-IDF.
    """
    if not documents:
        return []

    from sklearn.metrics.pairwise import cosine_similarity

    model = _get_model()
    if model is not None:
        return cosine_similarity(model.encode(documents))

    from sklearn.feature_extraction.text import TfidfVectorizer
    vectors = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True).fit_transform(documents)
    return cosine_similarity(vectors)
