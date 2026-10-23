# LisaFuji Browser changelog

## 1.1 beta REV P / REV Q -- 22-23 Oct 2026 -- update of the 1.1 beta release (staged)
- REV P: the Gateway menu's Picture Icons item carries a check mark; turning it on fetches the icons for the page
  on the screen at once, turning it off erases them.
- REV Q: the Speed menu sets the FujiNet too (LisaFuji REV S's way: web page over N:, reset, port again), FNSPEED.DATA
  beside the tool keeps speed and port, and the first port open of each launch probes for the speed (FnFind).
## 1.1 beta REV O -- 22 Oct 2026 -- RELEASE
- Picture icons on the page: the gateway (REV F) puts a slot after each picture link; after the text is drawn the
  Browser fetches a 96 x 48 icon for each slot (about a second each at 9600 baud) and draws it there; a click on an
  icon is the big picture; the icons survive a redraw. Gateway menu item 5, "Picture Icons on Pages", turns them
  off and on (it takes effect on the next fetch). Tested on a Lisa 2/10 (icon, redraw, click, toggle).
- Gateway REV F also no longer serves an icon as the big picture (the picture cache ignores icon documents).
## 1.0 beta REV N -- 21 Oct 2026 -- RELEASE 1.0 beta
- Version 1.0 beta (About box 21 October 2026); the program is REV M.  Overnight in LisaEm from its floppy against
  the public gateway: the copy's own key made and registered, the start page, the Apple Lisa article.
- Gateway REV E (20 Oct): self-registering keys (ids.txt, ids_banned.txt, gw_ids.py), limits on new copies; REV E1:
  a picture that is not shown and has no alt text of its own gets no line (the Wikipedia infobox logo made a second,
  unnumbered picture line); picture labels cut at 56 so the link number stays on the line.
## 0.2.1 beta REV M -- 20 Oct 2026
- Each copy makes its own access key for the public gateway on first use (seconds of the year and the idle count
  before the first request, through three Wichmann-Hill generators); kept in GATEWAYS.TEXT.  Tested in LisaEm against
  the real Pi.  On the 2/10, 0.2 beta had reached the key wall: this removes it.
## 0.2 beta REV K -- 17 Oct 2026 -- built, tested in LisaEm
- Pictures on click (only described pictures), drawn row by row, kept in LFBPICT.DATA so menus do not wipe them.
## 0.1 beta REV J -- 17 Oct 2026 -- RELEASE 0.1 beta
- Set Your Town (Gateway menu). Tested on the 2/10 through the public gateway.
## REV A-I -- 14-17 Oct 2026
- First build; the Gateway menu and the access key; reliability on the real FujiNet (the first STATUS after an OPEN
  waits 25 s, CLOSE before and after OPEN); page caching on the gateway.
