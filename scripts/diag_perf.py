"""Performance 诊断 — 在 VPS 上跑, 看命中率/IC 为何为空."""
from datetime import date
from src.dashboard.data_access import list_models
from src.dashboard.data import load_display_ohlcv
from src.performance import service
from src.performance.backfill import load_archive_signals
from src.serving.active_config import resolve_model
import yaml

df, src = load_display_ohlcv()
print(f"OHLCV 源: {src} | 最后一根: {df.index[-1].date()} | 今天: {date.today()}")
print("="*60)
for m in list_models():
    sigs = load_archive_signals(m)
    cfg = yaml.safe_load(resolve_model(m).config_path.read_text())
    T = cfg["label"]["T"]
    dates = [s.get("date") for s in sigs if s.get("date")]
    buys = sum(1 for s in sigs if s.get("signal") == "BUY")
    s, _ = service.get_summary(m)
    print(f"\n模型: {m}  (label.T={T}, 成熟需 {T+1} 天)")
    print(f"  archive: {len(sigs)} 条 | BUY {buys} / SILENT {len(sigs)-buys}")
    if dates:
        print(f"  日期范围: {min(dates)} ~ {max(dates)}")
    print(f"  n_total={s['n_total']} n_mature={s['n_mature']} n_pending={s['n_pending']} n_bets={s['n_bets']}")
    print(f"  hit_rate={s['hit_rate']} rank_ic={s['rank_ic']}")
