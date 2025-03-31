cmake_minimum_required(VERSION 3.16)

# Setup board for Pico 1
set(PICO_BOARD pico)

# Setup board for Pico 2W
# set(PICO_BOARD pico2)

include(pico_sdk_import.cmake)

project(pico_lvgl_display_demo)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

include_directories(
  ${CMAKE_CURRENT_LIST_DIR}
)



add_subdirectory(i2ckbd)
add_subdirectory(lcdspi)
add_subdirectory(${CMAKE_CURRENT_LIST_DIR}/lib/lvgl lvgl)


add_executable(pico_lvgl_display_demo
    main.c
    lv_port_indev_picocalc_kb.c
    lv_port_disp_picocalc_ILI9488.c
)

target_compile_options(pico_lvgl_display_demo PRIVATE -DPICOMITE
										-DPICO_HEAP_SIZE=0x1000 
										-DGUICONTROLS
										-DPICO_CORE0_STACK_SIZE=0x1000
										)

target_compile_definitions(pico_lvgl_display_demo PRIVATE LV_USE_DEMO_WIDGETS=1)

target_include_directories(pico_lvgl_display_demo PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/lib/lvgl/lvgl
    ${CMAKE_CURRENT_LIST_DIR}/lib/lvgl/lvgl/src
    ${CMAKE_CURRENT_LIST_DIR}/lib/lvgl/lvgl/demos
)


target_link_libraries(pico_lvgl_display_demo
  pico_stdlib
  hardware_flash
  hardware_irq
  hardware_adc
  hardware_pwm
  hardware_i2c
  hardware_spi
  hardware_dma
  hardware_exception
  hardware_pio
  pico_multicore
  i2ckbd
  lcdspi
  lvgl
  lvgl_demos
)

pico_enable_stdio_usb(pico_lvgl_display_demo 0)
pico_enable_stdio_uart(pico_lvgl_display_demo 1)
pico_add_extra_outputs(pico_lvgl_display_demo)
