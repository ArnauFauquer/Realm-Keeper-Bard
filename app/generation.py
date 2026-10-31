"""Image generation and transformation with the local engine (local_engine.py).

Create uses Krea 2 (text only); transform and 3D preparation use FLUX 3 Image
Klein with the images as references. Prompts are written in English.
"""

import re

from .local_engine import LocalEngine
from .style_profile import DEFAULT_EXPRESSION_3D, StyleProfile

CATEGORY_LABELS = {
    "character": "a character",
    "background": "a background/scene",
    "object": "an object",
    "map": "an illustrated map of a region",
}

# Characters are portrait (full-body sheet), backgrounds landscape (scenery
# panorama), objects square (inventory icon) and maps landscape but less
# elongated (book-plate proportions).
CATEGORY_ASPECT_RATIO = {
    "character": "9:16",
    "background": "16:9",
    "object": "1:1",
    "map": "3:2",
}


def generate_image_from_refs(
    engine: LocalEngine, prompt: str, image_paths: list[str], aspect_ratio: str = "1:1",
) -> tuple[bytes, str]:
    """Without references, generate with Krea 2; with references, edit with FLUX 3."""
    if image_paths:
        return engine.edit(prompt, image_paths, aspect_ratio)
    return engine.generate(prompt, aspect_ratio)


def _species_applies(profile: StyleProfile, category: str, use_species: bool) -> bool:
    return use_species and category == "character" and bool(profile.species_prompt.strip())


# Quoted names in a map description ("…", «…», “…” or '…').
QUOTED_NAME = re.compile(r""""([^"]+)"|«([^»]+)»|“([^”]+)”|(?<!\w)'([^']+)'(?!\w)""")
REGION_WORDS = ("region", "kingdom", "land", "lands", "country", "island", "province", "county",
                "comarca", "región", "reino", "tierra", "país", "pais", "isla", "provincia")


def map_labels(description: str) -> str:
    """Closed list of labels for a map. Krea repeats places and invents the
    title if it is only told what not to do ("don't repeat"): it works better to
    state positively how many labels there are and which. The first name is the
    title if a region word precedes it ("La comarca de \"Valle Bellota\"")."""
    names, seen = [], set()
    first_start = None
    for match in QUOTED_NAME.finditer(description):
        name = next(g for g in match.groups() if g).strip()
        if first_start is None:
            first_start = match.start()
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    if not names:
        return ""
    title = None
    # only if the word comes right before ("La comarca de ..."), not in "a region with the village ..."
    if any(w in REGION_WORDS for w in description[:first_start].lower().split()[-3:]):
        title, names = names[0], names[1:]
    title_line = (f"The cartouche shows only the title '{title}'." if title
                  else "The cartouche is a decorative frame with no text inside.")
    if not names:
        return f" Labels: {title_line}"
    quoted = ", ".join(f"'{n}'" for n in names)
    return (f" Labels: {title_line} The map has exactly {len(names)} place "
            f"{'label' if len(names) == 1 else 'labels'}, one next to each place, each name written a single "
            f"time on the whole map: {quoted}. Each of these places is drawn as one single vignette.")


def build_create_prompt(
    profile: StyleProfile, category: str, description: str, species_ref: bool = False,
    use_species: bool = False,
) -> str:
    """Prompt structure (style consistency):
    subject -> framing/point of view -> style -> constraints, each block
    short and separate instead of one long paragraph.
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
        f"{map_labels(description) if category == 'map' else ''}"
    )


# When unifying the species we must separate what is kept (everything about the
# individual) from what is redrawn (the physiognomy): with a generic "keep its
# shape" prompt the model kept the original humanoid body.
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

# Without anchor: only the character is attached.
SPECIES_TRANSFORM_SUBJECT = (
    "Subject: the attached image shows a character. Redraw it completely, "
    "correcting its physiology so it has the anatomy of the species "
    "described below, with a pose and gesture similar to the original. "
    f"{SPECIES_REMOVE_HUMAN} {SPECIES_KEEP_LIST}"
)

# With anchor: in v1 the character came first and the anchor second, and the
# model barely touched the anatomy (it edited the original instead of redrawing
# it). Now the anchor goes FIRST as the "base body" and the character second as
# "what they wear and who they are".
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


# Transform does not ask what the image is: FLUX sees it. Only the species (if
# one is chosen) and the map style change the result; framing and proportions
# come from the reference itself.
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
    category = "map" if is_map else ""
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
    """The SIZES aspect ratio closest to the image's (on a log scale, so that
    2:1 and 1:2 are equally far from 1:1)."""
    import math

    from PIL import Image

    from .local_engine import SIZES

    width, height = Image.open(image_path).size
    target = math.log(width / height)
    return min(SIZES, key=lambda r: abs(math.log(SIZES[r][0] / SIZES[r][1]) - target))


# "Sculpture" re-render before going 3D: without outlines or comic shading the
# 3D model reads volumes better (in tests: fewer facets, coherent backs and real
# cloth folds).
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
    """A FLUX 3 edit: the image as a grey clay sculpture."""
    from PIL import Image

    width, height = Image.open(image_path).size
    ratio = "9:16" if height > width * 1.3 else ("3:4" if height > width * 1.05 else "1:1")
    return generate_image_from_refs(engine, PREPARE_3D_PROMPT, [image_path], ratio)


# Minimal framing: only what the 3D model needs (full body, plain background,
# no base or ground shadow). Neither the pose, the tail nor the cape are
# rearranged: that moved the figure away from the original drawing.
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
    """A FLUX 3 edit: the image as a highly detailed grey sculpture.
    Replaces `prepare_for_3d` (smooth clay) when character and detail are wanted."""
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
    # Krea 2 only generates from text: the species anatomy goes in the prompt,
    # without the anchor image (in round 4 of the comparison the rat came out faithful this way).
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
    # Order matters: with an anchor, the prompt calls the anchor (base body)
    # "image 1" and the character "image 2".
    refs = _species_refs(profile, "map" if is_map else "character", use_species)
    prompt = build_transform_prompt(profile, extra_instructions, is_map, bool(refs), use_species)
    aspect_ratio = closest_aspect_ratio(reference_path)
    return generate_image_from_refs(engine, prompt, [*refs, reference_path], aspect_ratio)
