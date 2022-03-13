**Note:** The original `README.md` was moved to [`README.fomu.md`](README.fomu.md).

# Bootloader for the Orange Cartridge

This is a failsafe bootloader for the Orange Cartridge.  It is based
on the bootloader for the Orange Crab board, which was in turn bases
on the bootloader for the Fomu board.

## Requirements

To build the hardware, you need:

* Python 3.5+
* Nextpnr
* Project Trellis
* Yosys
* Git

Subproject hardware dependencies will be taken care of with `lxbuildenv`.

To build the software, you need:

* RISC-V toolchain

## Building the project

The hardware half will take care of building the software half, if it is run with `--boot-source bios` (which is the default).  Therefore, to build the bootloader, enter the `hw/` directory and run:

```
$ python3 foboot-bitstream.py --platform orangecart
```

This will verify you have the correct dependencies installed, compile the bootloader software, then synthesize the bootloader bitstream.  The resulting output will be in `build/gateware/`.  You should write `build/gateware/foboot.bit` to your SPI flash in order to get basic bootloader support.

If you see something like
```
Hexfiles have different number of words! (0 vs. 1474)
Failed to open input file
```

Just run `foboot-bitstream.py` again and it should sort itself out.

### Usage

You can write the bitstream to your SPI flash.

#### Loading using [`ecpprog`](https://github.com/gregdavill/ecpprog)

If you're using `ecpprog`, you would run the following:

```sh
$ ecpprog build/gateware/foboot.bit
init..
IDCODE: 0x41111043 (LFE5U-25)
ECP5 Status Register: 0x00200000
reset..
flash ID: 0xEF 0x40 0x18
file size: 236769
erase 64kB sector at 0x000000..
erase 64kB sector at 0x010000..
erase 64kB sector at 0x020000..
erase 64kB sector at 0x030000..
programming..  236769/236769
verify..       236769/236769  VERIFY OK
Bye.
$ 
```

After a power cycle, the Orange Cartridge show now show up when you
connect it to USB:

```
[3510871.569595] usb 1-2.1.1.3: new full-speed USB device number 37 using xhci_hcd
[3510871.682018] usb 1-2.1.1.3: New USB device found, idVendor=1209, idProduct=5a0c, bcdDevice= 1.01
[3510871.682022] usb 1-2.1.1.3: New USB device strings: Mfr=1, Product=2, SerialNumber=0
[3510871.682024] usb 1-2.1.1.3: Product: OrangeCart DFU Bootloader v4.0
[3510871.682026] usb 1-2.1.1.3: Manufacturer: Marcus
```

#### Using `openocd` to flash the bootloader

To program the SPI flash using openocd, use the following command line (openocd.cfg should
configure your JTAG adapter):

```sh
$ openocd -f openocd.cfg -f board/orangecart.cfg -c init -c "svf -quiet build/gateware/foboot_jtag_spi.svf" -c exit
Open On-Chip Debugger 0.11.0+dev-02577-g3eee6eb04 (2022-02-28-15:37)
Licensed under GNU GPL v2
For bug reports, read
	http://openocd.org/doc/doxygen/bugs.html
ftdi samples TDO on falling edge of TCK

Info : clock speed 10000 kHz
Info : JTAG tap: ecp5.tap tap/device found: 0x41111043 (mfg: 0x021 (Lattice Semi.), part: 0x1111, ver: 0x4)
Warn : gdb services need one or more targets defined
svf processing file: "build/gateware/foboot_jtag_spi.svf"

Time used: 0m12s359ms 
svf file programmed successfully for 4680 commands with 0 errors

$
```

#### Loading and running bitstreams
To load a new bitstream, use the `dfu-util -a 0 -D` command.  For example:

```sh
$ dfu-util -a 0 -D build/gateware/orangecart.bit
```

Use `-a 1` to upload to the data area following the bitstream, which can be used as input by
the bitstream itself.
