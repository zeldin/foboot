from migen import Module, Signal, If, Instance, ClockSignal, ResetSignal
from litex.soc.integration.doc import ModuleDoc
from litex.soc.interconnect.csr import AutoCSR, CSRStatus, CSRStorage, CSRField

class PWMLed(Module, AutoCSR):
    def __init__(self, revision, pads):
        rgba_pwm = Signal(3)

        self.intro = ModuleDoc("""RGB LED Controller

                The ICE40 contains two different RGB LED control devices.  The first is a
                constant-current LED source, which is fixed to deliver 4 mA to each of the
                three LEDs.  This block is called ``SB_RGBA_DRV``.

                The other is used for creating interesting fading effects, particularly
                for "breathing" effects used to indicate a given state.  This block is called
                ``SB_LEDDA_IP``.  This block feeds directly into ``SB_RGBA_DRV``.

                The RGB LED controller available on this device allows for control of these
                two LED control devices.  Additionally, it is possible to disable ``SB_LEDDA_IP``
                and directly control the individual LEDs.
                """)

        self.dat = CSRStorage(8, description="""
                            This is the value for the ``SB_LEDDA_IP.DAT`` register.  It is directly
                            written into the ``SB_LEDDA_IP`` hardware block, so you should
                            refer to http://www.latticesemi.com/view_document?document_id=50668.
                            The contents of this register are written to the address specified in
                            ``ADDR`` immediately upon writing this register.""")
        self.addr = CSRStorage(4, description="""
                            This register is directly connected to ``SB_LEDDA_IP.ADDR``.  This
                            register controls the address that is updated whenever ``DAT`` is
                            written.  Writing to this register has no immediate effect -- data
                            isn't written until the ``DAT`` register is written.""")
        self.ctrl = CSRStorage(fields=[
            CSRField("exe", description="Connected to ``SB_LEDDA_IP.LEDDEXE``.  Set this to ``1`` to enable the fading pattern."),
            CSRField("curren", description="Connected to ``SB_RGBA_DRV.CURREN``.  Set this to ``1`` to enable the current source."),
            CSRField("rgbleden", description="Connected to ``SB_RGBA_DRV.RGBLEDEN``.  Set this to ``1`` to enable the RGB PWM control logic."),
            CSRField("rraw", description="Set this to ``1`` to enable raw control of the red LED via the ``RAW.R`` register."),
            CSRField("graw", description="Set this to ``1`` to enable raw control of the green LED via the ``RAW.G`` register."),
            CSRField("braw", description="Set this to ``1`` to enable raw control of the blue LED via the ``RAW.B`` register."),
        ], description="Control logic for the RGB LED and LEDDA hardware PWM LED block.")
        self.raw = CSRStorage(fields=[
            CSRField("r", description="Raw value for the red LED when ``CTRL.RRAW`` is ``1``."),
            CSRField("g", description="Raw value for the green LED when ``CTRL.GRAW`` is ``1``."),
            CSRField("b", description="Raw value for the blue LED when ``CTRL.BRAW`` is ``1``."),
        ], description="""
                Normally the hardware ``SB_LEDDA_IP`` block controls the brightness of the LED,
                creating a gentle fading pattern.  However, by setting the appropriate bit in ``CTRL``,
                it is possible to manually control the three individual LEDs.""")

        ledd_value = Signal(3)
        self.comb += [
            If(self.ctrl.storage[3], rgba_pwm[0].eq(self.raw.storage[0])).Else(rgba_pwm[0].eq(ledd_value[0])),
            If(self.ctrl.storage[4], rgba_pwm[1].eq(self.raw.storage[1])).Else(rgba_pwm[1].eq(ledd_value[1])),
            If(self.ctrl.storage[5], rgba_pwm[2].eq(self.raw.storage[2])).Else(rgba_pwm[2].eq(ledd_value[2])),
        ]

        

        self.submodules.led = ecpled()

        self.comb += [
            self.led.data.eq(self.dat.storage),
            self.led.addr.eq(self.addr.storage),
            self.led.den.eq(self.dat.re),
            self.led.exe.eq(self.ctrl.storage[0]),
            ledd_value[0].eq(self.led.red_pwm),
            ledd_value[1].eq(self.led.green_pwm),
            ledd_value[2].eq(self.led.blue_pwm),
        ]

        self.comb += [
            pads.r.eq(~rgba_pwm[0]),
            pads.g.eq(~rgba_pwm[1]),
            pads.b.eq(~rgba_pwm[2]),
        ]


class ecpled(Module):
    def __init__(self):
        self.data = Signal(8)
        self.addr = Signal(4)
        self.den = Signal()
        self.exe = Signal()

        self.red_pwm = Signal()
        self.blue_pwm = Signal()
        self.green_pwm = Signal()

        # registers
        config_reg      = Signal(8)
        prescale_reg    = Signal(8,reset=200)
        on_time_reg     = Signal(8)
        off_time_reg    = Signal(8)
        breathe_on_reg  = Signal(8)
        breathe_off_reg = Signal(8)
        pwm_red_reg     = Signal(8,reset=128)
        pwm_green_reg   = Signal(8)
        pwm_blue_reg    = Signal(8)

        self.sync += [
            If(self.den,
                If(self.addr == 0x8,
                    config_reg.eq(self.data)
                ).Elif(self.addr == 0x9,
                    prescale_reg.eq(self.data)
                ).Elif(self.addr == 0xA,
                    on_time_reg.eq(self.data)
                ).Elif(self.addr == 0xB,
                    off_time_reg.eq(self.data)
                ).Elif(self.addr == 0x5,
                    breathe_on_reg.eq(self.data)
                ).Elif(self.addr == 0x6,
                    breathe_off_reg.eq(self.data)
                ).Elif(self.addr == 0x1,
                    pwm_red_reg.eq(self.data)
                ).Elif(self.addr == 0x2,
                    pwm_green_reg.eq(self.data)
                ).Elif(self.addr == 0x3,
                    pwm_blue_reg.eq(self.data)
                )
            )
        ]

        clk_div_counter = Signal(10)
        clk32k_en = Signal()

        # create a 32Khz Clock
        self.sync += [
            If(clk_div_counter >= prescale_reg,
                clk_div_counter.eq(0),
                clk32k_en.eq(1)
            ).Else(
                clk_div_counter.eq(clk_div_counter + 1),
                clk32k_en.eq(0)
            )
        ]

        #Inner loop sholud be operating at 32Khz
        #self.sync += [
        #    If(clk32k_en,
#
        #    )
        #]


        pwm_count = Signal(8)

        self.sync += [
            #If(clk32k_en,
                pwm_count.eq(pwm_count + 1),
            #)
        ]            

        self.comb += [
            self.red_pwm.eq(pwm_count < pwm_red_reg),
            self.green_pwm.eq(pwm_count < pwm_green_reg),
            self.blue_pwm.eq(pwm_count < pwm_blue_reg),
        ]
