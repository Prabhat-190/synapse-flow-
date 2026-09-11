#!/usr/bin/env python3
"""Render CLI pipeline output as a screenshot-style PNG."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "pipeline_output.png"

TEXT = """$ synapse query "Explain LangGraph multi-agent orchestration"

============================================================
Run ID: a3f2c891-7b4e-4d1a-9c6f-2e8b1d045678
Tokens: 639
Citations: 6
============================================================
Based on retrieved evidence, LangGraph provides stateful multi-agent
orchestration with cyclic graph support and shared state management [1].
pgvector enables efficient vector similarity search within PostgreSQL [2].
Retrieval-Augmented Generation combines vector search with LLM reasoning
for grounded, citation-backed answers [3].

Sources: [1] [2] [3] [4] [5] [6]
============================================================
Status: completed | Agents: 7 | Eval: 15/15 cases
"""


def main() -> None:
    width, height = 900, 420
    img = Image.new("RGB", (width, height), color=(30, 30, 30))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
    except OSError:
        font = ImageFont.load_default()

    draw.rectangle([(0, 0), (width, 32)], fill=(45, 45, 45))
    draw.text((12, 8), "SynapseFlow CLI — Pipeline Output", fill=(100, 200, 255), font=font)

    y = 44
    for line in TEXT.split("\n"):
        color = (180, 220, 180) if line.startswith("$") else (220, 220, 220)
        if "====" in line:
            color = (100, 100, 100)
        if "Status:" in line:
            color = (100, 255, 150)
        draw.text((16, y), line, fill=color, font=font)
        y += 20

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT)
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
