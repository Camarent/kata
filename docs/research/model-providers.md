# Model provider notes: an open-weights API provider

Example of the checks kata runs before it lets a cloud provider receive any user content.
Facts were checked on official pages where marked OFFICIAL and from third-party sources where
marked SECONDARY; unverified items are marked. Prices are deliberately left out because they
change often; re-check live pages before relying on any provider.

## Models and limits

| Item | Finding | Tag |
|---|---|---|
| API models | A fast "flash" model with thinking and non-thinking modes and vision, and a larger "pro" model without vision. Legacy model names remain accepted. | OFFICIAL |
| Context and output | 1M context, up to 384K output. | OFFICIAL |
| Time-of-day pricing | Peak and off-peak rates exist; off-peak is half of peak. | OFFICIAL |
| Concurrency | Limited per account, not per key; over the limit returns HTTP 429; more capacity on request. No fixed requests-per-minute figure. The server closes the connection if inference has not started after 10 minutes. | OFFICIAL |
| Free grant, minimum top-up, payment methods | Not confirmed from official sources; non-local cards reportedly fail at times. | UNVERIFIED / SECONDARY |

## Open weights

| Item | Finding | Tag |
|---|---|---|
| Licence | MIT for the model weights and repository; commercial use allowed. | OFFICIAL |
| Size | The large models are far too big for a single consumer GPU. | OFFICIAL |
| Small distills | A 14B reasoning distill (MIT, based on an Apache-2.0 model) should fit a single consumer GPU at 4-bit (estimate). Being a reasoning model, its latency must be tested before it is used for interactive tasks. | UNVERIFIED |

## API data handling

| Item | Finding | Tag |
|---|---|---|
| Governing law | The law of the provider's home jurisdiction; disputes in its courts. | OFFICIAL |
| Developer duties | The developer answers for inputs and outputs, must disclose AI-generated output to end users, and must handle personal-data consent, retention and erasure for their own users. | OFFICIAL |
| Input ownership | The developer keeps rights in inputs and receives rights in outputs; outputs may be used to train other models. | OFFICIAL |
| Training on API inputs | The API terms are silent on training on inputs. The privacy policy lists model training as a purpose for personal data and provides an opt-out. | OFFICIAL |
| Data location | Data is collected, processed and stored in the provider's home country. | OFFICIAL |
| Retention | No fixed period for API inputs and outputs; no zero-retention option found. | OFFICIAL / SECONDARY |
| Regulators | Several European regulators have restricted or questioned the provider's consumer app; no final sanction was found. | SECONDARY |
| Incidents | A 2025 exposure of an unauthenticated database containing chat history was reported and fixed quickly. | SECONDARY |

## Third-party hosts of open weights

Regional hosts and routers offer the open-weights models through OpenAI-compatible APIs.
Residency and data policy differ per host and were not verified for most of them. A router
sends data to whichever backend serves the request, so the region varies.

## Compatibility

- OpenAI-format and Anthropic-format endpoints are offered, so one adapter covers it.
- Supported: JSON output, tool calls, streaming (standard in the OpenAI format, not verified on
  the official page), prefix completion and fill-in-the-middle (beta).
- JSON mode: the prompt must contain the word "json" and an example. Invalid JSON can come back
  as empty content with a normal finish reason, so set a generous output limit and retry in
  code.
- Strict tool calls (beta) need all properties in `required` and `additionalProperties: false`;
  length and item-count constraints are unsupported.
- No reliable independent benchmarks were found for summarisation, tagging or code review.

## How kata uses this

- Treat a provider whose data leaves the user's jurisdiction, offers no retention guarantee and
  may train on requests as **non-sensitive only**: public text, the page the user has open,
  generic notes. Never credentials, other people's personal data, proprietary code or anything
  under an NDA.
- Safer options in order: a local model; a regional host with a verified data policy; the
  direct API for non-sensitive content only.
- Provider facts feed the policy flags (may train, jurisdiction, local) that the router uses
  with the secret scanner. See [`../decisions.md`](../decisions.md).
