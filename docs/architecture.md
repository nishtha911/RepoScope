## Track 2 local setup

Use Python 3.11 with the project's virtual environment active.

Run from the backend directory:

```powershell
python -m pip install "torch==2.14.1+cpu" --index-url [https://download.pytorch.org/whl/cpu](https://download.pytorch.org/whl/cpu)
python -m pip install -r requirements.txt
python -m pip check
```

Install CPU-only PyTorch first, then install the remaining dependencies.

Verify the runtime:

```powershell
python -c "import torch, sentence_transformers; print('PyTorch:', torch.__version__); print('CUDA build:', torch.version.cuda); print('Sentence Transformers:', sentence_transformers.__version__)"
```

For this CPU setup, CUDA build should print None.

These versions have passed import and dependency checks on Windows with
Python 3.11.9. The embedding experiment is still pending.



## Track 2 embedding spike

Tested on 6 October 2026 using Python 3.11.9 on Windows.

- Model: BAAI/bge-small-en-v1.5
- Device: CPU
- PyTorch: 2.14.1+cpu
- Sentence Transformers: 6.1.0
- Passage embedding shape: (3, 384)
- Query embedding shape: (1, 384)
- First-run model load time, including downloads: 34.44 seconds
- Embedding generation time: 0.17 seconds

Query: Where do we check whether a payment is authentic?

Ranking:
1. verify_payment — 0.8019
2. create_booking — 0.5251
3. resize_profile_picture — 0.4007

The expected payment candidate ranked first.

This is a small feasibility experiment using code plus English
descriptions. It is not a production retrieval benchmark.