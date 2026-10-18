# LisaFuji Browser

A text web browser for the Apple Lisa Office System. The Lisa asks a small gateway (a Raspberry Pi) for a page through
an RS-232 FujiNet; the gateway simplifies it to numbered text that fits the Lisa's window, 14 lines at a time, and the
Lisa shows it. Click a link's number (or type it and RETURN) to follow it.

Tool number **419314** in the GyroPilot series. Lisa Pascal, Workshop 3.0, Lisa Office System 3.1. The gateway is
Python (`gateway/gateway.py`).

## Status

- **0.1 beta** -- tested on a Lisa 2/10 with a real FujiNet, 16-17 October 2026: the Apple Inc. article on Wikipedia,
  all 99 pages (`releases/LISAFUJI_BROWSER_0_1.dc42`).
- **0.2 beta** -- pictures on click: a picture that has a description (alt text, a caption or a title) shows as a
  numbered link; following it, the gateway sends it dithered to black and white with Bill Atkinson's algorithm and the
  Lisa draws it row by row. Built and tested in LisaEm; waiting for the 2/10 (`releases/LISAFUJI_BROWSER_0_2_BETA.dc42`).
  The sources here are 0.2 (REV K).

## Using it

The start page (key H) lists the gateway's own pages: the weather in your town, the space station and who is aboard,
news, Wikipedia search and more. G goes to an address, S searches, SPACE / N / P page, B goes back, R reloads, L lists
the links. The Gateway menu sets the access key and your town (kept in GATEWAYS.TEXT) and chooses among gateways.

The public gateway needs an access key; ask on LisaList2. Or run your own: `gateway/gateway.py` (Python 3, the
`requests`, `beautifulsoup4` and `Pillow` packages).

## Credits

Tim O'Connor (bmwcyclist on LisaList2, GyroPilot on GitHub), with Claude (Anthropic). Lisa Pascal with the Lisa
Workshop 3.0 for Lisa Office System 3.1; built in LisaEm and proven on a Lisa 2/10 and a LisaFPGA with a FutureVision
Research FujiNet for RS-232.
