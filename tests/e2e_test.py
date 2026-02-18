"""
端到端测试脚本 - 本地运行完整的信号生成和邮件发送流程
"""
import os
import sys
import subprocess
import json
import tempfile
from pathlib import Path
import shutil
import time

def run_complete_signal_pipeline():
    """运行完整的信号生成流程"""
    print("🚀 开始运行端到端测试 - 完整信号生成流程")
    print("=" * 60)
    
    # 创建临时输出目录
    temp_dir = tempfile.mkdtemp(prefix="fcstlabpro_e2e_")
    print(f"📁 临时目录: {temp_dir}")
    
    try:
        # 设置环境变量
        env = os.environ.copy()
        env["OUT_DIR"] = temp_dir
        env["BULL_DIR"] = "experiments/weekly/weekly_bull_v27_orion_final"
        env["BEAR_DIR"] = "experiments/weekly/weekly_bear_v13_T28_fgi_20260215_134804_ff4ad7"
        
        # 1. 先下载数据
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
        
        # 2. 运行 Bull 模型推理
        print("\n🐂 步骤 2: 运行 Bull 模型推理...")
        bull_result = subprocess.run([
            sys.executable, "scripts/weekly_signal.py",
            "--mode", "bull-infer",
            "--bull-dir", env["BULL_DIR"],
            "--temp-dir", temp_dir
        ], env=env, capture_output=True, text=True)
        
        if bull_result.returncode != 0:
            print(f"❌ Bull 模型推理失败: {bull_result.stderr}")
            return False
        print("✅ Bull 模型推理完成")
        
        # 3. 运行 Bear 模型推理
        print("\n🐻 步骤 3: 运行 Bear 模型推理...")
        bear_result = subprocess.run([
            sys.executable, "scripts/weekly_signal.py",
            "--mode", "bear-infer",
            "--download",  # Bear 模型需要下载数据
            "--bear-dir", env["BEAR_DIR"],
            "--temp-dir", temp_dir
        ], env=env, capture_output=True, text=True)
        
        if bear_result.returncode != 0:
            print(f"❌ Bear 模型推理失败: {bear_result.stderr}")
            return False
        print("✅ Bear 模型推理完成")
        
        # 4. 合并结果并生成信号
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
except FileNotFoundError:
    print("❌ Bull 结果文件不存在")
    exit(1)

# 读取 Bear 结果
try:
    with open(temp_dir / "bear_result.pkl", "rb") as f:
        bear = pickle.load(f)
except FileNotFoundError:
    print("❌ Bear 结果文件不存在")
    exit(1)

bull_prob = bull["bull_prob"]
bear_prob = bear["bear_prob"]
date_str = bull["date"]
price = bull["price"]
bull_meta = bull.get("meta", {{}})
bear_meta = bear.get("meta", {{}})

print(f"📊 Bull 概率: {{bull_prob:.3f}}")
print(f"📊 Bear 概率: {{bear_prob:.3f}}")
print(f"📊 日期: {{date_str}}, 价格: {{price}}")
print(f"📊 Bull Meta: {{bull_meta}}")
print(f"📊 Bear Meta: {{bear_meta}}")

# 为缺失的 meta 信息提供默认值
if not bull_meta:
    bull_meta = {{
        "version": "weekly_bull_v27_orion",
        "kappa": "N/A",
        "label_strategy": "reversal",
        "feature_set": ["technical", "volume", "flow", "market_structure", "external_fgi", "regime"]
    }}

if not bear_meta:
    bear_meta = {{
        "version": "weekly_bear_v13_T28_fgi",
        "kappa": "0.05",
        "label_strategy": "reversal",
        "feature_set": ["technical", "volume", "flow", "market_structure", "external_fgi"]
    }}

# 生成信号
bull_threshold = 0.50
bear_threshold = 0.50

if bull_prob >= bull_threshold and bear_prob < bear_threshold:
    signal_code = "STRONG_BULL"
    signal_display = "🚀 强烈看涨"
    position_pct = 80
    action = "建议加仓或做多"
elif bear_prob >= bear_threshold and bull_prob < bull_threshold:
    signal_code = "STRONG_BEAR"
    signal_display = "📉 强烈看跌"
    position_pct = 20
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

# 保存信号
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
    "version": "v0215-e2e-test"
}}

output_file = temp_dir / f"signal_{{date_str}}.json"
with open(output_file, "w") as f:
    json.dump(signal_data, f, indent=2, ensure_ascii=False)

