这是一个寄存器自动化生成脚本的 Python 实现。该脚本使用 `pandas` 处理 Excel 数据，并生成 Verilog RTL、UVM 寄存器模型和 C 头文件。

### 1. 环境准备
你需要安装 `pandas` 和 `openpyxl`（用于读取 Excel）：
```bash
pip install pandas openpyxl
```

### 2. Python 脚本 `reg_gen.py`

```python
import pandas as pd
import argparse
import os
import re

class RegisterGenerator:
    def __init__(self, excel_path, out_dir, base_addr):
        self.excel_path = excel_path
        self.out_dir = out_dir
        self.base_addr = int(base_addr.replace('_', ''), 16)
        self.regs = {} # 存储解析后的寄存器数据

    def parse_excel(self):
        df = pd.read_excel(self.excel_path, sheet_name='registers')
        # 填充 Register Name 和 Offset (处理 Excel 中的合并单元格)
        df['Register Name'] = df['Register Name'].ffill()
        df['Offset'] = df['Offset'].ffill()

        for _, row in df.iterrows():
            reg_name = row['Register Name']
            offset = int(str(row['Offset']), 16)
            field_name = row['Field Name']
            bit_range = str(row['Bit Range'])
            access = row['Access'].upper()
            reset_val = int(str(row['Reset Value']), 16)
            desc = row['Description']

            # 解析 Bit Range (例如 "2:1" -> msb=2, lsb=1)
            if ':' in bit_range:
                msb, lsb = map(int, bit_range.split(':'))
            else:
                msb = lsb = int(bit_range)

            if reg_name not in self.regs:
                self.regs[reg_name] = {'offset': offset, 'fields': []}
            
            self.regs[reg_name]['fields'].append({
                'name': field_name,
                'msb': msb,
                'lsb': lsb,
                'width': msb - lsb + 1,
                'access': access,
                'reset': reset_val,
                'desc': desc
            })

    def gen_rtl(self):
        file_path = os.path.join(self.out_dir, "regfile_top.v")
        with open(file_path, 'w') as f:
            f.write("module regfile_top (\n    input clk, rst_n,\n")
            f.write("    input [31:0] addr, wdata, input wen, ren,\n")
            f.write("    output reg [31:0] rdata,\n")
            
            # 输出端口定义
            for name, info in self.regs.items():
                f.write(f"    output [{31}:0] {name.lower()}_q, \n")
                f.write(f"    output {name.lower()}_we, \n")
            f.write("    output reg error\n);\n\n")

            # 寄存器实例化与写逻辑
            for name, info in self.regs.items():
                f.write(f"  reg [31:0] {name.lower()}_r;\n")
                f.write(f"  assign {name.lower()}_q = {name.lower()}_r;\n")
                f.write(f"  assign {name.lower()}_we = wen && (addr == 32'h{info['offset']:08x});\n\n")
                
                f.write(f"  always @(posedge clk or negedge rst_n) begin\n")
                f.write(f"    if (!rst_n) begin\n")
                # 复位值拼接
                reset_all = 0
                for field in info['fields']:
                    reset_all |= (field['reset'] << field['lsb'])
                f.write(f"      {name.lower()}_r <= 32'h{reset_all:08x};\n")
                f.write(f"    end else if ({name.lower()}_we) begin\n")
                # 字段写逻辑 (RW, W1C等处理)
                for field in info['fields']:
                    mask = ((1 << field['width']) - 1) << field['lsb']
                    if field['access'] == 'RW':
                        f.write(f"      {name.lower()}_r[{field['msb']}:{field['lsb']}] <= wdata[{field['msb']}:{field['lsb']}];\n")
                    elif field['access'] == 'W1C':
                        f.write(f"      {name.lower()}_r[{field['msb']}:{field['lsb']}] <= {name.lower()}_r[{field['msb']}:{field['lsb']}] & ~wdata[{field['msb']}:{field['lsb']}];\n")
                f.write(f"    end\n  end\n\n")

            # 读逻辑
            f.write("  always @(*) begin\n    case(addr)\n")
            for name, info in self.regs.items():
                f.write(f"      32'h{info['offset']:08x}: rdata = {name.lower()}_r;\n")
            f.write("      default: rdata = 32'h0;\n    endcase\n  end\n")
            f.write("\nendmodule\n")

    def gen_uvm(self):
        file_path = os.path.join(self.out_dir, "ral_reg_block.sv")
        with open(file_path, 'w') as f:
            # 生成各个 Register Class
            for name, info in self.regs.items():
                f.write(f"class reg_{name.lower()} extends uvm_reg;\n")
                f.write(f"  `uvm_object_utils(reg_{name.lower()})\n")
                for field in info['fields']:
                    f.write(f"  rand uvm_reg_field {field['name']};\n")
                
                f.write(f"\n  function new(string name = \"reg_{name.lower()}\");\n")
                f.write(f"    super.new(name, 32, UVM_NO_COVERAGE);\n  endfunction\n\n")
                
                f.write("  virtual function void build();\n")
                for field in info['fields']:
                    f.write(f"    this.{field['name']} = uvm_reg_field::type_id::create(\"{field['name']}\");\n")
                    f.write(f"    this.{field['name']}.configure(this, {field['width']}, {field['lsb']}, \"{field['access']}\", 0, 'h{field['reset']:x}, 1, 1, 0);\n")
                f.write("  endfunction\nendclass\n\n")

            # 生成 Reg Block
            f.write("class ral_block extends uvm_reg_block;\n  `uvm_object_utils(ral_block)\n")
            for name in self.regs:
                f.write(f"  rand reg_{name.lower()} {name.lower()};\n")
            
            f.write("\n  function new(string name = \"ral_block\");\n")
            f.write(f"    super.new(name, UVM_NO_COVERAGE);\n  endfunction\n\n")

            f.write("  virtual function void build();\n")
            f.write("    this.default_map = create_map(\"default_map\", 'h{:x}, 4, UVM_LITTLE_ENDIAN);\n".format(self.base_addr))
            for name, info in self.regs.items():
                f.write(f"    this.{name.lower()} = reg_{name.lower()}::type_id::create(\"{name.lower()}\");\n")
                f.write(f"    this.{name.lower()}.configure(this, null, \"\");\n")
                f.write(f"    this.{name.lower()}.build();\n")
                f.write(f"    this.default_map.add_reg(this.{name.lower()}, 'h{info['offset']:x}, \"{info['fields'][0]['access']}\");\n")
            f.write("  endfunction\nendclass\n")

    def gen_c_header(self):
        file_path = os.path.join(self.out_dir, "regs.h")
        with open(file_path, 'w') as f:
            f.write(f"#ifndef REGS_H\n#define REGS_H\n\n")
            f.write(f"#define BASE_ADDR 0x{self.base_addr:08x}\n\n")
            
            for name, info in self.regs.items():
                reg_addr = f"(BASE_ADDR + 0x{info['offset']:04x})"
                f.write(f"/* Register {name} */\n")
                f.write(f"#define REG_{name.upper()} {reg_addr}\n")
                for field in info['fields']:
                    mask = ((1 << field['width']) - 1) << field['lsb']
                    f.write(f"#define {name.upper()}_{field['name'].upper()}_MASK 0x{mask:x}\n")
                    f.write(f"#define {name.upper()}_{field['name'].upper()}_SHIFT {field['lsb']}\n")
                f.write("\n")
            f.write("#endif\n")

    def run(self):
        if not os.path.exists(self.out_dir):
            os.makedirs(self.out_dir)
        self.parse_excel()
        self.gen_rtl()
        self.gen_uvm()
        self.gen_c_header()
        print(f"Generation complete in {self.out_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("excel", help="Path to registers.xlsx")
    parser.add_argument("--out_dir", default="./generated")
    parser.add_argument("--base_addr", default="0x40000000")
    args = parser.parse_args()

    gen = RegisterGenerator(args.excel, args.out_dir, args.base_addr)
    gen.run()
```

### 3. 实现说明

#### RTL 生成 (Verilog)
*   **多字段合并**：脚本首先将 Excel 数据按 `Register Name` 分组。对于同一个寄存器，它会生成一个统一的 `always` 块。
*   **写使能**：为每个寄存器生成一个 `_we` 信号。
*   **访问类型**：
    *   `RW`：正常的赋值逻辑。
    *   `W1C` (Write 1 Clear)：通过 `reg <= reg & ~wdata` 实现。
    *   `RO`：不会出现在写逻辑的分支中，保持复位值（或由外部硬件驱动，脚本中预留了端口）。

#### UVM 模型 (SystemVerilog)
*   继承自 `uvm_reg` 和 `uvm_reg_block`。
*   **`configure` 映射**：正确映射字段的宽度、起始位、访问权限（如 "RW", "RO"）和复位值。
*   **`add_map`**：在 `uvm_reg_block` 中根据 Excel 里的 `Offset` 自动计算偏移并添加到 `default_map`。

#### C 头文件
*   生成绝对地址宏：`#define REG_CTRL (BASE_ADDR + 0x0000)`。
*   生成掩码和偏移量：方便驱动开发人员使用 `(val & MASK) >> SHIFT`。

#### 扩展性说明
*   **非连续位域**：目前脚本基于 `msb:lsb` 连续位。如果需要处理非连续位（如 `7:4, 2:0`），建议在 Excel 中拆分为两个 Field。
*   **地址填充**：脚本使用了 `ffill()`，这意味着 Excel 中如果 `Register Name` 列只有第一行有值，后续行（同一寄存器的不同字段）会被自动补全。

### 4. 运行方法示例
准备一个名为 `registers.xlsx` 的文件，包含名为 `registers` 的 Sheet，格式如你题目所示。
执行：
```bash
python reg_gen.py registers.xlsx --out_dir ./output --base_addr 0x40000000
```
你会得到 `regfile_top.v`, `ral_reg_block.sv` 和 `regs.h` 三个文件。