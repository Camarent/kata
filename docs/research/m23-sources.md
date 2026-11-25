# M23 research: joke sources, placeholder images, vision model

Researched 2026-11-25. Only official pages used. Confidence: official / secondary / UNVERIFIED.

## 1. Joke sources

| item | finding | source URL | confidence |
|---|---|---|---|
| jokeapi: id / base URL | `jokeapi`, `https://v2.jokeapi.dev/` | https://v2.jokeapi.dev/ | official |
| jokeapi: auth | "JokeAPI doesn't require any API token, authorization or payment to work." Tokens only for outages or >120 req/min | https://jokeapi.dev/ | official |
| jokeapi: rate limit | 120 requests per minute per client; HTTP 429 above that. Kata (1 per 2 h) is far below | https://v2.jokeapi.dev/ | official |
| jokeapi: content type | JSON default; XML, YAML, plain text selectable via `format` parameter | https://jokeapi.dev/ | official |
| jokeapi: terms | No standalone terms. "By using this website and API you are agreeing to the privacy policy." Disclaimer: no liability for jokes served. GitHub page: "use this API at your own risk!" | https://v2.jokeapi.dev/ , https://github.com/Sv443/JokeAPI | official |
| jokeapi: caching | No caching terms on site or GitHub page. Bulk advice: to fetch all jokes use the GitHub repository | https://v2.jokeapi.dev/ | official (silent): caching unclear |
| jokeapi: licence of joke text | Not stated. Only "JokeAPI is licensed under the MIT License" (the software). GitHub README names no joke-content licence | https://v2.jokeapi.dev/ , https://github.com/Sv443/JokeAPI | official (absent) |
| jokeapi: attribution | No attribution rule for joke text stated | https://jokeapi.dev/ | official (absent) |
| jokeapi: safe-mode | `safe-mode`: "JokeAPI will try its best to serve only jokes that are considered safe for everyone." Dark category generally unsafe. "doesn't mean human error is out of the question" | https://v2.jokeapi.dev/ | official |
| jokeapi: blacklist flags | `blacklistFlags`: matching jokes "will not be served". Flags: nsfw, religious, political, racist, sexist, explicit | https://v2.jokeapi.dev/ | official |
| icanhazdadjoke: id / base URL | `icanhazdadjoke`, `https://icanhazdadjoke.com/` (API root same host; random joke at `/`) | https://icanhazdadjoke.com/api | official |
| icanhazdadjoke: auth | "No authentication is required to use the icanhazdadjoke.com API." | https://icanhazdadjoke.com/api | official |
| icanhazdadjoke: content type | Accept `text/html` (default), `application/json`, `text/plain`. No Accept header gives `text/plain` for curl. Send `Accept: application/json` | https://icanhazdadjoke.com/api | official |
| icanhazdadjoke: User-Agent | Site "kindly ask[s]" for a custom `User-Agent` on all requests, naming the library or site plus a contact URL or e-mail. A request, not a stated hard rule | https://icanhazdadjoke.com/api | official |
| icanhazdadjoke: rate limit | Not stated | https://icanhazdadjoke.com/api | official (absent) |
| icanhazdadjoke: terms | No terms of service on home, API or About page | https://icanhazdadjoke.com/about | official (absent) |
| icanhazdadjoke: licence of joke text | Not stated. Only the site logo is licensed (CC BY-SA 3.0); jokes have no licence line | https://icanhazdadjoke.com/about | official (absent) |
| icanhazdadjoke: attribution / caching | No rule stated for either | https://icanhazdadjoke.com/api | official (absent): caching unclear |
| icanhazdadjoke: safe content | No filter flags documented. Dad jokes only; no safe-mode switch | https://icanhazdadjoke.com/api | official (absent) |
| third source | None found with a clear licence. Not pursued | n/a | UNVERIFIED |

Summary per source:

| id | base URL | content type | attribution needed | caching allowed | verdict |
|---|---|---|---|---|---|
| jokeapi | https://v2.jokeapi.dev/ | application/json (default) | no rule stated | unclear | ACCEPT with filters: has `safe-mode` and `blacklistFlags`, no key, 120/min limit; text licence unstated, so show with a source credit anyway |
| icanhazdadjoke | https://icanhazdadjoke.com/ | application/json (send Accept) | no rule stated | unclear | ACCEPT as fallback: no key, short family-style jokes; no safety filter and no terms, so risk is only licence silence |

