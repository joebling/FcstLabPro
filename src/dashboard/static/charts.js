/* FcstLabPro 图表封装 — 集中 Chart.js 逻辑 (DRY).
   各页把数据放进 <script type="application/json"> 标签, 这里读取渲染. */
const FcstCharts = (function () {
  const INDIGO = '#4f46e5', VIOLET = '#8b5cf6', EMERALD = '#10b981',
        ROSE = '#f43f5e', AMBER = '#f59e0b';

  function _data(id) {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  }

  const BASE_OPTS = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { labels: { boxWidth: 12, font: { size: 11 } } } },
    scales: {
      x: { ticks: { maxTicksLimit: 8, font: { size: 10 } }, grid: { display: false } },
      y: { ticks: { font: { size: 10 } }, grid: { color: '#f1f5f9' } }
    }
  };

  function line(canvasId, labels, datasets, extra) {
    const el = document.getElementById(canvasId);
    if (!el) return;
    const opts = Object.assign({}, BASE_OPTS, extra || {});
    new Chart(el, { type: 'line', data: { labels, datasets }, options: opts });
  }

  function ds(label, data, color, fill) {
    return {
      label, data, borderColor: color,
      backgroundColor: fill ? color + '14' : color,
      fill: !!fill, pointRadius: 0, borderWidth: 2, tension: 0.2
    };
  }

  // ---- 总览页 ----
  function renderOverview() {
    const d = _data('ov-data');
    if (!d) return;

    const pc = document.getElementById('priceChart');
    if (pc) {
      new Chart(pc, {
        data: {
          labels: d.dates,
          datasets: [
            Object.assign(ds('收盘价', d.close, INDIGO, true), { type: 'line' }),
            { type: 'scatter', label: 'BUY 信号', data: d.buy,
              borderColor: EMERALD, backgroundColor: EMERALD,
              pointRadius: 6, pointStyle: 'triangle' }
          ]
        },
        options: BASE_OPTS
      });
    }

    const dc = document.getElementById('distChart');
    if (dc && d.dist) {
      const labels = Object.keys(d.dist), vals = Object.values(d.dist);
      const colors = labels.map(l => l === 'BUY' ? EMERALD : '#cbd5e1');
      new Chart(dc, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: vals, backgroundColor: colors, borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '62%',
                   plugins: { legend: { position: 'bottom', labels: { font: { size: 11 } } } } }
      });
    }
  }

  // ---- 市场页 ----
  function renderMarket() {
    const d = _data('mkt-data');
    if (!d) return;
    line('mktPrice', d.price.dates, [ds('BTC 收盘价', d.price.close, INDIGO, true)]);
    line('mktFgi', d.fgi.dates, [ds('FGI', d.fgi.series, VIOLET, true)]);
    line('mktFunding', d.funding.dates, [ds('资金费率', d.funding.series, AMBER, false)]);
    line('mktLs', d.long_short.dates, [ds('多空比', d.long_short.series, EMERALD, false)]);
    line('mktOi', d.open_interest.dates, [ds('持仓量(USD)', d.open_interest.series, INDIGO, true)]);
    if (d.macro) {
      line('mktMacro', d.macro.dxy.dates, [
        ds('DXY', d.macro.dxy.series, INDIGO, false),
        ds('VIX', d.macro.vix.series, ROSE, false),
        ds('Gold', d.macro.gold.series, AMBER, false)
      ]);
    }
  }

  // ---- 信号页 (IC/命中率时序由批次表驱动, 暂用 batches) ----
  function renderSignals() {
    const d = _data('sig-data');
    if (!d || !d.batches) return;
    const rows = d.batches.slice().reverse();  // 时间正序
    const labels = rows.map(r => r.score_date);
    const hit = rows.map(r => r.hit_rate);
    const ret = rows.map(r => r.avg_realized_return);
    line('sigChart', labels, [
      ds('命中率%', hit, EMERALD, false),
      ds('实现收益%', ret, INDIGO, false)
    ]);
  }

  return { renderOverview, renderMarket, renderSignals };
})();
