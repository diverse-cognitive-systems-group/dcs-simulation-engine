"""Compare player inputs, played conversations, and independent opening scenes."""

from functools import cache

import numpy as np

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"


@cache
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_ID, device="cpu")


def _samples(roots):
    inputs, conversations, openings = [], [], []

    def visit(session, history):
        dialogue = history.copy()
        played = False
        for part in session["parts"]:
            if isinstance(part, dict):
                visit(part, dialogue)
                continue
            replies = [event["content"].strip() for event in part.output if event["source"] == "npc" and event["content"].strip()]
            if part.prompt:
                prompt = part.prompt["content"].strip()
                inputs.append([prompt])
                dialogue.append(prompt)
                played = True
            elif replies:
                openings.append(replies)
            dialogue.extend(replies)
        if played:
            conversations.append(dialogue)

    for root in roots:
        visit(root, [])
    return {
        "Player input diversity": inputs,
        "Conversation diversity": conversations,
        "Opening scene diversity": openings,
    }


def _mean_distance(samples, vectors):
    centroids = np.array([np.mean([vectors[text] for text in sample], axis=0) for sample in samples], dtype=np.float64)
    unit = centroids / np.linalg.norm(centroids, axis=1, keepdims=True)
    count = len(samples)
    # The squared vector sum contains every pairwise dot product twice, plus the unit-vector diagonals.
    total = unit.sum(axis=0)
    similarity = (total @ total - count) / (count * (count - 1))
    return float(1 - np.clip(similarity, -1, 1))


def semantic_diversity(roots):
    """Return counts and mean cosine distances for the three coverage measures."""
    groups = _samples(roots)
    rows = [{"label": label, "count": len(samples), "score": None} for label, samples in groups.items()]
    texts = list(dict.fromkeys(text for samples in groups.values() if len(samples) >= 2 for sample in samples for text in sample))
    if not texts:
        return rows, ""
    try:
        model = _model()
    except ImportError:
        return rows, "Install sentence-transformers in the reporting environment to compute semantic distances."
    except OSError:
        return rows, f"Could not load {MODEL_ID}. Cache the model locally or allow its first download."
    vectors = dict(zip(texts, model.encode(texts, normalize_embeddings=True, show_progress_bar=False), strict=True))
    for row in rows:
        if row["count"] >= 2:
            row["score"] = _mean_distance(groups[row["label"]], vectors)
    return rows, ""
