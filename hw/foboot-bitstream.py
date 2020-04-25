#!/usr/bin/env python3
# This variable defines all the external programs that this module
# relies on.  lxbuildenv reads this variable in order to ensure
# the build will finish without exiting due to missing third-party
# programs.
LX_DEPENDENCIES = ["riscv", "icestorm", "yosys", "nextpnr-ice40"]

# Import lxbuildenv to integrate the deps/ directory
import lxbuildenv

# Disable pylint's E1101, which breaks completely on migen
#pylint:disable=E1101

#from migen import *
from migen import Module, Signal, Instance, ClockDomain, If
from migen.fhdl.specials import TSTriple
from migen.fhdl.decorators import ClockDomainsRenamer

from litex.build.lattice.platform import LatticePlatform
from litex.build.generic_platform import Pins, Subsignal
from litex.soc.integration.doc import AutoDoc, ModuleDoc
from litex.soc.integration.soc_core import SoCCore
from litex.soc.cores.cpu import CPUNone
from litex.soc.integration.builder import Builder
from litex.soc.interconnect import wishbone

from litex.soc.cores import spi_flash

from valentyusb.usbcore import io as usbio
from valentyusb.usbcore.cpu import epmem, unififo, epfifo, dummyusb, eptri
from valentyusb.usbcore.endpoint import EndpointType

import litex.soc.doc as lxsocdoc
import spibone

import argparse
import os

from rtl.version import Version
from rtl.romgen import RandomFirmwareROM, FirmwareROMHex
from rtl.messible import Messible
        


