# How to compile NES emulator
```bash
git clone https://github.com/shapoco/shapones.git

cd shapones
git apply shapones.patch
cd samples/v3/
mkdir build
cd build
export PICO_SDK_PATH=/to/where/your/pico/sdk/is
cmake ..
make
```

Copy picocalc_nes.uf2 into picocalc

use up/down key to select *.nes rom, 
* \- key is select
* = key is start,
* [ key is a 
* ] key is b

press -(select) and =(start) together, will reset the emulator to the rom selection page.

Due to the limitation of Pico memory, only ROMs with a size less than or equal to **44KB** can be used.

# Pre-compiled uf2

https://github.com/clockworkpi/PicoCalc/blob/master/Bin/PicoCalc%20SD/firmware/PicoCalc_NES_v1.0.uf2


