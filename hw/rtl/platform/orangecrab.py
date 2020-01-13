from migen import Module, Signal, Instance, ClockDomain, If

from litex.build.lattice.platform import LatticePlatform

from litex.soc.cores import up5kspram, spi_flash

from litex.soc.cores.clock import ECP5PLL
from migen.genlib.resetsync import AsyncResetSynchronizer


import lxsocdoc
import spibone

from ..version import Version
from ..romgen import RandomFirmwareROM, FirmwareROM
from ..fomutouch import TouchPads
from ..pwmled import PWMLed
from ..ecpreboot import ECPReboot
from ..messible import Messible

from litex.soc.interconnect.wishbone import SRAM

from litex.build.generic_platform import *

import argparse
import os



def add_platform_args(parser):
    parser.add_argument(
        "--revision", choices=["r0_1", "r0_2", "ex"], required=True,
        help="build foboot for a particular hardware revision"
    )
    parser.add_argument(
        "--device", choices=["25F", "45F", "85F"], default="25F",
        help="Select device density"
    )


class Platform(LatticePlatform):
    def __init__(self, revision=None, device="25F", toolchain="trellis"):
        self.revision = revision
        self.device = device
        if revision == "r0_1":
            from litex_boards.partner.platforms.OrangeCrab import _io, _connectors
            LatticePlatform.__init__(self, "LFE5U-" + device + "-8MG285C", _io, _connectors, toolchain=toolchain)
            self.spi_size = 1 * 1024 * 1024
            self.spi_dummy = 6
        elif revision == "r0_2":
            from litex_boards.partner.platforms.OrangeCrab_r2 import _io, _connectors
            LatticePlatform.__init__(self, "LFE5U-" + device + "-8MG285C", _io, _connectors, toolchain=toolchain)
            self.spi_size = 16 * 1024 * 1024
            self.spi_dummy = 4
        else:
            raise ValueError("Unrecognized revision: {}.  Known values: evt, dvt, pvt, hacker".format(revision))


    def create_programmer(self):
        raise ValueError("programming is not supported")


    def add_crg(self, soc):
        soc.submodules.crg = _CRG(self)

    def add_cpu_variant(self, soc, debug=False):
        pass

    def add_sram(self, soc):
        spram_size = 16*1024
        soc.submodules.spram = SRAM(spram_size)
        return spram_size

    def add_reboot(self, soc):
        soc.submodules.reboot = ECPReboot(soc)
    
    def add_rgb(self, soc):
        soc.submodules.rgb = PWMLed(self.revision, self.request("rgb_led"))
        #if platform.device[:4] == "LFE5":
        #    vdir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "rtl")
        #    platform.add_source(os.path.join(vdir, "sbled.v"))

    def finalise(self, output_dir):
        # create a bitstream for loading into FLASH
        input_config = os.path.join(output_dir, "gateware", "top.config")
        output_bitstream = os.path.join(output_dir, "gateware", "foboot.bit")
        os.system(f"ecppack --spimode qspi --freq 38.8 --compress --bootaddr 0x180000 --input {input_config} --bit {output_bitstream}")

        # create a SVF for loading with JTAG adapter
        output_svf = os.path.join(output_dir, "gateware", "top.svf")
        os.system(f"ecppack --input {input_config} --svf {output_svf}")


        print(
    f"""Foboot build complete.  Output files:
        {output_dir}/gateware/top.bit             Basic Bitstream file.  Load this onto the FPGA for testing.
        {output_dir}/gateware/foboot.bit          Optimised Bitstream file. (QSPI, Compressed, Higher CLK)  Load this into FLASH.
        {output_dir}/gateware/top.svf             Serial Vector Format File. Useful when loading over JTAG.
        {output_dir}/gateware/top.v               Source Verilog file.  Useful for debugging issues.
        {output_dir}/software/include/generated/  Directory with header files for API access.
        {output_dir}/software/bios/bios.elf       ELF file for debugging bios.
    """)


class _CRG(Module):
    def __init__(self, platform):
        clk48_raw = platform.request("clk48")

        reset_delay = Signal(64, reset=int(12e6*500e-6))
        self.clock_domains.cd_por = ClockDomain()
        self.reset = Signal()

        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_usb_12 = ClockDomain()
        self.clock_domains.cd_usb_48 = ClockDomain()

        platform.add_period_constraint(self.cd_usb_48.clk, 1e9/48e6)
        platform.add_period_constraint(self.cd_sys.clk, 1e9/12e6)
        platform.add_period_constraint(self.cd_usb_12.clk, 1e9/12e6)

        # POR reset logic- POR generated from sys clk, POR logic feeds sys clk
        # reset.
        self.comb += [
            self.cd_por.clk.eq(self.cd_usb_12.clk),
            self.cd_sys.rst.eq(reset_delay != 0),
            self.cd_usb_12.rst.eq(reset_delay != 0),
        ]

        # POR reset logic- POR generated from sys clk, POR logic feeds sys clk
        # reset.
        self.comb += [
            self.cd_usb_48.rst.eq(reset_delay != 0),
        ]

        self.submodules.pll = pll = ECP5PLL()
        pll.register_clkin(clk48_raw, 48e6)

        pll.create_clkout(self.cd_usb_48, 48e6, 0)
        pll.create_clkout(self.cd_usb_12, 12e6, 0)

        self.comb += self.cd_sys.clk.eq(self.cd_usb_12.clk)
        
        self.sync.por += \
            If(reset_delay != 0,
                reset_delay.eq(reset_delay - 1)
            )
        self.specials += AsyncResetSynchronizer(self.cd_por, self.reset)
            