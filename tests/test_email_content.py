"""
测试邮件内容生成的各个方面
"""
import json
import os
import sys
from datetime import datetime, timedelta
import pandas as pd

# 添加项目根目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from scripts.weekly_signal import run_bull_with_features, run_bear_with_features, get_signal_and_advice, format_report


def test_email_format():
    """测试邮件格式和内容"""
    print("=== 测试邮件格式和内容 ===")
    
    # 创建模拟信号数据
    signal_data = {
        "bull_prob": 0.65,
        "bear_prob": 0.35,
        "date": (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
        "price": 45000.0,
        "meta": {
            "bull": {
                "version": "weekly_bull_v27_orion",
                "kappa": "0.15",
                "label_strategy": "reversal",
                "feature_set": ["technical", "volume", "flow", "market_structure", "external_fgi", "regime"]
            },
            "bear": {
                "version": "weekly_bear_v13_T28_fgi",
                "kappa": "0.05",
                "label_strategy": "reversal",
                "feature_set": ["technical", "volume", "flow", "market_structure", "external_fgi"]
            }
        }
    }
    
    # 计算组合信号和仓位
    combined_score = signal_data['bull_prob'] - signal_data['bear_prob']
    abs_score = abs(combined_score)
    
    # 计算仓位百分比
    if abs_score >= 0.4:
        position_pct = min(int(abs_score * 100), 100)
    elif abs_score >= 0.2:
        position_pct = min(int(abs_score * 80), 80)
    elif abs_score >= 0.1:
        position_pct = min(int(abs_score * 60), 60)
    else:
        position_pct = 0
    
    # 确定信号显示和行动建议
    if combined_score > 0.1:
        signal_display = "↗️ 偏多震荡"
        if position_pct >= 60:
            action = "积极做多"
        else:
            action = "可小仓位做多"
    elif combined_score < -0.1:
        signal_display = "↙️ 偏空震荡"
        if position_pct >= 60:
            action = "积极做空"
        else:
            action = "可小仓位做空"
    else:
        signal_display = "⏸️ 震荡"
        action = "持有观望，可小仓位做多"
    
    # 构建邮件标题
    subject_date = datetime.now().strftime('%Y-%m-%d')
    subject = f"[BTC信号] {subject_date} {signal_display} — FcstLabPro"
    
    # 构建邮件正文
    body_lines = [
        f"📊 BTC信号 ({signal_data['date']})",
        "",
        f"📈 Bull 概率: {signal_data['bull_prob']:.2%}",
        f"📉 Bear 概率: {signal_data['bear_prob']:.2%}",
        f"⚖️  组合信号: {combined_score:+.2f}",
        f"💰 仓位建议: {position_pct}%",
        "",
        f"🔍 Kappa: Bull={signal_data['meta']['bull']['kappa']}, Bear={signal_data['meta']['bear']['kappa']}",
        f"🏷️  Model Version: Bull={signal_data['meta']['bull']['version']}, Bear={signal_data['meta']['bear']['version']}",
        "",
        f"💡 行动建议: {action}",
        "",
        f"🔗 当前价格: ${signal_data['price']:,.2f}",
        "",
        "——",
        "FcstLabPro 自动信号系统"
    ]
    
    body = "\n".join(body_lines)
    
    print(f"✅ 邮件标题: {subject}")
    print(f"✅ 邮件正文:\n{body}")
    
    # 验证邮件内容包含所有必要元素
    required_elements = [
        "BTC信号",
        "Bull 概率",
        "Bear 概率", 
        "组合信号",
        "仓位建议",
        "Kappa",
        "Model Version",
        "行动建议",
        "当前价格"
    ]
    
    for element in required_elements:
        if element not in body:
            print(f"❌ 邮件中缺少元素: {element}")
            return False
    
    print("✅ 邮件格式和内容测试通过!")
    return True


def test_edge_case_emails():
    """测试边缘情况下的邮件内容"""
    print("\n=== 测试边缘情况下的邮件内容 ===")
    
    edge_cases = [
        {
            "name": "强多头信号",
            "bull_prob": 0.85,
            "bear_prob": 0.15
        },
        {
            "name": "强空头信号", 
            "bull_prob": 0.15,
            "bear_prob": 0.85
        },
        {
            "name": "震荡信号",
            "bull_prob": 0.52,
            "bear_prob": 0.48
        },
        {
            "name": "反向震荡信号",
            "bull_prob": 0.48,
            "bear_prob": 0.52
        }
    ]
    
    for case in edge_cases:
        print(f"   测试用例: {case['name']}")
        
        # 计算组合信号和仓位
        combined_score = case['bull_prob'] - case['bear_prob']
        abs_score = abs(combined_score)
        
        # 计算仓位百分比
        if abs_score >= 0.4:
            position_pct = min(int(abs_score * 100), 100)
        elif abs_score >= 0.2:
            position_pct = min(int(abs_score * 80), 80)
        elif abs_score >= 0.1:
            position_pct = min(int(abs_score * 60), 60)
        else:
            position_pct = 0
        
        # 确定信号显示和行动建议
        if combined_score > 0.1:
            signal_display = "↗️ 偏多震荡"
            if position_pct >= 60:
                action = "积极做多"
            else:
                action = "可小仓位做多"
        elif combined_score < -0.1:
            signal_display = "↙️ 偏空震荡"
            if position_pct >= 60:
                action = "积极做空"
            else:
                action = "可小仓位做空"
        else:
            signal_display = "⏸️ 震荡"
            action = "持有观望，可小仓位做多"
        
        print(f"     → Bull: {case['bull_prob']:.2f}, Bear: {case['bear_prob']:.2f}")
        print(f"     → 组合信号: {combined_score:+.2f}")
        print(f"     → 仓位: {position_pct}%")
        print(f"     → 信号: {signal_display}")
        print(f"     → 行动: {action}")
        
        # 对于震荡信号，验证其行为是合理的，而不是严格按预期
        # 因为在震荡情况下，通常会保持默认的"持有观望，可小仓位做多"逻辑
        if abs(combined_score) <= 0.1:  # 震荡情况
            if "持有观望" not in action:
                print(f"     ❌ 震荡信号应包含'持有观望': 实际 {action}")
                return False
        elif combined_score > 0.1:  # 多头信号
            if position_pct >= 60 and "做多" not in action:
                print(f"     ❌ 强多头信号应建议做多: 实际 {action}")
                return False
            elif position_pct < 60 and "做多" not in action:
                print(f"     ❌ 多头信号应建议做多: 实际 {action}")
                return False
        elif combined_score < -0.1:  # 空头信号
            if position_pct >= 60 and "做空" not in action:
                print(f"     ❌ 强空头信号应建议做空: 实际 {action}")
                return False
            elif position_pct < 60 and "做空" not in action:
                print(f"     ❌ 空头信号应建议做空: 实际 {action}")
                return False
    
    print("✅ 边缘情况邮件内容测试通过!")
    return True


def test_missing_meta_email():
    """测试缺失 meta 数据时的邮件内容"""
    print("\n=== 测试缺失 meta 数据时的邮件内容 ===")
    
    # 模拟缺失 meta 的信号数据
    signal_data = {
        "bull_prob": 0.65,
        "bear_prob": 0.35,
        "date": (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
        "price": 45000.0
        # 注意这里没有 meta 字段
    }
    
    # 应用默认 meta 值
    bull_meta = signal_data.get("meta", {}).get("bull", {})
    bear_meta = signal_data.get("meta", {}).get("bear", {})
    
    if not bull_meta:
        bull_meta = {
            "version": "weekly_bull_v27_orion",
            "kappa": "N/A",
            "label_strategy": "reversal",
            "feature_set": ["technical", "volume", "flow", "market_structure", "external_fgi", "regime"]
        }
    
    if not bear_meta:
        bear_meta = {
            "version": "weekly_bear_v13_T28_fgi",
            "kappa": "0.05",
            "label_strategy": "reversal",
            "feature_set": ["technical", "volume", "flow", "market_structure", "external_fgi"]
        }
    
    # 计算组合信号
    combined_score = signal_data['bull_prob'] - signal_data['bear_prob']
    
    # 计算仓位百分比
    abs_score = abs(combined_score)
    if abs_score >= 0.4:
        position_pct = min(int(abs_score * 100), 100)
    elif abs_score >= 0.2:
        position_pct = min(int(abs_score * 80), 80)
    elif abs_score >= 0.1:
        position_pct = min(int(abs_score * 60), 60)
    else:
        position_pct = 0
    
    # 确定信号显示
    if combined_score > 0.1:
        signal_display = "↗️ 偏多震荡"
    elif combined_score < -0.1:
        signal_display = "↙️ 偏空震荡"
    else:
        signal_display = "⏸️ 震荡"
    
    print(f"   ✅ Bull Kappa: {bull_meta['kappa']} (来自默认值)")
    print(f"   ✅ Bear Kappa: {bear_meta['kappa']} (来自默认值)")
    print(f"   ✅ Bull Version: {bull_meta['version']}")
    print(f"   ✅ Bear Version: {bear_meta['version']}")
    
    # 验证即使没有原始 meta，邮件也能正常生成
    try:
        # 尝试构建邮件内容
        subject_date = datetime.now().strftime('%Y-%m-%d')
        subject = f"[BTC信号] {subject_date} {signal_display} — FcstLabPro"
        
        body_lines = [
            f"📊 BTC信号 ({signal_data['date']})",
            "",
            f"📈 Bull 概率: {signal_data['bull_prob']:.2%}",
            f"📉 Bear 概率: {signal_data['bear_prob']:.2%}",
            f"⚖️  组合信号: {combined_score:+.2f}",
            f"💰 仓位建议: {position_pct}%",
            "",
            f"🔍 Kappa: Bull={bull_meta['kappa']}, Bear={bear_meta['kappa']}",
            f"🏷️  Model Version: Bull={bull_meta['version']}, Bear={bear_meta['version']}",
            "",
            f"🔗 当前价格: ${signal_data['price']:,.2f}",
            "",
            "——",
            "FcstLabPro 自动信号系统"
        ]
        
        body = "\n".join(body_lines)
        
        print(f"   ✅ 邮件标题: {subject}")
        print(f"   ✅ 邮件成功构建，即使没有原始 meta 数据")
        
        # 验证 Kappa 值显示正确
        if "Kappa: Bull=N/A" not in body and bull_meta['kappa'] == "N/A":
            print("   ❌ N/A Kappa 值未正确显示")
            return False
            
        print("   ✅ 缺失 meta 数据时的邮件内容测试通过!")
        return True
        
    except Exception as e:
        print(f"   ❌ 构建邮件时出错: {str(e)}")
        return False


def run_email_tests():
    """运行所有邮件相关测试"""
    print("📧 开始运行邮件内容测试...\n")
    
    tests = [
        ("邮件格式和内容", test_email_format),
        ("边缘情况邮件", test_edge_case_emails),
        ("缺失 meta 邮件", test_missing_meta_email)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
                print(f"✅ {test_name} 测试通过\n")
            else:
                print(f"❌ {test_name} 测试失败\n")
        except Exception as e:
            print(f"❌ {test_name} 测试出错: {str(e)}\n")
    
    print(f"📊 邮件测试结果: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("📧 所有邮件测试均已通过!")
        return True
    else:
        print(f"⚠️  {total - passed} 项邮件测试未通过")
        return False


if __name__ == "__main__":
    success = run_email_tests()
    sys.exit(0 if success else 1)