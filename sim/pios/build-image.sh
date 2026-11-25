#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Build a UTM-bootable disk from the official Raspberry Pi OS image (the one Pi Imager writes for a Pi 4).
# Runs inside a privileged arm64 Debian container (see make-vm.sh); work files are in /w.
#
# The Pi boot partition and system partition are copied byte for byte. Only the boot path changes, because a
# virtual machine has no Pi firmware: a small UEFI partition with GRUB and Debian's arm64 kernel is added.
# GRUB follows /boot/firmware/cmdline.txt (for overlayroot=tmpfs), so raspi-config's own read-only switch is used.
set -euo pipefail
IMG=/w/${SRC_IMG:-raspios.img} DISK=${DISK:-loop-pios} OUT=/w/$DISK.raw SIZE_GB=${SIZE_GB:-24}
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq fdisk gdisk dosfstools e2fsprogs rsync qemu-utils >/dev/null

# Source partitions (from the image's MBR: 1 = FAT boot, 2 = ext4 system).
read -r B_START B_SECT < <(sfdisk -d "$IMG" | awk -F'[=,]' '/img1/{print $2+0, $4+0}')
read -r R_START R_SECT < <(sfdisk -d "$IMG" | awk -F'[=,]' '/img2/{print $2+0, $4+0}')

# Target: GPT with ESP (256 MiB), FIRMWARE (512 MiB, the Pi boot partition) and root (rest).
rm -f "$OUT"; truncate -s "${SIZE_GB}G" "$OUT"
sgdisk -o -n1:2048:+256M -t1:EF00 -c1:ESP -n2:0:+512M -t2:0700 -c2:FIRMWARE -n3:0:0 -t3:8300 -c3:rootfs "$OUT" >/dev/null
part() { sgdisk -i "$1" "$OUT" | awk -v k="$2" '$0 ~ k {print $NF}'; }
off() { echo $(( $(sgdisk -i "$1" "$OUT" | awk '/First sector/{print $3}') * 512 )); }
len() { local f l; f=$(sgdisk -i "$1" "$OUT" | awk '/First sector/{print $3}'); l=$(sgdisk -i "$1" "$OUT" | awk '/Last sector/{print $3}'); echo $(( (l - f + 1) * 512 )); }
P1=$(part 1 "unique GUID" | tr A-Z a-z); P2=$(part 2 "unique GUID" | tr A-Z a-z); P3=$(part 3 "unique GUID" | tr A-Z a-z)

# Copy the Pi partitions byte for byte, then grow the system filesystem to fill its partition.
dd if="$IMG" of="$OUT" bs=512 skip="$B_START" seek="$(( $(off 2) / 512 ))" count="$B_SECT" conv=notrunc,sparse status=none
dd if="$IMG" of="$OUT" bs=512 skip="$R_START" seek="$(( $(off 3) / 512 ))" count="$R_SECT" conv=notrunc,sparse status=none
LR=$(losetup -f --show -o "$(off 3)" --sizelimit "$(len 3)" "$OUT")
e2fsck -pf "$LR" >/dev/null || true; resize2fs -p "$LR" >/dev/null
LB=$(losetup -f --show -o "$(off 2)" --sizelimit "$(len 2)" "$OUT")
LE=$(losetup -f --show -o "$(off 1)" --sizelimit "$(len 1)" "$OUT")
mkfs.vfat -F 32 -n ESP "$LE" >/dev/null

T=/t; mkdir -p $T; mount "$LR" $T; mount "$LB" $T/boot/firmware; mkdir -p $T/boot/efi; mount "$LE" $T/boot/efi
for d in dev dev/pts proc sys; do mount --bind /$d $T/$d; done
cp /etc/resolv.conf $T/etc/resolv.conf.loop-sim; mount --bind /etc/resolv.conf $T/etc/resolv.conf

# fstab and cmdline.txt point at the new partitions (GPT PARTUUIDs).
sed -i -e "s#PARTUUID=[0-9a-f]*-01#PARTUUID=$P2#" -e "s#PARTUUID=[0-9a-f]*-02#PARTUUID=$P3#" $T/etc/fstab
grep -q /boot/efi $T/etc/fstab || echo "PARTUUID=$P1  /boot/efi  vfat  defaults,nofail  0  2" >> $T/etc/fstab
sed -i "s#root=PARTUUID=[0-9a-f-]*#root=PARTUUID=$P3#" $T/boot/firmware/cmdline.txt

