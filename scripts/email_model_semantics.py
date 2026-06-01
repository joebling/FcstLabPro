"""邮件里的模型语义说明。

这里集中维护 E1/E8/E20c/E21b 的 target 定义和版本口径。
注意: E21b 当前是 research/shadow only, 不得在邮件里暗示 production 默认启用。
"""

from __future__ import annotations

import html

LABEL_PROFILES: dict[str, dict[str, str]] = {
    "directional_filtered": {
        "short_name": "Directional / 终点确认",
        "target": "21 天后收盘价较今天上涨 ≥ 4%",
        "formula": "close[t+21] / close[t] ≥ 1.04",
        "observes": "第 21 天收盘价 (终点)",
        "style": "保守择时: 宁可漏过, 不轻易追反弹",
    },
    "touch_filtered": {
        "short_name": "Touch / 窗口触达",
        "target": "未来 21 天内任一日最高价触达 +4%",
        "formula": "max(high[t+1:t+22]) ≥ close[t] × 1.04",
        "observes": "窗口内任一日最高价 (触达即可)",
        "style": "反弹猎手: 更少漏报, 但更激进",
    },
}

MODEL_USAGE_NOTES: dict[str, dict[str, str]] = {
    "e1-conservative": {
        "status": "Production · E1 baseline",
        "usage": "生产保守版 directional 模型。适合弱势回补/反弹确认, 不是熊市万能买入器。",
        "regime": "E20c 同标签研究显示: directional 类模型牛市/震荡更稳, 真熊市会少发信号。",
    },
    "e8-touch": {
        "status": "Production · E8 touch",
        "usage": "生产 touch 模型。捕捉 21 天窗口内 +4% 触达, 比 directional 更偏反弹机会识别。",
        "regime": "E21b 同标签研究显示: touch 类模型多 regime 更稳定, 但执行规则仍要单独验证。",
    },
    "e20c-conservative-prune": {
        "status": "Candidate/Production · E20c prune",
        "usage": "28 特征 directional 剪枝模型。牛市/震荡保守择时; 熊市建议降低权重或关闭。",
        "regime": "OOS: bull kappa 0.42; bear 0.13; sideways 0.52。熊市几乎闭嘴 (recall 10%)。",
    },
    "e21b-touch-prune": {
        "status": "Research only · 暂不 promote",
        "usage": "81 特征 touch 剪枝模型。分类显著, 但止盈/执行层 PnL 未全线胜出。",
        "regime": "OOS: bull kappa 0.73; bear 0.70; sideways 0.84。全 regime 反弹猎手。",
    },
}


def _model_key(model: dict) -> str:
    """返回稳定模型 key: 优先 raw_name, 兼容旧 JSON 的 display name."""
    raw_name = str(model.get("raw_name") or "").strip().lower()
    if raw_name:
        return raw_name
    return str(model.get("name", "")).strip().lower().replace(" ", "-")


def _usage_note_for_model(model: dict) -> dict[str, str]:
    """根据模型名/标签/特征数返回邮件解释口径."""
    key = _model_key(model)
    if key in MODEL_USAGE_NOTES:
        return MODEL_USAGE_NOTES[key]

    label = str(model.get("label", ""))
    features = int(model.get("features", 0) or 0)
    if label == "directional_filtered" and features <= 50:
        return MODEL_USAGE_NOTES["e20c-conservative-prune"]
    if label == "touch_filtered" and features <= 90:
        return MODEL_USAGE_NOTES["e21b-touch-prune"]
    if label == "directional_filtered":
        return MODEL_USAGE_NOTES["e1-conservative"]
    if label == "touch_filtered":
        return MODEL_USAGE_NOTES["e8-touch"]
    return {
        "status": "Unknown profile",
        "usage": "此模型暂无内置语义说明, 请查看 production REPORT.md。",
        "regime": "无 regime 分层统计。",
    }


def build_model_semantics_html(data: dict) -> str:
    """模型语义说明: 每日邮件里提醒 target 到底是什么."""
    model = data.get("model", {})
    label = str(model.get("label", ""))
    profile = LABEL_PROFILES.get(label)
    if not profile:
        return ""
    note = _usage_note_for_model(model)

    return f"""
    <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px;
                padding: 14px 16px; margin-bottom: 16px;">
        <p style="color: #1d4ed8; font-size: 13px; font-weight: 700;
                  margin: 0 0 8px 0;">🧭 模型语义 / 怎么读这个信号</p>
        <table style="width: 100%; border-collapse: collapse; font-size: 13px;
                      color: #374151; line-height: 1.45;">
            {_row('标签', profile['short_name'], strong=True)}
            {_row('目标', profile['target'])}
            {_row('条件', profile['formula'], code=True)}
            {_row('看的什么', profile['observes'])}
            {_row('定位', profile['style'])}
        </table>
        <div style="background: white; border-radius: 6px; padding: 8px 10px;
                    margin-top: 10px; font-size: 12px; color: #374151; line-height: 1.5;">
            <b style="color: #111827;">版本口径:</b> {html.escape(note['status'])}<br>
            <b style="color: #111827;">使用提示:</b> {html.escape(note['usage'])}<br>
            <b style="color: #111827;">Regime:</b> {html.escape(note['regime'])}
        </div>
    </div>
    """


def _row(label: str, value: str, *, strong: bool = False, code: bool = False) -> str:
    """语义说明表格行."""
    safe = html.escape(value)
    if code:
        safe = f'<code style="background: #dbeafe; padding: 1px 4px; border-radius: 4px;">{safe}</code>'
    elif strong:
        safe = f'<span style="font-weight: 600; color: #111827;">{safe}</span>'
    return f"""
    <tr>
        <td style="color: #6b7280; padding: 3px 8px 3px 0; width: 86px;">{html.escape(label)}</td>
        <td>{safe}</td>
    </tr>
    """


def model_semantics_text(data: dict) -> list[str]:
    """纯文本版模型语义说明."""
    model = data.get("model", {})
    label = str(model.get("label", ""))
    profile = LABEL_PROFILES.get(label)
    if not profile:
        return []
    note = _usage_note_for_model(model)
    return [
        "",
        "模型语义 / 怎么读这个信号",
        "-" * 24,
        f"标签: {profile['short_name']}",
        f"目标: {profile['target']}",
        f"条件: {profile['formula']}",
        f"看的什么: {profile['observes']}",
        f"定位: {profile['style']}",
        f"版本口径: {note['status']}",
        f"使用提示: {note['usage']}",
        f"Regime: {note['regime']}",
    ]
