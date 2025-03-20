# PicoCalc Hello World

Demonstrate how to use spi screen and i2c keyboard on PicoCalc.

## Building
```
mkdir build
cd build
export PICO_SDK_PATH=/where/pico-sdk/is
cmake ..
make  
```

## Notes

 On PicoCalc, the default serial port of the Pico is the USB Type-C port, not its built-in Micro USB port.
