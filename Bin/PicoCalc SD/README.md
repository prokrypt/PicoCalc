# PicoCalc SD

This repository contains the official factory image and files for the **PicoCalc SD card**. It includes essential firmware, applications, and system files required for the proper functioning of **PicoCalc**.

## Directory Overview

```
├── bifdiag.bas
├── Chessnovice_johnybot.nes
├── firmware
│   ├── PicoCalc_Fuzix_v1.0.img
│   ├── PicoCalc_Fuzix_v1.0.uf2
│   ├── PicoCalc_MP3Player_v0.5.uf2
│   ├── PicoCalc_NES_v1.0.uf2
│   ├── PicoCalc_PicoMite_v1.0.uf2
│   ├── PicoCalc_stm32 #PicoCalc keyboard firmware
│   │   ├── PicoCalc_firmware_v1.0.bin
│   │   └── PicoCalc_firmware_v1.0.hex
│   └── PicoCalc_uLisp_v1.0.uf2
├── lorenz.bas
├── mand.bas
├── picocalc.bmp
└── README.md

```

## Flashing the Factory SD Image

To restore your **PicoCalc SD card** to its factory state, follow these steps:

### Requirements:
- A microSD card (at least **16GB** recommended)
- A computer with **Linux/macOS/Windows**
- A microSD card reader

## Custom Partitioning

The **PicoCalc SD card** uses a dual-partition structure:

| Partition | Size    | Format | Purpose |
|-----------|--------|--------|---------|
| `/dev/sdX1` | Remaining space | **FAT32** | Storage for PicoMite, uLisp, NES Emulator, etc. |
| `/dev/sdX2` | **32MB** | **fuzix filesystem** | Root filesystem for **FUZIX** |

### Manually Partitioning an SD Card

If you need to manually create an SD card for **PicoCalc**, use the provided **partitioning script**:

```bash
wget https://github.com/clockworkpi/PicoCalc/raw/refs/heads/master/Code/scripts/partition_usb_32mb.sh
chmod +x partition_usb_32mb.sh
sudo ./partition_usb_32mb.sh sdb
```
*(Replace `sdb` with your actual SD card device.)*

## Notes
- The **USB Type-C port** is the default **serial port** for **PicoCalc**, not the Micro USB port.
- FUZIX supports a maximum **32MB** root filesystem.
- Ensure you backup your data before modifying the SD card.

---
For more details, visit the official **[PicoCalc GitHub Repository](https://github.com/clockworkpi/PicoCalc)**.