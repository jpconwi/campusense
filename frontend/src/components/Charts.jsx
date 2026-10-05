/* Charts.jsx - plain SVG/CSS charts for the admin dashboard (no chart library). */

export function Donut({ chart }) {
  return (
    <div className="donut-box">
      <svg viewBox="0 0 42 42" className="donut" role="img" aria-label={`${chart.title}: ${chart.total} total`}>
        <title>{chart.title}</title>
        <circle cx="21" cy="21" r="15.9155" fill="none" stroke="#ecebff" strokeWidth="6" />
        {chart.segments.map((s) => (
          <circle key={s.label} cx="21" cy="21" r="15.9155" fill="none" stroke={s.color} strokeWidth="6"
                  strokeDasharray={`${s.dash} ${s.gap}`} strokeDashoffset={s.offset}>
            <title>{`${s.label}: ${s.count} (${s.pct}%)`}</title>
          </circle>
        ))}
        <text x="21" y="21.8" textAnchor="middle" className="donut-num">{chart.total}</text>
        <text x="21" y="26.4" textAnchor="middle" className="donut-lbl">total</text>
      </svg>
      <ul className="legend">
        {chart.segments.map((s) => (
          <li key={s.label}>
            <span className="dot" style={{ background: s.color }} />{s.label} <strong>{s.count}</strong> <em>({s.pct}%)</em>
          </li>
        ))}
        {chart.segments.length === 0 && <li className="empty">No data yet.</li>}
      </ul>
    </div>
  );
}

export function HBars({ items }) {
  if (!items.length) return <p className="empty">No data yet.</p>;
  return (
    <div className="hbars">
      {items.map((b) => (
        <div className="hbar-row" key={b.label}>
          <div className="hbar-label" title={b.label}>{b.label}</div>
          <div className="hbar-track"><div className="hbar-fill" style={{ width: `${b.width}%`, background: b.color }} /></div>
          <div className="hbar-num">{b.count}</div>
        </div>
      ))}
    </div>
  );
}

export function Trend({ t }) {
  return (
    <>
      <svg viewBox={`0 0 ${t.width} ${t.height}`} className="trend" role="img"
           aria-label={`Submissions per day over the last ${t.days} days, ${t.total} in total`}>
        {t.grid.map((g) => (
          <g key={g.y}>
            <line x1={t.left} x2={t.right} y1={g.y} y2={g.y} stroke="#e3e5f5" strokeWidth="1" />
            <text x={t.left - 6} y={g.y + 3.5} textAnchor="end" className="axis">{g.text}</text>
          </g>
        ))}
        {t.rects.map((r, i) => (
          <rect key={i} x={r.x} y={r.y} width={r.w} height={r.h} fill={r.color} rx="2"><title>{r.tip}</title></rect>
        ))}
        {t.labels.map((l) => (
          <text key={l.x} x={l.x} y={t.label_y} textAnchor="middle" className="axis">{l.text}</text>
        ))}
      </svg>
      <ul className="legend inline">
        {t.legend.map((l) => <li key={l.name}><span className="dot" style={{ background: l.color }} />{l.name}</li>)}
      </ul>
    </>
  );
}
