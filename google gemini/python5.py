python
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