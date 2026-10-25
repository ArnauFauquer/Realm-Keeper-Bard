"""Motor de imagen local: los modelos corren dentro del proceso con diffusers.

Sin servicios externos:
- Crear: Krea 2 Turbo (GGUF Q4), el que mejor clava el estilo de la app.
- Transformar / editar / preparar para 3D: FLUX 3 Image Klein (GGUF Q8), el que
  mejor conserva el original al editar con imágenes de referencia.

Los transformers salen de los GGUF de MODELS_DIR; el resto de componentes
(encoder de texto Qwen3-VL 4B, VAE, scheduler y configs) se descargan de
Hugging Face la primera vez y quedan en su caché (HF_HOME). Solo hay un modelo
cargado a la vez y con offload a CPU: con el escritorio abierto quedan ~8 GB de
VRAM y ni el encoder (8,8 GB) ni Krea Q4 caben enteros. Por defecto se usa
offload por capas ("group", sube a la GPU capa a capa con prefetch);
ENGINE_OFFLOAD=model mueve modelos enteros (más rápido si hay VRAM de sobra).
"""

import gc
import io
import random
import threading

from PIL import Image

from .config import FLUX3_GGUF, FLUX3_REPO, KREA_GGUF, KREA_REPO, OFFLOAD

# Tamaño en píxeles para cada proporción que usa la app (múltiplos de 16, ~1 MP).
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
        """Comprueba que hay GPU y pesos. Los modelos se cargan al primer uso."""
        import torch

        if not torch.cuda.is_available():
            raise LocalEngineError("No hay GPU CUDA disponible (¿Docker sin --gpus?).")
        missing = [p.name for p in (KREA_GGUF, FLUX3_GGUF) if not p.exists()]
        if missing:
            raise LocalEngineError(f"Faltan pesos en {KREA_GGUF.parent}: {', '.join(missing)}.")
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
        # Sin el "prompt upsampler" (Qwen3.5 9B que reescribe el prompt): el de la
        # app ya es detallado, y no cabe junto al resto. `.blocks` es una copia.
        blocks = ModularPipeline.from_pretrained(FLUX3_REPO).blocks
        blocks.sub_blocks.pop("prompt_upsampler")
        pipe = blocks.init_pipeline(FLUX3_REPO, components_manager=manager)
        pipe.load_components(names=["text_encoder", "tokenizer", "vae"], dtype=torch.bfloat16)
        pipe.update_components(transformer=transformer)
        # Las pocas capas BF16 del GGUF (embeddings de tiempo) llegan al cálculo sin
        # decuantizar y fallan: se pasan a bf16 normal (son pequeñas).
        for module in pipe.transformer.modules():
            for name, param in list(module.named_parameters(recurse=False)):
                if getattr(param, "quant_type", None) == gguf.GGMLQuantizationType.BF16:
                    module._parameters[name] = torch.nn.Parameter(
                        dequantize_gguf_tensor(param).to(torch.bfloat16), requires_grad=False)
        if OFFLOAD != "model":
            # El Q8 (6 GB) cabe entero; el offload por capas además le quita el tipo
            # GGUF a los pesos. Solo el encoder (8,8 GB) va por capas.
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
        """Texto a imagen con Krea 2 Turbo: 8 pasos, sin guía."""
        import torch

        w, h = SIZES.get(aspect_ratio, SIZES["1:1"])
        with self.lock:
            pipe = self._use("krea")
            # Krea corta el texto en max_sequence_length (512 por defecto) y un
            # personaje con anatomía pasa de 900 tokens: sin esto se pierde el estilo.
            tokens = len(pipe.tokenizer(prompt)["input_ids"])
            image = pipe(
                prompt, width=w, height=h, num_inference_steps=8, guidance_scale=0.0,
                max_sequence_length=max(512, -(-(tokens + 32) // 64) * 64),
                generator=torch.Generator("cpu").manual_seed(random.randint(0, 2**32 - 1)),
            ).images[0]
        return self._png(image)

    def edit(self, prompt: str, image_paths: list[str], aspect_ratio: str) -> tuple[bytes, str]:
        """Edición / multirreferencia con FLUX 3 Image Klein: 16 pasos, sin guía.

        FLUX 3 cita las referencias como <ref_image_N>; el prompt de la app habla de
        "the attached image" o "image 1/2", así que se le antepone el orden.
        """
        import torch

        if not image_paths:
            raise LocalEngineError("Editar necesita al menos una imagen de referencia.")
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
