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