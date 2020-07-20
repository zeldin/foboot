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


__attribute__((noreturn)) void reboot(void);

__attribute__((noreturn)) static inline void warmboot_to_image(uint8_t image_index) {
	reboot_ctrl_write(0xac | (image_index & 3) << 0);
	while (1);
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
    console_init();

    irq_setmask(0);
    irq_setie(1);
}


void board_flash_flush(void)
{
}


#define SECTOR_SIZE 0x1000 /* 4K */
#define FLASH_PAGE_SIZE 256
#define FILESYSTEM_BLOCK_SIZE 256

static inline uint32_t lba2addr(uint32_t block)
{
  return 0x20080000 + block * FILESYSTEM_BLOCK_SIZE;
}

uint32_t board_flash_read_blocks(uint8_t *dest, uint32_t block, uint32_t num_blocks)
{
    //printf("board_flash_read_block(dest=0x%08x,block=%u,num_blocks=%u)\n", dest, block, num_blocks);
    spiFree(); // Enable FLASH in memorymapped region

    uint32_t src = lba2addr(block);
    memcpy(dest, (uint8_t*) src, FILESYSTEM_BLOCK_SIZE * num_blocks);
}

#define MIN(a,b) a < b ? a : b

uint32_t board_flash_write_blocks(const uint8_t *src, uint32_t lba, uint32_t num_blocks)
{

    //printf("board_flash_write_block(src=0x%08x,lba=%u,num_blocks=%u)\n", src, lba, num_blocks);
    spiInit(); // disable Memory Mapped Mode

    while (num_blocks) {
        uint32_t const addr      = 0x80000 + lba * FILESYSTEM_BLOCK_SIZE;
        uint32_t const page_addr = addr & ~(SECTOR_SIZE - 1);

        uint32_t count = 8 - (lba % 8); // up to page boundary
        count = MIN(num_blocks, count);

        /* First block in the sector, we need to erase */
        if(addr == page_addr){
            spiBeginErase4(addr);
            while(spiIsBusy());
        }

        spiBeginWrite(addr, src, FILESYSTEM_BLOCK_SIZE);
        while(spiIsBusy());

        // adjust for next run
        lba        += count;
        src        += count * FILESYSTEM_BLOCK_SIZE;
        num_blocks -= count;
    }

    return 0; // success
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

    printf("\r\nHello TinyUF2! ^_^\r\n");

    while (1) {
        tud_task();
        led_blinking_task();
        reset_task();
    }

    return 0;
}
