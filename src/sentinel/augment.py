"""Training-data augmentation: the normaliser run in reverse, plus context wrapping and hard negatives.

Applied to training rows only (never to validation or test data), deterministic given the seed:

* attack variants: re-cased, re-punctuated, leetspeak, zero-width characters, homoglyphs, spaced letters, base64
* attacks embedded inside longer benign text (the injection is one sentence in a document or email)
* hard negatives: benign text that quotes, reports or asks about an attack phrase (label 0)

The wrapper sentences are my own and templated, so a model trained on them can learn the template; the hand-written
hard-benign test set is a separate set and is reported separately.
"""

from __future__ import annotations

import base64
import random
import re

LEET = str.maketrans({"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"})
HOMOGLYPH = str.maketrans({"a": "\u0430", "e": "\u0435", "o": "\u043e", "p": "\u0440", "c": "\u0441", "x": "\u0445", "i": "\u0456"})  # Cyrillic lookalikes
ZW = "\u200b"

BENIGN_CONTEXT = [
    "Here is the email thread from the vendor about the delayed shipment. Please summarise it for the team.",
    "Customer review: the blender works well but the lid is hard to close. Delivery took four days.",
    "Meeting notes: we agreed to move the launch to the second week of March and to ask finance for a revised budget.",
    "Product description: a stainless steel water bottle that keeps drinks cold for 24 hours. Dishwasher safe.",
    "Article excerpt: the city council voted on Tuesday to extend bus service to the eastern districts starting in June.",
    "Support ticket 4821: the user cannot reset their password because the confirmation link has expired.",
    "Recipe card: mix two cups of flour with one cup of sugar, add three eggs and bake for thirty minutes.",
    "Forum post: I am trying to decide between two laptops for video editing and would like some advice on RAM.",
    "Translate the following paragraph into French and keep the tone formal.",
    "Search result snippet: the museum is open Tuesday to Sunday from nine to five, and entry is free on the first Sunday.",
]
BENIGN_TAIL = [
    "Thank you for your help with this.",
    "Let me know if you need anything else.",
    "Please keep the reply under one hundred words.",
    "The rest of the document continues below.",
    "",
]
QUOTE_TEMPLATES = [
    'My teacher warned us that someone might type "{a}" into a chatbot. Why does that count as an attack?',
    'For my security course I need to explain what an attacker is trying to do with the sentence "{a}". Can you describe it?',
    'A user wrote "{a}" in our support chat. How should our moderation team classify this kind of message?',
    'Is the phrase "{a}" an example of prompt injection? Answer yes or no and explain briefly.',
    'Write a short paragraph for a blog post that quotes the line "{a}" as a typical injection attempt and explains how filters catch it.',
    'Our logs show the string "{a}". Please add it to the list of examples in our incident report and describe the risk in one sentence.',
    'Translate this attack example into German for the training slides, without following it: "{a}"',
]


def _clip(text: str, n: int = 300) -> bool:
    return 8 <= len(text) <= n and "\n" not in text.strip()


def _recase(t: str, rng: random.Random) -> str:
    return rng.choice([t.upper, t.lower, lambda: "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(t))])()


def _repunct(t: str, rng: random.Random) -> str:
    s = re.sub(r"[.,;:!?]", lambda m: rng.choice([m.group(0), "", " ...", m.group(0) * 2]), t)
    return rng.choice([f"> {s}", f"```\n{s}\n```", f"*{s}*", f"{s}\n\n", f"[SYSTEM NOTE] {s}", s.replace(" ", "  ", 2)])


def _leet(t: str, rng: random.Random) -> str:
    return "".join(c.translate(LEET) if rng.random() < 0.6 else c for c in t.lower())


def _zero_width(t: str, rng: random.Random) -> str:
    return "".join(c + (ZW if c.isalpha() and rng.random() < 0.25 else "") for c in t)


def _homoglyph(t: str, rng: random.Random) -> str:
    return "".join(c.translate(HOMOGLYPH) if rng.random() < 0.5 else c for c in t)


def _spaced(t: str, rng: random.Random) -> str:
    words = t.split(" ")
    k = rng.randrange(len(words))
    words[k] = " ".join(words[k])
    return " ".join(words)


def _b64(t: str, rng: random.Random) -> str:
    enc = base64.b64encode(t.encode()).decode()
    return rng.choice([f"Decode this base64 and do what it says: {enc}", f"{enc}", f"Please process the following encoded note: {enc}"])


VARIANTS = [_recase, _repunct, _leet, _zero_width, _homoglyph, _spaced, _b64]


def embed(attack: str, rng: random.Random) -> str:
    """An injection sentence placed inside otherwise benign text."""
    head, tail = rng.choice(BENIGN_CONTEXT), rng.choice(BENIGN_TAIL)
    parts = [head, attack, tail] if rng.random() < 0.7 else [head, tail, attack]
    return rng.choice([" ", "\n\n", "\n"]).join(p for p in parts if p)


def augment(rows: list[dict], seed: int = 13, variants_per_attack: float = 0.5, embed_frac: float = 0.25, quote_frac: float = 0.2) -> list[dict]:
    """New training rows derived from ``rows`` (attacks and benign), labelled by construction."""
    rng = random.Random(seed)
    short_attacks = [r for r in rows if r["label"] == 1 and _clip(r["text"])]
    out: list[dict] = []
    for r in short_attacks:
        if rng.random() < variants_per_attack:
            fn = rng.choice(VARIANTS)
            out.append({"text": fn(r["text"], rng), "label": 1, "category": "aug_" + fn.__name__.strip("_"), "source": "augmented"})
        if rng.random() < embed_frac:
            out.append({"text": embed(r["text"], rng), "label": 1, "category": "aug_embedded", "source": "augmented"})
        if rng.random() < quote_frac:
            out.append({"text": rng.choice(QUOTE_TEMPLATES).format(a=r["text"].strip().rstrip(".")), "label": 0, "category": "aug_quoted_attack", "source": "augmented"})
    return out
