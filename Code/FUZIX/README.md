# How to compile FUZIX 

All the operations in this document are performed in a Linux environment. A basic understanding of Linux, as well as familiarity with Git and pico sdk  development, is required.

## FUZIX 1.0
```bash
git clone https://github.com/EtchedPixels/FUZIX.git
cd FUZIX

git reset --hard f0d56efd5ba70211c4c2d0b084a154fcff30ac5a

git clone  https://github.com/clockworkpi/PicoCalc.git #get patch code

git apply PicoCalc/Code/FUZIX/fuzix.patch

export PICO_SDK_PATH=/to/where/your/pico/sdk/is
cd Kernel/platform/platform-rpipico
make world

```
## FUZIX 1.1
```
git clone https://github.com/EtchedPixels/FUZIX.git
cd FUZIX
git reset --hard c1ff46910d8a3c66e19d730527e5e2493bd324c3
git clone  https://github.com/clockworkpi/PicoCalc.git #get patch code
git apply PicoCalc/Code/FUZIX/fuzix1.1.patch
export PICO_SDK_PATH=/to/where/your/pico/sdk/is

make TARGET=rpipico SUBTARGET=pico2

```

Copy `build/fuzix.uf2` into picocalc like every pico device 

# Pre-compiled uf2
- https://github.com/clockworkpi/PicoCalc/blob/master/Bin/PicoCalc%20SD/firmware/PicoCalc_Fuzix_v1.0.uf2  
- https://github.com/clockworkpi/PicoCalc/blob/master/Bin/PicoCalc_Fuzix_v1.1_pico2.uf2
