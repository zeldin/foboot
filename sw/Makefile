GIT_VERSION := $(shell git describe --tags)

# Earlier versions of the Raspberry Pi image only had riscv32-gcc
ifneq (,$(wildcard /usr/bin/riscv32-unknown-elf-gcc))
TRGT       ?= riscv32-unknown-elf-
else
TRGT       ?= riscv64-unknown-elf-
endif

CC         := $(TRGT)gcc
CXX        := $(TRGT)g++
OBJCOPY    := $(TRGT)objcopy
OBJDUMP    := $(TRGT)objdump

RM         := rm -rf
COPY       := cp -a
PATH_SEP   := /

ifeq ($(OS),Windows_NT)
COPY       := copy
RM         := del
PATH_SEP   := \\
endif

ifeq ($(LITEX),1)
BASE_DIR   := ../../../../sw
LDSCRIPT   := $(BASE_DIR)/ld/linker.ld
LD_DIR     := ../include/generated
ADD_CFLAGS := -I../include -I$(BASE_DIR)/include 
ADD_LFLAGS := 
PACKAGE    := bios
else
BASE_DIR   := .
LD_DIR     := $(BASE_DIR)/ld
LDSCRIPT   := $(BASE_DIR)/ld/linker.ld
ADD_CFLAGS := -I$(BASE_DIR)/include
ADD_LFLAGS := 
PACKAGE    := foboot
endif

LDSCRIPTS  := $(LDSCRIPT) $(LD_DIR)/output_format.ld $(LD_DIR)/regions.ld
SRC_DIR    := $(BASE_DIR)/src
THIRD_PARTY := $(BASE_DIR)/third_party
DBG_CFLAGS := -ggdb3 -DDEBUG -Wall
DBG_LFLAGS := -ggdb3 -Wall
CFLAGS     := $(ADD_CFLAGS) \
			  -D__vexriscv__ -march=rv32im  -mabi=ilp32 \
			  -Wall -Wextra \
			  -ffunction-sections -fdata-sections -fno-common \
			  -fomit-frame-pointer -Os \
			  -DGIT_VERSION=u\"$(GIT_VERSION)\" -DUF2_VERSION_BASE=\"$(GIT_VERSION)\" -std=gnu11
CXXFLAGS   := $(CFLAGS) -std=c++11 -fno-rtti -fno-exceptions
LFLAGS     := $(CFLAGS) $(ADD_LFLAGS) -L$(LD_DIR) \
		      -ffreestanding \
			  -nostartfiles \
			  -specs=nano.specs \
			  -Wl,--gc-sections \
			  -Wl,--no-warn-mismatch \
			  -Wl,--script=$(LDSCRIPT) \
			  -Wl,--build-id=none

# TinyUSB additions
TINY_USB   := $(THIRD_PARTY)/tinyusb/src
CFLAGS     += -I$(TINY_USB) -I$(TINY_USB)/common -I$(TINY_USB)/device -I$(TINY_USB)/portable/valentyusb -I../include/generated
CFLAGS     += -DCFG_TUSB_MCU=OPT_MCU_VALENTYUSB_EPTRI

CSOURCES := $(TINY_USB)/class/msc/msc_device.c \
			$(TINY_USB)/class/cdc/cdc_device.c \
			$(TINY_USB)/class/hid/hid_device.c \
			$(TINY_USB)/common/tusb_fifo.c \
			$(TINY_USB)/device/usbd_control.c \
			$(TINY_USB)/device/usbd.c \
			$(TINY_USB)/portable/valentyusb/eptri/dcd_eptri.c \
			$(TINY_USB)/tusb.c

## TinyUF2

CFLAGS   += -DBOARD_FLASH_SIZE=0x80000 \
			-DBOARD_FLASH_BASE=0x20080000 \
			-DAPP_START_ADDRESS=0x20080000 \
            -DPRODUCT_NAME=\"OrangeCrab\ r0.2\" \
            -DINDEX_URL=\"https://github.com/gregdavill/OrangeCrab\" \
			-DVOLUME_LABEL=\"UF2\" \
			-DBOARD_ID=\"0x100\" \
			-DVENDOR_NAME=\"GsD\" \
			-DUF2_FAMILY=0xAA
            

OBJ_DIR    := .obj

