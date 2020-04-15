#include <irq.h>
#include <rgb.h>
#include <spi.h>
#include <generated/csr.h>
#include <generated/mem.h>

#include <stdio.h>

#include "tusb.h"

#define BOARD_BLINK_INTERVAL 500

static uint32_t blink_interval_ms = BOARD_BLINK_INTERVAL;

uint32_t reset_millis = 0;


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

uint32_t board_millis(void)
{
    return system_ticks;
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


void reset_task(void)
{
  if (!reset_millis)
    return;

  if (system_ticks > reset_millis)
    board_reset();
}


static void init(void)
{

    rgb_init();

    timer_init();

    irq_setmask(0);
    irq_setie(1);
}


void board_flash_flush(void)
{
}


uint32_t board_flash_read_blocks(uint8_t *dest, uint32_t block, uint32_t num_blocks)
{
}

uint32_t board_flash_write_blocks(const uint8_t *src, uint32_t lba, uint32_t num_blocks)
{
}

void board_reset(void)
{
}

int main(void)
{
    //board_check_app_start();
    init();

    //board_check_tinyuf2_start();

    tusb_init();

    //printf("Hello TinyUF2!\r\n");

    while (1) {
        tud_task();
        led_blinking_task();
        reset_task();
    }

    return 0;
}
