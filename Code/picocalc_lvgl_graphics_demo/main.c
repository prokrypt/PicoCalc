/**
 * PicoCalc LVGL Graphics Demo
 * 
 * Demo App Uses LVGL to show demos on the PicoCalc.
 * Implements basic keyboard input and display driver. 
 * 
 * Author: HsuahHanLai
 * https://www.hsuanhanlai.com/
 */

#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/gpio.h"


#include "lv_conf.h"
#include "lvgl/lvgl.h"
#include "lv_port_indev_picocalc_kb.h"
#include "lv_port_disp_picocalc_ILI9488.h"
#include "lvgl/demos/lv_demos.h"


#define ILI9488 1
#define USE_DEFAULT_DEMO 1

#define BYTE_PER_PIXEL (LV_COLOR_FORMAT_GET_SIZE(LV_COLOR_FORMAT_RGB565)) /*will be 2 for RGB565 */


const unsigned int LEDPIN = 25;

int main()
{
    // Initialize standard I/O
    stdio_init_all();

    // Initialize LED
    gpio_init(LEDPIN);
    gpio_set_dir(LEDPIN, GPIO_OUT);

    // Initialize LVGL
    lv_init();

    // Initialize the custom display driver
    lv_port_disp_init();

    // Initialize the keyboard input device (implementation in lv_port_indev_kbd.c)
    lv_port_indev_init();



#ifdef USE_DEFAULT_DEMO
    // Initialize and run LVGL demo
    lv_demo_widgets(); // Replace with the correct demo function if needed
#else
    // Create a screen
    lv_obj_t *screen = lv_obj_create(NULL);

    // Create a text box
    lv_obj_t *textbox = lv_textarea_create(screen);
    lv_obj_set_size(textbox, 200, 50); // Set size of the text box
    lv_obj_align(textbox, LV_ALIGN_CENTER, 0, 0); // Center the text box on the screen

    // Enable keyboard input for the text box
    lv_textarea_set_placeholder_text(textbox, "Enter text...");
    lv_textarea_set_one_line(textbox, true); // Set to single-line mode

    // Load the screen
    lv_scr_load(screen);
#endif

    // Main loop
    while (1)
    {
        lv_timer_handler();
        lv_tick_inc(5); // Increment LVGL tick by 5 milliseconds
        sleep_ms(1); // Sleep for 5 milliseconds}
    }
}
