import random
import textwrap
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

from app.config import config
from app.interfaces import ContentGeneratorInterface, GeneratedContent, Topic

CAPTION_TEMPLATES = {
    "relatable": [
        "Ye toh har kisi ki zindagi hai 😂👇\n\nTag someone jo same feel karta hai 👇",
        "Bhai ye toh meri hi kahani hai 🤣",
    ],
    "bollywood": [
        "Bollywood + Meme = Instant Comedy 🎬😂\n\nWo scene jo har baar hasi dilata hai 🤣",
    ],
    "indian": [
        "Sabka same haal hai bhai 😂",
    ],
}

HASHTAG_POOL = {
    "relatable": ["#memes", "#relatable", "#indianmemes", "#funny", "#hindimemes", "#lol", "#desimemes"],
    "bollywood": ["#bollywoodmemes", "#indianmemes", "#hindimemes", "#funny", "#viral", "#desimemes"],
    "indian": ["#indianmemes", "#desimemes", "#funny", "#viral", "#memesdaily"],
}

# Simple, distinct palette per category so V1 output doesn't look like one
# generic template regardless of topic.
PALETTES = {
    "relatable": {"bg": (255, 214, 10), "text": (20, 20, 20)},
    "bollywood": {"bg": (214, 40, 40), "text": (255, 255, 255)},
    "indian": {"bg": (19, 78, 74), "text": (255, 255, 255)},
}


class TemplateContentGenerator(ContentGeneratorInterface):
    """V1 caption generation is template-based, not a real LLM call — this is
    intentional (see CTO note in README: ship the simple version first). Because
    this class only implements ContentGeneratorInterface, swapping in a real LLM
    call later means writing one new class, not touching Scheduler/Publisher."""

    def __init__(self, output_dir=None):
        self.output_dir = output_dir or config.local_memes_dir

    def generate(self, topic: Topic) -> GeneratedContent:
        caption = self._build_caption(topic)
        hashtags = self._build_hashtags(topic)
        image_path = self._build_image(topic)
        return GeneratedContent(
            topic=topic,
            image_path=str(image_path),
            caption=caption,
            hashtags=hashtags,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _build_caption(self, topic: Topic) -> str:
        templates = CAPTION_TEMPLATES.get(topic.category, CAPTION_TEMPLATES["relatable"])
        base = random.choice(templates)
        return f"{base}\n\n👉 {topic.text}"

    def _build_hashtags(self, topic: Topic) -> list[str]:
        pool = HASHTAG_POOL.get(topic.category, HASHTAG_POOL["relatable"])
        return pool[:8]

    def _build_image(self, topic: Topic):
        palette = PALETTES.get(topic.category, PALETTES["relatable"])
        size = (1080, 1080)
        img = Image.new("RGB", size, color=palette["bg"])
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 56
            )
        except OSError:
            font = ImageFont.load_default()

        wrapped = textwrap.fill(topic.text, width=22)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=12)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pos = ((size[0] - text_w) / 2, (size[1] - text_h) / 2)
        draw.multiline_text(
            pos, wrapped, font=font, fill=palette["text"], align="center", spacing=12
        )

        filename = f"meme_{topic.category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = self.output_dir / filename
        img.save(path)
        return path
