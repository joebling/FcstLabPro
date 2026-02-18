"""
简化版端到端测试 - 验证完整的信号生成流程
"""
import os
import sys
import subprocess
import json
import tempfile
from pathlib import Path
import shutil

def run_end_to_end_test():
    """运行端到端测试"""
    print("🚀 FcstLabPro 端到端测试")
    print("=" * 80)
    
    # 创建临时输出目录
    temp_dir = tempfile.mkdtemp(prefix="fcstlabpro_e2e_")
    print(f"📁 临时目录: {temp_dir}")
    
    try:
        # 设置环境变量
        env = os.environ.copy()
        env["OUT_DIR"] = temp_dir
        env["BULL_DIR"] = "experiments/weekly/weekly_bull_v27_orion_final"
        env["BEAR_DIR"] = "experiments/weekly/weekly_bear_v13_T28_fgi_20260215_134804_ff4ad7"
        
        print("\n📥 步骤 1: 下载最新数据...")
        download_result = subprocess.run([
            sys.executable, "-c", '''
import sys
sys.path.insert(0, ".")
from src.data.downloader import download_binance_klines
from pathlib import Path

# 创建数据目录
data_dir = Path("./data/raw")
data_dir.mkdir(parents=True, exist_ok=True)

# 下载数据
print("📥 下载 Binance BTCUSDT 日线数据...")
df = download_binance_klines(
    symbol="BTCUSDT",
    interval="1d",
    start="2020-01-01",
)
data_path = data_dir / "btc_binance_BTCUSDT_1d.csv"
df.to_csv(data_path)
print(f"✅ 数据已保存到: {data_path}")
'''
        ], env=env, capture_output=True, text=True)
        
        if download_result.returncode != 0:
            print(f"❌ 数据下载失败: {download_result.stderr}")
            return False
        print("✅ 数据下载完成")
        
        print("\n🐂 步骤 2: 运行 Bull 模型推理...")
        bull_result = subprocess.run([
            sys.executable, "scripts/weekly_signal.py",
            "--mode", "bull-infer",
            "--bull-dir", env["BULL_DIR"],
            "--temp-dir", temp_dir
        ], env=env, capture_output=True, text=True)
        
        if bull_result.returncode != 0:
            print(f"❌ Bull 模型推理失败:\n{bull_result.stderr}")
            return False
        print("✅ Bull 模型推理完成")
        print(f"   输出: {bull_result.stdout[-200:]}")  # 显示最后200个字符
        
        print("\n🐻 步骤 3: 运行 Bear 模型推理...")
        bear_result = subprocess.run([
            sys.executable, "scripts/weekly_signal.py",
            "--mode", "bear-infer",
            "--download",  # Bear 模型需要下载数据
            "--bear-dir", env["BEAR_DIR"],
            "--temp-dir", temp_dir
        ], env=env, capture_output=True, text=True)
        
        if bear_result.returncode != 0:
            print(f"❌ Bear 模型推理失败:\n{bear_result.stderr}")
            return False
        print("✅ Bear 模型推理完成")
        print(f"   输出: {bear_result.stdout[-200:]}")  # 显示最后200个字符
        
        print("\n🔗 步骤 4: 合并结果并生成信号...")
        merge_result = subprocess.run([
            sys.executable, "-c", f'''
import pickle
import json
from pathlib import Path

temp_dir = Path("{temp_dir}")

# 读取 Bull 结果
try:
    with open(temp_dir / "bull_result.pkl", "rb") as f:
        bull = pickle.load(f)
    print(f"📊 Bull 结果加载成功: {{bull}}")
except FileNotFoundError:
    print("❌ Bull 结果文件不存在")
    exit(1)

# 读取 Bear 结果
try:
    with open(temp_dir / "bear_result.pkl", "rb") as f:
        bear = pickle.load(f)
    print(f"📊 Bear 结果加载成功: {{bear}}")
except FileNotFoundError:
    print("❌ Bear 结果文件不存在")
    exit(1)

bull_prob = bull["bull_prob"]
bear_prob = bear["bear_prob"]
date_str = bull["date"]
price = bull["price"]
bull_meta = bull.get("meta", {{}})
bear_meta = bear.get("meta", {{}})

print(f"📈 Bull 概率: {{bull_prob:.3f}}")
print(f"📉 Bear 概率: {{bear_prob:.3f}}")
print(f"📅 日期: {{date_str}}")
print(f"💰 价格: {{price}}")
print(f"🔍 Bull Meta: {{bull_meta}}")
print(f"🔍 Bear Meta: {{bear_meta}}")

# 为缺失的 meta 信息提供默认值
if not bull_meta:
    bull_meta = {{
        "version": "weekly_bull_v27_orion",
        "kappa": "N/A",
        "label_strategy": "reversal",
        "feature_set": ["technical", "volume", "flow", "market_structure", "external_fgi", "regime"]
    }}
    print("⚠️  Bull Meta 为空，使用默认值")

if not bear_meta:
    bear_meta = {{
        "version": "weekly_bear_v13_T28_fgi",
        "kappa": "0.05",
        "label_strategy": "reversal",
        "feature_set": ["technical", "volume", "flow", "market_structure", "external_fgi"]
    }}
    print("⚠️  Bear Meta 为空，使用默认值")

# 生成信号
bull_threshold = 0.50
bear_threshold = 0.50

if bull_prob >= bull_threshold and bear_prob < bear_threshold:
    signal_code = "STRONG_BULL"
    signal_display = "🚀 强烈看涨"
    position_pct = min(int((bull_prob - 0.5) * 100), 100)
    action = "建议加仓或做多"
elif bear_prob >= bear_threshold and bull_prob < bull_threshold:
    signal_code = "STRONG_BEAR"
    signal_display = "📉 强烈看跌"
    position_pct = max(int((1 - bear_prob) * 100), 0)
    action = "建议减仓或做空"
elif bull_prob > bear_prob:
    signal_code = "BULL"
    signal_display = "↗️ 偏多震荡"
    position_pct = 60
    action = "持有观望，可小仓位做多"
elif bear_prob > bull_prob:
    signal_code = "BEAR"
    signal_display = "↘️ 偏空震荡"
    position_pct = 40
    action = "持有观望，可小仓位做空"
else:
    signal_code = "NEUTRAL"
    signal_display = "⏸️ 震荡"
    position_pct = 50
    action = "维持当前仓位，无需操作"

# 构建信号数据
signal_data = {{
    "date": date_str,
    "price": price,
    "signal": signal_code,
    "signal_display": signal_display,
    "bull_prob": bull_prob,
    "bear_prob": bear_prob,
    "position_pct": position_pct,
    "action": action,
    "model_version": {{
        "bull": bull_meta.get("version", "N/A"),
        "bear": bear_meta.get("version", "N/A")
    }},
    "kappa": {{
        "bull": bull_meta.get("kappa", "N/A"),
        "bear": bear_meta.get("kappa", "N/A")
    }},
    "label_strategy": {{
        "bull": bull_meta.get("label_strategy", "N/A"),
        "bear": bear_meta.get("label_strategy", "N/A")
    }},
    "feature_set": {{
        "bull": bull_meta.get("feature_set", []),
        "bear": bear_meta.get("feature_set", [])
    }},
    "llm_analysis": None,
    "version": "v0215-e2e-test"
}}

# 保存信号
output_file = temp_dir / f"signal_{{date_str}}.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(signal_data, f, indent=2, ensure_ascii=False)

print(f"✅ 信号已保存: {{output_file}}")
print(f"📊 Bull Kappa: {{bull_meta.get('kappa', 'N/A')}}")
print(f"📊 Bear Kappa: {{bear_meta.get('kappa', 'N/A')}}")

# 显示最终信号
print("\\n📋 最终信号摘要:")
print(f"   - 日期: {{signal_data['date']}}")
print(f"   - 价格: ${{signal_data['price']}}")
print(f"   - 信号: {{signal_data['signal_display']}}")
print(f"   - Bull概率: {{signal_data['bull_prob']:.2%}}")
print(f"   - Bear概率: {{signal_data['bear_prob']:.2%}}")
print(f"   - Kappa: Bull={{signal_data['kappa']['bull']}}, Bear={{signal_data['kappa']['bear']}}")
print(f"   - 仓位: {{signal_data['position_pct']}}%")
print(f"   - 操作: {{signal_data['action']}}")
'''
        ], env=env, capture_output=True, text=True)
        
        if merge_result.returncode != 0:
            print(f"❌ 结果合并失败: {merge_result.stderr}")
            return False
        print("✅ 结果合并完成")
        print(merge_result.stdout)
        
        # 查找生成的信号文件
        signal_files = list(Path(temp_dir).glob("signal_*.json"))
        if not signal_files:
            print("❌ 未找到信号文件")
            return False
        
        signal_file = signal_files[0]
        print(f"\n📄 生成的信号文件: {signal_file}")
        
        # 读取并显示信号数据
        with open(signal_file, 'r', encoding='utf-8') as f:
            signal_data = json.load(f)
        
        print(f"\n✅ 端到端测试成功完成!")
        print(f"✅ 信号数据已生成并保存到: {signal_file}")
        print(f"✅ Bull Kappa: {signal_data['kappa']['bull']}")
        print(f"✅ Bear Kappa: {signal_data['kappa']['bear']}")
        
        return True, signal_file
        
    except Exception as e:
        print(f"❌ 端到端测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
            print(f"\n🗑️ 清理临时目录: {temp_dir}")
        except:
            pass


def test_manual_email_sending(signal_file_path):
    """指导用户如何手动测试邮件发送"""
    print(f"\n📧 邮件发送测试指南")
    print("=" * 50)
    print(f"要测试实际邮件发送，请按以下步骤操作:")
    print(f"1. 设置 SMTP 环境变量:")
    print(f"   export SMTP_HOST=smtp.gmail.com  # 或 smtp.qq.com")
    print(f"   export SMTP_PORT=587")
    print(f"   export SMTP_USER=your_email@gmail.com")
    print(f"   export SMTP_PASS=your_app_password")
    print(f"   export MAIL_TO=recipient@example.com")
    print(f"")
    print(f"2. 运行邮件发送脚本:")
    print(f"   python scripts/send_signal_email.py {signal_file_path}")
    print(f"")
    print(f"3. 或者，您也可以使用以下命令测试邮件功能:")
    print(f"   source venv_py310/bin/activate && SMTP_USER=test@demo.com SMTP_PASS=dummy python scripts/send_signal_email.py {signal_file_path}")


def main():
    """主函数"""
    result = run_end_to_end_test()
    
    if result and isinstance(result, tuple):
        success, signal_file = result
        if success:
            test_manual_email_sending(signal_file)
            return True
    elif result:
        test_manual_email_sending("PATH_TO_YOUR_SIGNAL_FILE.json")
        return True
    
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)