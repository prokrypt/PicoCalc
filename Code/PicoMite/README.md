# How to compile PicoMite(MMBasic)

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
Copy `build/PicoMite.uf2` into picocalc like every pico device
