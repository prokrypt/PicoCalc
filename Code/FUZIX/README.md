# How to compile FUZIX 
```bash
git clone https://github.com/EtchedPixels/FUZIX.git
cd FUZIX

git reset --hard f0d56efd5ba70211c4c2d0b084a154fcff30ac5a
git apply fuzix.patch

export PICO_SDK_PATH=/to/where/your/pico/sdk/is
cd Kernel/platform/platform-rpipico
make world

```

Copy `build/fuzix.uf2` into picocalc like every pico device 