class BaseSoC(SoCCore, AutoDoc):
    """Fomu Bootloader and Base SoC

    Fomu is an FPGA that fits in your USB port.  This reference manual
    documents the basic SoC that runs the bootloader, and that can be
    reused to run your own RISC-V programs.

    This reference manual only describes a particular version of the SoC.
    The register sets described here are guaranteed to be available
    with a given ``major version``, but are not guaranteed to be available on
    any other version.  Naturally, you are free to create your own SoC
    that does not provide these hardware blocks. To see what the version of the
    bitstream you're running, check the ``VERSION`` registers.
    """

    csr_map = {
        "ctrl":           0,  # provided by default (optional)
        "crg":            1,  # user
        "uart_phy":       2,  # provided by default (optional)
        "uart":           3,  # provided by default (optional)
        "identifier_mem": 4,  # provided by default (optional)
        "timer0":         5,  # provided by default (optional)
        "cpu_or_bridge":  8,
        "usb":            9,
        "picorvspi":      10,
        "touch":          11,
        "reboot":         12,
        "rgb":            13,
        "version":        14,
        "lxspi":          15,
        "messible":       16,
        "button":         17,
    }
    csr_map.update(SoCCore.csr_map)

    SoCCore.mem_map = {
        "rom":              0x00000000,  # (default shadow @0x80000000)
        "sram":             0x10000000,  # (default shadow @0xa0000000)
        "spiflash":         0x20000000,  # (default shadow @0xa0000000)
        "main_ram":         0x40000000,  # (default shadow @0xc0000000)
        "csr":              0xe0000000,  # (default shadow @0xe0000000)
        "vexriscv_debug":   0xf00f0000,
    }
    mem_map.update(SoCCore.mem_map)

    interrupt_map = {
        "timer0": 2,
        "usb": 3,
    }
    interrupt_map.update(SoCCore.interrupt_map)

    
    
    def __init__(self, platform, boot_source="rand",
                 debug=None, bios_file=None,
                 use_dsp=False, placer="heap", output_dir="build",
                 pnr_seed=0,
                 **kwargs):
        # Disable integrated RAM as we'll add it later
        self.integrated_sram_size = 0

        self.output_dir = output_dir

        clk_freq = int(12e6)
        platform.add_crg(self)

        SoCCore.__init__(self, platform, clk_freq, integrated_sram_size=0, with_uart=False, csr_data_width=32, **kwargs)
        
        usb_debug = False
        if debug is not None:
            if debug == "uart":
                from litex.soc.cores.uart import UARTWishboneBridge
                self.submodules.uart_bridge = UARTWishboneBridge(platform.request("serial"), clk_freq, baudrate=115200)
                self.add_wb_master(self.uart_bridge.wishbone)
            elif debug == "usb":
                usb_debug = True
            elif debug == "spi":
                import spibone
                # Add SPI Wishbone bridge
                debug_device = [
                    ("spidebug", 0,
                        Subsignal("mosi", Pins("dbg:0")),
                        Subsignal("miso", Pins("dbg:1")),
                        Subsignal("clk",  Pins("dbg:2")),
                        Subsignal("cs_n", Pins("dbg:3")),
                    )
                ]
                platform.add_extension(debug_device)
                spi_pads = platform.request("spidebug")
                self.submodules.spibone = ClockDomainsRenamer("usb_12")(spibone.SpiWishboneBridge(spi_pads, wires=4))
                self.add_wb_master(self.spibone.wishbone)
            if hasattr(self, "cpu") and not isinstance(self.cpu, CPUNone):
                platform.add_cpu_variant(self, debug=True)
                self.register_mem("vexriscv_debug", 0xf00f0000, self.cpu.debug_bus, 0x100)
        else:
            if hasattr(self, "cpu") and not isinstance(self.cpu, CPUNone):
                platform.add_cpu_variant(self)

        # SPRAM- UP5K has single port RAM, might as well use it as SRAM to
        # free up scarce block RAM.
        spram_size = platform.add_sram(self)
        self.register_mem("sram", self.mem_map["sram"], self.spram.bus, spram_size)

        # Add a Messible for device->host communications
        self.submodules.messible = Messible()

        if boot_source == "rand":
            kwargs['cpu_reset_address'] = 0
            bios_size = 0x2000
            self.submodules.random_rom = RandomFirmwareROM(bios_size)
            self.add_constant("ROM_DISABLE", 1)
            self.register_rom(self.random_rom.bus, bios_size)
        elif boot_source == "bios":
            kwargs['cpu_reset_address'] = 0
            if bios_file is None:
                self.integrated_rom_size = bios_size = 0x4000
                self.submodules.rom = wishbone.SRAM(bios_size, read_only=True, init=[])
                self.register_rom(self.rom.bus, bios_size)
            else:
                bios_size = 0x4000
                self.submodules.firmware_rom = FirmwareROMHex(bios_size, bios_file)
                self.add_constant("ROM_DISABLE", 1)
                self.register_rom(self.firmware_rom.bus, bios_size)

        elif boot_source == "spi":
            kwargs['cpu_reset_address'] = 0
            self.integrated_rom_size = bios_size = 0x2000
            gateware_size = 0x1a000
            self.flash_boot_address = self.mem_map["spiflash"] + gateware_size
            self.submodules.rom = wishbone.SRAM(bios_size, read_only=True, init=[])
            self.register_rom(self.rom.bus, bios_size)
        else:
            raise ValueError("unrecognized boot_source: {}".format(boot_source))

        # The litex SPI module supports memory-mapped reads, as well as a bit-banged mode
        # for doing writes.
        spi_pads = platform.request("spiflash4x")
        self.submodules.lxspi = spi_flash.SpiFlashDualQuad(spi_pads, dummy=platform.spi_dummy, endianness="little")
        self.lxspi.add_clk_primitive(platform.device)
        self.register_mem("spiflash", self.mem_map["spiflash"], self.lxspi.bus, size=platform.spi_size)

        # Add USB pads, as well as the appropriate USB controller.  If no CPU is
        # present, use the DummyUsb controller.
        usb_pads = platform.request("usb")
        usb_iobuf = usbio.IoBuf(usb_pads.d_p, usb_pads.d_n, usb_pads.pullup)
        if hasattr(self, "cpu") and not isinstance(self.cpu, CPUNone):
            self.submodules.usb = eptri.TriEndpointInterface(usb_iobuf, debug=usb_debug)
        else:
            self.submodules.usb = dummyusb.DummyUsb(usb_iobuf, debug=usb_debug)

        if usb_debug:
            self.add_wb_master(self.usb.debug_bridge.wishbone)
        # For the EVT board, ensure the pulldown pin is tristated as an input
        if hasattr(usb_pads, "pulldown"):
            pulldown = TSTriple()
            self.specials += pulldown.get_tristate(usb_pads.pulldown)
            self.comb += pulldown.oe.eq(0)

        # Add GPIO pads for the touch buttons
        if hasattr(platform, "add_touch"):
            platform.add_touch(self)

        if hasattr(platform, "add_button"):
            platform.add_button(self)

        # Allow the user to reboot the ICE40.  Additionally, connect the CPU
        # RESET line to a register that can be modified, to allow for
        # us to debug programs even during reset.
        platform.add_reboot(self)
        if hasattr(self, "cpu") and not isinstance(self.cpu, CPUNone):
            self.cpu.cpu_params.update(
                i_externalResetVector=self.reboot.addr.storage,
            )

        platform.add_rgb(self)

        self.submodules.version = Version(platform.revision, platform.hw_platform, self, pnr_seed, models=[
                ("0x45", "E", "Fomu EVT"),
                ("0x44", "D", "Fomu DVT"),
                ("0x50", "P", "Fomu PVT (production)"),
                ("0x48", "H", "Fomu Hacker"),
                ("0x11", "1", "OrangeCrab r0.1"),
                ("0x12", "2", "OrangeCrab r0.2"),
                ("0x3f", "?", "Unknown model"),
            ])

        if hasattr(platform, "build_templates"):
            platform.build_templates(use_dsp, pnr_seed, placer)
            

