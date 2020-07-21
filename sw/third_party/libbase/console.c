/*
 * console.c
 *
 * Copyright (C) 2019 Sylvain Munaut
 * All rights reserved.
 *
 * LGPL v3+, see LICENSE.lgpl3
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 3 of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with this program; if not, write to the Free Software Foundation,
 * Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
 */

#include <stdint.h>

#include "mini-printf.h"

#include <generated/csr.h>
#include <hw/flags.h>
#include <uart.h>

static char _printf_buf[2];


void console_init(void)
{
//    uart_init();
}

char getchar(void)
{
	return -1;
}

int getchar_nowait(void)
{
	return -1;
}

void putchar(char c)
{
//    uart_write(c);
}

void puts(const char *p)
{
	char c;
	while ((c = *(p++)) != 0x00) {
		if (c == '\n')
			putchar('\r');
		putchar(c);
	}
}

int printf(const char *fmt, ...)
{
        va_list va;
        int l;

        va_start(va, fmt);
        l = mini_vsnprintf(_printf_buf, 256, fmt, va);
        va_end(va);

	puts(_printf_buf);

	return l;
}