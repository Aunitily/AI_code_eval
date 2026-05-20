这是一个通用的覆盖率合并与解析 Python 脚本。它能够自动识别工具环境（Synopsys **urg** 或 Cadence **imc**），执行合并，并解析生成的文本报告以导出 CSV。

### Python 脚本：`cov_manager.py`

```python
import os
import subprocess
import shutil
import re
import csv
import glob

class CoverageManager:
    def __init__(self, top_module="top", extra_opts=""):
        self.top_module = top_module
        self.extra_opts = extra_opts
        self.tool = self._detect_tool()
        self.report_dir = "cov_report_dir"
        self.merged_db = "merged_vdb" if self.tool == "urg" else "merged_db"

    def _detect_tool(self):
        """检测系统中安装的工具，优先选择 urg"""
        if shutil.which("urg"):
            print("[Info] Detected Synopsys 'urg' tool.")
            return "urg"
        elif shutil.which("imc"):
            print("[Info] Detected Cadence 'imc' tool.")
            return "imc"
        else:
            raise EnvironmentError("Neither 'urg' nor 'imc' found in PATH.")

    def find_databases(self, search_path):
        """扫描指定目录下的覆盖率数据库"""
        if self.tool == "urg":
            # Synopsys 使用 .vdb 目录
            return glob.glob(os.path.join(search_path, "**/*.vdb"), recursive=True)
        else:
            # Cadence imc 目录扫描逻辑（通常在 cov_work 目录下）
            return glob.glob(os.path.join(search_path, "**/scope/*"), recursive=True)

    def run_merge(self, db_list):
        """根据工具执行合并命令"""
        if not db_list:
            print("[Error] No coverage databases found.")
            return False

        if self.tool == "urg":
            # -format text 选项方便后续解析文本报告
            db_args = " ".join([f"-dir {db}" for db in db_list])
            cmd = f"urg -full64 {db_args} -dbname {self.merged_db} -report {self.report_dir} -format text {self.extra_opts}"
        else:
            # Cadence IMC 使用批处理脚本或命令
            db_args = " ".join(db_list)
            cmd = f"imc -batch -execute \"merge {db_args} -out {self.merged_db}; report -hierarchy -summary -out {self.report_dir}/imc_hier.txt\" {self.extra_opts}"

        print(f"[Run] {cmd}")
        if not os.path.exists(self.report_dir):
            os.makedirs(self.report_dir)
            
        process = subprocess.run(cmd, shell=True)
        return process.returncode == 0

    def parse_and_export(self):
        """解析报告并生成 CSV"""
        data = []
        
        if self.tool == "urg":
            # 解析 urg 生成的 hierarchy.txt
            # 路径通常是: {report_dir}/hierarchy.txt
            report_path = os.path.join(self.report_dir, "hierarchy.txt")
            data = self._parse_urg_text(report_path)
        else:
            # 解析 imc 生成的文本报告
            report_path = os.path.join(self.report_dir, "imc_hier.txt")
            data = self._parse_imc_text(report_path)

        # 写入 CSV
        csv_file = "coverage_summary.csv"
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Module Name", "Line Coverage", "Condition Coverage"])
            for row in data:
                writer.writerow(row)
                # 低于 90% 的警告
                try:
                    cond_val = float(row[2].replace('%', ''))
                    if cond_val < 90.0:
                        print(f"[Warning] Module '{row[0]}' Condition Coverage is low: {row[2]}")
                except ValueError:
                    pass

        print(f"[Success] Report generated: {csv_file}")

    def _parse_urg_text(self, file_path):
        """
        解析 Synopsys urg 的 hierarchy.txt
        典型格式：
        Module / Instance      |  Line  |  Cond
        ---------------------------------------
        top                    |  95.2% |  87.5%
        """
        results = []
        if not os.path.exists(file_path):
            print(f"[Error] Urg report {file_path} not found.")
            return results

        # 正则提取：模块名 | 行覆盖率 | 条件覆盖率
        # 假设格式为： 名称 | 比例 | 比例 ...
        pattern = re.compile(r"^\s*(\S+)\s+\|\s+([\d\.]+)%\s+\|\s+([\d\.]+)%")
        
        with open(file_path, 'r') as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    results.append([match.group(1), f"{match.group(2)}%", f"{match.group(3)}%"])
        return results

    def _parse_imc_text(self, file_path):
        """
        解析 Cadence IMC 文本报告
        典型格式示例：
        top (module)  95.2  87.5
        """
        results = []
        if not os.path.exists(file_path): return results
        
        # 简化版正则，根据实际 imc report 输出调整
        pattern = re.compile(r"^\s*(\S+)\s+.*\s+([\d\.]+)\s+([\d\.]+)\s*$")
        with open(file_path, 'r') as f:
            for line in f:
                if "block" in line or "module" in line: # 过滤包含层级的行
                    match = pattern.search(line)
                    if match:
                        results.append([match.group(1), f"{match.group(2)}%", f"{match.group(3)}%"])
        return results

# --- 使用示例 ---
if __name__ == "__main__":
    # 配置
    SEARCH_PATH = "./cov_work"  # 数据库所在目录
    EXTRA = "-norecurse"        # 额外参数
    
    manager = CoverageManager(top_module="top", extra_opts=EXTRA)
    
    # 1. 扫描
    dbs = manager.find_databases(SEARCH_PATH)
    print(f"[Info] Found {len(dbs)} databases.")
    
    # 2. 合并
    if manager.run_merge(dbs):
        # 3. 解析并生成报告
        manager.parse_and_export()
```

### 关键设计点：

1.  **工具自适应**：
    *   使用 `shutil.which` 检查环境变量。
    *   封装了 `run_merge`，根据不同工具链生成不同的 Shell 命令。
2.  **URG 解析逻辑**：
    *   使用了 `urg -format text` 参数。这会生成一个简单的 `hierarchy.txt` 文件，比解析复杂的 `urgReport/*.xml` 更加轻量且不容易出错。
3.  **IMC 解析逻辑**：
    *   通过 `imc -batch -execute` 直接在命令行完成合并与报告生成。
    *   解析 `report -hierarchy` 输出的文本文件。
4.  **警告机制**：
    *   在 CSV 生成循环中，将字符串格式的覆盖率（如 `"87.5%"`）转换为 `float` 进行比较。
5.  **灵活性**：
    *   `extra_opts` 允许用户传递类似 `-norecurse` 或 `-parallel` 等工具特定参数。

### 如何运行：
1.  将脚本保存为 `cov_manager.py`。
2.  确保你的环境已加载 VCS/Verdi (urg) 或 Xcelium (imc)。
3.  运行：
    ```bash
    python3 cov_manager.py
    ```
4.  检查当前目录下的 `coverage_summary.csv` 和终端输出的警告信息。