#ifndef APP_OFFSET
#define APP_OFFSET 0x20000 #128K
#endif
#include "generated/mem.h"

.section .text.start
.global _start

_start:

  li a0, SRAM_BASE
  li a1, SRAM_BASE + 0x10000
  li a2, SPIFLASH_BASE + APP_OFFSET

copy_loop:
  beq a0,a1,copy_done
  lw t0,0(a2)
  sw t0,0(a0)
  add a0,a0,4
  add a2,a2,4
  j copy_loop
copy_done:

  li a0, SRAM_BASE # Firmware in SPRAM
  jr a0
  nop
