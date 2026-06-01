"""测试邮件内容生成 — 适配 v0305 模型无关架构."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.send_signal_email import build_html, build_plain_text, SIGNAL_STYLE


# ── 测试数据工厂 ──

def _make_signal(signal="BUY", **overrides):
    """构建测试用信号 JSON."""
    base = {
        "date": "2026-03-08",
        "price": 85432.10,
        "signal": signal,
        "signal_display": f"{SIGNAL_STYLE[signal]['emoji']} {SIGNAL_STYLE[signal]['label']}",
        "reason": "模型信号: y_pred=1 (预测跌后反弹)",
        "regime": "非熊市",
        "regime_detail": "63d 滚动收益 = +12.3% (threshold=-10%)",
        "position": {
            "in_position": False,
            "entry_date": None,
            "entry_price": None,
            "days_held": 0,
            "floating_pnl": 0.0,
        },
        "history": {
            "total_trades": 0,
            "wins": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "total_pnl": 0.0,
            "recent": [],
            "exit_stats": {},
        },
        "model": {
            "name": "E1 Conservative",
            "version": "v0305",
            "type": "LightGBM",
            "label": "directional_filtered",
            "features": 129,
            "kappa": 0.19,
            "variant": "止盈+regime",
            "backtest": {
                "cagr": "9.8%",
                "max_dd": "-12.7%",
                "pf": 1.32,
                "sharpe": 0.63,
            },
        },
        "strategy": {"T": 21, "X": 0.04, "take_profit": True, "regime_switch": True},
        "risk_notes": ["策略变体: conservative"],
        "llm_analysis": None,
    }
    base.update(overrides)
    return base


# ── 测试用例 ──

def test_all_signal_types():
    """每种信号类型都能正确渲染."""
    print("=== 测试 4 种信号类型 ===")
    for sig in ("BUY", "HOLD", "SELL", "SILENT"):
        data = _make_signal(sig)
        html = build_html(data)
        style = SIGNAL_STYLE[sig]
        assert style["color"] in html, f"{sig}: 颜色 {style['color']} 未出现"
        assert style["label"] in html, f"{sig}: 标签 {style['label']} 未出现"
        assert "$85,432.10" in html, f"{sig}: 价格未出现"
        print(f"  ✅ {sig}")
    print("✅ 信号类型测试通过\n")


def test_position_card():
    """持仓卡片在持仓时显示，空仓时隐藏."""
    print("=== 测试持仓卡片 ===")

    # 空仓: 不显示持仓卡片
    html_empty = build_html(_make_signal("SILENT"))
    assert "持仓状态" not in html_empty, "空仓时不应显示持仓卡片"
    print("  ✅ 空仓: 不显示")

    # 持仓中: 显示持仓卡片
    data = _make_signal("HOLD", position={
        "in_position": True,
        "entry_date": "2026-03-05",
        "entry_price": 83200.0,
        "days_held": 3,
        "floating_pnl": 0.0268,
    })
    html_hold = build_html(data)
    assert "持仓状态" in html_hold, "持仓时应显示持仓卡片"
    assert "$83,200.00" in html_hold, "应显示买入价"
    assert "+2.68%" in html_hold, "应显示浮盈"
    print("  ✅ 持仓: 显示买入价/浮盈/天数")
    print("✅ 持仓卡片测试通过\n")


def test_history_card():
    """历史战绩在有数据时显示."""
    print("=== 测试历史战绩 ===")

    # 无历史
    html_empty = build_html(_make_signal("BUY"))
    assert "尚无历史交易" in html_empty, "无历史时应显示提示"
    print("  ✅ 无历史: 显示提示")

    # 有历史
    data = _make_signal("BUY", history={
        "total_trades": 5,
        "wins": 3,
        "win_rate": 0.6,
        "avg_pnl": 0.0123,
        "total_pnl": 0.0615,
        "recent": [
            {"entry": "03-01", "exit": "03-05", "pnl": "+4.2%", "reason": "止盈"},
            {"entry": "02-15", "exit": "02-28", "pnl": "-1.3%", "reason": "到期"},
        ],
        "exit_stats": {},
    })
    html_hist = build_html(data)
    assert "5 笔" in html_hist, "应显示总笔数"
    assert "60%" in html_hist, "应显示胜率"
    assert "+4.2%" in html_hist, "应显示最近交易"
    print("  ✅ 有历史: 显示胜率/笔数/最近交易")
    print("✅ 历史战绩测试通过\n")


def test_llm_section():
    """LLM 分析在有内容时显示."""
    print("=== 测试 LLM 区块 ===")

    # 无 LLM
    html_no_llm = build_html(_make_signal("BUY"))
    assert "AI 策略解读" not in html_no_llm, "无 LLM 时不应显示"
    print("  ✅ 无 LLM: 不显示")

    # 有 LLM
    data = _make_signal("BUY", llm_analysis="**信号解读**: 模型在超卖区域发出信号。")
    html_llm = build_html(data)
    assert "AI 策略解读" in html_llm, "有 LLM 时应显示"
    assert "<strong>信号解读</strong>" in html_llm, "应转换 markdown 加粗"
    print("  ✅ 有 LLM: 显示并转换 markdown")
    print("✅ LLM 区块测试通过\n")


def test_model_info():
    """模型信息区块显示正确."""
    print("=== 测试模型信息 ===")
    html = build_html(_make_signal("BUY"))
    assert "E1 Conservative" in html, "应显示模型名"
    assert "LightGBM" in html, "应显示模型类型"
    assert "Kappa=0.19" in html or "0.19" in html, "应显示 Kappa"
    assert "9.8%" in html, "应显示 CAGR"
    assert "模型语义" in html, "应显示模型语义说明"
    assert "Directional / 终点确认" in html, "应显示 directional 标签含义"
    assert "close[t+21] / close[t]" in html, "应显示 directional 触发条件"
    print("  ✅ 模型名/类型/Kappa/CAGR/语义均正确")
    print("✅ 模型信息测试通过\n")


def test_different_models():
    """不同模型 (E1 vs E8) 都能正确渲染."""
    print("=== 测试多模型兼容 ===")

    # E8
    e8_data = _make_signal("BUY", model={
        "name": "E8 Touch",
        "version": "v0305",
        "type": "LightGBM",
        "label": "touch_filtered",
        "features": 129,
        "kappa": 0.751,
        "variant": "止盈+regime",
        "backtest": {
            "cagr": "16.0%",
            "max_dd": "-21.4%",
            "pf": 1.28,
            "sharpe": 0.76,
        },
    })
    html_e8 = build_html(e8_data)
    assert "E8 Touch" in html_e8, "应显示 E8 模型名"
    assert "touch_filtered" in html_e8, "应显示 touch 标签"
    assert "16.0%" in html_e8, "应显示 E8 CAGR"
    assert "Touch / 窗口触达" in html_e8, "应显示 touch 标签含义"
    assert "max(high[t+1:t+22])" in html_e8, "应显示 touch 触发条件"
    assert "Production · E8 touch" in html_e8, "应显示 E8 production 口径"
    print("  ✅ E8 模型渲染正确")
    print("✅ 多模型兼容测试通过\n")


def test_plain_text():
    """纯文本备用正文."""
    print("=== 测试纯文本 ===")
    text = build_plain_text(_make_signal("BUY"))
    assert "$85,432.10" in text, "应包含价格"
    assert "E1 Conservative" in text, "应包含模型名"
    assert "Kappa=0.19" in text, "应包含 Kappa"
    assert "模型语义 / 怎么读这个信号" in text, "应包含模型语义说明"
    assert "Directional / 终点确认" in text, "应包含 directional 标签含义"
    print("  ✅ 纯文本包含关键信息和模型语义")
    print("✅ 纯文本测试通过\n")


def test_regime_display():
    """Regime 状态正确显示."""
    print("=== 测试 Regime 显示 ===")

    html_bull = build_html(_make_signal("BUY", regime="非熊市"))
    assert "🟢" in html_bull, "非熊市应显示绿点"
    print("  ✅ 非熊市: 绿点")

    html_bear = build_html(_make_signal("SILENT", regime="熊市"))
    assert "🔴" in html_bear, "熊市应显示红点"
    print("  ✅ 熊市: 红点")
    print("✅ Regime 显示测试通过\n")


# ── Runner ──

def run_all():
    print("📧 邮件模板测试 (v0305 模型无关版)\n")
    tests = [
        test_all_signal_types,
        test_position_card,
        test_history_card,
        test_llm_section,
        test_model_info,
        test_different_models,
        test_plain_text,
        test_regime_display,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"❌ {t.__name__}: {e}\n")
        except Exception as e:
            print(f"❌ {t.__name__} 异常: {e}\n")

    print(f"📊 结果: {passed}/{len(tests)} 通过")
    return passed == len(tests)


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
