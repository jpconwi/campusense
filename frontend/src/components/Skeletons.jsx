/* Skeletons.jsx - shimmer placeholders that mirror the real layouts while data loads.
 * Pieces: Sk (one block), then page-shaped skeletons built from it.
 * Every skeleton is aria-hidden; the wrapper announces one polite "Loading" message. */

/** One shimmering block. w/h accept any CSS size; r = border radius. */
export function Sk({ w, h = 14, r, className = "", style }) {
  return <span className={"sk " + className} style={{ width: w, height: h, borderRadius: r, ...style }} aria-hidden="true" />;
}

function Heading({ intro = true }) {
  return (
    <div className="sk-heading" aria-hidden="true">
      <Sk h={30} w="min(260px, 60%)" r={8} />
      {intro && <Sk h={14} w="min(420px, 85%)" />}
    </div>
  );
}

function Toolbar() {
  return (
    <div className="sk-toolbar" aria-hidden="true">
      <Sk h={38} w="min(380px, 100%)" r={999} />
      <Sk h={14} w={70} />
    </div>
  );
}

export function TableSkeleton({ rows = 6, cols = 5, title = true, toolbar = true }) {
  return (
    <>
      {title && <Heading />}
      {toolbar && <Toolbar />}
      <div className="sk-table" aria-hidden="true">
        <div className="sk-tr sk-th">
          {Array.from({ length: cols }, (_, i) => <Sk key={i} h={12} w={`${50 + ((i * 17) % 40)}%`} />)}
        </div>
        {Array.from({ length: rows }, (_, r) => (
          <div className="sk-tr" key={r}>
            {Array.from({ length: cols }, (_, c) => (
              <Sk key={c} h={13} w={`${40 + ((r * 13 + c * 23) % 55)}%`} />
            ))}
          </div>
        ))}
      </div>
    </>
  );
}

function StatCards({ n = 8 }) {
  return (
    <div className="sk-stats" aria-hidden="true">
      {Array.from({ length: n }, (_, i) => (
        <div className="sk-card sk-stat" key={i}>
          <div className="sk-split"><Sk h={32} w={54} r={8} /><Sk h={38} w={38} r={11} /></div>
          <Sk h={12} w="70%" />
        </div>
      ))}
    </div>
  );
}

function TileGrid({ n = 5 }) {
  return (
    <div className="sk-tiles" aria-hidden="true">
      {Array.from({ length: n }, (_, i) => (
        <div className={"sk-card sk-tile" + (i === 0 ? " wide" : "")} key={i}>
          <Sk h={46} w={46} r={13} />
          <div className="sk-lines"><Sk h={15} w="55%" /><Sk h={12} w="85%" /></div>
        </div>
      ))}
    </div>
  );
}

export function HomeSkeleton() {
  return (
    <>
      <div className="sk-hero" aria-hidden="true">
        <Sk h={12} w={110} className="on-dark" />
        <Sk h={32} w="min(320px, 70%)" r={8} className="on-dark" />
        <Sk h={14} w="min(260px, 60%)" className="on-dark" />
        <div className="sk-split start"><Sk h={40} w={150} r={9} className="on-dark" /><Sk h={40} w={160} r={9} className="on-dark" /></div>
      </div>
      <TileGrid n={5} />
    </>
  );
}

export function DashboardSkeleton() {
  return (
    <>
      <Heading />
      <div className="sk-card sk-attn" aria-hidden="true"><Sk h={16} w={170} /><Sk h={26} w={120} r={999} /><Sk h={26} w={140} r={999} /></div>
      <StatCards n={8} />
      <div className="sk-card sk-chart" aria-hidden="true"><Sk h={18} w={220} /><Sk h={150} r={10} /></div>
      <div className="sk-charts" aria-hidden="true">
        {Array.from({ length: 4 }, (_, i) => (
          <div className="sk-card sk-chart" key={i}>
            <Sk h={18} w={150} />
            <div className="sk-split start"><Sk h={110} w={110} r={999} /><div className="sk-lines grow"><Sk h={12} /><Sk h={12} w="80%" /><Sk h={12} w="60%" /></div></div>
          </div>
        ))}
      </div>
    </>
  );
}

export function FormListSkeleton() {
  return (
    <>
      <Heading />
      <Sk h={40} w={150} r={9} style={{ marginBottom: 18 }} />
      <TableSkeleton rows={4} cols={5} title={false} toolbar={false} />
    </>
  );
}

export function ProfileSkeleton() {
  return (
    <>
      <Heading />
      <div className="sk-card" aria-hidden="true">
        {Array.from({ length: 5 }, (_, i) => (
          <div className="sk-split start sk-dl" key={i}><Sk h={14} w={120} /><Sk h={14} w={`${35 + i * 9}%`} /></div>
        ))}
      </div>
    </>
  );
}

/** Messages of an old chat while it is being opened. */
export function ChatSkeleton() {
  return (
    <div className="sk-chat" aria-hidden="true">
      <div className="sk-msg user"><Sk h={44} w="min(320px, 70%)" r={18} /></div>
      <div className="sk-msg"><Sk h={34} w={34} r={999} /><div className="sk-lines grow"><Sk h={14} w="90%" /><Sk h={14} w="75%" /><Sk h={14} w="40%" /></div></div>
      <div className="sk-msg user"><Sk h={40} w="min(240px, 55%)" r={18} /></div>
      <div className="sk-msg"><Sk h={34} w={34} r={999} /><div className="sk-lines grow"><Sk h={14} w="85%" /><Sk h={14} w="60%" /></div></div>
    </div>
  );
}

/** "AI is answering" bubble: three shimmering lines instead of dots. */
export function ReplySkeleton() {
  return (
    <span className="sk-reply" role="status" aria-label="NEMSAI is writing an answer">
      <Sk h={13} w={230} /><Sk h={13} w={170} /><Sk h={13} w={200} />
    </span>
  );
}

/** Sidebar chat list while it loads. */
export function HistorySkeleton({ n = 5 }) {
  return (
    <div className="sk-history" aria-hidden="true">
      {Array.from({ length: n }, (_, i) => <Sk key={i} h={30} w="100%" r={8} className="on-dark" style={{ opacity: 1 - i * 0.14 }} />)}
    </div>
  );
}

const VARIANTS = {
  table: () => <TableSkeleton />,
  dashboard: DashboardSkeleton,
  home: HomeSkeleton,
  form: FormListSkeleton,
  profile: ProfileSkeleton,
};

/** Whole-page skeleton. Screen readers hear `label` once. */
export function PageSkeleton({ variant = "table", label = "Loading...", wide }) {
  const Body = VARIANTS[variant] || VARIANTS.table;
  return (
    <div className="page" aria-busy="true" style={wide ? { maxWidth: wide } : undefined}>
      <span className="sr-only" role="status">{label}</span>
      <Body />
    </div>
  );
}

/** Whole app while the first sign-in check runs: sidebar + page skeleton. */
export function AppSkeleton() {
  return (
    <div className="shell" aria-busy="true">
      <aside className="sidebar sk-sidebar" aria-hidden="true">
        <div className="sb-top"><img src="/logo.png" alt="" /><div className="sb-brand"><strong>NEMSAI</strong><span>NEMSU Tandag</span></div></div>
        <Sk h={42} w="100%" r={12} className="on-dark" />
        <div className="sk-lines">
          {Array.from({ length: 6 }, (_, i) => <Sk key={i} h={36} w="100%" r={10} className="on-dark" />)}
        </div>
      </aside>
      <div className="main">
        <PageSkeleton variant="home" label="Loading NEMSAI..." />
      </div>
    </div>
  );
}
