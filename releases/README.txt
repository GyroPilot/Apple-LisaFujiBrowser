LisaFuji Browser 1.0 beta for the Apple Lisa Office System       October 2026 (release build REV N)
A text web browser through an RS-232 FujiNet and the LisaWeb gateway.  Tool 419314.

USE
  Needs an RS-232 FujiNet on Serial B at 9600 baud.  Open the tool; nothing is sent to the FujiNet
  until you press a key.

    H  the start page (weather in your town, the space station, news, Wikipedia search ...)
    G  go to an address        S  search Wikipedia        ?  help
    On a page: click a link's number, or type it and RETURN.  SPACE next page, P previous,
    B back, R reload, L the links.  A [picture: ...] link draws the picture, line by line.

  The public gateway is Tim's Raspberry Pi.  This copy makes its own access key the first time
  it asks the gateway for a page, and keeps it in GATEWAYS.TEXT on the floppy: nothing to ask
  for, nothing to type.  The Gateway menu can set your town, a named key, or another gateway.

SOURCE
  Lisa Pascal, Workshop 3.0.  github.com/GyroPilot/Apple-LisaFujiBrowser  (the gateway is in
  gateway/: Python 3 with requests, beautifulsoup4 and Pillow; run your own anywhere).
  Tim O'Connor (bmwcyclist), with Claude.  Tested on a Lisa 2/10, October 2026.

WHAT'S IN THIS RELEASE
  LISAFUJI_BROWSER_1_0.dc42             the release floppy
  LisaFujiBrowser_1.0_beta_source.zip   Lisa Pascal sources, exec files, the icon and the gateway
