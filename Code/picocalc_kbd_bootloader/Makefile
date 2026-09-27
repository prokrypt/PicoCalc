# PicoCalc keyboard I2C bootloader (STM32F103R8).
#   make            -> build/kbd_bootloader.bin with arm-none-eabi-gcc (must stay under 8 KB)
#   make clang      -> same with clang + lld (what the branch was checked with)
#   make hosttest   -> run kbdflash.py against the protocol core (tools/sim_test.py)
#   make emutest    -> run the built bootloader in an STM32F103 emulator (tools/emu_test.py)
CROSS  ?= arm-none-eabi-
CC      = $(CROSS)gcc
OBJCOPY = $(CROSS)objcopy
SIZE    = $(CROSS)size
CFLAGS  = -mcpu=cortex-m3 -mthumb -Os -ffreestanding -fno-common -ffunction-sections \
          -Wall -Wextra -Werror -std=c99
LDFLAGS = -nostdlib -nostartfiles -T link.ld -Wl,--gc-sections -Wl,-Map=build/kbd_bootloader.map

all: build/kbd_bootloader.bin

build/kbd_bootloader.elf: bl_main.c bl_core.c bl_core.h link.ld
	mkdir -p build
	$(CC) $(CFLAGS) $(LDFLAGS) bl_main.c bl_core.c -o $@
	$(SIZE) $@

build/kbd_bootloader.bin: build/kbd_bootloader.elf
	$(OBJCOPY) -O binary $< $@
	@test $$(stat -c %s $@) -le 8192 || (echo "bootloader over 8 KB" && false)

build/libblcore.so: bl_core.c bl_core.h tools/host_hal.c
	mkdir -p build
	cc -O1 -g -Wall -Wextra -Werror -std=c99 -shared -fPIC -I. bl_core.c tools/host_hal.c -o $@

clang:
	mkdir -p build
	clang --target=thumbv7m-none-eabi $(filter-out -mcpu=cortex-m3,$(CFLAGS)) -mcpu=cortex-m3 \
	  -nostdlib -fuse-ld=lld -Wl,-T,link.ld -Wl,--gc-sections bl_main.c bl_core.c -o build/kbd_bootloader.elf
	llvm-objcopy -O binary build/kbd_bootloader.elf build/kbd_bootloader.bin
	@test $$(stat -c %s build/kbd_bootloader.bin) -le 8192 || (echo "bootloader over 8 KB" && false)
	@ls -l build/kbd_bootloader.bin

hosttest: build/libblcore.so
	python3 tools/sim_test.py build/libblcore.so

# needs `pip install unicorn` and the app .bin (tools/build_app.sh); EMU_ARGS=--quick for a short run
APP_BIN ?= build/app/picocalc_keyboard.ino.bin
emutest: build/kbd_bootloader.bin
	python3 tools/emu_test.py build/kbd_bootloader.bin $(APP_BIN) $(EMU_ARGS)

clean:
	rm -rf build

.PHONY: all clang hosttest emutest clean