# GRUB lives on the ESP (writable even when the system runs read-only), and reads cmdline.txt for overlayroot.
mkdir -p $T/boot/efi/grub; rm -rf $T/boot/grub; ln -s efi/grub $T/boot/grub
mkdir -p $T/etc/default/grub.d
cat > $T/etc/default/grub.d/90-loop-sim.cfg <<'EOF'
# loop-sim: one menu entry from /etc/grub.d/09_loop_sim (Debian arm64 kernel only; the image's own
# Pi kernels cannot boot a VM), following /boot/firmware/cmdline.txt for root and overlayroot=tmpfs.
GRUB_TIMEOUT=1
GRUB_DISABLE_OS_PROBER=true
EOF
mkdir -p $T/etc/grub.d
cat > $T/etc/grub.d/09_loop_sim <<'EOF'
#!/bin/sh
# loop-sim GRUB entry: newest Debian arm64 kernel, root and overlayroot taken from the Pi's cmdline.txt.
set -e
K=$(ls /boot/vmlinuz-*-arm64 2>/dev/null | sort -V | tail -1); [ -n "$K" ] || exit 0
V=${K#/boot/vmlinuz-}
C=/boot/firmware/cmdline.txt
ROOT=$(grep -o 'root=PARTUUID=[^ ]*' "$C")
FSUUID=$(blkid -s UUID -o value "/dev/disk/by-partuuid/${ROOT#root=PARTUUID=}")
RO=$(grep -o 'overlayroot=tmpfs[^ ]*' "$C" || true)
cat <<ENTRY
menuentry 'Raspberry Pi OS (loop-sim)' {
  insmod part_gpt
  insmod ext2
  search --no-floppy --fs-uuid --set=root $FSUUID
  linux /boot/vmlinuz-$V $ROOT rw console=tty1 console=ttyAMA0,115200 rootwait fsck.repair=yes $RO
  initrd /boot/initrd.img-$V
}
ENTRY
EOF
chmod 755 $T/etc/grub.d/09_loop_sim
cat > $T/etc/systemd/system/loop-sim-grub.path <<'EOF'
[Unit]
Description=loop-sim: rebuild the GRUB menu when cmdline.txt changes (raspi-config read-only switch)
[Path]
PathChanged=/boot/firmware/cmdline.txt
[Install]
WantedBy=multi-user.target
EOF
install -m 644 /w/loop-sim-grub.service $T/etc/systemd/system/loop-sim-grub.service
install -m 755 /w/loop-sim-initramfs $T/usr/local/sbin/loop-sim-initramfs
install -m 755 /w/loop-sim-grubcfg $T/usr/local/sbin/loop-sim-grubcfg

chroot $T /bin/bash -euo pipefail <<'CHROOT'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -q --no-install-recommends linux-image-arm64 grub-efi-arm64 >/var/log/loop-sim-build.log 2>&1 \
  || { tail -20 /var/log/loop-sim-build.log; exit 1; }
sed -i 's/^MODULES=.*/MODULES=most/' /etc/initramfs-tools/initramfs.conf
update-initramfs -u -k all >/dev/null 2>&1 || true
# A self-contained GRUB (grub-install cannot probe the disk inside a container): it finds the ESP by its
# /grub/grub.cfg and loads that menu, which update-grub maintains once the VM is running.
mkdir -p /boot/efi/EFI/BOOT /boot/efi/grub
cp -r /usr/lib/grub/arm64-efi /boot/efi/grub/ 2>/dev/null || true
cat > /tmp/bootstrap.cfg <<'CFG'
search --no-floppy --file --set=root /grub/grub.cfg
set prefix=($root)/grub
configfile ($root)/grub/grub.cfg
CFG
grub-mkstandalone --format=arm64-efi --output=/boot/efi/EFI/BOOT/BOOTAA64.EFI \
  --modules="part_gpt fat ext2 search search_fs_file configfile linux normal" \
  "boot/grub/grub.cfg=/tmp/bootstrap.cfg"
chmod -x /etc/grub.d/10_linux /etc/grub.d/20_linux_xen /etc/grub.d/30_uefi-firmware 2>/dev/null || true
systemctl enable loop-sim-grub.path >/dev/null 2>&1
CHROOT

# update-grub cannot see the disk from inside a container, so write a minimal menu for the first boot;
# the VM regenerates the full menu itself (cloud-init runcmd and loop-sim-grub.path run update-grub).
KVER=$(ls $T/boot/vmlinuz-*-arm64 | sed 's#.*/vmlinuz-##' | sort -V | tail -1)
RUUID=$(blkid -s UUID -o value "$LR")
cat > $T/boot/efi/grub/grub.cfg <<EOF
set timeout=1
insmod part_gpt
insmod ext2
search --no-floppy --fs-uuid --set=root $RUUID
menuentry "Raspberry Pi OS (loop-sim, first boot)" {
  linux /boot/vmlinuz-$KVER root=PARTUUID=$P3 rw console=tty1 console=ttyAMA0,115200 rootwait fsck.repair=yes
  initrd /boot/initrd.img-$KVER
}
EOF
ls $T/boot/initrd.img-$KVER >/dev/null

# vcgencmd stand-in (no VideoCore in a VM), ahead of the real one in PATH.
install -m 755 /w/standins/vcgencmd $T/usr/local/bin/vcgencmd
mkdir -p $T/etc/loop-sim

# Pi Imager-style first-boot settings: cloud-init NoCloud files on the boot partition.
install -m 644 /w/seed/user-data /w/seed/network-config /w/seed/meta-data $T/boot/firmware/
touch $T/boot/firmware/ssh

umount $T/etc/resolv.conf; rm -f $T/etc/resolv.conf.loop-sim
for d in sys proc dev/pts dev; do umount $T/$d; done
umount $T/boot/efi $T/boot/firmware $T; losetup -d "$LE" "$LB" "$LR"
qemu-img convert -O qcow2 "$OUT" /w/$DISK.qcow2 && rm -f "$OUT"
qemu-img create -q -f qcow2 /w/data-$DISK.qcow2 4G
echo "BUILD_DONE root=PARTUUID=$P3"
