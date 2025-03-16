cmake_minimum_required(VERSION 3.16)

# Set the target board
set(YAHAL_BOARD "rpi-pico")
# set(YAHAL_DIR ~/gitlab/YAHAL)

# Locate the YAHAL library folder
include(YAHAL_import.cmake)

project(pico-mp3-player)

add_executable(pico-mp3-player
    pico_mp3_player.cpp
    main_task.cpp
    sd_reader_task.cpp
    mp3_decoder_task.cpp
    i2ckbd.cpp
)

# Add YAHAL, MAD and FatFs libraries
yahal_add_me(pico-mp3-player)
yahal_add_library(pico-mp3-player MAD)
yahal_add_library(pico-mp3-player FatFs)
yahal_add_library(pico-mp3-player uGUI)

yahal_add_custom_targets(pico-mp3-player)
yahal_add_extra_outputs(pico-mp3-player)
