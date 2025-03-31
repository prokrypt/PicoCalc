# How to compile uLisp 

uLisp for PicoCalc uses [Arduino IDE](https://www.arduino.cc/en/software) for development  

All the operations in this document are performed in a Linux environment. A basic understanding of Linux, as well as familiarity with Git and Arduino development, is required. 

## Install arduino-pico 

Open up the Arduino IDE and go to File->Preferences.

In the dialog that pops up, enter the following URL in the "Additional Boards Manager URLs" field:

https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json

![image](https://user-images.githubusercontent.com/11875/111917251-3c57f400-8a3c-11eb-8120-810a8328ab3f.png)

Hit OK to close the dialog.

Go to Tools->Boards->Board Manager in the IDE

Type "pico" in the search box and select "Add":

![image](https://user-images.githubusercontent.com/11875/111917223-12063680-8a3c-11eb-8884-4f32b8f0feb1.png)


Original document reference: https://github.com/earlephilhower/arduino-pico/blob/master/README.md

## Patch code
```
git clone https://github.com/technoblogy/ulisp-arm.git

cd uLisp-arm

git reset --hard 97e61151dfb236311089abd3e89029e367613f70  #Switch to the required version

git clone  https://github.com/clockworkpi/PicoCalc.git #get patch code

git apply  PicoCalc/Code/uLisp/uLisp.patch

```

Install **TFT_eSPI 2.5.34** in arduino ide and patch it

```
cp patches/Setup60_RP2040_ILI9488.h ~/Arduino/libraries/TFT_eSPI/User_Setups/Setup60_RP2040_ILI9488.h
```

Add a new include   
```
#include <User_Setups/Setup60_RP2040_ILI9488.h> 
```
and comment out 
```
#include <User_Setup.h>
```
in  `~/Arduino/libraries/TFT_eSPI/User_Setup_Select.h`

Install `arduino_picocalc_kbd` for interacting with picocalc's keyboard via i2c.  
```
cd ~/Arduino/libraries
git clone https://github.com/cuu/arduino_picocalc_kbd.git
```

## Compile and upload

In arduino ide ,config board and other arguments  

Put pico in BOOTSEL mode by pressing BOOTSEL key and power on it  

Hit the upload button in arduino ide  

Here is the screenshot for reference:  

![ulisp arduino](https://github.com/clockworkpi/PicoCalc/blob/master/wiki/arduino_uLisp_compile.png)

It should be noted that uLisp's default serial port speed is **9600**


## Pre-compiled uf2
https://github.com/clockworkpi/PicoCalc/blob/master/Bin/PicoCalc%20SD/firmware/PicoCalc_uLisp_v1.0.uf2

