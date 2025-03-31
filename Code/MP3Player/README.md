# PicoCalc simple mp3 player

All the operations in this document are performed in a Linux environment. A basic understanding of Linux, as well as familiarity with Git and cross-compilation  development, is required.

## toolchain

```
arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi
```

YAHAL   
https://github.com/cuu/YAHAL.git branch picocalc

## How to compile

### Get this code
```
git clone  https://github.com/clockworkpi/PicoCalc.git

```

### Get YAHAL first
```
git clone -b picocalc https://github.com/cuu/YAHAL.git
```
### Get arm toolchain

```
wget https://developer.arm.com/-/media/Files/downloads/gnu/13.3.rel1/binrel/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi.tar.xz
tar xvf arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi.tar.xz
```

### Compile

set **YAHAL_DIR** to the path of your local YAHAL location
```bash
export YAHAL_DIR=/wherever/yahal/is
```
set **arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi/bin** in your $PATH 

```bash
export PATH=/wherever/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi/bin/is:$PATH
```

then
 
```bash
mkdir build
cd build
cmake ..
make
```

Copy pico-mp3-player.uf2 to picocalc

### Notes
Currently only supports up to **64** mp3 files, and only ascii characters are legal mp3 filename.

#### Special thanks

https://git.fh-aachen.de/Terstegge/YAHAL

Thanks to YAHAL  
Without this great project YAHAL, mp3 playback on pico would be a pain  

## Pre-compiled uf2

https://github.com/clockworkpi/PicoCalc/blob/master/Bin/PicoCalc%20SD/firmware/PicoCalc_MP3Player_v0.5.uf2


