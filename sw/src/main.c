#include <stdio.h>
#include <irq.h>
#include <uart.h>
#include <usb.h>
#include <rgb.h>
#include <spi.h>
#include <generated/csr.h>
#include <generated/mem.h>

#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#include "tusb.h"

void fomu_error(uint32_t line)
{
    (void)line;
    TU_BREAKPOINT();
}

volatile uint32_t system_ticks = 0;
static void timer_init(void)
{
    int t;

    timer0_en_write(0);
    t = CONFIG_CLOCK_FREQUENCY / 1000; // 1000 kHz tick
    timer0_reload_write(t);
    timer0_load_write(t);
    timer0_en_write(1);
    timer0_ev_enable_write(1);
    timer0_ev_pending_write(1);
    irq_setmask(irq_getmask() | (1 << TIMER0_INTERRUPT));
}

void isr(void)
{
    unsigned int irqs;

    irqs = irq_pending() & irq_getmask();

#if CFG_TUSB_RHPORT0_MODE == OPT_MODE_DEVICE
    if (irqs & (1 << USB_INTERRUPT))
    {
        tud_irq_handler(0);
    }
#endif
    if (irqs & (1 << TIMER0_INTERRUPT))
    {
        system_ticks++;
        timer0_ev_pending_write(1);
    }
}

/* Blink pattern
 * - 250 ms  : device not mounted
 * - 1000 ms : device mounted
 * - 2500 ms : device is suspended
 */
enum
{
    BLINK_NOT_MOUNTED = 250,
    BLINK_MOUNTED = 1000,
    BLINK_SUSPENDED = 2500,
};

static uint32_t blink_interval_ms = BLINK_NOT_MOUNTED;

void led_blinking_task(void);
void cdc_task(void);

static void init(void)
{

    rgb_init();
    usb_init();

    timer_init();

#ifdef CSR_UART_BASE
    init_printf(NULL, rv_putchar);
#endif

    irq_setmask(0);
    irq_setie(1);
}

int main(int argc, char **argv)
{
    (void)argc;
    (void)argv;

    init();
    tusb_init();

    while (1)
    {
        tud_task(); // tinyusb device task
        led_blinking_task();

        cdc_task();
    }

    return 0;
}

//--------------------------------------------------------------------+
// Device callbacks
//--------------------------------------------------------------------+

// Invoked when device is mounted
void tud_mount_cb(void)
{
    blink_interval_ms = BLINK_MOUNTED;
}

// Invoked when device is unmounted
void tud_umount_cb(void)
{
    blink_interval_ms = BLINK_NOT_MOUNTED;
}

// Invoked when usb bus is suspended
// remote_wakeup_en : if host allow us  to perform remote wakeup
// Within 7ms, device must draw an average of current less than 2.5 mA from bus
void tud_suspend_cb(bool remote_wakeup_en)
{
    (void)remote_wakeup_en;
    blink_interval_ms = BLINK_SUSPENDED;
}

// Invoked when usb bus is resumed
void tud_resume_cb(void)
{
    blink_interval_ms = BLINK_MOUNTED;
}

//--------------------------------------------------------------------+
// USB CDC
//--------------------------------------------------------------------+
void cdc_task(void)
{
    if (tud_cdc_connected())
    {
        // connected and there are data available
        if (tud_cdc_available())
        {
            uint8_t buf[64];

            // read and echo back
            uint32_t count = tud_cdc_read(buf, sizeof(buf));

            for (uint32_t i = 0; i < count; i++)
            {
                tud_cdc_write_char(buf[i]);

                if (buf[i] == '\r')
                    tud_cdc_write_char('\n');
            }

            tud_cdc_write_flush();
        }
    }
}

// Invoked when cdc when line state changed e.g connected/disconnected
void tud_cdc_line_state_cb(uint8_t itf, bool dtr, bool rts)
{
    (void)itf;

    // connected
    if (dtr && rts)
    {
        // print initial message when connected
        tud_cdc_write_str("\r\nTinyUSB CDC MSC device example\r\n");
    }
}

// Invoked when CDC interface received data from host
void tud_cdc_rx_cb(uint8_t itf)
{
    (void)itf;
}

//--------------------------------------------------------------------+
// BLINKING TASK
//--------------------------------------------------------------------+
void led_blinking_task(void)
{
    static uint32_t start_ms = 0;
    static bool led_state = false;

    // Blink every interval ms
    if (system_ticks - start_ms < blink_interval_ms)
        return; // not enough time
    start_ms += blink_interval_ms;

    rgb_config_write(0);

    if (led_state)
    {
        rgb__r_write(0);
        rgb__g_write(0);
        rgb__b_write(0);
    }
    else
    {

        rgb__r_write(0);
        rgb__g_write(250);
        rgb__b_write(250);
    }

    led_state = 1 - led_state; // toggle
}
