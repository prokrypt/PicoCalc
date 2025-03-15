# Setting Up Arduino Development for PicoCalc keyboard

This guide walks you through setting up your Arduino environment to develop for the PicoCalc keyboard (STM32F103R8T6) microcontroller using the [STM32duino Arduino Core](https://github.com/stm32duino/Arduino_Core_STM32). It also includes instructions to manually install the [XPowersLib](https://github.com/cuu/XPowersLib.git) library.

## 1. Install Arduino IDE
Download and install the latest version of [Arduino IDE](https://www.arduino.cc/en/software) for your operating system.

## 2. Install STM32duino Core via Board Manager
To use STM32 microcontrollers with Arduino, you need to install the STM32duino core.

### **Steps:**
1. Open **Arduino IDE**.
2. Go to **File** → **Preferences**.
3. In the **Additional Board Manager URLs** field, add the following URL:
   ```
   https://github.com/stm32duino/BoardManagerFiles/raw/main/package_stmicroelectronics_index.json
   ```
4. Click **OK**.
5. Open **Tools** → **Board** → **Boards Manager**.
6. Search for **STM32** and install **STM32 MCU based boards** by STMicroelectronics.

## 3. Select the Correct Board and Settings
Once the STM32 core is installed, configure the board settings:

1. Go to **Tools** → **Board** → **STM32 Boards** → **Generic STM32F1 series**.
2. In **Tools** menu, configure the following settings:
   - **Board part number**: `Generic F103R8Tx`
   - **Upload method**: `STM32CubeProgrammer(Serial)`

## 4. Install XPowersLib Manually
Instead of installing XPowersLib via the Arduino Library Manager, we will manually clone it into the correct location.

### **Steps:**
1. Open a terminal.
2. Navigate to your Arduino libraries folder:
   ```bash
   cd ~/Arduino/libraries
   ```
3. Clone the XPowersLib repository from the correct branch:
   ```bash
   git clone -b stm32f103r8t6 https://github.com/cuu/XPowersLib.git
   ```

This ensures the library is correctly placed for the Arduino IDE to detect it.

## 5. Get Code 
```bash
git clone https://github.com/clockworkpi/PicoCalc.git
```
the keyboard code is in `Code/picocalc_keyboard`

open Code/picocalc_keyboard/picocalc_keyboard.ino in Arduino IDE 


## 6. Upload Code to PicoCalc Keyboard
To upload your code:

1. Connect the picocalc board to your PC using a usb type-c cable.
2. Set the **DIP 1** to ON
3. Long-Press the **Power On** button to power on.
4. Click the **Upload** button in Arduino IDE.
5. After upload, set **DIP 1** to OFF

Here is a screenshot of working arduino ide:  

![screenshot](https://github.com/clockworkpi/PicoCalc/blob/master/wiki/picocalc_keyboard_arduino_ide_compile.png)

DIP switches are on the back of picocalc mainboard  
![dips](https://github.com/clockworkpi/PicoCalc/blob/master/wiki/picocalc_back_dip_switch.png)

### Libraries version info  

* STM32 MCU based boards 2.10.0
* XPowersLib 0.2.3 (cuu mod)

