from migen import Module, Signal, Instance, ClockDomain, If

from litex.build.lattice.platform import LatticePlatform

from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.soc.cores import up5kspram, spi_flash

from litex_boards.targets.fomu import _CRG


from ..romgen import RandomFirmwareROM, FirmwareROM
from ..fomutouch import TouchPads
from ..sbwarmboot import SBWarmBoot
from rtl.sbled import SBLED

import argparse
import os



class _CRG(Module):
    def __init__(self, platform):
        clk12_raw = platform.request("clk12")
        clk48 = Signal()
        clk12 = Signal()
        lock = Signal()

        reset_delay = Signal(12, reset=4095)
        self.clock_domains.cd_por = ClockDomain()
        self.reset = Signal()

        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_usb_12 = ClockDomain()
        self.clock_domains.cd_usb_48 = ClockDomain()

        platform.add_period_constraint(self.cd_usb_48.clk, 1e9/48e6)
        platform.add_period_constraint(self.cd_sys.clk, 1e9/12e6)
        platform.add_period_constraint(self.cd_usb_12.clk, 1e9/12e6)
        platform.add_period_constraint(clk12_raw, 1e9/12e6)

        # POR reset logic- POR generated from sys clk, POR logic feeds sys clk
        # reset.
        self.comb += [
            self.cd_por.clk.eq(clk12),
            self.cd_sys.rst.eq(reset_delay != 0),
            self.cd_usb_12.rst.eq(reset_delay != 0),
        ]

        # POR reset logic- POR generated from sys clk, POR logic feeds sys clk
        # reset.
        self.comb += [
            self.cd_usb_48.rst.eq(reset_delay != 0),
        ]


        self.specials += Instance(
            "SB_PLL40_2F_PAD",
            # Parameters
            p_DIVR = 0,
            p_DIVF = 63,
            p_DIVQ = 4,
            p_FILTER_RANGE = 1,
            p_FEEDBACK_PATH = "SIMPLE",
            p_DELAY_ADJUSTMENT_MODE_FEEDBACK = "FIXED",
            p_FDA_FEEDBACK = 0,
            p_DELAY_ADJUSTMENT_MODE_RELATIVE = "FIXED",
            p_FDA_RELATIVE = 0,
            p_SHIFTREG_DIV_MODE = 0,
            p_PLLOUT_SELECT_PORTA = "GENCLK",
            p_PLLOUT_SELECT_PORTB = "SHIFTREG_0deg",
            p_ENABLE_ICEGATE_PORTA = 0,
            p_ENABLE_ICEGATE_PORTB = 0,
            # IO
            i_PACKAGEPIN = clk12_raw,
            o_PLLOUTGLOBALA = clk48,
            o_PLLOUTGLOBALB = clk12,
            #i_EXTFEEDBACK,
            #i_DYNAMICDELAY,
            o_LOCK = lock,
            i_BYPASS = 0,
            i_RESETB = 1,
            #i_LATCHINPUTVALUE,
            #o_SDO,
            #i_SDI,
        )

        self.comb += self.cd_sys.clk.eq(clk12)
        self.comb += self.cd_usb_12.clk.eq(clk12)
        self.comb += self.cd_usb_48.clk.eq(clk48)

        self.sync.por += \
            If((reset_delay != 0) & lock,
                reset_delay.eq(reset_delay - 1)
            )
        self.specials += AsyncResetSynchronizer(self.cd_por, self.reset)




def add_platform_args(parser):
    parser.add_argument(
        "--revision", choices=["0.3"], required=True,
        help="build foboot for a particular hardware revision"
    )



