LisaFuji Browser 1.3, update 1 (3 November 2026, release build REV V)      tool 419314
Same LisaFuji Browser 1.3 program with these changes, tested on a Lisa 2/10 through an ESProFile running
ESPFuji on 3 November 2026; the floppy LISAFUJI_BROWSER_1_3.dc42 replaces the earlier one of the same name:
- A failed connection through an ESProFile now shows the ESProFile's own reason ("the drive said: ...")
  instead of only "status 207".
- The release floppy's disk name is exact (no trailing spaces).

--------------------------------------------------------------------------------------------------------------

LisaFuji Browser 1.3 for the Lisa Office System                       1 November 2026
A web browser for the Lisa, with pictures and HTTPS sites, no longer beta. Pages come from a
LisaWeb gateway (the public one runs on Tim's Raspberry Pi) through a FujiNet: an RS-232 FujiNet on
Serial B, a LisaFPGA with LisaNet, or an ESProFile running ESPFuji. Pictures show on the page as
icons and full size on click; H start page, G address, S search, B back. Tested on a Lisa 2/10
through an ESProFile (HTTPS, pictures, back and forward). Tool 419314, T. O'Connor (bmwcyclist).
Source (MIT): github.com/GyroPilot/Apple-LisaFujiBrowser