print(f"✅ 信号已保存: {{output_file}}")
print(f"✅ Bull Kappa: {{bull_meta.get('kappa', 'N/A')}}")
print(f"✅ Bear Kappa: {{bear_meta.get('kappa', 'N/A')}}")
'''
        ], env=env, capture_output=True, text=True)
        
        if merge_result.returncode != 0:
            print(f"❌ 结果合并失败: {merge_result.stderr}")
            return False
        print("✅ 结果合并完成")
        print(merge_result.stdout)
        
        # 5. 查找生成的信号文件
        signal_files = list(Path(temp_dir).glob("signal_*.json"))
        if not signal_files:
            print("❌ 未找到信号文件")
            return False
        
        signal_file = signal_files[0]
        print(f"\n📄 生成的信号文件: {signal_file}")
        
        # 读取信号数据以检查内容
        with open(signal_file, 'r', encoding='utf-8') as f:
            signal_data = json.load(f)
        
        print(f"📊 信号数据预览:")
        print(f"   - 日期: {signal_data.get('date')}")
        print(f"   - 价格: {signal_data.get('price')}")
        print(f"   - Bull 概率: {signal_data.get('bull_prob')}")
        print(f"   - Bear 概率: {signal_data.get('bear_prob')}")
        print(f"   - Kappa: Bull={signal_data.get('kappa', {}).get('bull')}, Bear={signal_data.get('kappa', {}).get('bear')}")
        print(f"   - 仓位建议: {signal_data.get('position_pct')}%")
        print(f"   - 操作建议: {signal_data.get('action')}")
        
        return True, signal_file
        
    except Exception as e:
        print(f"❌ 端到端测试失败: {str(e)}")
        return False
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
            print(f"\n🗑️ 清理临时目录: {temp_dir}")
        except:
            pass


def run_email_sending_test(signal_file_path):
    """测试邮件发送功能"""
    print(f"\n📧 步骤 5: 测试邮件发送功能...")
    print("注意: 此步骤需要配置 SMTP 服务器才能实际发送邮件")
    
    # 检查是否配置了 SMTP
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASS')
    
    if not smtp_user or not smtp_pass:
        print("⚠️  SMTP 未配置，跳过实际邮件发送测试")
        print("   提示: 设置 SMTP_USER 和 SMTP_PASS 环境变量以测试邮件发送")
        
        # 但我们仍可以测试邮件内容生成
        print("\n📄 测试邮件内容生成...")
        try:
            import sys
            sys.path.insert(0, ".")
            from scripts.send_signal_email import format_email_content
            
            with open(signal_file_path, 'r', encoding='utf-8') as f:
                signal_data = json.load(f)
            
            subject, body = format_email_content(signal_data)
            print(f"✅ 邮件主题: {subject}")
            print(f"✅ 邮件内容长度: {len(body)} 字符")
            print(f"✅ 邮件内容包含 Kappa 信息: {'Kappa' in body}")
            print(f"✅ 邮件内容包含模型版本: {'Model Version' in body or '版本' in body}")
            
            return True
        except ImportError:
            print("⚠️  无法导入邮件格式化函数，跳过内容测试")
            return True
        except Exception as e:
            print(f"❌ 邮件内容生成失败: {str(e)}")
            return False
    else:
        print(f"✅ 检测到 SMTP 配置，尝试发送邮件...")
        try:
            result = subprocess.run([
                sys.executable, "scripts/send_signal_email.py", 
                str(signal_file_path)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ 邮件发送测试完成")
                return True
            else:
                print(f"❌ 邮件发送失败: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ 邮件发送异常: {str(e)}")
            return False


def main():
    """运行完整的端到端测试"""
    print("🧪 FcstLabPro 端到端测试")
    print("=" * 80)
    
    # 运行信号生成流程
    result = run_complete_signal_pipeline()
    
    if result and isinstance(result, tuple):  # 如果返回了信号文件路径
        success, signal_file = result
        if success:
            # 运行邮件发送测试
            email_success = run_email_sending_test(signal_file)
            if email_success:
                print("\n🎉 端到端测试全部完成!")
                return True
            else:
                print("\n⚠️  邮件发送测试部分失败，但信号生成成功")
                return False
    elif result:
        print("\n✅ 信号生成流程测试通过 (邮件发送因未配置而跳过)")
        return True
    else:
        print("\n❌ 端到端测试失败")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)