"""Generación y transformación de imágenes con el motor local (local_engine.py).

Crear usa Krea 2 (solo texto); transformar y preparar para 3D usan FLUX 3 Image
Klein con las imágenes como referencia. Los prompts van en inglés.
"""

from .local_engine import LocalEngine
from .style_profile import DEFAULT_EXPRESSION_3D, StyleProfile

CATEGORY_LABELS = {
    "personaje": "a character",
    "fondo": "a background/scene",
    "objeto": "an object",
    "mapa": "an illustrated map of a region",
}

# Personajes en vertical (ficha de cuerpo entero), fondos en horizontal
# (panorámica de escenario), objetos cuadrados (icono de inventario) y mapas
# apaisados pero menos alargados (proporción de lámina de libro).
CATEGORY_ASPECT_RATIO = {
    "personaje": "9:16",
    "fondo": "16:9",
    "objeto": "1:1",
    "mapa": "3:2",
}


def generate_image_from_refs(
    engine: LocalEngine, prompt: str, image_paths: list[str], aspect_ratio: str = "1:1",
) -> tuple[bytes, str]:
    """Sin referencias genera con Krea 2; con referencias edita con FLUX 3."""
    if image_paths:
        return engine.edit(prompt, image_paths, aspect_ratio)
    return engine.generate(prompt, aspect_ratio)


def _species_applies(profile: StyleProfile, category: str, use_species: bool) -> bool:
    return use_species and category == "personaje" and bool(profile.species_prompt.strip())


def build_create_prompt(
    profile: StyleProfile, category: str, description: str, species_ref: bool = False,
    use_species: bool = False,
) -> str:
    """Estructura del prompt (consistencia de estilo):
    sujeto -> encuadre/punto de vista -> estilo -> restricciones, cada bloque
    corto y separado en vez de un único párrafo largo.
    """
    label = CATEGORY_LABELS.get(category, category)
    species_block = ""
    if _species_applies(profile, category, use_species):
        ref_line = (
            " The attached image is the species anatomy reference: copy its "
            "physiology, proportions and the shape of the head, eyes, snout, "
            "hands, feet and tail, but not its clothes, objects, colors, "
            "expression or pose."
            if species_ref
            else ""
        )
        species_block = f"Species anatomy: {profile.species_prompt}{ref_line}\n\n"
    return (
        f"Subject: {label} for a Dungeons & Dragons campaign. "
        f"{description.strip()}\n\n"
        f"{species_block}"
        f"Framing and point of view: {profile.pov_for(category)}\n\n"
        f"Visual style (use exactly this style, it is the same in every "
        f"image of this world): {profile.style_for(category)}\n\n"
        f"Constraints: {profile.constraints_for(category)}"
    )


# Al unificar la especie hay que separar qué se conserva (todo lo del
# individuo) de qué se rehace (la fisionomía): con el prompt genérico de
# "conserva su forma" el modelo mantenía el cuerpo humanoide del original.
SPECIES_KEEP_LIST = (
    "Keep EVERYTHING about the character without losing any detail: every "
    "garment, armor piece, strap, buckle, emblem, weapon, object they hold or "
    "carry hanging, wings, bandages, patches, prostheses, scars and bitten "
    "ears; the colors of the clothes, fur and tail, and the shape of the tail "
    "tip (if it has a tuft of hair, keep it); their build (if fat, still "
    "fat); their own hairstyle or tufts as rat fur (if they have curly hair, "
    "they still have curly hair); eye color; and the EXACT facial expression "
    "(if smiling, still smiling; if showing teeth, still showing them; if "
    "scared, still scared). Go over the character piece by piece: nothing "
    "that appears may be missing or simplified away."
)

SPECIES_REMOVE_HUMAN = (
    "Remove any human anatomy trait the character has: human chest, waist "
    "and hips, human muscles or abs, human hands or feet, human toes sticking "
    "out of footwear, a flat anime face or anime eyes. Their anatomy must be "
    "the species' anatomy."
)

