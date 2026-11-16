# mapviewer

**读懂 map 文件：到底是谁占了我的 Flash 和 RAM。**

Flash 快满了，RAM 快爆了。你打开 map 文件，看到几万行十六进制，然后合上了。

这个工具就是为了那一步——**把 map 文件变成一张能看懂的账单。**

```
  FLASH    20.6 KB / 512.0 KB     4.0%  █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
  RAM      14.9 KB / 128.0 KB    11.7%  ████░░░░░░░░░░░░░░░░░░░░░░░░░░
  校验    FLASH  链接器   20.6 KB / 解析   20.6 KB  ✓
  校验    RAM  链接器   14.9 KB / 解析   14.9 KB  ✓

    #        大小    占比  符号                            来源
  --------------------------------------------------------------------------
    1      8.2 KB   23.2%  heap_area                       sysmem.o
    2      2.6 KB    7.3%  _dtoa_r                         lib_a-dtoa.o  [lib]
    3      2.4 KB    6.9%  _vfprintf_r                     lib_a-vfprintf.o  [lib]
    ...

  谁在占地方:
    我的代码     25.2 KB   70.9%  █████████████████░░░░░░░
    静态库       10.3 KB   29.1%  ███████░░░░░░░░░░░░░░░░░
```

**那个「校验」行是重点。** 它拿链接器自己声明的段大小，和解析出来的合计对账——对得上，才说明这个工具没算错。任何统计工具如果不自证，你就只能盲信它。

## 为什么做它

在嵌入式里，空间不够时最常听到的一句话是"再优化优化"，但没人告诉你**优化谁**。

翻 map 文件能找到答案，但过程极其痛苦：段名、地址、大小、来源文件，几万行，还不是排序的。

这个工具做的事情只有一件：**按大小排序，告诉你前十名是谁，以及它们是不是你自己写的。**

因为真相通常是：**大头往往是库，不是你的代码。** 一句 `printf("%f")` 能吃掉 10 KB，而你可能只是想在调试时打一行浮点数。

## 支持什么

- **GCC**（`arm-none-eabi-ld`）生成的 `.map`
- **Keil / armcc**（`armlink`）生成的 `.map`
- 纯 Python 标准库，**不需要安装任何依赖**
- 只读文件，不改动工程

## 用法

```bash
python mapviewer.py firmware.map
```

常用参数：

```bash
python mapviewer.py firmware.map -n 30          # 看前 30 名
python mapviewer.py firmware.map -k ram         # 只看 RAM
python mapviewer.py firmware.map -k flash       # 只看 Flash
python mapviewer.py firmware.map -b module      # 按模块聚合，而不是按符号
python mapviewer.py firmware.map --html out.html  # 顺手导一份网页报告
python mapviewer.py new.map --diff old.map      # 和上一次构建对比
python mapviewer.py firmware.map --discarded    # 看被裁掉了什么
python mapviewer.py firmware.map -g HAL_        # 只看名字里含 HAL_ 的
```

## 怎么拿到 map 文件

**GCC（Makefile / CMake / STM32CubeIDE）**

链接时加 `-Wl,-Map=build/firmware.map`。CubeIDE 默认会生成在 `Debug/` 下。

建议同时打开 `-ffunction-sections -fdata-sections` + `-Wl,--gc-sections`，这样每个函数是独立段，工具才能按函数名统计。

**Keil（MDK）**

`Options for Target → Listing → Linker Listing`，勾上 **Memory Map**，编译后在 `Objects/` 或工程根目录找 `.map`。

## 输出怎么读

1. **先看总量条。** Flash 过了 80% 就要开始管了，RAM 过了 70% 要开始怕了（栈还没算呢）。
2. **再看"谁在占地方"。** 库超过 40%，优先做这几件事：
   - 换 `newlib-nano`（`--specs=nano.specs`）
   - 关掉 printf 的浮点支持（`-u _printf_float` 不要加）
   - 检查 `_sbrk` / `malloc` 是不是被无意中拉进来了（`heap_area` 那一行）
3. **最后看具体符号。** 排名靠前又意外的，通常是一次"顺手加的功能"。

## 两个版本对比（最有用的功能）

单独一份 map 只是一串数字。**两份放在一起，才是一份体检报告。**

```bash
python mapviewer.py build/Debug/xxx.map --diff build/Release/xxx.map
```

