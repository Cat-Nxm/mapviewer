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
