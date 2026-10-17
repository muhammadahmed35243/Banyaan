import Link from "next/link";
import NewSessionButton from "@/components/NewSessionButton";

const FEATURES = [
  {
    title: "Agent teams that work in parallel",
    body: "A planner splits your goal into researchers, analysts and writers. Independent parts run side by side; an analyst waits for the researchers it needs. Several goals can run in one session at once.",
  },
  {
    title: "Tools grown on demand, behind a gate",
    body: "When no tool fits, the Toolsmith writes one. A Builder, Tester and Critic check it in a sandbox, and nothing is loaded until a human approves the code.",
  },
  {
    title: "Watchers that keep running",
    body: "Say “any time I get a payment email, tell me”. A watcher reads your inbox read-only, raises alerts, can push to your phone via ntfy and forward alerts by email.",
  },
  {
    title: "You hold the keys",
    body: "Credentials go into an encrypted vault and agents never see them. Every secret, risky action and new tool waits for your decision, and answers say plainly when something was not done.",
  },
];

// Decorative four-point stars: few, mixed sizes, asymmetric, low opacity.
const STARS = [
  { top: "14%", left: "78%", size: 56, opacity: 0.22 },
  { top: "58%", left: "88%", size: 24, opacity: 0.18 },
  { top: "28%", left: "64%", size: 16, opacity: 0.14 },
  { top: "70%", left: "70%", size: 36, opacity: 0.1 },
];

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col">
      <section className="relative overflow-hidden bg-af-blue text-white">
        {STARS.map((s, i) => (
          <span key={i} aria-hidden className="af-star text-white"
            style={{ top: s.top, left: s.left, width: s.size, height: s.size, opacity: s.opacity }} />
        ))}
        <nav className="relative mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <span className="text-lg font-bold tracking-tight">🌳 Banyan</span>
          <Link href="/sessions" className="text-sm font-medium text-white/85 hover:text-white">Sessions →</Link>
        </nav>
        <div className="relative mx-auto max-w-6xl px-6 pb-20 pt-12 sm:pt-20">
          <h1 className="text-5xl font-bold tracking-tight sm:text-7xl">Banyan</h1>
          <p className="mt-4 max-w-2xl font-serif text-2xl italic text-white/90 sm:text-3xl">
            Agents that grow their own tools, with humans as the gatekeepers.
          </p>
          <p className="mt-6 max-w-2xl text-base text-white/85">
            Give it a goal. It plans a team of agents, runs them in parallel, builds missing tools in a
            sandbox, and stops for you at every decision that matters.
          </p>
          <div className="mt-10 flex flex-wrap gap-3">
            <Link href="/sessions"
              className="rounded-lg bg-white px-5 py-2.5 text-sm font-medium text-af-blue hover:bg-af-cream">
              Open sessions
            </Link>
            <NewSessionButton
              className="rounded-lg border border-white/70 px-5 py-2.5 text-sm font-medium text-white hover:bg-white/10">
              Start a new session
            </NewSessionButton>
          </div>
        </div>
      </section>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-16">
        <h2 className="text-3xl font-bold tracking-tight text-af-cream">What it does</h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-xl border border-slate-800 bg-slate-900 p-6">
              <h3 className="text-lg font-semibold text-af-cream">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-300">{f.body}</p>
            </div>
          ))}
        </div>
        <div className="mt-6 rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h3 className="text-lg font-semibold text-af-cream">See it live</h3>
          <p className="mt-2 text-sm leading-relaxed text-slate-300">
            Each session shows the agent tree as it grows, a <span className="text-af-medium">System map</span> of
            every message between agents, the LLM, tools and the vault, and a{" "}
            <span className="text-af-medium">Timeline</span> of who worked when. Talk to it with your voice, or
            press <code className="rounded bg-slate-800 px-1">▶ Demo</code> for a guided run.
          </p>
        </div>
      </main>

      <footer className="border-t border-slate-800 px-6 py-6 text-center text-xs text-slate-500">
        Deployed on Clouds by Alternate Futures
      </footer>
    </div>
  );
}