Decision: ACCEPT `jokeapi` as primary with `safe-mode`, `blacklistFlags=nsfw,religious,political,racist,sexist,explicit`, `type=single`, `format=json`; keep the length cap and the 2-hour fetch limit in Kata.
Decision: ACCEPT `icanhazdadjoke` as fallback, with a descriptive `User-Agent` (app name plus a project URL, no personal data) and `Accept: application/json`.
Decision: neither source states a text licence or a caching rule. Cache only the latest joke per source for the 2-hour window, show a "source: name" credit, never redistribute or bulk-store jokes.

## 2. Safety-pin placeholder images

All licences read from Wikimedia Commons file metadata (API) and the freesvg page. Prefer the first two (no attribution needed).

| item | finding | source URL | confidence |
|---|---|---|---|
| Black Safety Pin.svg | Licence CC0. Author Torsten Henning. Direct: https://upload.wikimedia.org/wikipedia/commons/1/15/Black_Safety_Pin.svg | https://commons.wikimedia.org/wiki/File:Black_Safety_Pin.svg | official |
| SafetyPin (freesvg #115500) | Licence Public Domain (CC0), "No attribution required". Published by OpenClipart. Download: https://freesvg.org/download/115500 | https://freesvg.org/safetypin | official |
| Safety Pin Closed (30977033712).jpg | Licence: public domain (Commons metadata). Author Glen Bledsoe. Direct: https://upload.wikimedia.org/wikipedia/commons/3/35/Safety_Pin_Closed_%2830977033712%29.jpg | https://commons.wikimedia.org/wiki/File:Safety_Pin_Closed_(30977033712).jpg | official (metadata field; recheck file page before shipping) |
| Safety Pins(PSF).png | Licence: public domain (Commons metadata). Author Pearson Scott Foresman. Direct: https://upload.wikimedia.org/wikipedia/commons/f/f7/Safety_Pins%28PSF%29.png | https://commons.wikimedia.org/wiki/File:Safety_Pins(PSF).png | official (metadata field; recheck) |
| A bag of safety pins in China.jpg | Licence CC BY 4.0. Author Yejianfei. Needs attribution. Direct: https://upload.wikimedia.org/wikipedia/commons/8/80/A_bag_of_safety_pins_in_China.jpg | https://commons.wikimedia.org/wiki/File:A_bag_of_safety_pins_in_China.jpg | official |

Decision: ship `Black_Safety_Pin.svg` (CC0, vector, scales, no attribution) as the placeholder; keep the freesvg CC0 file as spare.
Decision: avoid the CC BY-SA files (share-alike duty) and the Science Museum Group object (CC BY-NC-SA).

## 3. Vision model

### 3a. Cloud (Anthropic)

| item | finding | source URL | confidence |
|---|---|---|---|
| Current vision models | All current models take image input. Ids: `claude-fable-5-2`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`. Older with vision: `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-8`, others | https://platform.claude.com/docs/en/about-claude/models/overview , https://platform.claude.com/docs/en/build-with-claude/vision | official |
| Price Haiku 5.5 (`claude-haiku-5-5`) | $0.10 / MTok input, $0.50 / MTok output for prompts up to 100,000 tokens; $0.50 / $2.50 above that | https://platform.claude.com/docs/en/about-claude/pricing | official |
| Price Sonnet 5.5 (`claude-sonnet-5-5`) | $2 input / $10 output per MTok | same | official |
| Price Opus 5.5 (`claude-opus-5-5`) | $4 input / $20 output per MTok | same | official |
| Price Fable 5.2 (`claude-fable-5-2`) | $8 input / $40 output per MTok | same | official |
| Price Haiku 4.5 (`claude-haiku-4-5-20251001`) | $1 input / $5 output per MTok | same | official |
| Batch API | 50% off input and output (Haiku 5.5 batch: $0.05 / $0.25) | same | official |
| Image token formula | Patches of 28x28 px; cost = ceil(w/28) x ceil(h/28). Standard tier cap 1,568 tokens (long edge 1,568 px). Claude 4.7 and later: high-resolution tier, cap 4,784 tokens, long edge 2,576 px | https://platform.claude.com/docs/en/build-with-claude/vision | official |
| Page image cost (PDF) | PDF support: image part "at most 1,568 visual tokens on every model"; text part 1,500-3,000 tokens per page. No extra PDF fee | https://platform.claude.com/docs/en/build-with-claude/pdf-support | official |
| Direct page image, example | 1000x1000 px = 1,296 tokens; 1920x1080 px = 2,691 tokens on the high-resolution tier (Haiku 5.5 is "4.7 and later"; docs do not list its tier explicitly) | https://platform.claude.com/docs/en/build-with-claude/vision | official; Haiku 5.5 tier is inferred |
| Cost estimate per page image | Assume 1,500 to 2,700 input tokens per page image, plus about 500 output tokens of transcript. Haiku 5.5: roughly 0.15 to 0.27 cent input plus 0.025 cent output, so about $0.0004 to $0.0006 per page; about $0.5 per 1,000 pages. Sonnet 5.5: about $0.003 to $0.01 per page. Own arithmetic from the listed prices | derived from pages above | derived; verify with token counting |
| Tokeniser note | Claude 4.7 and later use a tokeniser with about 30% more tokens for the same text | https://platform.claude.com/docs/en/about-claude/pricing | official |

Decision: cloud model is `claude-haiku-5-5` (cheapest current model with vision, same ids family, retirement not before October 7, 2027). Fall back to `claude-sonnet-5-5` only if Haiku misreads dense pages in a test. Set a per-job page cap and call token counting before large PDFs.

### 3b. Local (Ollama)

| item | finding | source URL | confidence |
|---|---|---|---|
| `glm-ocr` | 0.9B parameters; tags: latest 2.7 GB, q8_0 1.8 GB, bf16 2.7 GB; 128K context; text and image input. "Multimodal OCR model for complex document understanding": text, tables, figures. Licence not named on the page ("fully open-sourced"); check the repository | https://ollama.com/library/glm-ocr | official (licence UNVERIFIED) |
| `deepseek-ocr` | 3B, vision tag, "token-efficient OCR" | https://ollama.com/search?q=ocr | official |
| GPU fit | Size class 2-3 GB on disk, so about 4 GB VRAM likely suffices by size alone; CPU run also plausible for a 0.9B model. Memory use at run time is not on the page | https://ollama.com/library/glm-ocr | derived |
| Owner node | Cannot verify the owner's node, its GPU or its free VRAM. Test with `ollama run glm-ocr` there before relying on it | n/a | UNVERIFIED |

Decision: local option is `glm-ocr` (0.9B, about 2.7 GB); `deepseek-ocr` (3B) as the larger alternative. Both are untested on the owner node; first run is a manual smoke test.

## Not found

- Explicit caching or text-licence statement for JokeAPI and icanhazdadjoke jokes.
- Rate limit and terms of service for icanhazdadjoke.
- A third clean-joke source with a clear licence.
- Explicit resolution-tier statement for Haiku 5.5 (inferred from "Claude 4.7 and later").
- Licence of `glm-ocr` weights (not on the Ollama page).
- Runtime VRAM for `glm-ocr`; any fact about the owner's node.
- Re-check of the two public-domain JPEG/PNG Commons files beyond API metadata.

## Recommendation

- Joke source: `jokeapi` primary (filters, JSON, no key), `icanhazdadjoke` fallback; 2-hour minimum gap, credit shown, descriptive `User-Agent` for the fallback.
- Placeholder image: `Black_Safety_Pin.svg`, CC0, Torsten Henning.
- Vision model: cloud `claude-haiku-5-5` ($0.10 / $0.50 per MTok); local `glm-ocr` as optional offline path, node fit unverified.
- `[reader]` setting: ship disabled (`false`). It sends page images to a paid cloud API or needs a local model Kata cannot verify; the owner must opt in.

## Confirmation

Decision: the owner delegated these choices to the lead on 2026-11-25; the Recommendation above is accepted as written. `[reader]` ships disabled until the owner enables it.
