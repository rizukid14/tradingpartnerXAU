import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH_DIR = os.path.join(BASE_DIR, "scratch")
DOCS_DIR = os.path.join(BASE_DIR, "docs")

def organize_docs():
    print("[*] Merapikan folder docs/...")
    arch_dir = os.path.join(DOCS_DIR, "architecture")
    os.makedirs(arch_dir, exist_ok=True)
    
    files_to_move = [
        ("FULL_PROMPT_SAMPLE_M30.md", arch_dir),
        ("PROMPT_SPECIFICATION_V2.md", arch_dir),
    ]
    for filename, target_dir in files_to_move:
        src = os.path.join(DOCS_DIR, filename)
        dst = os.path.join(target_dir, filename)
        if os.path.exists(src):
            shutil.move(src, dst)
            print(f"  -> Dipindahkan: docs/{filename} -> docs/architecture/{filename}")

def organize_scratch():
    print("[*] Merapikan folder scratch/...")
    backtests_dir = os.path.join(SCRATCH_DIR, "backtests")
    quick_tests_dir = os.path.join(SCRATCH_DIR, "quick_tests")
    research_tools_dir = os.path.join(SCRATCH_DIR, "research_tools")
    csv_outputs_dir = os.path.join(SCRATCH_DIR, "csv_outputs")

    for d in [backtests_dir, quick_tests_dir, research_tools_dir, csv_outputs_dir]:
        os.makedirs(d, exist_ok=True)

    items = os.listdir(SCRATCH_DIR)
    for item in items:
        item_path = os.path.join(SCRATCH_DIR, item)
        if os.path.isdir(item_path):
            continue  # Skip subfolders

        # 1. CSV Output files
        if item.endswith(".csv"):
            shutil.move(item_path, os.path.join(csv_outputs_dir, item))
            print(f"  -> CSV Output: {item} -> scratch/csv_outputs/")

        # 2. Backtest Runners
        elif (item.startswith("backtest_") or 
              item.startswith("run_") or 
              "backtest" in item or 
              item in ["xau_m30_strategies.py", "compare_breakout_vs_retest.py", "compare_csm_boitoki_vs_atr.py"]):
            shutil.move(item_path, os.path.join(backtests_dir, item))
            print(f"  -> Backtest: {item} -> scratch/backtests/")

        # 3. Quick Tests & Inspection
        elif (item.startswith("test_") or 
              item.startswith("inspect_") or 
              item.startswith("smoke_") or 
              item.startswith("check_") or 
              item.startswith("verify_") or 
              item.startswith("print_") or
              item in ["find_dry.py", "cancel_pending.py", "diagnose_funnel.py", "_count_ai.py", "benchmark_macro.py"]):
            shutil.move(item_path, os.path.join(quick_tests_dir, item))
            print(f"  -> Quick Test: {item} -> scratch/quick_tests/")

        # 4. Research Tools & Miners
        elif (item.startswith("download_") or 
              item.startswith("pattern_") or 
              item.startswith("harmonic_") or 
              "research" in item or 
              item in ["build_whispers.py", "filter_whispers.py", "gen_registry.py", "stat_lib.py", "rank_pairs.py"]):
            shutil.move(item_path, os.path.join(research_tools_dir, item))
            print(f"  -> Research Tool: {item} -> scratch/research_tools/")

def main():
    organize_docs()
    organize_scratch()
    print("\n[+] Perapihan folder selesai dengan sukses!")

if __name__ == "__main__":
    main()
