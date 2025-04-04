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




// The event handler
static void textarea_event_handler(lv_event_t *e) {
    lv_obj_t *textarea = lv_event_get_target(e);
    printf("Textarea: '%s'\n", lv_textarea_get_text(textarea));
}


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

    // The textarea
    lv_obj_t *input = lv_textarea_create(screen);
    lv_obj_set_width(input, 280);
    lv_obj_set_height(input, LV_SIZE_CONTENT);    /// 20
    lv_obj_center(input);
    // Enable keyboard input for the text box
    lv_textarea_set_placeholder_text(input, "Input:");
    lv_textarea_set_one_line(input, true);
    lv_obj_set_style_anim_time(input, 5000, LV_PART_CURSOR|LV_STATE_FOCUSED);
    // Textarea event handler
    lv_obj_add_event_cb(input, textarea_event_handler, LV_EVENT_READY, input);

    // Load the screen
    lv_scr_load(screen);
#endif

    // Main loop
    while (1)
    {
        lv_timer_handler();
        lv_tick_inc(20); // Increment LVGL tick by 5 milliseconds
        sleep_ms(5); // Sleep for 5 milliseconds}
    }
}
