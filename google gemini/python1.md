这是一个实现该功能的 Python 脚本 `run_flow.py`。它使用了 `argparse` 处理参数，`subprocess` 调用系统命令，并包含了日志检查和归档逻辑。

### Python 脚本：`run_flow.py`

```python
import argparse
import subprocess
import os
import sys
import re
from datetime import datetime
import shutil

def check_log_for_errors(log_file):
    """检查日志文件中是否存在 'ERROR' 关键字（不区分大小写）"""
    if not os.path.exists(log_file):
        print(f"[Error] Log file {log_file} not found.")
        return True
    
    error_pattern = re.compile(r'error', re.IGNORECASE)
    with open(log_file, 'r') as f:
        for line in f:
            if error_pattern.search(line):
                print(f"[Error] Found ERROR in {log_file}: {line.strip()}")
                return True
    return False

def archive_log(log_file, step_name):
    """将日志移动到 ./logs/ 目录并重命名"""
    log_dir = "./logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_log_name = f"{step_name}_{timestamp}.log"
    dest_path = os.path.join(log_dir, new_log_name)
    
    if os.path.exists(log_file):
        shutil.move(log_file, dest_path)
        print(f"[Info] Log archived to: {dest_path}")
    return dest_path

def run_command(cmd, step_name, log_file):
    """运行 shell 命令并处理结果"""
    print(f"\n[Step] Starting {step_name}...")
    print(f"[Cmd] {cmd}")
    
    try:
        # 执行命令
        process = subprocess.run(cmd, shell=True)
        
        # 1. 检查命令返回值
        if process.returncode != 0:
            print(f"[Error] {step_name} command failed with return code {process.returncode}")
            archive_log(log_file, step_name)
            sys.exit(1)
            
        # 2. 检查日志内容
        if check_log_for_errors(log_file):
            print(f"[Error] {step_name} finished but contains ERRORs.")
            archive_log(log_file, step_name)
            sys.exit(1)
            
        # 3. 归档成功日志
        archive_log(log_file, step_name)
        print(f"[Success] {step_name} completed successfully.")
        
    except Exception as e:
        print(f"[Error] Exception occurred during {step_name}: {str(e)}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="EDA Tool Flow Script")
    parser.add_argument("--top", required=True, help="Top module name")
    parser.add_argument("--rtl_list", required=True, help="RTL file list (.f file)")
    parser.add_argument("--syn", action="store_true", default=False, help="Execute Synthesis")
    parser.add_argument("--sim", action="store_true", default=False, help="Execute Simulation")
    
    args = parser.parse_args()

    # 步骤 1: Lint (始终执行或作为流程第一步)
    lint_log = "lint.log"
    lint_cmd = f"spyglass -run lint -top {args.top} -filelist {args.rtl_list} -log {lint_log}"
    run_command(lint_cmd, "lint", lint_log)

    # 步骤 2: 综合 (如果开启)
    if args.syn:
        syn_log = "syn.log"
        # 注意：dc_shell 通常需要通过环境变量或 -x 传递 top 和 rtl_list 参数给 TCL 脚本
        syn_cmd = f"dc_shell -f run_synthesis.tcl -x \"set top {args.top}; set rtl_list {args.rtl_list}\" -log {syn_log}"
        run_command(syn_cmd, "synthesis", syn_log)

    # 步骤 3: 仿真 (如果开启)
    if args.sim:
        sim_log = "sim.log"
        sim_cmd = f"vcs -f {args.rtl_list} -top {args.top} +define+SIM -l {sim_log}"
        run_command(sim_cmd, "simulation", sim_log)

    print("\n[All Done] Full flow finished without errors.")

if __name__ == "__main__":
    main()
```

### 脚本功能说明：

1.  **参数解析**：
    *   使用 `argparse` 库。`--syn` 和 `--sim` 是布尔标志（Flag），加上即为 `True`。
2.  **错误检查逻辑**：
    *   `check_log_for_errors` 函数通过正则表达式 `re.IGNORECASE` 搜索日志中的 "error" 关键字。
    *   如果命令本身的退出码（Return Code）非 0，也会直接判定为失败。
3.  **日志管理**：
    *   在每个步骤结束后，脚本会自动创建 `./logs/` 文件夹。
    *   文件名格式为 `步骤名_年月日_时分秒.log`（例如 `lint_20231027_103001.log`），防止多次运行的日志相互覆盖。
4.  **流程控制**：
    *   如果在任何一步检测到错误，脚本会调用 `sys.exit(1)` 立即终止，不会执行后续步骤。
5.  **DC Shell 命令优化**：
    *   在调用 `dc_shell` 时，我加入了 `-x` 参数。这允许将 Python 接收到的 `top` 和 `rtl_list` 变量传递给 TCL 环境，这样你的 `run_synthesis.tcl` 内部可以直接使用 `$top` 和 `$rtl_list` 变量。

### 如何使用：

1.  确保环境中有 `spyglass`, `dc_shell`, `vcs` 工具。
2.  赋予脚本执行权限：
    ```bash
    chmod +x run_flow.py
    ```
3.  运行示例：
    ```bash
    python run_flow.py --top top_module --rtl_list rtl.f --syn --sim
    ```
4.  运行后查看结果：
    *   如果成功，所有日志都在 `./logs/` 下。
    *   如果有错误，终端会打印错误行并停止运行。