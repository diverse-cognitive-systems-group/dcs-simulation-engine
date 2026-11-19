"""Compare player inputs, played conversations, and independent opening scenes."""

from functools import cache

import numpy as np

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MEDIUM_DISTANCE = 0.30
HIGH_DISTANCE = 0.60


@cache
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_ID, device="cpu")


def _samples(roots):
    inputs, conversations, openings = [], [], []
    paths = []

    def visit(session, history, number):
        session["path_number"] = number
        session["path_label"] = f"{'Branch' if '.' in number else 'Session'} {number}"
        dialogue = history.copy()
        if any(part.prompt for part in session["parts"] if not isinstance(part, dict)):
            paths.append(session)
            conversations.append(dialogue)
        branch = 0
        for part in session["parts"]:
            if isinstance(part, dict):
                branch += 1
                visit(part, dialogue, f"{number}.{branch}")
                continue
            replies = [event["content"].strip() for event in part.output if event["source"] == "npc" and event["content"].strip()]
            if part.prompt:
                prompt = part.prompt["content"].strip()
                inputs.append([prompt])
                dialogue.append(prompt)
            elif replies:
                openings.append(replies)
            dialogue.extend(replies)

    for index, root in enumerate(roots, 1):
        visit(root, [], str(index))
    return {
        "Player input diversity": inputs,
        "Conversation diversity": conversations,
        "Opening scene diversity": openings,
    }, paths


def _unit_centroids(samples, vectors):
    centroids = np.array([np.mean([vectors[text] for text in sample], axis=0) for sample in samples], dtype=np.float64)
    return centroids / np.linalg.norm(centroids, axis=1, keepdims=True)


def _distance_summary(distances):
    count = len(distances)
    pairs = distances[np.triu_indices(count, k=1)]
    score = float(pairs.mean())
    bands = ("Low", "Medium", "High")
    bins = (MEDIUM_DISTANCE, HIGH_DISTANCE)
    distribution = dict(zip(bands, np.bincount(np.digitize(pairs, bins), minlength=3).tolist(), strict=True))

    # Count connected groups of two or more samples linked by low-distance pairs.
    seen = np.zeros(count, dtype=bool)
    groups = 0
    for index in range(count):
        if seen[index]:
            continue
        seen[index] = True
        pending = [index]
        while pending:
            current = pending.pop()
            neighbors = np.flatnonzero((distances[current] < MEDIUM_DISTANCE) & ~seen)
            seen[neighbors] = True
            pending.extend(neighbors)
            if current == index and neighbors.size:
                groups += 1

    return {
        "score": score,
        "band": bands[np.digitize(score, bins)],
        "distribution": distribution,
        "groups": groups,
        "isolated": int(((distances < HIGH_DISTANCE).sum(axis=1) == 1).sum()),
        "pairs": len(pairs),
    }


def _compare_paths(paths, distances):
    order = [0]
    remaining = list(range(1, len(paths)))
    while remaining:
        following = min(remaining, key=distances[order[-1]].__getitem__)
        remaining.remove(following)
        order.append(following)

    for index, path in enumerate(paths):
        values = distances[index]
        nearest = min((other for other in range(len(paths)) if other != index), key=values.__getitem__)
        path["distances"] = values[order].tolist()
        path["closest"] = (paths[nearest]["path_number"], paths[nearest]["path_label"], values[nearest])
    return [paths[index] for index in order]


def semantic_diversity(roots):
    """Return counts and mean cosine distances for the three coverage measures."""
    groups, paths = _samples(roots)
    rows = [{"label": label, "count": len(samples), "score": None} for label, samples in groups.items()]
    texts = list(dict.fromkeys(text for samples in groups.values() if len(samples) >= 2 for sample in samples for text in sample))
    if not texts:
        return rows, [], ""
    try:
        model = _model()
    except ImportError:
        return rows, [], "Install sentence-transformers in the reporting environment to compute semantic distances."
    except OSError:
        return rows, [], f"Could not load {MODEL_ID}. Cache the model locally or allow its first download."
    vectors = dict(zip(texts, model.encode(texts, normalize_embeddings=True, show_progress_bar=False), strict=True))
    for row in rows:
        if row["count"] >= 2:
            unit = _unit_centroids(groups[row["label"]], vectors)
            distances = 1 - np.clip(unit @ unit.T, -1, 1)
            row.update(_distance_summary(distances))
            if row["label"] == "Conversation diversity":
                paths = _compare_paths(paths, distances)
    return rows, paths, ""
