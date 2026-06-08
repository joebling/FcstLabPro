"""crypto-market-data 适配器测试 — JSON→CSV 转换 / 缺仓库报错.

全部用 tmp_path 造假 JSON, 不碰真仓库/网络。
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.data import crypto_market_data as cmd


def _write_fake_repo(root, key, days=3):
    """在 tmp_path 造一个 crypto-market-data 风格的 JSON。"""
    src_name = cmd.DATASETS[key][0]
    daily = root / "data" / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    base = pd.Timestamp("2026-06-01")
    data = [
        {"timestamp": int((base + pd.Timedelta(days=i)).value // 1_000_000),
         "value": 1.0 + i, "last_modified": 0}
        for i in range(days)
    ]
    (daily / src_name).write_text(json.dumps({"name": key, "data": data}))


def test_convert_one_writes_csv(monkeypatch, tmp_path):
    repo = tmp_path / "crypto-market-data"
    _write_fake_repo(repo, "funding")
    monkeypatch.setattr(cmd, "repo_dir", lambda: repo)
    monkeypatch.setattr(cmd, "EXTERNAL_DIR", tmp_path / "ext")

    df = cmd.convert_one("funding")
    assert not df.empty
    # 列名必须是市场页要的
    assert "funding_rate_mean" in df.columns
    # 落盘文件存在且可被 date 索引读回
    out = tmp_path / "ext" / "cmd_funding.csv"
    assert out.exists()
    back = pd.read_csv(out, parse_dates=["date"]).set_index("date")
    assert len(back) == 3
    assert back.index.max().date().isoformat() == "2026-06-03"


def test_convert_one_dedups_and_sorts(monkeypatch, tmp_path):
    """重复日期取 last + 升序 — 防脏数据破坏 freshness 判定。"""
    repo = tmp_path / "crypto-market-data"
    daily = repo / "data" / "daily"
    daily.mkdir(parents=True)
    ts = int(pd.Timestamp("2026-06-01").value // 1_000_000)
    data = [
        {"timestamp": ts, "value": 1.0, "last_modified": 0},
        {"timestamp": ts, "value": 9.0, "last_modified": 0},  # dup, 应取这个
    ]
    (daily / "btc_open_interest.json").write_text(json.dumps({"data": data}))
    monkeypatch.setattr(cmd, "repo_dir", lambda: repo)
    monkeypatch.setattr(cmd, "EXTERNAL_DIR", tmp_path / "ext")

    df = cmd.convert_one("open_interest")
    assert len(df) == 1
    assert df["open_interest_usd"].iloc[-1] == 9.0


def test_convert_one_missing_repo_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(cmd, "repo_dir", lambda: tmp_path / "nope")
    with pytest.raises(FileNotFoundError):
        cmd.convert_one("taker_ratio")


def test_repo_dir_env_override(monkeypatch):
    monkeypatch.setenv("CRYPTO_MARKET_DATA_DIR", "/custom/path")
    assert str(cmd.repo_dir()) == "/custom/path"
