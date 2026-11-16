# -*- coding: utf-8 -*-
"""生成两份用于自测的示例 map 文件(GCC / armcc), 内容是 STM32F407VE 常见工程的典型分布。"""
from pathlib import Path

OUT = Path(__file__).parent

FLASH_ENTRIES = [
    (".isr_vector", 0x188, "./build/startup_stm32f407xx.o"),
    (".text.Reset_Handler", 0x5C, "./build/startup_stm32f407xx.o"),
    (".text.SystemInit", 0x1B4, "./build/system_stm32f4xx.o"),
    (".text.main", 0x2A8, "./build/main.o"),
    (".text.HAL_Init", 0x38, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.o"),
    (".text.HAL_MspInit", 0xE4, "./Core/Src/stm32f4xx_hal_msp.o"),
    (".text.HAL_GPIO_Init", 0x214, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.o"),
    (".text.HAL_GPIO_WritePin", 0x4C, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.o"),
    (".text.HAL_UART_Init", 0x1F8, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.o"),
    (".text.HAL_UART_Transmit", 0x134, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.o"),
    (".text.HAL_UART_Receive_IT", 0xBC, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.o"),
    (".text.HAL_RCC_OscConfig", 0x2D0, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.o"),
    (".text.HAL_RCC_ClockConfig", 0x16C, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.o"),
    (".text.HAL_SPI_Transmit", 0x158, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_spi.o"),
    (".text.HAL_ADC_Start", 0x78, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc.o"),
    (".text.HAL_TIM_Base_Init", 0x9C, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.o"),
    (".text.HAL_Delay", 0x44, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.o"),
    (".text.app_task", 0x3D8, "./App/Src/app_task.o"),
    (".text.app_protocol_parse", 0x51C, "./App/Src/app_protocol.o"),
    (".text.app_protocol_encode", 0x284, "./App/Src/app_protocol.o"),
    (".text.app_crc16", 0x74, "./App/Src/app_crc.o"),
    (".text.app_flash_save", 0x1A8, "./App/Src/app_param.o"),
    (".text.app_sensor_update", 0x2F0, "./App/Src/app_sensor.o"),
    (".text.app_uart_rx_cb", 0xC8, "./App/Src/app_uart.o"),
    (".rodata.app_version", 0x18, "./App/Src/app_main.o"),
    (".rodata", 0x2C4, "./App/Src/app_table.o"),
    (".text.printf", 0x1C4, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-printf.o)"),
    (".text.vfprintf", 0x4A8, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-vfprintf.o)"),
    (".text._vfprintf_r", 0x9C0, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-vfprintf.o)"),
    (".text.memcpy", 0x58, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-memcpy.o)"),
    (".text.memset", 0x4C, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-memset.o)"),
    (".text.strlen", 0x3C, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-strlen.o)"),
    (".text.strcmp", 0x44, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-strcmp.o)"),
    (".text.malloc", 0x1D8, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-malloc.o)"),
    (".text._malloc_r", 0x3AC, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-malloc.o)"),
    (".text._free_r", 0x2B4, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-malloc.o)"),
    (".text.__sfvwrite", 0x2C8, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-sfvwrite.o)"),
    (".text.__ssputc_r", 0x1A4, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-ssputc.o)"),
    (".text._dtoa_r", 0xA4C, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-dtoa.o)"),
    (".text.__aeabi_dadd", 0x8C, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libgcc.a(_adddf3.o)"),
    (".text.__aeabi_dmul", 0x94, "./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libgcc.a(_muldf3.o)"),
    (".text.FPU_Enable", 0x24, "./build/startup_stm32f407xx.o"),
]

RAM_ENTRIES = [
    (".data.uwTickPrio", 0x4, "./build/main.o"),
    (".data.huart1", 0x98, "./Core/Src/usart.o"),
    (".data.g_app_ctx", 0x210, "./App/Src/app_task.o"),
    (".data.g_rx_buf", 0x400, "./App/Src/app_uart.o"),
    (".data.g_tx_buf", 0x400, "./App/Src/app_uart.o"),
    (".data.g_param_cache", 0x180, "./App/Src/app_param.o"),
    (".bss.g_adc_dma_buf", 0x800, "./App/Src/app_sensor.o"),
    (".bss.g_ring_buf", 0x200, "./App/Src/app_protocol.o"),
    (".bss.heap_area", 0x2100, "./Core/Src/sysmem.o"),
    (".bss.sensor_frame", 0x140, "./App/Src/app_sensor.o"),
    (".bss.g_err_log", 0x300, "./App/Src/app_log.o"),
    ("COMMON", 0x38, "./Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.o"),
    ("COMMON", 0x1C, "./App/Src/app_crc.o"),
]


def group_flash(section):
    if section.startswith(".isr_vector"):
        return ".isr_vector"
    if section.startswith(".rodata"):
        return ".rodata"
    if section.startswith(".ARM"):
        return ".ARM.exidx"
    return ".text"


def group_ram(section):
    if section.startswith(".data") or section == "COMMON":
        return ".data"
    return ".bss"


def gcc():
    L = []
    L.append("Archive member included to satisfy reference by file (symbol)")
    L.append("")
    L.append(" ./arm-none-eabi/lib/thumb/v7e-m+fp/hard/libc_nano.a(lib_a-printf.o)")
    L.append("                               ./build/main.o (printf)")
    L.append("")
    L.append("Discarded input sections")
    L.append("")
    L.append(" .text          0x00000000        0x0 ./build/unused.o")
    L.append(" .bss           0x00000000       0x20 ./build/unused.o")
    L.append("")
    L.append("Memory Configuration")
    L.append("")
    L.append("Name             Origin             Length             Attributes")
    L.append("FLASH            0x0000000008000000 0x0000000000080000 xr")
    L.append("RAM              0x0000000002000000 0x0000000000020000 xrw")
    L.append("CCMRAM           0x0000000001000000 0x0000000000010000 rw")
    L.append("*default*        0x0000000000000000 0xffffffffffffffff")
    L.append("")
    L.append("Linker script and memory map")
    L.append("")

    addr = 0x08000000
    order = [".isr_vector", ".text", ".rodata", ".ARM.exidx"]
    groups = {}
    for sec, sz, obj in FLASH_ENTRIES:
        groups.setdefault(group_flash(sec), []).append((sec, sz, obj))
    for gname in order:
        items = groups.get(gname)
        if not items:
            continue
        total = sum(sz for _, sz, _ in items)
        L.append(f"{gname:<16} 0x{addr:08x}      0x{total:x}")
        L.append(f" *({gname}*)")
        for sec, sz, obj in items:
            L.append(f" {sec:<28} 0x{addr:08x}      0x{sz:x} {obj}")
            addr += sz
            if addr % 4:
                addr += 4 - addr % 4
        L.append("")
    L.append("                0x%08x                _etext = ." % addr)
    L.append("")

    raddr = 0x20000000
    rgroups = {}
    for sec, sz, obj in RAM_ENTRIES:
        rgroups.setdefault(group_ram(sec), []).append((sec, sz, obj))
    for gname in [".data", ".bss"]:
        items = rgroups.get(gname)
        if not items:
            continue
        total = sum(sz for _, sz, _ in items)
        L.append(f"{gname:<16} 0x{raddr:08x}      0x{total:x}")
        L.append(f" *({gname}*)")
        for sec, sz, obj in items:
            L.append(f" {sec:<28} 0x{raddr:08x}      0x{sz:x} {obj}")
            raddr += sz
        L.append("")
    return "\n".join(L) + "\n"


def armcc():
    L = []
    L.append("Component: ARM Compiler 5.06 update 7 (build 960) Tool: armlink [4d3601]")
    L.append("")
    L.append("==============================================================================")
    L.append("")
    L.append("Memory Map of the image")
    L.append("")
    L.append("  Image Entry point : 0x08000189")
    L.append("")
    L.append("  Load Region LR_IROM1 (Base: 0x08000000, Size: 0x0000A1C4, Max: 0x00080000, ABSOLUTE)")
    L.append("")
    L.append("    Execution Region ER_IROM1 (Exec base: 0x08000000, Load base: 0x08000000, Size: 0x0000A1C4, Max: 0x00080000, ABSOLUTE)")
    L.append("")
    L.append("    Exec Addr    Load Addr   Size         Type   Attr      Idx    E Section Name        Object")
    L.append("")
    addr = 0x08000000
    LRAM = 0x20000000
    for s, sz, o in FLASH_ENTRIES:
        L.append(f"   0x{addr:08x}   0x{addr:08x}   0x{sz:08x}   Code   RO        {100}    {s:<24}{o}")
        addr += sz
        if addr % 4:
            addr += 4 - addr % 4
    L.append("")
    L.append("    Execution Region RW_IRAM1 (Exec base: 0x20000000, Load base: 0x0800A1C4, Size: 0x00003E7C, Max: 0x00020000, ABSOLUTE)")
    L.append("")
    L.append("    Exec Addr    Load Addr   Size         Type   Attr      Idx    E Section Name        Object")
    L.append("")
    for s, sz, o in RAM_ENTRIES:
        L.append(f"   0x{LRAM:08x}   0x{addr:08x}   0x{sz:08x}   Data   RW        {100}    {s:<24}{o}")
        LRAM += sz
    L.append("")
    L.append("==============================================================================")
    L.append("")
    L.append("Image component sizes")
    L.append("")
    L.append("      Code (inc. data)   RO Data    RW Data    ZI Data      Debug   Object Name")
    L.append("      1536         44       1024       2048       1280       2048   main.o")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    (OUT / "samples").mkdir(exist_ok=True)
    (OUT / "samples" / "sample_gcc.map").write_text(gcc(), encoding="utf-8")
    (OUT / "samples" / "sample_armcc.map").write_text(armcc(), encoding="utf-8")
    print("生成完毕")
