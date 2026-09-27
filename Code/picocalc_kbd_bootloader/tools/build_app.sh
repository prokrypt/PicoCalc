#!/bin/sh
# Build the keyboard app linked at 0x08002000, above the I2C bootloader.
# Needs arduino-cli with the STM32 core 2.10.0 and cuu's XPowersLib (see the wiki page
# "Setting-Up-Arduino-Development-for-PicoCalc-keyboard").
#
# Checked with arduino-cli 1.3.1 + STM32 core 2.10.0: build.flash_offset sets both
# LD_FLASH_OFFSET (linker origin) and -DVECT_TAB_OFFSET; the sketch's build_opt.h adds
# -DUSER_VECT_TAB_ADDRESS so SystemInit() points VTOR at 0x08002000 itself.
# upload.maximum_size=64512 ends the app's FLASH region at the info page (0x0800FC00).
# Extra arduino-cli arguments go in ARDUINO_CLI_EXTRA, e.g. when the arduino.cc
# downloads are blocked and ctags was built locally:
#   ARDUINO_CLI_EXTRA="--build-property runtime.tools.ctags.path=/path/to/ctags-dir"
set -e
here=$(cd "$(dirname "$0")" && pwd)
sketch="$here/../../picocalc_keyboard"
out="${1:-$here/../build/app}"
arduino-cli compile \
  --fqbn STMicroelectronics:stm32:GenF1:pnum=GENERIC_F103R8TX \
  --build-property build.flash_offset=0x2000 \
  --build-property upload.maximum_size=64512 \
  $ARDUINO_CLI_EXTRA \
  --output-dir "$out" "$sketch"
bin=$(ls "$out"/*.ino.bin)
python3 "$here/mkimage.py" check "$bin"
echo "app image: $bin  (copy to /sd/kbd/app.bin for kbdflash)"
