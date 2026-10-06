from time import perf_counter

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def main():
    passages = [
        {
            "name": "verify_payment",
            "text": (
                "Function: verify_payment(signature)\n"
                "Description: Verify that a payment signature is authentic.\n"
                "Code:\n"
                "def verify_payment(signature):\n"
                "    return signature == 'valid'\n"
            ),
        },
        {
            "name": "resize_profile_picture",
            "text": (
                "Function: resize_profile_picture(image)\n"
                "Description: Resize an uploaded profile picture.\n"
                "Code:\n"
                "def resize_profile_picture(image):\n"
                "    return image.resize((128, 128))\n"
            ),
        },
        {
            "name": "create_booking",
            "text": (
                "Function: create_booking(user_id)\n"
                "Description: Create a booking record for a user.\n"
                "Code:\n"
                "def create_booking(user_id):\n"
                "    return {'user_id': user_id, 'status': 'pending'}\n"
            ),
        },
    ]

    question = "Where do we check whether a payment is authentic?"

    started = perf_counter()
    model = SentenceTransformer(MODEL_NAME, device="cpu")
    load_seconds = perf_counter() - started

    started = perf_counter()

    passage_embeddings = model.encode(
        [passage["text"] for passage in passages],
        batch_size=4,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    query_embedding = model.encode(
        [QUERY_PREFIX + question],
        batch_size=1,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    embedding_seconds = perf_counter() - started

    assert passage_embeddings.shape == (3, 384)
    assert query_embedding.shape == (1, 384)
    assert np.isfinite(passage_embeddings).all()
    assert np.isfinite(query_embedding).all()

    scores = (query_embedding @ passage_embeddings.T)[0]
    ranking = np.argsort(-scores)

    print(f"Model: {MODEL_NAME}")
    print(f"Device: {model.device}")
    print(f"Passage embeddings: {passage_embeddings.shape}")
    print(f"Query embedding: {query_embedding.shape}")
    print(f"Model load time: {load_seconds:.2f} seconds")
    print(f"Embedding time: {embedding_seconds:.2f} seconds")
    print(f"\nQuestion: {question}")
    print("\nResults:")

    for rank, index in enumerate(ranking, start=1):
        print(
            f"{rank}. {passages[index]['name']} "
            f"| similarity: {scores[index]:.4f}"
        )

    top_result = passages[ranking[0]]["name"]
    print(f"\nPayment candidate ranked first: {top_result == 'verify_payment'}")


if __name__ == "__main__":
    main()