from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import random

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
COLORS = [(220, 20, 60), (0, 120, 215), (0, 153, 51), (255, 140, 0), (128, 0, 128), (0, 139, 139)]

server = Server("calib")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [types.Tool(name="calibration_image", description="Return a test image with lettered square markers.",
                       inputSchema={"type": "object", "properties": {"width": {"type": "integer"},
                                                                     "height": {"type": "integer"}},
                                    "required": ["width", "height"], "additionalProperties": False})]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    width, height = arguments["width"], arguments["height"]
    rng = random.Random()
    img = Image.new("RGB", (width, height), (243, 243, 243))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("arial.ttf", 16)
    truth, placed = {}, []
    for i, letter in enumerate("ABCDEFGHIJ"):
        while True:
            x, y = rng.randint(30, width - 60), rng.randint(30, height - 30)
            if all(abs(x - px) > 80 or abs(y - py) > 40 for px, py in placed):
                break
        placed.append((x, y))
        draw.rectangle((x - 6, y - 6, x + 6, y + 6), fill=COLORS[i % len(COLORS)])
        draw.text((x + 12, y - 9), letter, fill=(0, 0, 0), font=font)
        truth[letter] = [x, y]
    with open(os.path.join(HERE, "out", f"calib_truth_{width}x{height}.json"), "w", encoding="utf-8") as f:
        json.dump(truth, f)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return [types.TextContent(type="text", text=f"image size {width}x{height}"),
            types.ImageContent(type="image", data=base64.b64encode(buf.getvalue()).decode("ascii"), mimeType="image/png")]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
