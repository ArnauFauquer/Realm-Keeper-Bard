"""World style profile: the style prompt and the point-of-view prompts.

All prompts are in English (decision of 24 Oct 2026): local image models
understand English far better.

This is what keeps the same visual approach across images generated at
different times: it is defined once and reused in every generation (create or
transform characters/backgrounds/objects).
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import DATA_DIR, STYLE_PATH

CATEGORIES = ("character", "background", "object", "map")

# Fixed style descriptor: repeated EXACTLY the same in every generation
# (consistency across generations). Thick, clean outline with few inner lines
# (this is what the user asked for and validated). Compared with the previous
# version, flat "sticker"-style highlights are replaced by a softer, continuous
# light gradient, and some nuance is restored in the face.
DEFAULT_STYLE_PROMPT = (
    "Clean fantasy illustration style, high-quality cartoon: thick, uniform "
    "black ink outline, with few inner lines. Avoid busy detail: no fine "
    "engravings, scratches, fabric wrinkles or intricate ornamental patterns "
    "(a simple emblem or embroidery is fine). Give the shapes volume with "
    "soft multi-tone shading and a gradual, blended transition between light "
    "and shadow; avoid hard oval highlights or isolated white spots that look "
    "like a sticker stuck on top of the drawing, the highlight must blend into "
    "the color gradient. Also apply subtle shading on the face (cheeks, nose, "
    "neck, cheekbones) to give the features volume, without reaching a "
    "realistic painterly finish. Not photorealistic: stylized proportions and "
    "shapes, closer to a cartoon than to digital painting, but with more "
    "nuance than a fully flat drawing. Dramatic, high-contrast lighting on the "
    "subject itself (one strong key light with marked shadows that bring out "
    "the volume), even if the background is flat; the drama comes from the "
    "light and shadow contrast on the character, not from an elaborate "
    "background. Keep and do not soften the subject's intensity, attitude and "
    "expression: dynamic poses, intense, aggressive, menacing or sinister "
    "gestures and looks if the character is that type; do not make them look "
    "kinder, calmer or more childish than they are. Saturated color palette. "
    "Always keep this same style, "
    "this same palette and this same level of detail in every image."
)

DEFAULT_CONSTRAINTS = (
    "Do not include text, titles, letters, logos, watermarks, frames or "
    "interface elements of any kind in the image; only the illustration."
)

# Maps use neither the general style nor the general constraints: the general
# style is designed for characters (thick outline, dramatic light on the
# subject) and the constraints forbid all text, but a map needs place labels.
# The prompt is in English, but the names are given in quotes in the
# description so the model copies them verbatim instead of translating them.
DEFAULT_MAP_STYLE = (
    "Classic fantasy cartographer's map, in the style of Tolkien's maps or "
    "the Dungeons & Dragons supplements, hand-drawn with a dip pen on aged "
    "parchment and colored with soft, muted watercolor washes (moss green, "
    "ochre, earth brown, greyish blue for water). The terrain is shown with "
    "cartographic symbols, not scenes: forests as masses of small repeated "
    "trees, relief with hatching and stippling strokes, rivers as winding "
    "lines with drawn banks, roads as dashed lines. Each important place is a "
    "small, detailed vignette drawn on the map, like an illustrated icon, "
    "never a large scene. A cartouche with the region's name, a classic "
    "compass rose and a simple double-line border with a discreet ornament in "
    "the corners. Always keep this same style in every map."
)

DEFAULT_MAP_CONSTRAINTS = (
    "The only text allowed is the map labels: the region's name as a title in "
    "a cartouche and the name of each place next to its illustration. Write "
    "them copied letter by letter exactly as they appear in quotes in the "
    "description, in their original language and with their accents; do not "
    "translate them and do not invent new names. Calligraphic old-map lettering, "
    "clear and legible. Each place is drawn and labeled only once: do not "
    "repeat any place or any label. Do not add any other text, legend, "
    "logo, watermark or interface element."
)

# Common species anatomy (characters only). The style above fixes the linework
# but not the physiognomy: without this each character came out with a different
# anatomy (humanoid, anime or animal). It separates what belongs to the SPECIES
# (unified) from what belongs to the INDIVIDUAL (always preserved).
DEFAULT_SPECIES_PROMPT = (
    "The characters are anthropomorphic rats with ANIMAL physiology, not "
    "human: a real rat that walks upright and wears clothes, not a person with "
    "a rat's head. Head: large relative to the body, long pointed rat snout "
    "with a pink nose at the tip, long thin whiskers, large, round, thin ears "
    "of pink skin, round expressive eyes with the white of the eye visible (no "
    "anime eyes, no dot eyes). Body: standing on the hind legs with a slight "
    "hunch, narrow sloping shoulders, short neck, short thin arms; no human "
    "anatomy (no human chest, waist, hips, abs or muscles). Hands: furry rat "
    "paws with thin fingers and small claws, never human hands or human skin. "
    "Feet: long rat hind feet with pink soles and claws, never human feet. "
    "Always BAREFOOT: no shoes, boots or sandals; at most bandages or cloth "
    "strips around the ankle, leaving the rat foot visible. Long thin rat "
    "tail. Short, slightly scruffy fur all over the body, with loose tufts on "
    "the cheeks and crown. What sets each individual apart is NOT part of the "
    "species and is always kept: build (fat, thin, strong), fur color and "
    "texture, their own hairstyle or tufts (for example curly fur), eye color, "
    "scars, bitten ears, patches, prostheses and wings or other special "
    "features. Female characters are distinguished by eyelashes, expression, "
    "attitude and clothing, not by human anatomy."
)

# Species anchor image: attached as a second reference so the model sees the
# anatomy instead of only reading it. Path relative to DATA_DIR.
DEFAULT_SPECIES_REF = "references/species_rat.jpg"

# Style ONLY for preparing the image that is converted to 3D. It should have
# little "logic": it only translates the medium (drawing -> grey sculpture with
# relief) and forbids touching anything else. The more own style is added
# (dark fantasy, realistic anatomy, frown...) the further it drifts from the
# original character (thinner, harsher, less good-natured). It doesn't touch the
# 2D style at all.
DEFAULT_STYLE_3D = (
    "Translate this illustration into a 3D sculpt without changing the character. Keep every "
    "detail of the drawing exactly as it is: same pose, same body shape, volumes and proportions "
    "(do not slim it down), same face and expression, same clothes, accessories, patches, "
    "stitching, wraps, tail and claws. Only the medium changes: render it as a physical sculpted "
    "figure in a single matte light-grey clay-like material, where fur, fabric weave, stitches "
    "and wraps become fine sculpted relief. Soft even studio light. Keep the warm, cozy, "
    "good-natured storybook feel of the drawing: do not make the character thinner, more "
    "muscular, more realistic, harsher, darker or more serious."
)

DEFAULT_EXPRESSION_3D = (
    "Keep exactly the same facial expression and mood as the reference image: do not make the "
    "character angrier, sadder, cuter or more menacing than in the reference."
)

# Characters and objects get a plain single-color background (no texture, no
# gradient, no cast shadow) so the "remove background" workflow (rembg) can cut
# them out with clean edges. They also get no pedestal, base or ground under the
# subject (nothing to cut out besides the character or object itself). Scene
# backgrounds don't have this constraint because they are meant to fill the
# whole frame.
FLAT_BACKGROUND_HINT = (
    "Background of a single flat, completely uniform color (light neutral "
    "grey), no textures, no gradients, no cast shadow on the background and no "
    "vignette, with sharp contrast between subject and background so it can "
    "be cut out cleanly later. Do not include any pedestal, base, platform, "
    "floor or ground under the subject: it must rest directly on the flat "
    "background, with no visible surface under the feet or the base of the "
    "object."
)

DEFAULT_POV = {
    "character": (
        "TOP FRAMING PRIORITY: the character and absolutely everything they "
        "wear, carry, hold or drag (weapons, tails, wings, capes, chains, tied "
        "objects, etc.) must be fully visible inside the image, never cut off "
        "at any edge. This matters more than the size of the character: if "
        "something does not fit, zoom out as much as needed. The frame is tall "
        "and narrow, so avoid stretching long weapons, tails or chains "
        "diagonally toward a corner (that is what most easily leaves the "
        "frame); instead, keep those long elements more vertical, close to the "
        "body or the side of the character, or coil/bend them naturally so "
        "they fit whole. Never crop or leave out of frame any part of the "
        "character or their objects. Role-playing "
        "character sheet: full body visible from head to toe (hands and feet "
        "not cropped), three-quarter view with correct perspective, centered "
        f"vertical framing, standing. {FLAT_BACKGROUND_HINT}"
    ),
    "background": (
        "Wide horizontal establishing shot meant as a role-playing scene "
        "background, wide angle, horizon at mid height, good depth between "
        "foreground/midground/background, no characters in the foreground."
    ),
    "object": (
        "A single object centered in the frame like an inventory icon, "
        "three-quarter view, good studio lighting that brings out the "
        f"object's shape and material. {FLAT_BACKGROUND_HINT}"
    ),
    "map": (
        "Complete map of the region in landscape format, in a pure top-down "
        "view (from above, no perspective, no horizon); only the place "
        "vignettes are drawn in a slight three-quarter view. The whole region "
        "inside the frame, with the border visible on all four sides and no "
        "important place cut off. Uncluttered composition, like a real map: "
        "the place vignettes are small relative to the map and spread out and "
        "well separated, and most of the surface is cartographic terrain "
        "(forests, relief, rivers, roads connecting the places); nothing "
        "crowded or squeezed together. No characters."
    ),
}


# Data saved before the English rename used Spanish category keys and paths.
_LEGACY_CATEGORIES = {"personaje": "character", "fondo": "background", "objeto": "object", "mapa": "map"}


def _migrate_ref(path: str) -> str:
    if path.startswith("referencias/"):
        path = "references/" + path[len("referencias/"):]
    return path.replace("especie_rata.jpg", "species_rat.jpg")


@dataclass
class StyleProfile:
    style_prompt: str = DEFAULT_STYLE_PROMPT
    constraints: str = DEFAULT_CONSTRAINTS
    pov: dict = field(default_factory=lambda: dict(DEFAULT_POV))
    style_3d: str = DEFAULT_STYLE_3D
    species_prompt: str = DEFAULT_SPECIES_PROMPT
    species_ref: str = DEFAULT_SPECIES_REF
    map_style: str = DEFAULT_MAP_STYLE
    map_constraints: str = DEFAULT_MAP_CONSTRAINTS

    def pov_for(self, category: str) -> str:
        return self.pov.get(category, "")

    def style_for(self, category: str) -> str:
        return self.map_style if category == "map" else self.style_prompt

    def constraints_for(self, category: str) -> str:
        return self.map_constraints if category == "map" else self.constraints

    def species_ref_path(self) -> str | None:
        """Absolute path of the anchor image, or None if there is none or it is missing."""
        if not self.species_ref:
            return None
        path = Path(self.species_ref)
        if not path.is_absolute():
            path = DATA_DIR / path
        return str(path) if path.exists() else None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StyleProfile":
        pov = dict(DEFAULT_POV)
        # legacy Spanish category keys
        pov.update({_LEGACY_CATEGORIES.get(k, k): v for k, v in data.get("pov", {}).items()})
        return cls(
            style_prompt=data.get("style_prompt", DEFAULT_STYLE_PROMPT),
            constraints=data.get("constraints", DEFAULT_CONSTRAINTS),
            pov=pov,
            style_3d=data.get("style_3d", DEFAULT_STYLE_3D),
            species_prompt=data.get("species_prompt", DEFAULT_SPECIES_PROMPT),
            species_ref=data.get("species_ref", DEFAULT_SPECIES_REF),
            map_style=data.get("map_style", DEFAULT_MAP_STYLE),
            map_constraints=data.get("map_constraints", DEFAULT_MAP_CONSTRAINTS),
        )


# Since 25 Oct 2026 the general style and the anatomy are named templates (you
# can have several and pick one when generating); the point of view, maps and 3D
# style are shared by all. StyleProfile is still the "resolved" profile that
# generation.py receives.
@dataclass
class StylePreset:
    id: str
    name: str
    style_prompt: str = DEFAULT_STYLE_PROMPT
    constraints: str = DEFAULT_CONSTRAINTS


@dataclass
class SpeciesPreset:
    id: str
    name: str
    species_prompt: str = DEFAULT_SPECIES_PROMPT
    species_ref: str = DEFAULT_SPECIES_REF


@dataclass
class StyleLibrary:
    styles: list = field(default_factory=lambda: [StylePreset("style", "World style")])
    species: list = field(default_factory=lambda: [SpeciesPreset("rat", "Rat")])
    active_style: str = "style"
    active_species: str = "rat"
    pov: dict = field(default_factory=lambda: dict(DEFAULT_POV))
    style_3d: str = DEFAULT_STYLE_3D
    map_style: str = DEFAULT_MAP_STYLE
    map_constraints: str = DEFAULT_MAP_CONSTRAINTS

    def find_style(self, style_id: str | None) -> StylePreset:
        by_id = {s.id: s for s in self.styles}
        return by_id.get(style_id) or by_id.get(self.active_style) or self.styles[0]

    def find_species(self, species_id: str | None) -> SpeciesPreset | None:
        by_id = {s.id: s for s in self.species}
        return by_id.get(species_id) if species_id else None

    def resolve(self, style_id: str | None = None, species_id: str | None = None) -> StyleProfile:
        """Flat profile with the chosen style and anatomy templates (without
        anatomy: empty species_prompt, which generation.py treats as disabled)."""
        style = self.find_style(style_id)
        species = self.find_species(species_id)
        return StyleProfile(
            style_prompt=style.style_prompt,
            constraints=style.constraints,
            pov=dict(self.pov),
            style_3d=self.style_3d,
            species_prompt=species.species_prompt if species else "",
            species_ref=species.species_ref if species else "",
            map_style=self.map_style,
            map_constraints=self.map_constraints,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StyleLibrary":
        pov = dict(DEFAULT_POV)
        # legacy Spanish category keys
        pov.update({_LEGACY_CATEGORIES.get(k, k): v for k, v in data.get("pov", {}).items()})
        if "styles" not in data:
            # old format (a single flat profile): converted into one template of each
            old = StyleProfile.from_dict(data)
            styles = [StylePreset("style", "World style", old.style_prompt, old.constraints)]
            species = [SpeciesPreset("rat", "Rat", old.species_prompt, _migrate_ref(old.species_ref))]
        else:
            styles = [StylePreset(**s) for s in data["styles"]] or [StylePreset("style", "World style")]
            species = [SpeciesPreset(**{**s, "species_ref": _migrate_ref(s.get("species_ref", ""))})
                       for s in data.get("species", [])]
        return cls(
            styles=styles,
            species=species,
            active_style=data.get("active_style", styles[0].id),
            active_species=data.get("active_species", species[0].id if species else ""),
            pov=pov,
            style_3d=data.get("style_3d", DEFAULT_STYLE_3D),
            map_style=data.get("map_style", DEFAULT_MAP_STYLE),
            map_constraints=data.get("map_constraints", DEFAULT_MAP_CONSTRAINTS),
        )


def load_style_library() -> StyleLibrary:
    if not STYLE_PATH.exists():
        return StyleLibrary()
    try:
        data = json.loads(STYLE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return StyleLibrary()
    return StyleLibrary.from_dict(data)


def save_style_library(library: StyleLibrary) -> None:
    STYLE_PATH.write_text(
        json.dumps(library.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