```
  旧  Release                         5.8 KB
  新  Debug                          28.4 KB
  变化                          +22.5 KB   (+387.1%)

  FLASH     5.4 KB  →  19.8 KB     +14.4 KB  (+265.3%)
  RAM        409 B  →   8.6 KB      +8.2 KB  (+2041.3%)

  新增模块 (15)
    +   6.8 KB  uart_serial.c.obj
    +   2.0 KB  iap_upgrade.c.obj
    +   1.5 KB  iap_aes.c.obj

  变大的符号
       +2.0 KB  s_dmaRxBuffer        uart_serial.c.obj
       +1.0 KB  s_crc32_table        iap_crc.c.obj
```

它回答的是真正要紧的问题：

- **这次改动多吃了多少？是哪个模块吃的？**
- **两个配置（Debug / Release）到底差在哪？** —— 差的不只是优化等级，可能是**模块根本不一样**
- **昨天还能装下，今天装不下了，是谁干的？**


## 看被裁掉了什么

```bash
python mapviewer.py firmware.map --discarded
```

```
  条目        651 条
  总计        122.6 KB
    代码         38.8 KB   ← 真正被裁掉的程序
    调试信息     83.9 KB   不进 Flash, 可以忽略

  丢弃最多的模块
      1     13.1 KB  stm32f1xx_hal_i2c.c.obj
      2      8.6 KB  stm32f1xx_hal_tim.c.obj

  整个文件一行都没进固件 (10)
        1.0 KB  stm32f1xx_hal_flash_ex.c.obj
         518 B  stm32f1xx_hal_exti.c.obj
```

**行数会骗人。** 一个开了 `-ffunction-sections` 的工程，Discarded 块动辄几千行——但其中九成是 `.debug_*`，本来就不进 Flash。看"代码"那一行才是真的。

两个用处：

- **削编译时间**：整个文件都没进固件的 HAL 模块，在 `hal_conf.h` 里关掉就行。
- **发现"没启用的功能"**：`syscalls.c` 整个被丢弃 = `printf` 没有重定向，哪天你想用串口打日志，输出会静默消失。


## 只看某一类

```bash
python mapviewer.py firmware.map -g uart -k ram
```

```
  [RAM]  匹配 6.0 KB / 全量 8.6 KB    69.9%  ████████████████░░░░░░

      1      2.0 KB   23.4%  .bss.s_txBuffer       s_txBuffer       uart_serial.c.obj
      2      2.0 KB   23.4%  .bss.s_dmaRxBuffer    s_dmaRxBuffer    uart_serial.c.obj
      3      2.0 KB   23.4%  .bss.s_rxBuffer       s_rxBuffer       uart_serial.c.obj
```

匹配范围是**符号名 / 模块名 / 段名**，不区分大小写。

注意占比的分母始终是**全量**，不是匹配子集——这样每一行的百分比和不过滤时是一致的，可以横向对比。

`--discarded` 也支持 `-g`：

```bash
python mapviewer.py firmware.map --discarded -g i2c
```


## 常见疑问：bin 有 19 KB，为什么 map 分析只有 5.4 KB？

大概率不是工具算错，是**你比了两次不同的构建**。按出现频率排：

1. **map 和 bin 不是同一次构建**（最常见）
   同一个工程，Debug 和 Release 能差三倍以上。先看两边的时间戳，和所在的 `build/Debug` / `build/Release` 目录。
2. **bin 被 0xFF 填充**
   `objcopy -O binary` 会把最低地址到最高地址之间铺平，中间的洞全填 0xFF。map 里的段是紧凑的，bin 是补过空白的。
3. **bin 是多个镜像拼起来的**
   比如 BL + APP 合成一个烧录文件。map 只描述其中一个。

**怎么确认（一条命令）：**

```bash
arm-none-eabi-size -A build/Release/xxx.elf
```

把 `.text` + `.rodata` + `.isr_vector` 加起来，和 map 的 FLASH 数对一下。对得上，说明是同一份构建，那问题就在 bin 的生成方式上。


## 已知限制

- `.data` 的初值在 Flash 里也有一份拷贝，目前统一算进 RAM，会让 Flash 略微低估
- 栈的峰值用量不在 map 里，无法统计（这是所有 map 工具的盲区）
- 段名归类靠前缀匹配，如果链接脚本用了非常规段名，可能归到 `other`

## Roadmap

- [ ] 支持 IAR（`.map` 格式又不一样）
- [ ] 输出树状图（按目录层级看占用）
- [ ] 与上一次构建对比，显示"这次多了 3 KB，是谁"
- [ ] 检测常见浪费：未使用的 HAL 模块、重复的 printf 实现

## License

MIT
