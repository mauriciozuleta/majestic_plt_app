"""Local sentence embeddings for the knowledge base, ported from the
prelim_training_tool app (Xenova/all-MiniLM-L6-v2, quantized ONNX). Same model
and same recipe as its embed.ts — tokenize, run the ONNX graph, mean-pool over
the attention mask, L2-normalize — so vectors are 384-dim unit vectors and a
plain dot product is cosine similarity. Runs offline; the model files live in
`models/all-MiniLM-L6-v2/` next to this module.
"""

import base64
import os
import threading
from pathlib import Path

import numpy as np

MODEL_DIR = Path(__file__).resolve().parent / 'models' / 'all-MiniLM-L6-v2'
MODEL_ID = 'Xenova/all-MiniLM-L6-v2'
MAX_TOKENS = 512
BATCH_SIZE = 16

_lock = threading.Lock()
_session = None
_tokenizer = None
_input_names: set[str] = set()


def _load():
    global _session, _tokenizer, _input_names
    with _lock:
        if _session is not None:
            return
        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_path = MODEL_DIR / 'onnx' / 'model_quantized.onnx'
        tokenizer_path = MODEL_DIR / 'tokenizer.json'
        if not model_path.exists() or not tokenizer_path.exists():
            raise FileNotFoundError(f'Embedding model files not found in {MODEL_DIR}')
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        tokenizer.enable_padding()
        options = ort.SessionOptions()
        options.log_severity_level = 3
        # Half the cores by default (EMBED_THREADS overrides): a long embedding job
        # (a big document) must not take the whole machine from the app and the chat.
        options.intra_op_num_threads = int(os.environ.get('EMBED_THREADS') or max(2, (os.cpu_count() or 4) // 2))
        options.inter_op_num_threads = 1
        _session = ort.InferenceSession(str(model_path), options, providers=['CPUExecutionProvider'])
        _tokenizer = tokenizer
        _input_names = {node.name for node in _session.get_inputs()}


def is_available() -> bool:
    try:
        _load()
        return True
    except Exception:
        return False


def embed_texts(texts: list[str]) -> list[np.ndarray]:
    """One normalized float32 vector per text."""
    if not texts:
        return []
    _load()
    vectors: list[np.ndarray] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        encodings = _tokenizer.encode_batch(batch)
        ids = np.array([e.ids for e in encodings], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        feeds = {'input_ids': ids, 'attention_mask': mask}
        if 'token_type_ids' in _input_names:
            feeds['token_type_ids'] = np.zeros_like(ids)
        hidden = _session.run(None, feeds)[0]  # (batch, tokens, 384)
        weights = mask[:, :, None].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        pooled /= np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
        vectors.extend(pooled.astype(np.float32))
    return vectors


def embed_text(text: str) -> np.ndarray:
    return embed_texts([text])[0]


def encode_vector(vector: np.ndarray) -> str:
    """Compact JSON-safe form for storing in a .rag.json chunk."""
    return base64.b64encode(vector.astype(np.float32).tobytes()).decode('ascii')


def decode_vector(encoded: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(encoded), dtype=np.float32)