# Sin ancla: solo se adjunta el personaje.
SPECIES_TRANSFORM_SUBJECT = (
    "Subject: the attached image shows a character. Redraw it completely, "
    "correcting its physiology so it has the anatomy of the species "
    "described below, with a pose and gesture similar to the original. "
    f"{SPECIES_REMOVE_HUMAN} {SPECIES_KEEP_LIST}"
)

# Con ancla: en la v1 el personaje iba primero y el ancla segunda, y el modelo
# apenas tocaba la anatomía (editaba el original en vez de redibujarlo). Ahora
# el ancla va PRIMERO como "cuerpo base" y el personaje segundo como "lo que
# lleva y quién es".
SPECIES_TRANSFORM_SUBJECT_WITH_REF = (
    "Subject: draw a new character combining the two attached images. "
    "Image 1 = the species BASE BODY: the final character must be built "
    "exactly like it (same head shape, long snout, whiskers, eyes with the "
    "white visible, ears, head and body proportions, narrow shoulders, slight "
    "hunch, paw-hands, long rat feet and the same kind of linework and "
    "shading). From image 1 do NOT copy its clothes, staff, bag, fur color, "
    "expression or pose. "
    "Image 2 = WHO the character is: their clothes, gear, colors, "
    "distinctive features, expression and overall pose. "
    f"{SPECIES_REMOVE_HUMAN} {SPECIES_KEEP_LIST}"
)


# Transformar no pregunta qué es la imagen: FLUX la ve. Solo cambian el
# resultado la especie (si se elige una) y el estilo de mapa; el encuadre y la
# proporción salen de la propia referencia.
TRANSFORM_FRAMING = (
    "Keep the composition, framing and point of view of the attached image. "
    "If it shows a character or an object, it and everything it wears, holds "
    "or carries must stay fully visible, never cut off at the edges."
)


def build_transform_prompt(
    profile: StyleProfile, extra_instructions: str, is_map: bool = False,
    species_ref: bool = False, use_species: bool = False,
) -> str:
    extra = extra_instructions.strip()
    extra_line = f"\n\nAdditional details: {extra}" if extra else ""
    category = "mapa" if is_map else ""
    if use_species and not is_map and profile.species_prompt.strip():
        subject = SPECIES_TRANSFORM_SUBJECT_WITH_REF if species_ref else SPECIES_TRANSFORM_SUBJECT
        species_block = f"\n\nSpecies anatomy: {profile.species_prompt}"
    else:
        what = ", which shows an illustrated map of a region" if is_map else ""
        subject = (
            f"Subject: the attached image{what}. Redraw it "
            "completely applying the following art style, but keeping its "
            "identity, shape, distinctive colors and characteristic elements "
            "(do not change who or what it is, only its visual treatment). "
            "Also keep its original attitude, intensity and expression exactly "
            "as strong: if the subject is aggressive, menacing, sinister or "
            "dramatic in the reference, the result must convey that same "
            "aggressiveness and drama, not a softer, kinder or calmer version."
        )
        species_block = ""
    base_removal_line = (
        ""
        if is_map
        else "\n\nIf the reference image shows a single character or object "
        "standing on a pedestal, base, plinth or platform, remove it "
        "completely: the result must not include any base under the subject."
    )
    return (
        f"{subject}{extra_line}{base_removal_line}{species_block}\n\n"
        f"Framing and point of view: {TRANSFORM_FRAMING}\n\n"
        f"Visual style (use exactly this style, it is the same in every "
        f"image of this world): {profile.style_for(category)}\n\n"
        f"Constraints: {profile.constraints_for(category)}"
    )


def closest_aspect_ratio(image_path: str) -> str:
    """La proporción de SIZES más parecida a la de la imagen (en escala logarítmica,
    para que 2:1 y 1:2 queden igual de lejos de 1:1)."""
    import math

    from PIL import Image

    from .local_engine import SIZES

    width, height = Image.open(image_path).size
    target = math.log(width / height)
    return min(SIZES, key=lambda r: abs(math.log(SIZES[r][0] / SIZES[r][1]) - target))


