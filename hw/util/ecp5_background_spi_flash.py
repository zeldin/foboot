import struct
import sys
import textwrap

def reverse_byte(x):
    x = ((x & 0x55) << 1) | ((x & 0xAA) >> 1)
    x = ((x & 0x33) << 2) | ((x & 0xCC) >> 2)
    x = ((x & 0x0F) << 4) | ((x & 0xF0) >> 4)
    return x

def reverse_bits(x):
    return "".join(["{:02X}".format(reverse_byte(b)) for b in reversed(x)])

def wrap(line):
    return "\n".join(textwrap.wrap(line, 79, subsequent_indent='  '))

def spi_exchange(data, match=None, mask=None, ignore=0, file=None):
    data = reverse_bits(data)
    if match is not None and len(match) > ignore and len(data) > 0:
        if mask is not None and len(mask) < len(match):
            mask += b'\x00'*(len(match)*len(mask))
        mask = reverse_bits(b'\x00'*ignore +
                            (b'\xff'*(len(match)-ignore) if mask is None
                             else mask[ignore:len(match)]))
        match = reverse_bits(match)
        if len(match) < len(data):
            match = "0"*(len(data)-len(match)) + match
            mask = "0"*(len(data)-len(mask)) + mask
        else:
            match = match[-len(data):]
            mask = mask[-len(data):]
        print(wrap("SDR {} TDI ({}) TDO ({}) MASK ({});".format(
	    4*len(data), data, match, mask)), file=file)
    else:
        print(wrap("SDR {} TDI ({});".format(4*len(data), data)), file=file)

def check_not_busy(read_status_opcode, file=None):
    spi_exchange(struct.pack('>Bx', read_status_opcode),
                 match=b'\0\0', mask=b'\0\1', ignore=1, file=file)

def delay(sec, file=None):
    print("RUNTEST IDLE {:.3G} SEC;".format(sec), file=file)

def header(idcode, file=None):
    print("""
STATE RESET;
HDR   0;
HIR   0;
TDR   0;
TIR   0;
ENDDR DRPAUSE;
ENDIR IRPAUSE;
STATE IDLE;

SIR   8   TDI (E0);
SDR   32  TDI (00000000) TDO ({:08X}) MASK (FFFFFFFF);
SIR   8   TDI (1C);
SDR   510 TDI (3FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
      FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF);

// Enter Programming mode
SIR   8   TDI (C6);
SDR   8   TDI (00);
RUNTEST IDLE 2 TCK 1.00E-02 SEC;

// Erase
SIR   8   TDI (0E);
SDR   8   TDI (01);
RUNTEST IDLE 2 TCK 2.0E-1 SEC;

// Read STATUS
SIR   8   TDI (3C);
SDR   32  TDI (00000000) TDO  (00000000) MASK (0000B000);

// Exit Programming mode
SIR   8   TDI (26);
RUNTEST IDLE 2 TCK 1.00E-02 SEC;

// BYPASS
SIR   8   TDI (FF);
STATE IDLE;
RUNTEST 32 TCK;
RUNTEST 2.00E-2 SEC;
// Enter SPI mode
ENDDR IDLE;
SIR   8   TDI (3A);
SDR   16  TDI (68FE);
RUNTEST 32 TCK;
RUNTEST 2.00E-2 SEC;
SDR   64  TDI (FFFFFFFFFFFFFFFF);
SDR   2   TDI (3);
SDR   8   TDI (FF);
""".format(idcode), file=file)

def footer(file=None):
    print("""
SIR   8   TDI (79);
RUNTEST IDLE 32 TCK;
""", file=file)

def create_spi_flash_svf_from_file(idcode, bitfile, output=None,
                                   flash_id=0xef4018,
                                   write_disable_opcode=0x04,
                                   read_status_opcode=0x05,
                                   write_enable_opcode=0x06,
                                   block_erase_opcode=0xd8,
                                   block_erase_size=65536,
                                   block_erase_time=2,
                                   page_program_opcode=0x02,
                                   page_program_size=256,
                                   page_program_time=3e-3,
                                   fast_read_opcode=0x0b,
                                   jedec_id_opcode=0x9f):
    header(idcode, file=output)
    spi_exchange(struct.pack('>Bxxx', jedec_id_opcode),
                 match=struct.pack('>I', flash_id), ignore=1, file=output)
    check_not_busy(read_status_opcode, file=output)
    addr = 0
    curr_block = None
    while True:
        page = bitfile.read(page_program_size)
        if not page:
            break
        if addr // block_erase_size != curr_block:
            # Erase
            curr_block = addr // block_erase_size
            spi_exchange(struct.pack('>B', write_enable_opcode), file=output)
            spi_exchange(struct.pack('>I', (block_erase_opcode << 24) | addr),
                         file=output)
            delay(block_erase_time, file=output)
            check_not_busy(read_status_opcode, file=output)
        # Program
        spi_exchange(struct.pack('>B', write_enable_opcode), file=output)
        spi_exchange(struct.pack('>I', (page_program_opcode << 24) | addr)
                     + page, file=output)
        delay(page_program_time, file=output)
        check_not_busy(read_status_opcode, file=output)
        addr += len(page)
    spi_exchange(struct.pack('>B', write_disable_opcode), file=output)
    bitfile.seek(0)
    addr = 0
    while True:
        page = bitfile.read(page_program_size)
        if not page:
            break
        # Verify
        spi_exchange(struct.pack('>Ix', (fast_read_opcode << 24) | addr)
                     + b'\0'*len(page), match=b'\0\0\0\0\0'+page,
                     ignore=5, file=output)
        addr += len(page)
    footer(file=output)

def create_spi_flash_svf(input, output=None, **kwargs):
    with open(input, 'rb') as bf:
        tmp = bf.read(256)
        pos = tmp.find(b'\xe2\0\0\0')
        if pos >= 0 and pos + 8 <= len(tmp):
            idcode, = struct.unpack_from('>I', tmp, pos + 4)
        else:
            raise(Exception("No IDCODE found"))
        bf.seek(0)
        if output is not None:
            with open(output, 'w') as sf:
                create_spi_flash_svf_from_file(idcode, bf, output=sf, **kwargs)
        else:
            create_spi_flash_svf_from_file(idcode, bf, **kwargs)

if __name__ == "__main__":
    create_spi_flash_svf(sys.argv[1],
                         None if len(sys.argv)<3 else sys.argv[2])
