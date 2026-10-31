"""Local image engine: the models run inside the process with diffusers.

No external services:
- Create: Krea 2 Turbo (GGUF Q4), the best at nailing the app's style.
- Transform / edit / prepare for 3D: FLUX 3 Image Klein (GGUF Q8), the best at
  preserving the original when editing with reference images.

The transformers come from the GGUF files in MODELS_DIR; the remaining
components (Qwen3-VL 4B text encoder, VAE, scheduler and configs) are downloaded
from Hugging Face on first use and kept in its cache (HF_HOME). Only one model
is loaded at a time, with CPU offload: with the desktop open about 8 GB of VRAM
remain, and neither the encoder (8.8 GB) nor Krea Q4 fit whole. By default
layer-wise offload is used ("group", moves layers to the GPU with prefetch);
ENGINE_OFFLOAD=model moves whole models (faster when there is VRAM to spare).
"""

import gc
import io
import random
import threading

from PIL import Image

from .config import FLUX3_GGUF, FLUX3_REPO, KREA_GGUF, KREA_REPO, OFFLOAD

# Pixel size for each aspect ratio the app uses (multiples of 16, ~1 MP).
SIZES = {
    "9:16": (768, 1344),
    "16:9": (1344, 768),
    "1:1": (1024, 1024),
    "3:2": (1248, 832),
    "3:4": (896, 1152),
    "4:3": (1152, 896),
    "2:3": (832, 1248),
}


class LocalEngineError(RuntimeError):
    pass