CSOURCES   += $(wildcard $(SRC_DIR)/*.c) $(wildcard $(THIRD_PARTY)/libbase/*.c) $(wildcard $(THIRD_PARTY)/*.c) 
CPPSOURCES := $(wildcard $(SRC_DIR)/*.cpp) $(wildcard $(THIRD_PARTY)/libbase/*.cpp) $(wildcard $(THIRD_PARTY)/*.cpp)
ASOURCES   := $(wildcard $(SRC_DIR)/*.S) $(wildcard $(THIRD_PARTY)/libbase/*.S) $(wildcard $(THIRD_PARTY)/*.S)
COBJS      := $(addprefix $(OBJ_DIR)/, $(notdir $(CSOURCES:.c=.o)))
CXXOBJS    := $(addprefix $(OBJ_DIR)/, $(notdir $(CPPSOURCES:.cpp=.o)))
AOBJS      := $(addprefix $(OBJ_DIR)/, $(notdir $(ASOURCES:.S=.o)))
OBJECTS    := $(COBJS) $(CXXOBJS) $(AOBJS)
VPATH      := $(SRC_DIR) $(THIRD_PARTY) $(THIRD_PARTY)/libbase $(TINY_USB) $(TINY_USB)/class/msc $(TINY_USB)/class/cdc $(TINY_USB)/class/hid $(TINY_USB)/common $(TINY_USB)/device $(TINY_USB)/portable/valentyusb/eptri

QUIET      := 

ALL        := all
TARGET     := $(PACKAGE).elf
CLEAN      := clean

$(ALL): $(TARGET) $(PACKAGE).bin $(PACKAGE).ihex

$(OBJECTS): | $(OBJ_DIR)

$(TARGET): $(OBJECTS) $(LDSCRIPTS)
	$(QUIET) echo "  LD       $@"
	$(QUIET) $(CC) $(OBJECTS) $(LFLAGS) -o $@

$(PACKAGE).bin: $(TARGET)
	$(QUIET) echo "  OBJCOPY  $@"
	$(QUIET) $(OBJCOPY) -O binary $(TARGET) $@
	
$(PACKAGE).lst: $(TARGET)
	$(QUIET) echo "  OBJDUMP  $@"
	$(QUIET) $(OBJDUMP) -DS $(TARGET) > $@

$(PACKAGE).dfu: $(TARGET)
	$(QUIET) echo "  DFU      $@"
	$(QUIET) $(COPY) $(PACKAGE).bin $@
	$(QUIET) dfu-suffix -v 1209 -p 70b1 -a $@

$(PACKAGE).ihex: $(TARGET)
	$(QUIET) echo "  IHEX     $(PACKAGE).ihex"
	$(QUIET) $(OBJCOPY) -O ihex $(TARGET) $@

#$(DEBUG): CFLAGS += $(DBG_CFLAGS)
#$(DEBUG): LFLAGS += $(DBG_LFLAGS)
#CFLAGS += $(DBG_CFLAGS)
#LFLAGS += $(DBG_LFLAGS)
#$(DEBUG): $(TARGET)

$(OBJ_DIR):
	$(QUIET) mkdir $(OBJ_DIR)

$(COBJS) : $(OBJ_DIR)/%.o : %.c $(BASE_DIR)/Makefile
	$(QUIET) echo "  CC       $<	$(notdir $@)"
	$(QUIET) $(CC) -c $< $(CFLAGS) -o $@ -MMD

$(OBJ_DIR)/%.o: %.cpp
	$(QUIET) echo "  CXX      $<	$(notdir $@)"
	$(QUIET) $(CXX) -c $< $(CXXFLAGS) -o $@ -MMD

$(OBJ_DIR)/%.o: %.S
	$(QUIET) echo "  AS       $<	$(notdir $@)"
	$(QUIET) $(CC) -x assembler-with-cpp -c $< $(CFLAGS) -o $@ -MMD

.PHONY: clean

clean:
	$(QUIET) echo "  RM      $(subst /,$(PATH_SEP),$(wildcard $(OBJ_DIR)/*.d))"
	-$(QUIET) $(RM) $(subst /,$(PATH_SEP),$(wildcard $(OBJ_DIR)/*.d))
	$(QUIET) echo "  RM      $(subst /,$(PATH_SEP),$(wildcard $(OBJ_DIR)/*.d))"
	-$(QUIET) $(RM) $(subst /,$(PATH_SEP),$(wildcard $(OBJ_DIR)/*.o))
	$(QUIET) echo "  RM      $(TARGET) $(PACKAGE).bin $(PACKAGE).symbol $(PACKAGE).ihex $(PACKAGE).dfu"
	-$(QUIET) $(RM) $(TARGET) $(PACKAGE).bin $(PACKAGE).symbol $(PACKAGE).ihex $(PACKAGE).dfu

include $(wildcard $(OBJ_DIR)/*.d)
