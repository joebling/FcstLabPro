"""数据健康检查脚本.

在预测前检查数据源是否正常.
"""

import os
import sys
import pandas as pd
from datetime import datetime, timedelta

# 项目根目录
PROJECT_ROOT = "/Users/qiubling/Desktop/projects/FcstLabPro"


def check_binance_data(data_path: str) -> dict:
    """检查 Binance K线数据."""
    result = {
        "status": "OK",
        "message": "",
        "details": {}
    }

    if not os.path.exists(data_path):
        result["status"] = "ERROR"
        result["message"] = f"Binance 数据文件不存在: {data_path}"
        return result

    try:
        df = pd.read_csv(data_path)
        result["details"]["total_rows"] = len(df)

        # 检查列
        required_cols = ["date", "open", "high", "low", "close", "volume"]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            result["status"] = "ERROR"
            result["message"] = f"缺少必要列: {missing_cols}"
            return result

        result["details"]["columns"] = list(df.columns)

        # 检查日期范围
        df['date'] = pd.to_datetime(df['date'])
        result["details"]["date_range"] = {
            "start": str(df['date'].min()),
            "end": str(df['date'].max())
        }

        # 检查最新数据是否足够新
        latest_date = df['date'].max()
        days_old = (datetime.now() - latest_date).days
        result["details"]["days_old"] = days_old

        if days_old > 2:
            result["status"] = "WARNING"
            result["message"] = f"数据较旧: {days_old} 天前的数据"
        else:
            result["message"] = f"数据正常，最新日期: {latest_date.date()}"

        # 检查是否有 NaN
        nan_count = df[required_cols].isna().sum().sum()
        result["details"]["nan_count"] = int(nan_count)
        if nan_count > 0:
            result["status"] = "WARNING"
            result["message"] = f"数据包含 {nan_count} 个 NaN 值"

        # 检查价格是否合理
        if (df['close'] <= 0).any():
            result["status"] = "ERROR"
            result["message"] = "数据包含非正价格"
            return result

    except Exception as e:
        result["status"] = "ERROR"
        result["message"] = f"读取数据失败: {str(e)}"

    return result


def check_fgi_data(fgi_path: str) -> dict:
    """检查 FGI 数据."""
    result = {
        "status": "OK",
        "message": "",
        "details": {}
    }

    if not os.path.exists(fgi_path):
        result["status"] = "WARNING"
        result["message"] = f"FGI 数据文件不存在: {fgi_path} (可选)"
        return result

    try:
        df = pd.read_csv(fgi_path)
        result["details"]["total_rows"] = len(df)

        # 检查列
        if 'fgi_value' not in df.columns:
            result["status"] = "ERROR"
            result["message"] = "FGI 数据缺少 fgi_value 列"
            return result

        # 检查日期范围
        df['date'] = pd.to_datetime(df['date'])
        result["details"]["date_range"] = {
            "start": str(df['date'].min()),
            "end": str(df['date'].max())
        }

        # 检查最新数据是否足够新
        latest_date = df['date'].max()
        days_old = (datetime.now() - latest_date).days
        result["details"]["days_old"] = days_old

        if days_old > 7:
            result["status"] = "WARNING"
            result["message"] = f"FGI 数据较旧: {days_old} 天前的数据"
        else:
            result["message"] = f"FGI 数据正常，最新日期: {latest_date.date()}"

        # 检查 FGI 值范围
        if 'fgi_value' in df.columns:
            fgi_min = df['fgi_value'].min()
            fgi_max = df['fgi_value'].max()
            result["details"]["fgi_range"] = {"min": fgi_min, "max": fgi_max}
            if fgi_min < 0 or fgi_max > 100:
                result["status"] = "WARNING"
                result["message"] = f"FGI 值超出正常范围 [0, 100]: [{fgi_min}, {fgi_max}]"

    except Exception as e:
        result["status"] = "ERROR"
        result["message"] = f"读取 FGI 数据失败: {str(e)}"

    return result


def check_all():
    """检查所有数据源."""
    print("=" * 60)
    print("FcstLabPro v7 数据健康检查")
    print("=" * 60)

    # Binance 数据
    print("\n[1/2] 检查 Binance K线数据...")
    binance_path = "data/raw/btc_binance_BTCUSDT_1d.csv"
    binance_result = check_binance_data(binance_path)

    status_icon = {
        "OK": "✅",
        "WARNING": "⚠️",
        "ERROR": "❌"
    }
    print(f"{status_icon[binance_result['status']]} {binance_result['message']}")
    if binance_result['details']:
        for k, v in binance_result['details'].items():
            print(f"   - {k}: {v}")

    # FGI 数据
    print("\n[2/2] 检查 FGI 数据...")
    fgi_path = "data/external/fear_greed_index.csv"
    fgi_result = check_fgi_data(fgi_path)

    print(f"{status_icon[fgi_result['status']]} {fgi_result['message']}")
    if fgi_result['details']:
        for k, v in fgi_result['details'].items():
            print(f"   - {k}: {v}")

    # 总结
    print("\n" + "=" * 60)
    print("检查总结")
    print("=" * 60)

    all_ok = binance_result['status'] in ["OK", "WARNING"] and fgi_result['status'] in ["OK", "WARNING"]

    if all_ok:
        print("✅ 数据检查通过，可以进行预测")
        return 0
    else:
        print("❌ 数据检查未通过，请修复后重试")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(check_all())
