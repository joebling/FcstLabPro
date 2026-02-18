#!/usr/bin/env python3
"""
信号策略回测实验
测试3个优化点：
1. 降低阈值（0.50 → 0.40/0.35）
2. 更细粒度的信号（偏多震荡/偏空震荡）
3. 更灵活的仓位调整（震荡市也微调）
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_orion_predictions():
    """加载 Orion-BiX 预测结果"""
    csv_path = PROJECT_ROOT / "experiments/weekly/weekly_bull_v27_orion_20260215_211945.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"预测文件不存在: {csv_path}")
    return pd.read_csv(csv_path)


def load_prices():
    """加载价格数据"""
    prices_path = PROJECT_ROOT / "data/raw/btc_binance_BTCUSDT_1d.csv"
    if not prices_path.exists():
        raise FileNotFoundError(f"价格文件不存在: {prices_path}")
    df = pd.read_csv(prices_path)
    df['timestamp'] = pd.to_datetime(df['date'])
    return df


class SignalStrategy:
    """信号策略基类"""
    
    def __init__(self, name, bull_threshold=0.50, bear_threshold=0.50):
        self.name = name
        self.bull_threshold = bull_threshold
        self.bear_threshold = bear_threshold
    
    def get_signal(self, bull_prob, bear_prob):
        """获取信号代码"""
        raise NotImplementedError
    
    def get_position(self, signal_code, bull_prob, bear_prob):
        """获取仓位建议"""
        raise NotImplementedError


class StrategyV0_Original(SignalStrategy):
    """原始策略（当前使用）"""
    
    def __init__(self):
        super().__init__("v0_original", bull_threshold=0.50, bear_threshold=0.50)
    
    def get_signal(self, bull_prob, bear_prob):
        bull_on = bull_prob >= self.bull_threshold
        bear_on = bear_prob >= self.bear_threshold
        
        if bull_on and not bear_on:
            return "BULL"
        elif not bull_on and bear_on:
            return "BEAR"
        elif not bull_on and not bear_on:
            return "NEUTRAL"
        else:
            return "VOLATILE"
    
    def get_position(self, signal_code, bull_prob, bear_prob):
        base = 50
        if signal_code == "BULL":
            return min(70, base + 20)
        elif signal_code == "BEAR":
            return max(20, base - 30)
        elif signal_code == "NEUTRAL":
            return base
        else:  # VOLATILE
            return max(30, base - 15)


class StrategyV1_LowerThreshold(SignalStrategy):
    """策略1：降低阈值"""
    
    def __init__(self):
        super().__init__("v1_lower_threshold", bull_threshold=0.40, bear_threshold=0.35)
    
    def get_signal(self, bull_prob, bear_prob):
        bull_on = bull_prob >= self.bull_threshold
        bear_on = bear_prob >= self.bear_threshold
        
        if bull_on and not bear_on:
            return "BULL"
        elif not bull_on and bear_on:
            return "BEAR"
        elif not bull_on and not bear_on:
            return "NEUTRAL"
        else:
            return "VOLATILE"
    
    def get_position(self, signal_code, bull_prob, bear_prob):
        base = 50
        if signal_code == "BULL":
            strength = max(0, (bull_prob - 0.40) / 0.20)
            return min(70, base + int(strength * 20))
        elif signal_code == "BEAR":
            strength = max(0, (bear_prob - 0.35) / 0.20)
            return max(20, base - int(strength * 30))
        elif signal_code == "NEUTRAL":
            return base
        else:  # VOLATILE
            return max(30, base - 15)


class StrategyV2_GranularSignals(SignalStrategy):
    """策略2：更细粒度的信号（偏多震荡/偏空震荡）"""
    
    def __init__(self):
        super().__init__("v2_granular_signals", bull_threshold=0.50, bear_threshold=0.50)
    
    def get_signal(self, bull_prob, bear_prob):
        bull_on = bull_prob >= self.bull_threshold
        bear_on = bear_prob >= self.bear_threshold
        
        if bull_on and not bear_on:
            return "BULL"
        elif not bull_on and bear_on:
            return "BEAR"
        elif not bull_on and not bear_on:
            # 细粒度震荡信号
            if bull_prob > bear_prob:
                return "NEUTRAL_BULLISH"
            else:
                return "NEUTRAL_BEARISH"
        else:
            return "VOLATILE"
    
    def get_position(self, signal_code, bull_prob, bear_prob):
        base = 50
        if signal_code == "BULL":
            return min(70, base + 20)
        elif signal_code == "BEAR":
            return max(20, base - 30)
        elif signal_code == "NEUTRAL_BULLISH":
            return min(55, base + 5)
        elif signal_code == "NEUTRAL_BEARISH":
            return max(45, base - 5)
        else:  # VOLATILE
            return max(30, base - 15)


class StrategyV3_FlexiblePosition(SignalStrategy):
    """策略3：更灵活的仓位调整（震荡市也根据概率微调）"""
    
    def __init__(self):
        super().__init__("v3_flexible_position", bull_threshold=0.50, bear_threshold=0.50)
    
    def get_signal(self, bull_prob, bear_prob):
        bull_on = bull_prob >= self.bull_threshold
        bear_on = bear_prob >= self.bear_threshold
        
        if bull_on and not bear_on:
            return "BULL"
        elif not bull_on and bear_on:
            return "BEAR"
        elif not bull_on and not bear_on:
            return "NEUTRAL"
        else:
            return "VOLATILE"
    
    def get_position(self, signal_code, bull_prob, bear_prob):
        base = 50
        if signal_code == "BULL":
            strength = max(0, (bull_prob - 0.40) / 0.30)
            return min(70, base + int(strength * 20))
        elif signal_code == "BEAR":
            strength = max(0, (bear_prob - 0.35) / 0.30)
            return max(20, base - int(strength * 30))
        elif signal_code == "NEUTRAL":
            # 震荡市根据概率偏向微调
            diff = bull_prob - bear_prob
            adjustment = int(np.clip(diff * 100, -10, 10))
            return np.clip(base + adjustment, 40, 60)
        else:  # VOLATILE
            return max(30, base - 15)


class StrategyV4_AllOptimizations(SignalStrategy):
    """策略4：所有优化结合"""
    
    def __init__(self):
        super().__init__("v4_all_optimizations", bull_threshold=0.40, bear_threshold=0.35)
    
    def get_signal(self, bull_prob, bear_prob):
        bull_on = bull_prob >= self.bull_threshold
        bear_on = bear_prob >= self.bear_threshold
        
        if bull_on and not bear_on:
            return "BULL"
        elif not bull_on and bear_on:
            return "BEAR"
        elif not bull_on and not bear_on:
            if bull_prob > bear_prob:
                return "NEUTRAL_BULLISH"
            else:
                return "NEUTRAL_BEARISH"
        else:
            return "VOLATILE"
    
    def get_position(self, signal_code, bull_prob, bear_prob):
        base = 50
        if signal_code == "BULL":
            strength = max(0, (bull_prob - 0.40) / 0.20)
            return min(70, base + int(strength * 20))
        elif signal_code == "BEAR":
            strength = max(0, (bear_prob - 0.35) / 0.20)
            return max(20, base - int(strength * 30))
        elif signal_code == "NEUTRAL_BULLISH":
            diff = bull_prob - bear_prob
            adjustment = int(np.clip(diff * 100, 0, 10))
            return np.clip(base + adjustment, 50, 60)
        elif signal_code == "NEUTRAL_BEARISH":
            diff = bear_prob - bull_prob
            adjustment = int(np.clip(diff * 100, 0, 10))
            return np.clip(base - adjustment, 40, 50)
        else:  # VOLATILE
            return max(30, base - 15)


def backtest_strategy(strategy, predictions_df, prices_df, initial_capital=10000, transaction_cost=0.001):
    """回测单个策略"""
    results = []
    capital = initial_capital
    position_pct = 50  # 初始仓位
    current_position = 0  # 0: 空仓, 1: 满仓 (简化版)
    
    for _, row in predictions_df.iterrows():
        train_end = int(row['train_end'])
        kappa = row.get('kappa', 0)
        
        # 使用 kappa 模拟概率：kappa > 0 表示有正收益
        # kappa 范围大致映射到 0.3-0.7 区间
        bull_prob = np.clip(0.5 + kappa * 0.2, 0.3, 0.7)
        bear_prob = np.clip(0.5 - kappa * 0.1, 0.2, 0.6)
        
        # 下一个 OOS 窗口 (假设 63 天)
        test_start = train_end
        test_end = min(train_end + 63, len(prices_df))
        
        if test_end <= test_start:
            continue
        
        # 获取测试期价格
        test_prices = prices_df.iloc[test_start:test_end]['close'].values
        
        if len(test_prices) < 10:
            continue
        
        # 计算策略信号和仓位
        signal_code = strategy.get_signal(bull_prob, bear_prob)
        target_position = strategy.get_position(signal_code, bull_prob, bear_prob)
        
        # 简化回测：假设仓位是0-100%，每天根据仓位调整
        daily_returns = []
        for i in range(1, len(test_prices)):
            price_ret = (test_prices[i] - test_prices[i-1]) / test_prices[i-1]
            # 仓位收益 = 价格收益 * 仓位比例
            position_ret = price_ret * (target_position / 100)
            # 扣除交易成本（如果仓位变化）
            if i == 1 and target_position != position_pct:
                position_ret -= transaction_cost * abs(target_position - position_pct) / 100
            daily_returns.append(position_ret)
        
        # 更新仓位
        position_pct = target_position
        
        # 计算累积收益
        cumulative = np.cumprod([1 + r for r in daily_returns])
        total_return = cumulative[-1] - 1
        
        # 最大回撤
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0
        
        # 夏普比率
        avg_daily = np.mean(daily_returns)
        std_daily = np.std(daily_returns)
        sharpe = avg_daily / (std_daily + 1e-10) * np.sqrt(252) if std_daily > 0 else 0
        
        results.append({
            'train_end': train_end,
            'kappa': kappa,
            'bull_prob': bull_prob,
            'bear_prob': bear_prob,
            'signal': signal_code,
            'position': target_position,
            'total_return': total_return,
            'max_drawdown': max_drawdown,
            'sharpe': sharpe,
            'n_days': len(daily_returns),
        })
    
    return pd.DataFrame(results)


def analyze_backtest_results(strategy_name, backtest_df):
    """分析回测结果"""
    if len(backtest_df) == 0:
        return None
    
    # 汇总统计
    total_return = (1 + backtest_df['total_return']).prod() - 1
    annual_return = (1 + total_return) ** (252 / backtest_df['n_days'].sum()) - 1
    avg_drawdown = backtest_df['max_drawdown'].mean()
    max_drawdown = backtest_df['max_drawdown'].max()
    avg_sharpe = backtest_df['sharpe'].mean()
    
    # 卡玛比率
    calmar = annual_return / (avg_drawdown + 1e-10) if avg_drawdown > 0 else 0
    
    # 信号分布
    signal_counts = backtest_df['signal'].value_counts().to_dict()
    
    return {
        'strategy': strategy_name,
        'total_return': total_return,
        'annual_return': annual_return,
        'avg_drawdown': avg_drawdown,
        'max_drawdown': max_drawdown,
        'avg_sharpe': avg_sharpe,
        'calmar_ratio': calmar,
        'n_folds': len(backtest_df),
        'signal_distribution': signal_counts,
    }


def main():
    """主函数：运行所有策略回测"""
    print("=" * 80)
    print("信号策略回测实验")
    print("=" * 80)
    
    # 加载数据
    print("\n📥 加载数据...")
    predictions_df = load_orion_predictions()
    prices_df = load_prices()
    print(f"   预测数据: {len(predictions_df)} 个fold")
    print(f"   价格数据: {len(prices_df)} 天")
    
    # 定义策略
    strategies = [
        StrategyV0_Original(),
        StrategyV1_LowerThreshold(),
        StrategyV2_GranularSignals(),
        StrategyV3_FlexiblePosition(),
        StrategyV4_AllOptimizations(),
    ]
    
    # 运行回测
    all_results = []
    for strategy in strategies:
        print(f"\n🔄 回测策略: {strategy.name}")
        backtest_df = backtest_strategy(strategy, predictions_df, prices_df)
        analysis = analyze_backtest_results(strategy.name, backtest_df)
        if analysis:
            all_results.append(analysis)
            print(f"   年化收益: {analysis['annual_return']*100:+.2f}%")
            print(f"   最大回撤: {analysis['max_drawdown']*100:.2f}%")
            print(f"   卡玛比率: {analysis['calmar_ratio']:.2f}")
            print(f"   信号分布: {analysis['signal_distribution']}")
    
    # 保存结果
    output_dir = Path(__file__).parent
    output_dir.mkdir(exist_ok=True)
    
    # 保存详细回测结果
    results_df = pd.DataFrame(all_results)
    results_path = output_dir / "strategy_backtest_results.csv"
    results_df.to_csv(results_path, index=False)
    print(f"\n💾 回测结果已保存: {results_path}")
    
    # 打印对比表格
    print("\n" + "=" * 80)
    print("策略对比总结")
    print("=" * 80)
    print(f"\n| 策略 | 年化收益 | 最大回撤 | 卡玛比率 | 夏普比率 | Folds |")
    print(f"|------|----------|----------|----------|----------|-------|")
    for r in all_results:
        print(f"| {r['strategy']:20} | {r['annual_return']*100:>+7.2f}% | {r['max_drawdown']*100:>7.2f}% | {r['calmar_ratio']:>8.2f} | {r['avg_sharpe']:>8.2f} | {r['n_folds']:5d} |")
    
    # 找出最优策略
    if all_results:
        best_by_return = max(all_results, key=lambda x: x['annual_return'])
        best_by_calmar = max(all_results, key=lambda x: x['calmar_ratio'])
        
        print(f"\n🏆 按年化收益最优: {best_by_return['strategy']} ({best_by_return['annual_return']*100:+.2f}%)")
        print(f"🏆 按卡玛比率最优: {best_by_calmar['strategy']} (卡玛={best_by_calmar['calmar_ratio']:.2f})")
    
    print("\n✅ 回测完成！")


if __name__ == "__main__":
    main()
