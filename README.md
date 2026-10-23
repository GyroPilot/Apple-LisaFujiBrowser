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
  Lisa draws it row by row (`releases/LISAFUJI_BROWSER_0_2_BETA.dc42`).
- **1.0 beta (REV N) -- 21 October 2026.** Each copy makes its own access key the first time it talks to the public
  gateway, so there is nothing to ask for or type; the gateway registers it, and a copy that misbehaves can be switched
  off. Release floppy `releases/LISAFUJI_BROWSER_1_0.dc42`.
- **1.1 beta (REV O) -- 22 October 2026.** Picture icons on the page: a small 96 x 48 icon of each described
  picture appears under its link a moment after the text, so you can see what a picture is before you ask for it;
  click the icon (or follow the link) for the big one. Gateway menu: *Picture Icons on Pages* turns them off and on.
  Tested on a Lisa 2/10. Release floppy `releases/LISAFUJI_BROWSER_1_1.dc42`; the sources here are 1.1 beta (REV O).

## Using it

The start page (key H) lists the gateway's own pages: the weather in your town, the space station and who is aboard,
news, Wikipedia search and more. G goes to an address, S searches, SPACE / N / P page, B goes back, R reloads, L lists
the links. The Gateway menu sets the access key and your town (kept in GATEWAYS.TEXT) and chooses among gateways.

The public gateway (Tim's Raspberry Pi) is open to the Browser: on the first request a copy makes its own key (`u`
and eleven letters and digits, kept in GATEWAYS.TEXT on its floppy) and the gateway registers it. Limits: 3 new
copies an hour from one address and 40 a day; 60 requests a minute and 3000 a day for a copy. The Gateway menu can
still set a named key or choose another gateway. Or run your own: `gateway/gateway.py` (Python 3, the `requests`,
`beautifulsoup4` and `Pillow` packages); `gateway/gw_ids.py` lists, bans and unbans the self-made keys. The gateway here
is REV F: it serves the icons (`/w/thumb`) and marks the icon slots in a page when a Browser asks for them (`tv=1`).

## Credits

Tim O'Connor (bmwcyclist on LisaList2, GyroPilot on GitHub), with Claude (Anthropic). Lisa Pascal with the Lisa
Workshop 3.0 for Lisa Office System 3.1; built in LisaEm and proven on a Lisa 2/10 and a LisaFPGA with a FutureVision
Research FujiNet for RS-232.

## The speed (phase 2, 23 October 2026)

The tool sets the FujiNet's speed too: Speed > Use 19200 baud posts the new speed to the adapter's own web page through the
FujiNet's network device, presses its Reset button and opens the port again at the new speed (about 20 seconds;
the adapter's WiFi must be up). At its first port open of each launch the tool probes for the speed (the saved one,
then the other of 9600/19200) and keeps what answers, so after any one tool changes the adapter the others follow.
The choice is kept in FNSPEED.DATA beside the tool.
