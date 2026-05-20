python
import re
import json
import os

def parse_sim_log(log_path: str) -> list:
    """
    解析仿真日志，提取测试结果。
    支持 VCS/Xcelium 格式及单个文件中包含多个测试用例的情况。
    """
    if not os.path.exists(log_path):
        print(f"Error: File {log_path} not found.")
        return []

    with open(log_path, 'r') as f:
        content = f.read()

    # 使用大量的等号作为分隔符切分不同的测试块
    # 允许处理一个 log 文件里有多个 ============ 隔开的任务
    test_blocks = re.split(r'={40,}', content)
    
    results = []

    # 定义各个字段的正则表达式
    patterns = {
        "test_name": r"Test:\s+(\S+)",
        "seed": r"Seed:\s+(\d+)",
        "start_time": r"Start time:\s+(.*)",
        "summary": r"Summary:\s+(\d+)\s+error[s]?,\s+(\d+)\s+warning[s]?,\s+(\d+)\s+fatal[s]?",
        # 兼容 VCS (Simulation PASSED) 和 Xcelium (TEST PASSED)
        "result": r"(?:Simulation|TEST)\s+(PASSED|FAILED)",
        "elapsed_time": r"Elapsed time:\s+([\d\.]+)\s+seconds"
    }

    for block in test_blocks:
        block = block.strip()
        if not block:
            continue
            
        # 提取基本信息
        test_name_match = re.search(patterns["test_name"], block)
        if not test_name_match:
            continue # 如果连 test_name 都没找到，说明不是有效的测试块
            
        res_dict = {
            "test_name": test_name_match.group(1),
            "seed": None,
            "start_time": None,
            "error_count": 0,
            "warning_count": 0,
            "fatal_count": 0,
            "result": None,
            "elapsed_time_sec": 0.0
        }

        # 解析 Seed
        seed_match = re.search(patterns["seed"], block)
        if seed_match: res_dict["seed"] = int(seed_match.group(1))

        # 解析 Start Time
        st_match = re.search(patterns["start_time"], block)
        if st_match: res_dict["start_time"] = st_match.group(1).strip()

        # 解析 Summary (Errors, Warnings, Fatals)
        summary_match = re.search(patterns["summary"], block)
        if summary_match:
            res_dict["error_count"] = int(summary_match.group(1))
            res_dict["warning_count"] = int(summary_match.group(2))
            res_dict["fatal_count"] = int(summary_match.group(3))

        # 解析 Result
        result_match = re.search(patterns["result"], block)
        if result_match:
            res_dict["result"] = result_match.group(1).upper()
        else:
            # 策略：如果没有明确 PASSED/FAILED，则根据 error/fatal 计数判断
            if res_dict["error_count"] > 0 or res_dict["fatal_count"] > 0:
                res_dict["result"] = "FAILED"
            else:
                res_dict["result"] = "PASS_BY_LOG_CHECK" # 或者默认为 PASS

        # 解析 Elapsed Time
        time_match = re.search(patterns["elapsed_time"], block)
        if time_match: res_dict["elapsed_time_sec"] = float(time_match.group(1))

        results.append(res_dict)

    return results

def save_to_json(data, output_file):
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    print(f"Results saved to {output_file}")

# --- 测试代码 ---
if __name__ == "__main__":
    # 模拟生成的 log 内容
    sample_log = "sim_result.log"
    with open(sample_log, "w") as f:
        f.write("""
================================================
Test: test_apb_write_001
Seed: 98765
Start time: 2025-01-15 10:23:45
------------------------------------------------
UVM_ERROR @ 400 ns: scoreboard [DATA_MISMATCH] Expected 0xAB, got 0xCD
------------------------------------------------
Summary: 1 error, 1 warning, 0 fatal
Simulation FAILED
Elapsed time: 1.23 seconds
================================================
Test: test_apb_read_002
Seed: 11223
Start time: 2025-01-15 11:00:00
------------------------------------------------
Summary: 0 error, 0 warning, 0 fatal
TEST PASSED
Elapsed time: 0.95 seconds
================================================
""")

    # 执行解析
    parsed_data = parse_sim_log(sample_log)
    
    # 输出到 JSON
    save_to_json(parsed_data, "simulation_results.json")
    
    # 打印查看
    for entry in parsed_data:
        print(f"Test: {entry['test_name']} | Result: {entry['result']} | Errors: {entry['error_count']}")