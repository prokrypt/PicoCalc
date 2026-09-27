#!/bin/sh
# Build the keyboard app linked at 0x08002000, above the I2C bootloader.
# Needs arduino-cli with the STM32 core 2.10.0 and cuu's XPowersLib (see the wiki page
# "Setting-Up-Arduino-Development-for-PicoCalc-keyboard").
#
# build.flash_offset moves both the linker origin and VECT_TAB_OFFSET in the
# stm32duino core; upload.maximum_size stops the app at the info page (0x0800FC00).
set -e
here=$(cd "$(dirname "$0")" && pwd)
sketch="$here/../../picocalc_keyboard"
out="${1:-$here/../build/app}"
arduino-cli compile \
  --fqbn STMicroelectronics:stm32:GenF1:pnum=GENERIC_F103R8TX \
  --build-property build.flash_offset=0x2000 \
  --build-property upload.maximum_size=64512 \
  --output-dir "$out" "$sketch"
bin=$(ls "$out"/*.ino.bin)
python3 "$here/mkimage.py" check "$bin"
echo "app image: $bin  (copy to /sd/kbd/app.bin for kbdflash)"