def main():
    parser = argparse.ArgumentParser(
        description="Build Fomu Main Gateware")
    parser.add_argument(
        "--boot-source", choices=["spi", "rand", "bios"], default="bios",
        help="where to have the CPU obtain its executable code from"
    )
    parser.add_argument(
        "--document-only", default=False, action="store_true",
        help="Don't build gateware or software, only build documentation"
    )
    parser.add_argument(
        "--platform", choices=["fomu", "orangecrab"], required=True,
        help="build foboot for a particular hardware"
    )
    parser.add_argument(
        "--bios", help="use specified file as a BIOS, rather than building one"
    )
    parser.add_argument(
        "--with-debug", help="enable debug support", choices=["usb", "uart", "spi", None]
    )
    parser.add_argument(
        "--with-dsp", help="use dsp inference in yosys (not all yosys builds have -dsp)", action="store_true"
    )
    parser.add_argument(
        "--no-cpu", help="disable cpu generation for debugging purposes", action="store_true"
    )
    parser.add_argument(
        "--placer", choices=["sa", "heap"], default="heap", help="which placer to use in nextpnr"
    )
    parser.add_argument(
        "--seed", default=0, help="seed to use in nextpnr"
    )
    parser.add_argument(
        "--export-random-rom-file", help="Generate a random ROM file and save it to a file"
    )
    parser.add_argument(
        "--skip-gateware", help="Skip generating gateware", default=False
    )
    args, _ = parser.parse_known_args()

    # Select platform based arguments
    if args.platform == "orangecrab":
        from rtl.platform.orangecrab import Platform, add_platform_args
    elif args.platform == "fomu":
        from rtl.platform.fomu import Platform, add_platform_args

    # Add any platform independent args
    add_platform_args(parser)
    args = parser.parse_args()

    # load our platform file
    if args.platform == "orangecrab":
        platform = Platform(revision=args.revision, device=args.device)
    elif args.platform == "fomu":
        platform = Platform(revision=args.revision)

    output_dir = 'build'
    #if args.export_random_rom_file is not None:
    rom_rand = os.path.join(output_dir, "gateware", "rand_rom.hex")
    os.system(f"ecpbram  --generate {rom_rand} --seed {0} --width {32} --depth {int(0x4000/4)}")

    compile_software = False
    if (args.boot_source == "bios" or args.boot_source == "spi") and args.bios is None:
        compile_software = True

    compile_gateware = True
    if args.skip_gateware:
        compile_gateware = False

    cpu_type = "vexriscv"
    cpu_variant = "minimal"
    if args.with_debug:
        cpu_variant = cpu_variant + "+debug"

    if args.no_cpu:
        cpu_type = None
        cpu_variant = None

    if args.document_only:
        compile_gateware = False
        compile_software = False


    os.environ["LITEX"] = "1" # Give our Makefile something to look for

    
    
    soc = BaseSoC(platform, cpu_type=cpu_type, cpu_variant=cpu_variant,
                            debug=args.with_debug, boot_source=args.boot_source,
                            bios_file=args.bios,
                            use_dsp=args.with_dsp, placer=args.placer,
                            pnr_seed=int(args.seed),
                            output_dir=output_dir)
    builder = Builder(soc, output_dir=output_dir, csr_csv="build/csr.csv", csr_svd="build/soc.svd",
                      compile_software=compile_software, compile_gateware=compile_gateware)
    if compile_software:
        builder.software_packages = [
            ("bios", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sw")))
        ]
    vns = builder.build()
    soc.do_exit(vns)
    lxsocdoc.generate_docs(soc, "build/documentation/", project_name="Fomu Bootloader", author="Sean Cross")

    if not args.document_only:
        platform.finalise(output_dir)


if __name__ == "__main__":
    main()


def export_random_rom_file(filename):
    size = 0x2000
    def xorshift32(x):
        x = x ^ (x << 13) & 0xffffffff
        x = x ^ (x >> 17) & 0xffffffff
        x = x ^ (x << 5)  & 0xffffffff
        return x & 0xffffffff

    def get_rand(x):
        out = 0
        for i in range(32):
            x = xorshift32(x)
            if (x & 1) == 1:
                out = out | (1 << i)
        return out & 0xffffffff
    seed = 1
    with open(filename, "w", newline="\n") as output:
        for _ in range(int(size / 4)):
            seed = get_rand(seed)
            print("{:08x}".format(seed), file=output)
    return 0