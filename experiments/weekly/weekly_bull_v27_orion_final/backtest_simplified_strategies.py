#!/usr/bin/env python3
"""
简化版策略回测
基于 kappa 方向的交易策略对比
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_data():
    """加载数据"""
    predictions_path = PROJECT_ROOT / "experiments/weekly/weekly_bull_v27_orion_20260215_211945.csv"
    prices_path = PROJECT_ROOT / "data/raw/btc_binance_BTCUSDT_1d.csv"
    
    predictions_df = pd.read_csv(predictions_path)
    prices_df = pd.read_csv(prices_path)
    prices_df['timestamp'] = pd.to_datetime(prices_df['date'])
    
    return predictions_df, prices_df


class Strategy:
    """策略基类"""
    
    def __init__(self, name):
        self.name = name
    
    def get_position(self, kappa, current_price):
        """获取仓位建议（0-100%）"""
        raise NotImplementedError


class Strategy0_BuyHold(Strategy):
    """策略0：买入持有（基准）"""
    
    def __init__(self):
        super().__init__("v0_buy_hold")
    
    def get_position(self, kappa, current_price):
        return 100  # 永远满仓


class Strategy1_KappaDirection(Strategy):
    """策略1：简单 kappa 方向策略"""
    
    def __init__(self, kappa_threshold=0):
        super().__init__(f"v1_kappa_dir_thr_{kappa_threshold}")
        self.kappa_threshold = kappa_threshold
    
    def get_position(self, kappa, current_price):
        if kappa > self.kappa_threshold:
            return 80
        elif kappa < -self.kappa_threshold:
            return 20
        else:
            return 50


class Strategy2_KappaStrength(Strategy):
    """策略2：kappa 强度策略（线性仓位）"""
    
    def __init__(self, max_position=80, min_position=20):
        super().__init__(f"v2_kappa_strength_{min_position}-{max_position}")
        self.max_position = max_position
        self.min_position = min_position
    
    def get_position(self, kappa, current_price):
        # kappa 范围假设是 -0.5 到 +0.5
        normalized_kappa = np.clip(kappa, -0.5, 0.5)
        # 映射到 0-1
        weight = (normalized_kappa + 0.5) / 1.0
        # 映射到仓位
        position = self.min_position + weight * (self.max_position - self.min_position)
        return position


class Strategy3_ThresholdAdjusted(Strategy):
    """策略3：调整阈值（和之前讨论的类似）"""
    
    def __init__(self, bull_threshold=0.2, bear_threshold=-0.15):
        super().__init__(f"v3_threshold_adjusted")
        self.bull_threshold = bull_threshold
        self.bear_threshold = bear_threshold
    
    def get_position(self, kappa, current_price):
        if kappa > self.bull_threshold:
            return 70
        elif kappa < self.bear_threshold:
            return 20
        elif kappa > 0:
            return 55
        else:
            return 45


def backtest_strategy(strategy, predictions_df, prices_df, initial_capital=10000):
    """回测单个策略"""
    capital = initial_capital
    position_pct = 50  # 初始仓位
    history = []
    
    for idx, row in predictions_df.iterrows():
        train_end = int(row['train_end'])
        kappa = row['kappa']
        
        # 获取当前价格
        if train_end >= len(prices_df):
            continue
        
        current_price = prices_df.iloc[train_end]['close']
        
        # 计算目标仓位
        target_position = strategy.get_position(kappa, current_price)
        
        # 计算下一个窗口（63天）的价格变化
        test_start = train_end
        test_end = min(train_end + 63, len(prices_df))
        
        if test_end <= test_start:
            continue
        
        # 获取测试期价格
        test_prices = prices_df.iloc[test_start:test_end]['close'].values
        
        if len(test_prices) < 2:
            continue
        
        # 计算策略在这个窗口的收益
        # 简化版：假设仓位是 target_position，持有整个窗口
        entry_price = test_prices[0]
        exit_price = test_prices[-1]
        
        # 价格变化
        price_return = (exit_price - entry_price) / entry_price
        
        # 仓位收益
        position_return = price_return * (target_position / 100)
        
        # 更新资本
        capital = capital * (1 + position_return)
        
        # 计算回撤
        if idx == 0:
            peak = capital
        else:
            peak = max(peak, capital)
        
        drawdown = (peak - capital) / peak if peak > 0 else 0
        
        history.append({
            'train_end': train_end,
            'kappa': kappa,
            'position': target_position,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'price_return': price_return,
            'position_return': position_return,
            'capital': capital,
            'drawdown': drawdown,
        })
    
    if len(history) == 0:
        return None, None
    
    history_df = pd.DataFrame(history)
    
    # 计算汇总统计
    total_return = (history_df['capital'].iloc[-1] / initial_capital) - 1
    n_days = (prices_df.iloc[history_df['train_end'].iloc[-1]]['timestamp'] - 
              prices_df.iloc[history_df['train_end'].iloc[0]]['timestamp']).days
    annual_return = (1 + total_return) ** (365 / n_days) - 1 if n_days > 0 else 0
    max_drawdown = history_df['drawdown'].max()
    calmar_ratio = annual_return / (max_drawdown + 1e-10) if max_drawdown > 0 else 0
    
    # 计算每日收益用于夏普比率
    daily_returns = []
    for i in range(1, len(history_df)):
        ret = (history_df['capital'].iloc[i] / history_df['capital'].iloc[i-1]) - 1
        daily_returns.append(ret)
    
    if len(daily_returns) > 0:
        avg_daily = np.mean(daily_returns)
        std_daily = np.std(daily_returns)
        sharpe_ratio = avg_daily / (std_daily + 1e-10) * np.sqrt(252) if std_daily > 0 else 0
    else:
        sharpe_ratio = 0
    
    stats = {
        'strategy': strategy.name,
        'total_return': total_return,
        'annual_return': annual_return,
        'max_drawdown': max_drawdown,
        'calmar_ratio': calmar_ratio,
        'sharpe_ratio': sharpe_ratio,
        'final_capital': history_df['capital'].iloc[-1],
        'n_windows': len(history_df),
    }
    
    return stats, history_df


def main():
    print("=" * 80)
    print("简化版策略回测")
    print("=" * 80)
    
    # 加载数据
    print("\n📥 加载数据...")
    predictions_df, prices_df = load_data()
    print(f"   预测数据: {len(predictions_df)} 个fold")
    print(f"   价格数据: {len(prices_df)} 天")
    
    # 定义策略
    strategies = [
        Strategy0_BuyHold(),
        Strategy1_KappaDirection(kappa_threshold=0),
        Strategy1_KappaDirection(kappa_threshold=0.1),
        Strategy2_KappaStrength(min_position=20, max_position=80),
        Strategy2_KappaStrength(min_position=30, max_position=70),
        Strategy3_ThresholdAdjusted(bull_threshold=0.2, bear_threshold=-0.15),
    ]
    
    # 运行回测
    all_stats = []
    all_history = {}
    
    for strategy in strategies:
        print(f"\n🔄 回测策略: {strategy.name}")
        stats, history = backtest_strategy(strategy, predictions_df, prices_df)
        
        if stats:
            all_stats.append(stats)
            all_history[strategy.name] = history
            print(f"   年化收益: {stats['annual_return']*100:+.2f}%")
            print(f"   最大回撤: {stats['max_drawdown']*100:.2f}%")
            print(f"   卡玛比率: {stats['calmar_ratio']:.2f}")
            print(f"   夏普比率: {stats['sharpe_ratio']:.2f}")
            print(f"   最终资金: ${stats['final_capital']:.2f}")
    
    # 保存结果
    output_dir = Path(__file__).parent
    output_dir.mkdir(exist_ok=True)
    
    # 保存汇总统计
    stats_df = pd.DataFrame(all_stats)
    stats_path = output_dir / "simplified_backtest_summary.csv"
    stats_df.to_csv(stats_path, index=False)
    print(f"\n💾 汇总结果已保存: {stats_path}")
    
    # 打印对比表格
    print("\n" + "=" * 80)
    print("策略对比总结")
    print("=" * 80)
    
    print(f"\n| 策略 | 年化收益 | 最大回撤 | 卡玛比率 | 夏普比率 | 最终资金 |")
    print(f"|------|----------|----------|----------|----------|----------|")
    for s in all_stats:
        print(f"| {s['strategy']:30} | {s['annual_return']*100:>+7.2f}% | {s['max_drawdown']*100:>7.2f}% | {s['calmar_ratio']:>8.2f} | {s['sharpe_ratio']:>8.2f} | ${s['final_capital']:>7.0f} |")
    
    # 找出最优策略
    if all_stats:
        best_by_return = max(all_stats, key=lambda x: x['annual_return'])
        best_by_calmar = max(all_stats, key=lambda x: x['calmar_ratio'])
        best_by_sharpe = max(all_stats, key=lambda x: x['sharpe_ratio'])
        
        print(f"\n🏆 按年化收益最优: {best_by_return['strategy']} ({best_by_return['annual_return']*100:+.2f}%)")
        print(f"🏆 按卡玛比率最优: {best_by_calmar['strategy']} (卡玛={best_by_calmar['calmar_ratio']:.2f})")
        print(f"🏆 按夏普比率最优: {best_by_sharpe['strategy']} (夏普={best_by_sharpe['sharpe_ratio']:.2f})")
    
    print("\n✅ 回测完成！")
    print("\n⚠️  注意：此回测是基于 kappa 的简化策略，绝对收益仅供参考，")
    print("    但策略之间的相对比较是有意义的！")


if __name__ == "__main__":
    main()
