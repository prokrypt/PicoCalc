/**
 * PicoCalc Hello World
 * https://www.clockworkpi.com/
 */
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/gpio.h"

#include "i2ckbd.h"
#include "lcdspi.h"
#include "psram_spi.h"

const uint LEDPIN = 25;
psram_spi_inst_t* async_spi_inst;

int psram_test(psram_spi_inst_t*psram_spi){
    uint32_t psram_begin, psram_elapsed;
    float psram_speed;
    char buf[128];
    sprintf(buf,"Testing PSRAM...\n");
    printf("%s",buf);
    lcd_print_string(buf);

    // **************** 8 bits testing ****************
    psram_begin = time_us_32();
    for (uint32_t addr = 0; addr < (8 * 1024 * 1024); ++addr) {
        psram_write8(psram_spi, addr, (addr & 0xFF));
    }
    psram_elapsed = time_us_32() - psram_begin;
    psram_speed = 1000000.0 * 8 * 1024.0 * 1024 / psram_elapsed;
    sprintf(buf,"8 bit: PSRAM write 8MB in %d us, %d B/s\n", psram_elapsed, (uint32_t)psram_speed);
    printf("%s", buf);
    lcd_print_string(buf);

    psram_begin = time_us_32();
    for (uint32_t addr = 0; addr < (8 * 1024 * 1024); ++addr) {
        psram_write8_async(psram_spi, addr, (addr & 0xFF));
    }
    psram_elapsed = time_us_32() - psram_begin;
    psram_speed = 1000000.0 * 8 * 1024.0 * 1024 / psram_elapsed;
    sprintf(buf,"8 bit: PSRAM write async 8MB in %d us, %d B/s\n", psram_elapsed, (uint32_t)psram_speed);
    printf("%s", buf);
    lcd_print_string(buf);

    psram_begin = time_us_32();
    for (uint32_t addr = 0; addr < (8 * 1024 * 1024); ++addr) {
        uint8_t result = psram_read8(psram_spi, addr);
        if ((uint8_t)(addr & 0xFF) != result) {
            sprintf(buf,"\nPSRAM failure at address %x (%x != %x)\n", addr, addr & 0xFF, result);
            printf("%s", buf);
            lcd_print_string(buf);
            return 1;
        }
    }
    psram_elapsed = time_us_32() - psram_begin;
    psram_speed = 1000000.0 * 8 * 1024.0 * 1024 / psram_elapsed;
    sprintf(buf,"8 bit: PSRAM read 8MB in %d us, %d B/s\n", psram_elapsed, (uint32_t)psram_speed);
    printf("%s", buf);
    lcd_print_string(buf);

    // **************** 16 bits testing ****************
    psram_begin = time_us_32();
    for (uint32_t addr = 0; addr < (8 * 1024 * 1024); addr += 2) {
        psram_write16(psram_spi, addr, (((addr + 1) & 0xFF) << 8) | (addr & 0xFF));
    }
    psram_elapsed = time_us_32() - psram_begin;
    psram_speed = 1000000.0 * 8 * 1024.0 * 1024 / psram_elapsed;
    sprintf(buf,"16 bit: PSRAM write 8MB in %d us, %d B/s\n", psram_elapsed, (uint32_t)psram_speed);
    printf("%s", buf);
    lcd_print_string(buf);

    psram_begin = time_us_32();
    for (uint32_t addr = 0; addr < (8 * 1024 * 1024); addr += 2) {
        uint16_t result = psram_read16(psram_spi, addr);
        if ((uint16_t)(
                (((addr + 1) & 0xFF) << 8) |
                (addr & 0xFF)) != result
                ) {
            sprintf(buf,"PSRAM failure at address %x (%x != %x) ", addr, (
                    (((addr + 1) & 0xFF) << 8) |
                    (addr & 0xFF)), result
            );
            printf("%s", buf);
            lcd_print_string(buf);
            return 1;
        }
    }
    psram_elapsed = (time_us_32() - psram_begin);
    psram_speed = 1000000.0 * 8 * 1024 * 1024 / psram_elapsed;
    sprintf(buf,"16 bit: PSRAM read 8MB in %d us, %d B/s\n", psram_elapsed, (uint32_t)psram_speed);
    printf("%s", buf);
    lcd_print_string(buf);

    // **************** 32 bits testing ****************
    psram_begin = time_us_32();
    for (uint32_t addr = 0; addr < (8 * 1024 * 1024); addr += 4) {
        psram_write32(
                psram_spi, addr,
                (uint32_t)(
                        (((addr + 3) & 0xFF) << 24) |
                        (((addr + 2) & 0xFF) << 16) |
                        (((addr + 1) & 0xFF) << 8)  |
                        (addr & 0XFF))
        );
    }
    psram_elapsed = time_us_32() - psram_begin;
    psram_speed = 1000000.0 * 8 * 1024.0 * 1024 / psram_elapsed;
    sprintf(buf,"32 bit: PSRAM write 8MB in %d us, %d B/s\n", psram_elapsed, (uint32_t)psram_speed);
    printf("%s", buf);
    lcd_print_string(buf);

    psram_begin = time_us_32();
    for (uint32_t addr = 0; addr < (8 * 1024 * 1024); addr += 4) {
        uint32_t result = psram_read32(psram_spi, addr);
        if ((uint32_t)(
                (((addr + 3) & 0xFF) << 24) |
                (((addr + 2) & 0xFF) << 16) |
                (((addr + 1) & 0xFF) << 8)  |
                (addr & 0XFF)) != result
                ) {
            sprintf(buf,"PSRAM failure at address %x (%x != %x) ", addr, (
                    (((addr + 3) & 0xFF) << 24) |
                    (((addr + 2) & 0xFF) << 16) |
                    (((addr + 1) & 0xFF) << 8)  |
                    (addr & 0XFF)), result
            );
            printf("%s", buf);
            lcd_print_string(buf);
            return 1;
        }
    }
    psram_elapsed = (time_us_32() - psram_begin);
    psram_speed = 1000000.0 * 8 * 1024 * 1024 / psram_elapsed;
    sprintf(buf,"32 bit: PSRAM read 8MB in %d us, %d B/s\n", psram_elapsed, (uint32_t)psram_speed);
    printf("%s", buf);
    lcd_print_string(buf);
    // **************** n bits testing ****************
    uint8_t write_data[256];
    for (size_t i = 0; i < 256; ++i) {
        write_data[i] = i;
    }
    psram_begin = time_us_32();
    for (uint32_t addr = 0; addr < (8 * 1024 * 1024); addr += 256) {
        for (uint32_t step = 0; step < 256; step += 16) {
            psram_write(psram_spi, addr + step, write_data + step, 16);
        }
    }
    psram_elapsed = time_us_32() - psram_begin;
    psram_speed = 1000000.0 * 8 * 1024.0 * 1024 / psram_elapsed;
    sprintf(buf,"128 bit: PSRAM write 8MB in %d us, %d B/s\n", psram_elapsed, (uint32_t)psram_speed);
    printf("%s", buf);
    lcd_print_string(buf);

    psram_begin = time_us_32();
    uint8_t read_data[16];
    for (uint32_t addr = 0; addr < (8 * 1024 * 1024); addr += 256) {
        for (uint32_t step = 0; step < 256; step += 16) {
            psram_read(psram_spi, addr + step, read_data, 16);
            if (memcmp(read_data, write_data + step, 16) != 0) {
                sprintf(buf,"PSRAM failure at address %x", addr);
                printf("%s", buf);
                lcd_print_string(buf);
                return 1;
            }
        }
    }
    psram_elapsed = time_us_32() - psram_begin;
    psram_speed = 1000000.0 * 8 * 1024.0 * 1024 / psram_elapsed;
    sprintf(buf,"128 bit: PSRAM read 8MB in %d us, %d B/s\n", psram_elapsed, (uint32_t)psram_speed);
    printf("%s", buf);
    lcd_print_string(buf);

    lcd_print_string("PSRAM testing done\n");
}

int main() {

    stdio_init_all();

    init_i2c_kbd();
    lcd_init();

    gpio_init(LEDPIN);
    gpio_set_dir(LEDPIN, GPIO_OUT);

    lcd_clear();
    lcd_print_string("Hello World PicoCalc\n");
    gpio_put(LEDPIN, 1);
    sleep_ms(500);
    gpio_put(LEDPIN, 0);

    psram_spi_inst_t psram_spi = psram_spi_init_clkdiv(pio1, -1,1.0f,true);

    psram_test(&psram_spi);
    while (1) {
        int c = lcd_getc(0);
        if(c != -1 && c > 0) {
            lcd_putc(0,c);
        }
        sleep_ms(10);
    }
}

