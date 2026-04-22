import io
import torch
from PIL import Image
from typing import List, Optional, Union
from pathlib import Path
from loguru import logger

from config import embedding

torch.serialization.add_safe_globals(["_ LOAD STATE DICT SKIP"])


def load_image_from_url(url: str) -> Optional[Image.Image]:
    try:
        import requests as _req
        response = _req.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        if image.mode != "RGB":
            image = image.convert("RGB")
        return image
    except Exception as e:
        logger.warning(f"Failed to load image {url}: {e}")
        return None


def load_image_from_path(path: Union[str, Path]) -> Optional[Image.Image]:
    try:
        image = Image.open(path)
        if image.mode != "RGB":
            image = image.convert("RGB")
        return image
    except Exception as e:
        logger.warning(f"Failed to load image {path}: {e}")
        return None


class SigLIPEmbeddingModel:
    def __init__(self, model_name: str = None, device: str = None):
        self.model_name = model_name or embedding.model
        actual_device = device or embedding.device
        if actual_device == "cuda" and not torch.cuda.is_available():
            actual_device = "cpu"
        self.device = actual_device
        self._processor = None
        self._model = None
        self._text_model = None

    def _load(self):
        if self._model is not None:
            return

        logger.info(f"Loading SigLIP model: {self.model_name} on {self.device}")

        from transformers import AutoProcessor, AutoModel

        if self.device == "cuda":
            self._model = AutoModel.from_pretrained(
                self.model_name,
                device_map="auto",
                torch_dtype=torch.float32,
            )
        else:
            self._model = AutoModel.from_pretrained(
                self.model_name,
            ).to(self.device)

        self._processor = AutoProcessor.from_pretrained(self.model_name)
        self._model.eval()

        logger.success(f"SigLIP model loaded successfully")

    def get_image_embeddings(self, images: List[Image.Image]) -> List[List[float]]:
        self._load()

        if not images:
            return []

        inputs = self._processor(images=images, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model.get_image_features(**inputs)
            if hasattr(outputs, 'pooler_output'):
                embeddings = outputs.pooler_output.cpu().float().numpy().tolist()
            else:
                embeddings = outputs.last_hidden_state[:, 0].cpu().float().numpy().tolist()

        return embeddings

    def get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        self._load()

        if not texts:
            return []

        inputs = self._processor(
            text=texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model.get_text_features(**inputs)
            if hasattr(outputs, 'pooler_output'):
                embeddings = outputs.pooler_output.cpu().float().numpy().tolist()
            else:
                embeddings = outputs.last_hidden_state[:, 0].cpu().float().numpy().tolist()

        return embeddings

    def encode_image_from_url(self, url: str) -> Optional[List[float]]:
        image = load_image_from_url(url)
        if image is None:
            return None

        embeddings = self.get_image_embeddings([image])
        return embeddings[0] if embeddings else None

    def encode_image_from_path(self, path: Union[str, Path]) -> Optional[List[float]]:
        image = load_image_from_path(path)
        if image is None:
            return None

        embeddings = self.get_image_embeddings([image])
        return embeddings[0] if embeddings else None

    def encode_text(self, text: str) -> Optional[List[float]]:
        embeddings = self.get_text_embeddings([text])
        return embeddings[0] if embeddings else None

    def batch_encode_images_from_urls(self, urls: List[str], batch_size: int = None) -> List[Optional[List[float]]]:
        bs = batch_size or embedding.batch_size
        results = []

        for i in range(0, len(urls), bs):
            batch_urls = urls[i:i + bs]
            logger.debug(f"Encoding batch {i // bs + 1}: {len(batch_urls)} images")

            images = []
            for url in batch_urls:
                img = load_image_from_url(url)
                images.append(img if img else Image.new("RGB", (384, 384)))

            embeddings = self.get_image_embeddings(images)

            for j, emb in enumerate(embeddings):
                if images[j].size == (384, 384) and sum(emb) == 0:
                    results.append(None)
                else:
                    results.append(emb)

        return results

    def encode_product(self, image_url: str, info_text: str = "") -> dict:
        image_emb = None
        info_emb = None

        if image_url:
            image_emb = self.encode_image_from_url(image_url)

        if info_text:
            info_emb = self.encode_text(info_text)

        return {
            "image_embedding": image_emb,
            "info_embedding": info_emb,
        }


_model_instance: Optional[SigLIPEmbeddingModel] = None


def get_embedding_model() -> SigLIPEmbeddingModel:
    global _model_instance
    if _model_instance is None:
        _model_instance = SigLIPEmbeddingModel()
    return _model_instance


def encode_product_image(image_url: str) -> Optional[List[float]]:
    model = get_embedding_model()
    return model.encode_image_from_url(image_url)


def encode_product_info(info_text: str) -> Optional[List[float]]:
    model = get_embedding_model()
    return model.encode_text(info_text)


def encode_product(image_url: str, info_text: str = "") -> dict:
    model = get_embedding_model()
    return model.encode_product(image_url, info_text)