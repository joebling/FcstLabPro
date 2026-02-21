"""Plotting functions."""

import numpy as np
import matplotlib.pyplot as plt


def plot_strategy_comparison(strategy_results, save_path=None):
    """
    绘制策略对比图.
    
    Parameters
    ----------
    strategy_results : dict
        策略结果字典 {name: result_dict}
    save_path : str, optional
        保存路径, by default None
    """
    plt.figure(figsize=(14, 8))
    
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    
    for i, (name, result) in enumerate(strategy_results.items()):
        if 'cumulative' in result:
            cumulative = result['cumulative']
            plt.plot(range(len(cumulative)), cumulative, 
                    label=name, color=colors[i % len(colors)], linewidth=2)
    
    plt.title('Strategy Cumulative Returns Comparison', fontsize=14)
    plt.xlabel('Trading Days', fontsize=12)
    plt.ylabel('Cumulative Return', fontsize=12)
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300)
        print(f"Plot saved to {save_path}")
    
    plt.close()