class Platform(LatticePlatform):
    def __init__(self, revision=None, toolchain="icestorm"):
        self.revision = revision
        self.hw_platform = "fomu"


        from litex.build.generic_platform import IOStandard, Subsignal, Pins

        _io = [
            ("clk12", 0, Pins("35"), IOStandard("LVCMOS33")),

            ("user_led_n", 0, Pins("11"), IOStandard("LVCMOS33")),
            ("rgb_led", 0,
                Subsignal("r", Pins("40")),
                Subsignal("g", Pins("39")),
                Subsignal("b", Pins("41")),
                IOStandard("LVCMOS33"),
            ),

            ("usb", 0,
                Subsignal("d_p", Pins("43")),
                Subsignal("d_n", Pins("42")),
                Subsignal("pullup",   Pins("38")),
                IOStandard("LVCMOS33")
            ),

            ("spiflash4x", 0,
                Subsignal("cs_n", Pins("16"), IOStandard("LVCMOS33")),
                Subsignal("clk",  Pins("15"), IOStandard("LVCMOS33")),
                Subsignal("dq",   Pins("14 17 12 13"), IOStandard("LVCMOS33")),
            ),
            
        ]
        LatticePlatform.__init__(self, "ice40-up5k-sg48", _io, [], toolchain="icestorm")

        self.spi_size = 16 * 1024 * 1024
        self.spi_dummy = 6
      
        self.warmboot_offsets = [
            160,
            160,
            157696,
            262144,
            262144 + 32768,
        ]

    def add_crg(self, soc):
        soc.submodules.crg = _CRG(self)

    def add_cpu_variant(self, soc, debug=False):
        if debug:
            soc.cpu.use_external_variant("rtl/VexRiscv_Fomu_Debug.v")
        else:
            soc.cpu.use_external_variant("rtl/VexRiscv_Fomu.v")
    
    def add_sram(self, soc):
        spram_size = 128*1024
        soc.submodules.spram = up5kspram.Up5kSPRAM(size=spram_size)
        return spram_size

    def add_reboot(self, soc):
        soc.submodules.reboot = SBWarmBoot(soc, self.warmboot_offsets)

    def add_touch(self, soc):
        ...
        #self.add_extension(TouchPads.touch_device)
        #soc.submodules.touch = TouchPads(self.request("touch_pads"))

    def add_rgb(self, soc):
        soc.submodules.rgb = SBLED(self.revision, self.request("rgb_led"))
            

    def create_programmer(self):
        raise ValueError("programming is not supported")

    def build_templates(self, use_dsp, pnr_seed, placer):
        # Override default LiteX's yosys/build templates
        assert hasattr(self.toolchain, "yosys_template")
        assert hasattr(self.toolchain, "build_template")
        self.toolchain.yosys_template = [
            "{read_files}",
            "attrmap -tocase keep -imap keep=\"true\" keep=1 -imap keep=\"false\" keep=0 -remove keep=0",
            "synth_ice40 -json {build_name}.json -top {build_name}",
        ]
        self.toolchain.build_template = [
            "yosys -q -l {build_name}.rpt {build_name}.ys",
            "nextpnr-ice40 --json {build_name}.json --pcf {build_name}.pcf --asc {build_name}.txt \
            --pre-pack {build_name}_pre_pack.py --{architecture} --package {package}",
            "icepack {build_name}.txt {build_name}.bin"
        ]

        # Add "-relut -dffe_min_ce_use 4" to the synth_ice40 command.
        # The "-reult" adds an additional LUT pass to pack more stuff in,
        # and the "-dffe_min_ce_use 4" flag prevents Yosys from generating a
        # Clock Enable signal for a LUT that has fewer than 4 flip-flops.
        # This increases density, and lets us use the FPGA more efficiently.
        self.toolchain.yosys_template[2] += " -relut -abc2 -dffe_min_ce_use 4 -relut"
        if use_dsp:
            self.toolchain.yosys_template[2] += " -dsp"

        # Disable final deep-sleep power down so firmware words are loaded
        # onto softcore's address bus.
        self.toolchain.build_template[2] = "icepack -s {build_name}.txt {build_name}.bin"

        # Allow us to set the nextpnr seed
        self.toolchain.build_template[1] += " --seed " + str(pnr_seed)

        if placer is not None:
            self.toolchain.build_template[1] += " --placer {}".format(placer)

    def finalise(self, output_dir):

        output_file = os.path.join(output_dir, "gateware", "combine.bin")
        
        gateware = os.path.join(output_dir, "gateware", "icebreaker_bitsy.bin")
        firmware = os.path.join(output_dir, "software", "uf2", "bios.bin")
        
        # Pad bitstream to 128K
        with open(output_file, 'wb') as f:
            f.write(open(gateware, "rb").read())
            f.seek(128 * 1024)
            f.write(open(firmware, "rb").read())


#        make_multiboot_header(os.path.join(output_dir, "gateware", "multiboot-header.bin"),
#                                self.warmboot_offsets)
#
#        with open(os.path.join(output_dir, 'gateware', 'multiboot-header.bin'), 'rb') as multiboot_header_file:
#            multiboot_header = multiboot_header_file.read()
#            with open(os.path.join(output_dir, 'gateware', 'top.bin'), 'rb') as top_file:
#                top = top_file.read()
#                with open(os.path.join(output_dir, 'gateware', 'top-multiboot.bin'), 'wb') as top_multiboot_file:
#                    top_multiboot_file.write(multiboot_header)
#                    top_multiboot_file.write(top)

                

        print(
    """Foboot build complete.  Output files:
        {}/gateware/top.bin             Bitstream file.  Load this onto the FPGA for testing.
        {}/gateware/top-multiboot.bin   Multiboot-enabled bitstream file.  Flash this onto FPGA ROM.
        {}/gateware/top.v               Source Verilog file.  Useful for debugging issues.
        {}/software/include/generated/  Directory with header files for API access.
        {}/software/bios/bios.elf       ELF file for debugging bios.
    """.format(output_dir, output_dir, output_dir, output_dir, output_dir))



def make_multiboot_header(filename, boot_offsets=[160]):
    """
    ICE40 allows you to program the SB_WARMBOOT state machine by adding the following
    values to the bitstream, before any given image:

    [7e aa 99 7e]       Sync Header
    [92 00 k0]          Boot mode (k = 1 for cold boot, 0 for warmboot)
    [44 03 o1 o2 o3]    Boot address
    [82 00 00]          Bank offset
    [01 08]             Reboot
    [...]               Padding (up to 32 bytes)

    Note that in ICE40, the second nybble indicates the number of remaining bytes
    (with the exception of the sync header).

    The above construct is repeated five times:

    INITIAL_BOOT        The image loaded at first boot
    BOOT_S00            The first image for SB_WARMBOOT
    BOOT_S01            The second image for SB_WARMBOOT
    BOOT_S10            The third image for SB_WARMBOOT
    BOOT_S11            The fourth image for SB_WARMBOOT
    """
    while len(boot_offsets) < 5:
        boot_offsets.append(boot_offsets[0])

    with open(filename, 'wb') as output:
        for offset in boot_offsets:
            # Sync Header
            output.write(bytes([0x7e, 0xaa, 0x99, 0x7e]))

            # Boot mode
            output.write(bytes([0x92, 0x00, 0x00]))

            # Boot address
            output.write(bytes([0x44, 0x03,
                    (offset >> 16) & 0xff,
                    (offset >> 8)  & 0xff,
                    (offset >> 0)  & 0xff]))

            # Bank offset
            output.write(bytes([0x82, 0x00, 0x00]))

            # Reboot command
            output.write(bytes([0x01, 0x08]))

            for x in range(17, 32):
                output.write(bytes([0]))