# Re-render "de escultura" antes de pasar a 3D: sin contornos ni sombreado de
# cómic, el modelo 3D lee mejor los volúmenes (en las pruebas, menos facetas,
# espaldas coherentes y pliegues de tela reales).
PREPARE_3D_PROMPT = (
    "Re-render the character in the attached image as a 3D sculpt for a "
    "printed tabletop miniature: unpainted matte light-grey clay material, "
    "soft even studio lighting from the front, gentle ambient occlusion so "
    "every fold, strap, hair strand and facial feature reads clearly as "
    "real 3D relief. No black outlines, no cel shading, no cast shadows. "
    "Keep exactly the same pose, proportions, costume, accessories and "
    "silhouette. Full body in frame with a small margin, front view, "
    "orthographic-looking camera, plain pure white background, no base."
)


def prepare_for_3d(engine: LocalEngine, image_path: str) -> tuple[bytes, str]:
    """Una edición con FLUX 3: la imagen como escultura de arcilla gris."""
    from PIL import Image

    width, height = Image.open(image_path).size
    ratio = "9:16" if height > width * 1.3 else ("3:4" if height > width * 1.05 else "1:1")
    return generate_image_from_refs(engine, PREPARE_3D_PROMPT, [image_path], ratio)


# Encuadre mínimo: solo lo que necesita el modelo 3D (cuerpo entero, fondo liso,
# sin base ni sombra en el suelo). No se reordena ni la pose, ni la cola, ni la capa:
# eso alejaba la figura del dibujo original.
DETAILED_3D_FRAMING = (
    "Full body, nothing cropped, plain flat light-grey background, no floor, no base, "
    "no cast shadow on the ground, no text."
)


def build_detailed_3d_prompt(profile: StyleProfile, expression: str = "") -> str:
    expression = expression.strip() or DEFAULT_EXPRESSION_3D
    return (
        f"{profile.style_3d}\n\n"
        f"Expression and character notes: {expression}\n\n"
        f"Framing: {DETAILED_3D_FRAMING}"
    )


def prepare_for_3d_detailed(
    engine: LocalEngine, profile: StyleProfile, image_path: str, expression: str = ""
) -> tuple[bytes, str]:
    """Una edición con FLUX 3: la imagen como escultura gris muy detallada.
    Sustituye a `prepare_for_3d` (arcilla lisa) cuando se quiere carácter y detalle."""
    from PIL import Image

    width, height = Image.open(image_path).size
    ratio = "9:16" if height > width * 1.6 else ("3:4" if height > width * 1.05 else "1:1")
    prompt = build_detailed_3d_prompt(profile, expression)
    return generate_image_from_refs(engine, prompt, [image_path], ratio)


def _species_refs(profile: StyleProfile, category: str, use_species: bool) -> list[str]:
    if not _species_applies(profile, category, use_species):
        return []
    ref = profile.species_ref_path()
    return [ref] if ref else []


def generate_create(
    engine: LocalEngine, profile: StyleProfile, category: str, description: str,
    use_species: bool = True,
) -> tuple[bytes, str]:
    # Krea 2 solo genera desde texto: la anatomía de la especie va en el prompt,
    # sin la imagen ancla (en la ronda 4 de la comparativa la rata salió fiel así).
    prompt = build_create_prompt(profile, category, description, False, use_species)
    aspect_ratio = CATEGORY_ASPECT_RATIO.get(category, "1:1")
    return generate_image_from_refs(engine, prompt, [], aspect_ratio)


def generate_transform(
    engine: LocalEngine,
    profile: StyleProfile,
    reference_path: str,
    extra_instructions: str = "",
    is_map: bool = False,
    use_species: bool = True,
) -> tuple[bytes, str]:
    # El orden importa: con ancla, el prompt llama "image 1" al ancla (cuerpo
    # base) e "image 2" al personaje.
    refs = _species_refs(profile, "mapa" if is_map else "personaje", use_species)
    prompt = build_transform_prompt(profile, extra_instructions, is_map, bool(refs), use_species)
    aspect_ratio = closest_aspect_ratio(reference_path)
    return generate_image_from_refs(engine, prompt, [*refs, reference_path], aspect_ratio)
