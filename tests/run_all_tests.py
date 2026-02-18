#!/usr/bin/env python3
"""
FcstLabPro 测试运行器
运行所有测试以验证推理流程和邮件内容
"""
import subprocess
import sys
import os

def run_test_script(script_name, description):
    """运行单个测试脚本"""
    print(f"\n🧪 运行 {description}: {script_name}")
    print("-" * 60)
    
    result = subprocess.run([
        sys.executable, 
        os.path.join("tests", script_name)
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ {script_name} - 通过")
        return True
    else:
        print(f"❌ {script_name} - 失败")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        return False

def main():
    """运行所有测试"""
    print("🚀 开始运行 FcstLabPro 完整测试套件")
    print("=" * 60)
    
    tests = [
        ("test_inference_pipeline.py", "推理流程测试"),
        ("test_email_content.py", "邮件内容测试")
    ]
    
    passed = 0
    total = len(tests)
    
    for script_name, description in tests:
        if run_test_script(script_name, description):
            passed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 测试汇总: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("🎉 所有测试均已通过！")
        return 0
    else:
        print(f"⚠️  {total - passed} 项测试未通过")
        return 1

if __name__ == "__main__":
    sys.exit(main())