# How to Create an Official PicoCalc SD Card  

The purpose of this wiki is to document the partitioning and creation process of the official PicoCalc SD card.

⚠ Warning: This process involves disk partitioning and formatting, which may result in data loss if performed incorrectly. Do not proceed unless you have sufficient experience with Linux system administration.

We are not responsible for any data loss or damage caused by improper use of these instructions. Proceed at your own risk.


## Script  

```bash
#!/bin/bash

DEVICE="/dev/$1"

if [ -z "$DEVICE" ]; then
  echo "No disk"
  exit 1
fi

if [ ! -b "$DEVICE" ]; then
  echo "$DEVICE not existed"
  exit 1
fi


echo "Warn: $DEVICE will be destroyed and all data on this disk will be lost,Do you want to continue?"
read -p "Confirm？(y/n) " confirm
if [ "$confirm" != "y" ]; then
  echo "Canceled"
  exit 1
fi


echo "Begin partition..."

# use parted to create msdos partition table
echo "Create msdos partition table..."
parted "$DEVICE" mklabel msdos


TOTAL_SIZE=$(lsblk -bno SIZE "$DEVICE")
SIZE_MB=$(( TOTAL_SIZE / 1024 / 1024 ))


PART1_SIZE=$(( SIZE_MB - 32 ))


echo "Create first partition in size ${PART1_SIZE}MB, FAT32..."
parted "$DEVICE" mkpart primary fat32 1MiB ${PART1_SIZE}MiB


sleep 2

echo "Format first partition FAT32..."
mkfs.fat -F32 -v -I  "${DEVICE}1"


echo "Create second partition in size 32MB..."
parted "$DEVICE" mkpart primary ${PART1_SIZE}MiB 100%


echo "All done："
fdisk -l "$DEVICE"
```

## How to Use the Script

- Insert a blank SD card into your computer.
- Run the script:
```bash
sudo ./partition_usb_32mb.sh sdb
```
(Replace "sdb" with the correct device name for your SD card.) 

***BE CARFUL ABOUT THIS***
***BE CARFUL ABOUT THIS***
***BE CARFUL ABOUT THIS***

If you are not careful, all the original data on the disk will be destroyed.  

This script prepares the SD card for PicoMite, uLisp, NES emulators, and other Pico firmware using the fatfs library.

Additionally, FUZIX can use `/dev/sdb2` (32MB partition) as its root filesystem, as FUZIX supports a maximum partition size of 32MB.

## Flashing the FUZIX 32MB Image
- Download the FUZIX image:
 [PicoCalc_Fuzix_v1.0.img](https://github.com/clockworkpi/PicoCalc/blob/master/Bin/PicoCalc%20SD/firmware/PicoCalc_Fuzix_v1.0.img)

- Flash the image to the second partition:
```bash
sudo dd if=filesystem.img of=/dev/sdb2
```

## Example Partition Layout

After running the script, your SD card should have the following partition structure:

```
Disk /dev/sdb: 59.48 GiB, 63864569856 bytes, 124735488 sectors
Disk model: STORAGE DEVICE  
Units: sectors of 1 * 512 = 512 bytes
Sector size (logical/physical): 512 bytes / 512 bytes
I/O size (minimum/optimal): 512 bytes / 512 bytes
Disklabel type: dos
Disk identifier: 0x66a93eb2

Device     Boot     Start       End   Sectors  Size Id Type
/dev/sdb1            2048 124669951 124667904 59.4G  c W95 FAT32 (LBA)
/dev/sdb2       124669952 124735487     65536   32M 83 Linux
```

Now your SD card is ready for PicoCalc, FUZIX, and other supported firmware!

