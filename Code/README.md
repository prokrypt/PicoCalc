# Code 
Here are all the patch codes of PicoCalc's factory program

* PicoCalc_Fuzix_v1.0
* PicoCalc_MP3Player_v0.5
* PicoCalc_NES_v1.0
* PicoCalc_PicoMite_v1.0
* PicoCalc_uLisp_v1.0


# Preparation

See how to setup pico sdk development   

https://github.com/clockworkpi/PicoCalc/wiki/Setting-Up-the-Pico-SDK-on-Linux-for-Pico-Development


## How to compile FUZIX 
```bash
git clone https://github.com/EtchedPixels/FUZIX.git
cd FUZIX

git reset --hard f0d56efd5ba70211c4c2d0b084a154fcff30ac5a
git apply fuzix.patch

export PICO_SDK_PATH=/to/where/your/pico/sdk/is
cd Kernel/platform/platform-rpipico
make world

```

now copy `build/fuzix.uf2` into picocalc like every pico device 

## How to compile PicoMite(MMB)

```bash
git clone https://github.com/cuu/PicoMite.git
cd PicoMite

git apply PicoMite.patch

export PICO_SDK_PATH=/to/where/your/pico/sdk/is
mkdir build
cd build
cmake ..
make
```
copy `build/PicoMite.uf2` into picocalc like every pico device


## How to compile NES emulator
```bash
git clone https://github.com/shapoco/shapones.git

cd shapones
git apply ~/github/clockworkpi/PicoCalc/Code/shapones.patch
cd samples/v3/
mkdir build
cd build
export PICO_SDK_PATH=/to/where/your/pico/sdk/is
cmake ..
make
```

copy picocalc_nes.uf2 into picocalc

use up/down key to select *.nes rom, 
* \- key is select
* = key is start,
* [ key is a 
* ] key is b

press -(select) and =(start) together, will reset the emulator to the rom selection page.