class LocalEngine:
    def __init__(self):
        self.ready = False
        self.loaded: str | None = None  # "krea" | "flux3"
        self.pipe = None
        self.lock = threading.Lock()

    # ------------------------------------------------------------ estado
    def is_running(self) -> bool:
        return self.ready

    def ensure_running(self, timeout: float = 0) -> None:
        """Check that a GPU and the weights are present. Models load on first use."""
        import torch

        if not torch.cuda.is_available():
            raise LocalEngineError("No CUDA GPU available (Docker without --gpus?).")
        missing = [p.name for p in (KREA_GGUF, FLUX3_GGUF) if not p.exists()]
        if missing:
            raise LocalEngineError(f"Missing weights in {KREA_GGUF.parent}: {', '.join(missing)}.")
        self.ready = True

    def stop(self) -> None:
        with self.lock:
            self._unload()
        self.ready = False

    # ------------------------------------------------------------ carga
    def _unload(self) -> None:
        import torch

        self.pipe, self.loaded = None, None
        gc.collect()
        torch.cuda.empty_cache()

    def _use(self, name: str):
        if self.loaded == name:
            return self.pipe
        self._unload()
        self.pipe = self._load_krea() if name == "krea" else self._load_flux3()
        self.loaded = name
        return self.pipe

    @staticmethod
    def _load_krea():
        import torch
        from diffusers import GGUFQuantizationConfig, Krea2Pipeline, Krea2Transformer2DModel

        transformer = Krea2Transformer2DModel.from_single_file(
            str(KREA_GGUF), config=KREA_REPO, subfolder="transformer",
            quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
            dtype=torch.bfloat16,
        )
        pipe = Krea2Pipeline.from_pretrained(KREA_REPO, transformer=transformer, dtype=torch.bfloat16)
        if OFFLOAD == "model":
            pipe.enable_model_cpu_offload()
        else:
            pipe.enable_group_offload(onload_device=torch.device("cuda"), offload_type="leaf_level", use_stream=True)
        return pipe

    @staticmethod
    def _load_flux3():
        import torch
        from diffusers import ComponentsManager, Flux3Transformer2DModel, GGUFQuantizationConfig, ModularPipeline
        import gguf
        from diffusers.hooks import apply_group_offloading
        from diffusers.quantizers.gguf.utils import dequantize_gguf_tensor

        transformer = Flux3Transformer2DModel.from_single_file(
            str(FLUX3_GGUF), config=FLUX3_REPO, subfolder="transformer",
            quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
            dtype=torch.bfloat16,
        )
        manager = None
        if OFFLOAD == "model":
            manager = ComponentsManager()
            manager.enable_auto_cpu_offload(device="cuda")
        # Without the "prompt upsampler" (Qwen3.5 9B that rewrites the prompt): the
        # app's prompt is already detailed, and it doesn't fit alongside the rest.
        # `.blocks` is a copy.
        blocks = ModularPipeline.from_pretrained(FLUX3_REPO).blocks
        blocks.sub_blocks.pop("prompt_upsampler")
        pipe = blocks.init_pipeline(FLUX3_REPO, components_manager=manager)
        pipe.load_components(names=["text_encoder", "tokenizer", "vae"], dtype=torch.bfloat16)
        pipe.update_components(transformer=transformer)
        # The few BF16 layers in the GGUF (time embeddings) reach the computation
        # without being dequantized and fail: convert them to plain bf16 (they're small).
        for module in pipe.transformer.modules():
            for name, param in list(module.named_parameters(recurse=False)):
                if getattr(param, "quant_type", None) == gguf.GGMLQuantizationType.BF16:
                    module._parameters[name] = torch.nn.Parameter(
                        dequantize_gguf_tensor(param).to(torch.bfloat16), requires_grad=False)
        if OFFLOAD != "model":
            # The Q8 (6 GB) fits whole; layer offload would also strip the GGUF
            # type from the weights. Only the encoder (8.8 GB) is offloaded per layer.
            pipe.transformer.to("cuda")
            pipe.vae.to("cuda")
            apply_group_offloading(pipe.text_encoder, onload_device=torch.device("cuda"),
                                   offload_type="leaf_level", use_stream=True)
        return pipe

    @staticmethod
    def _png(image: Image.Image) -> tuple[bytes, str]:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue(), "image/png"

    # ------------------------------------------------------------ modelos
    def generate(self, prompt: str, aspect_ratio: str) -> tuple[bytes, str]:
        """Text to image with Krea 2 Turbo: 8 steps, no guidance."""
        import torch

        w, h = SIZES.get(aspect_ratio, SIZES["1:1"])
        with self.lock:
            pipe = self._use("krea")
            # Krea truncates the text at max_sequence_length (512 by default) and a
            # character with anatomy exceeds 900 tokens: without this the style is lost.
            tokens = len(pipe.tokenizer(prompt)["input_ids"])
            image = pipe(
                prompt, width=w, height=h, num_inference_steps=8, guidance_scale=0.0,
                max_sequence_length=max(512, -(-(tokens + 32) // 64) * 64),
                generator=torch.Generator("cpu").manual_seed(random.randint(0, 2**32 - 1)),
            ).images[0]
        return self._png(image)

    def edit(self, prompt: str, image_paths: list[str], aspect_ratio: str) -> tuple[bytes, str]:
        """Edit / multi-reference with FLUX 3 Image Klein: 16 steps, no guidance.

        FLUX 3 cites references as <ref_image_N>; the app's prompt says
        "the attached image" or "image 1/2", so the ordering is prepended.
        """
        import torch

        if not image_paths:
            raise LocalEngineError("Editing needs at least one reference image.")
        w, h = SIZES.get(aspect_ratio, SIZES["1:1"])
        refs = ", ".join(f"image {i + 1} = <ref_image_{i}>" for i in range(len(image_paths)))
        text = f"Reference images, in order: {refs}.\n\n{prompt}"
        images = [Image.open(p).convert("RGB") for p in image_paths]
        with self.lock:
            pipe = self._use("flux3")
            image = pipe(
                prompt=text, image=images, width=w, height=h, num_inference_steps=16,
                generator=torch.Generator("cpu").manual_seed(random.randint(0, 2**32 - 1)),
                output="images",
            )[0]
        return self._png(image)
