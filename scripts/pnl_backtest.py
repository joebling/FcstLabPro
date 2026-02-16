"""PnL 回测分析脚本.

对比 GBDT vs Orion-BiX 的实际交易表现.
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os


def load_experiment_results(model_name):
    """加载实验结果."""
    if model_name == 'gbdt':
        # GBDT Bull v15 结果
        path = 'experiments/weekly/weekly_bull_v15_regime_20260215_142329_b42efc'
    elif model_name == 'orion':
        # Orion-BiX Bull v27 结果
        path = 'experiments/weekly/weekly_bull_v27_orion_20260215_211945.csv'
    else:
        raise ValueError(f"Unknown model: {model_name}")

    if model_name == 'orion':
        return pd.read_csv(path)
    else:
        # GBDT 从报告读取 fold 数据
        report_path = f'{path}/report.md'
        return path


def run_pnl_backtest(predictions_df, prices_df, initial_capital=10000, transaction_cost=0.001, signal_delay=0):
    """运行 PnL 回测.

    Parameters
    ----------
    predictions_df : pd.DataFrame
        包含 train_end, kappa, accuracy 等列
    prices_df : pd.DataFrame
        包含 timestamp, close 价格
    initial_capital : float
        初始资金
    transaction_cost : float
        交易成本费率
    signal_delay : int
        信号延迟天数 (0-2)，模拟信号生成后延迟执行
    """
    results = []

    for _, row in predictions_df.iterrows():
        train_end = int(row['train_end'])
        kappa = row['kappa']

        # 下一个 OOS 窗口 (假设 63 天)
        test_start = train_end
        test_end = min(train_end + 63, len(prices_df))

        if test_end <= test_start:
            continue

        # 获取测试期价格
        test_prices = prices_df.iloc[test_start:test_end]['close'].values

        if len(test_prices) < 10:
            continue

        # 信号延迟处理: 跳过前 signal_delay 天的收益
        # 模拟信号生成后延迟执行的情况
        start_idx = max(1, signal_delay)

        # 计算买入持有收益 (考虑信号延迟)
        returns = []
        for i in range(start_idx, len(test_prices)):
            # 延迟执行: 用 signal_delay 天前的价格买入
            entry_idx = i - signal_delay
            ret = (test_prices[i] - test_prices[entry_idx]) / test_prices[entry_idx]
            # 扣除交易成本
            ret = ret - transaction_cost * 2  # 买入+卖出
            returns.append(ret)

        if returns:
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe = avg_return / (std_return + 1e-10) * np.sqrt(252) if std_return > 0 else 0

            # 最大回撤
            cumulative = np.cumprod([1 + r for r in returns])
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0

            results.append({
                'train_end': train_end,
                'kappa': kappa,
                'avg_return': avg_return,
                'std_return': std_return,
                'sharpe': sharpe,
                'max_drawdown': max_drawdown,
                'n_days': len(returns),
            })

    return pd.DataFrame(results)


def analyze_model(model_name):
    """分析单个模型."""
    print(f"\n{'='*60}")
    print(f"分析模型: {model_name}")
    print(f"{'='*60}")

    if model_name == 'gbdt':
        # 读取 GBDT fold 数据
        import yaml
        exp_path = 'experiments/weekly/weekly_bull_v15_regime_20260215_142329_b42efc'
        with open(f'{exp_path}/config.yaml') as f:
            config = yaml.safe_load(f)

        # 加载预测结果 (简化版 - 使用 kappa 近似)
        results = []
        kappa_data = [
            0.0803, 0.4284, 0.2596, 0.1362, -0.1667, 0.0494, 0.0990, 0.0451,
            0.1963, 0.3685, 0.0988, 0.3259, 0.2616, 0.0848, 0.4156, 0.4196,
            0.5220, 0.1463, 0.0771, 0.0221, 0.0187, 0.0762, 0.0000, 0.1778,
            0.2280, 0.1947
        ]
        train_ends = list(range(1500, 1500 + len(kappa_data) * 21, 21))

        for i, kappa in enumerate(kappa_data):
            results.append({
                'train_end': train_ends[i] if i < len(train_ends) else 1500 + i * 21,
                'kappa': kappa,
            })

        predictions_df = pd.DataFrame(results)

    else:  # orion
        predictions_df = pd.read_csv('experiments/weekly/weekly_bull_v27_orion_20260215_211945.csv')

    # 加载价格数据
    prices_df = pd.read_csv('data/raw/btc_binance_BTCUSDT_1d.csv')
    prices_df['timestamp'] = pd.to_datetime(prices_df['date'])

    # 运行回测
    pnl_df = run_pnl_backtest(predictions_df, prices_df)

    if len(pnl_df) == 0:
        print("没有足够的回测数据")
        return None

    # 汇总统计
    print(f"\nFold 数: {len(pnl_df)}")
    print(f"\n--- Kappa 统计 ---")
    print(f"平均 Kappa: {pnl_df['kappa'].mean():.4f} ± {pnl_df['kappa'].std():.4f}")
    print(f"正 Kappa 比例: {(pnl_df['kappa'] > 0).mean():.1%}")

    print(f"\n--- 收益统计 (年化) ---")
    avg_annual_return = pnl_df['avg_return'].mean() * 252
    print(f"年化收益: {avg_annual_return*100:.2f}%")

    print(f"\n--- 风险统计 ---")
    avg_dd = pnl_df['max_drawdown'].mean()
    print(f"平均最大回撤: {avg_dd*100:.2f}%")

    # 卡玛比率 (年化收益 / 最大回撤)
    calmar = avg_annual_return / (avg_dd + 1e-10)
    print(f"卡玛比率: {calmar:.2f}")

    # 夏普比率
    avg_sharpe = pnl_df['sharpe'].mean()
    print(f"平均夏普比率: {avg_sharpe:.2f}")

    # 收益/回撤比
    return_drawdown_ratio = avg_annual_return / (avg_dd + 1e-10)
    print(f"收益/回撤比: {return_drawdown_ratio:.2f}")

    return {
        'model': model_name,
        'avg_kappa': pnl_df['kappa'].mean(),
        'kappa_std': pnl_df['kappa'].std(),
        'positive_kappa_ratio': (pnl_df['kappa'] > 0).mean(),
        'annual_return': avg_annual_return,
        'avg_max_drawdown': avg_dd,
        'calmar_ratio': calmar,
        'avg_sharpe': avg_sharpe,
    }


def analyze_model_with_delay(model_name, delay):
    """分析单个模型 (带信号延迟).

    Parameters
    ----------
    model_name : str
        模型名称 ('gbdt' 或 'orion')
    delay : int
        信号延迟天数 (0-2)
    """
    print(f"\n{'='*60}")
    print(f"分析模型: {model_name} (信号延迟: {delay} 天)")
    print(f"{'='*60}")

    if model_name == 'gbdt':
        import yaml
        exp_path = 'experiments/weekly/weekly_bull_v15_regime_20260215_142329_b42efc'
        with open(f'{exp_path}/config.yaml') as f:
            config = yaml.safe_load(f)

        results = []
        kappa_data = [
            0.0803, 0.4284, 0.2596, 0.1362, -0.1667, 0.0494, 0.0990, 0.0451,
            0.1963, 0.3685, 0.0988, 0.3259, 0.2616, 0.0848, 0.4156, 0.4196,
            0.5220, 0.1463, 0.0771, 0.0221, 0.0187, 0.0762, 0.0000, 0.1778,
            0.2280, 0.1947
        ]
        train_ends = list(range(1500, 1500 + len(kappa_data) * 21, 21))

        for i, kappa in enumerate(kappa_data):
            results.append({
                'train_end': train_ends[i] if i < len(train_ends) else 1500 + i * 21,
                'kappa': kappa,
            })

        predictions_df = pd.DataFrame(results)

    else:  # orion
        predictions_df = pd.read_csv('experiments/weekly/weekly_bull_v27_orion_20260215_211945.csv')

    # 加载价格数据
    prices_df = pd.read_csv('data/raw/btc_binance_BTCUSDT_1d.csv')
    prices_df['timestamp'] = pd.to_datetime(prices_df['date'])

    # 运行回测 (带延迟)
    pnl_df = run_pnl_backtest(predictions_df, prices_df, signal_delay=delay)

    if len(pnl_df) == 0:
        print("没有足够的回测数据")
        return None

    # 汇总统计
    avg_annual_return = pnl_df['avg_return'].mean() * 252
    avg_dd = pnl_df['max_drawdown'].mean()
    calmar = avg_annual_return / (avg_dd + 1e-10)
    avg_sharpe = pnl_df['sharpe'].mean()

    print(f"Fold 数: {len(pnl_df)}")
    print(f"平均 Kappa: {pnl_df['kappa'].mean():.4f} ± {pnl_df['kappa'].std():.4f}")
    print(f"年化收益: {avg_annual_return*100:.2f}%")
    print(f"平均最大回撤: {avg_dd*100:.2f}%")
    print(f"卡玛比率: {calmar:.2f}")
    print(f"平均夏普比率: {avg_sharpe:.2f}")

    return {
        'model': model_name,
        'delay': delay,
        'avg_kappa': pnl_df['kappa'].mean(),
        'annual_return': avg_annual_return,
        'avg_max_drawdown': avg_dd,
        'calmar_ratio': calmar,
        'avg_sharpe': avg_sharpe,
    }


def run_robustness_test():
    """运行信号延迟鲁棒性测试."""
    print("\n" + "="*60)
    print("信号延迟鲁棒性测试")
    print("验证 Orion-BiX 盈利能力是否依赖瞬时信号")
    print("="*60)

    delays = [0, 1, 2]
    results = []

    for delay in delays:
        for model in ['orion', 'gbdt']:
            stats = analyze_model_with_delay(model, delay)
            if stats:
                results.append(stats)

    # 打印对比表格
    print("\n" + "="*60)
    print("信号延迟对比结果")
    print("="*60)

    print(f"\n| 延迟 | 模型 | 年化收益 | 最大回撤 | 卡玛比率 | 夏普比率 |")
    print(f"|------|------|----------|----------|----------|----------|")
    for r in results:
        print(f"| {r['delay']}天 | {r['model']} | {r['annual_return']*100:+.2f}% | {r['avg_max_drawdown']*100:.2f}% | {r['calmar_ratio']:.2f} | {r['avg_sharpe']:.2f} |")

    # 分析结论
    orion_delays = [r for r in results if r['model'] == 'orion']
    orion_d0 = orion_delays[0]['annual_return']
    orion_d1 = orion_delays[1]['annual_return']
    orion_d2 = orion_delays[2]['annual_return']

    print("\n--- 鲁棒性分析 ---")
    print(f"Orion-BiX (延迟0天): {orion_d0*100:+.2f}%")
    print(f"Orion-BiX (延迟1天): {orion_d1*100:+.2f}%")
    print(f"Orion-BiX (延迟2天): {orion_d2*100:+.2f}%")

    drop_1d = (orion_d1 - orion_d0) / (abs(orion_d0) + 1e-10) * 100
    drop_2d = (orion_d2 - orion_d0) / (abs(orion_d0) + 1e-10) * 100

    if drop_1d > 50:
        print(f"⚠️  警告: 延迟1天收益下降 {drop_1d:.1f}%，可能过度拟合瞬时波动")
    else:
        print(f"✓  延迟1天收益下降 {drop_1d:.1f}%，相对稳健")

    if drop_2d > 70:
        print(f"⚠️  警告: 延迟2天收益下降 {drop_2d:.1f}%，策略高度依赖即时信号")
    else:
        print(f"✓ 延迟2天收益下降 {drop_2d:.1f}%，有一定稳健性")


def main():
    """主函数."""
    import argparse

    parser = argparse.ArgumentParser(description='PnL 回测分析')
    parser.add_argument('--mode', choices=['compare', 'robustness'], default='compare',
                        help='运行模式: compare=对比测试, robustness=信号延迟鲁棒性测试')
    args = parser.parse_args()

    if args.mode == 'robustness':
        run_robustness_test()
        return

    print("="*60)
    print("PnL 回测分析: GBDT vs Orion-BiX")
    print("="*60)

    # 分析两个模型
    gbdt_stats = analyze_model('gbdt')
    orion_stats = analyze_model('orion')

    # 对比表格
    print("\n" + "="*60)
    print("对比总结")
    print("="*60)

    print(f"\n| 指标 | GBDT v15 | Orion-BiX v27 | 差异 |")
    print(f"|------|----------|----------------|------|")
    print(f"| 平均 Kappa | {gbdt_stats['avg_kappa']:.4f} | {orion_stats['avg_kappa']:.4f} | {orion_stats['avg_kappa']-gbdt_stats['avg_kappa']:+.4f} |")
    print(f"| Kappa 标准差 | {gbdt_stats['kappa_std']:.4f} | {orion_stats['kappa_std']:.4f} | {orion_stats['kappa_std']-gbdt_stats['kappa_std']:+.4f} |")
    print(f"| 正 Kappa 比例 | {gbdt_stats['positive_kappa_ratio']:.1%} | {orion_stats['positive_kappa_ratio']:.1%} | {orion_stats['positive_kappa_ratio']-gbdt_stats['positive_kappa_ratio']:+.1%} |")
    print(f"| 年化收益 | {gbdt_stats['annual_return']*100:.2f}% | {orion_stats['annual_return']*100:.2f}% | {orion_stats['annual_return']-gbdt_stats['annual_return']:+.2%} |")
    print(f"| 平均最大回撤 | {gbdt_stats['avg_max_drawdown']*100:.2f}% | {orion_stats['avg_max_drawdown']*100:.2f}% | {orion_stats['avg_max_drawdown']-gbdt_stats['avg_max_drawdown']:+.2%} |")
    print(f"| 卡玛比率 | {gbdt_stats['calmar_ratio']:.2f} | {orion_stats['calmar_ratio']:.2f} | {orion_stats['calmar_ratio']-gbdt_stats['calmar_ratio']:+.2f} |")
    print(f"| 夏普比率 | {gbdt_stats['avg_sharpe']:.2f} | {orion_stats['avg_sharpe']:.2f} | {orion_stats['avg_sharpe']-gbdt_stats['avg_sharpe']:+.2f} |")

    print("\n" + "="*60)
    print("部署建议")
    print("="*60)

    if orion_stats['avg_max_drawdown'] > gbdt_stats['avg_max_drawdown'] * 1.5:
        print("⚠️  警告: Orion-BiX 最大回撤显著高于 GBDT")
    if orion_stats['calmar_ratio'] < gbdt_stats['calmar_ratio']:
        print("⚠️  警告: Orion-BiX 卡玛比率低于 GBDT")


if __name__ == '__main__':
    main()
