import { useState, useEffect, useRef } from "react";

// ============================================================
// DESIGN TOKENS
// ============================================================
const tokens = {
  colors: {
    bg0: "#080A0F",
    bg1: "#0C0F18",
    bg2: "#111520",
    bg3: "#161B2E",
    surface1: "#1A2035",
    surface2: "#1F2640",
    border1: "rgba(255,255,255,0.06)",
    border2: "rgba(255,255,255,0.10)",
    borderAccent: "rgba(99,179,237,0.25)",
    text1: "#F0F4FF",
    text2: "#A8B4CC",
    text3: "#5A6580",
    accent: "#63B3ED",
    accentGlow: "rgba(99,179,237,0.18)",
    accentSoft: "rgba(99,179,237,0.10)",
    green: "#68D391",
    greenGlow: "rgba(104,211,145,0.18)",
    amber: "#F6AD55",
    amberGlow: "rgba(246,173,85,0.18)",
    red: "#FC8181",
    redGlow: "rgba(252,129,129,0.22)",
    purple: "#B794F4",
    purpleGlow: "rgba(183,148,244,0.18)",
    normal: "#68D391",
    highLoad: "#F6AD55",
    fatigue: "#B794F4",
    risk: "#FC8181",
  },
  radii: { sm: "8px", md: "14px", lg: "20px", xl: "28px", pill: "999px" },
  font: {
    display: "'Instrument Serif', Georgia, serif",
    ui: "'DM Sans', system-ui, sans-serif",
    mono: "'JetBrains Mono', 'Fira Code', monospace",
  },
};

// ============================================================
// SAMPLE DATA
// ============================================================
const cognitiveHistory = [
  { time: "09:00", score: 28, state: "Normal" },
  { time: "09:30", score: 34, state: "Normal" },
  { time: "10:00", score: 45, state: "Normal" },
  { time: "10:30", score: 62, state: "High Load" },
  { time: "11:00", score: 71, state: "High Load" },
  { time: "11:30", score: 58, state: "High Load" },
  { time: "12:00", score: 40, state: "Normal" },
  { time: "12:30", score: 35, state: "Normal" },
  { time: "13:00", score: 42, state: "Normal" },
  { time: "13:30", score: 55, state: "High Load" },
  { time: "14:00", score: 78, state: "Fatigue" },
  { time: "14:30", score: 82, state: "Fatigue" },
  { time: "15:00", score: 67, state: "High Load" },
];

const liveMetrics = [
  { label: "Keystrokes/min", value: "84", delta: "+12%", up: true, icon: "⌨" },
  { label: "Error Rate", value: "3.2%", delta: "+0.8%", up: false, icon: "⚠" },
  { label: "Break Gap", value: "94 min", delta: "−18 min", up: false, icon: "⏱" },
  { label: "Focus Depth", value: "0.61", delta: "−0.14", up: false, icon: "◎" },
];

const explanationItems = [
  { label: "Sustained focus", weight: 38, dir: "↑" },
  { label: "Error frequency", weight: 27, dir: "↑" },
  { label: "Break deprivation", weight: 22, dir: "↑" },
  { label: "Typing cadence shift", weight: 13, dir: "↑" },
];

const alertHistory = [
  { time: "14:32", type: "Fatigue", msg: "90+ min without break. Cognitive efficiency declining.", resolved: false },
  { time: "11:17", type: "High Load", msg: "Elevated load sustained for 45 min.", resolved: true },
  { time: "09:52", type: "Normal", msg: "Baseline restored after morning break.", resolved: true },
];

const coachMessages = [
  { role: "ai", text: "Your load has been elevated for 94 minutes. Your error rate is up 0.8% — a reliable early signal. A 10-minute walk now will likely recover 30+ minutes of deep focus later." },
  { role: "user", text: "I'm in the middle of something important." },
  { role: "ai", text: "Understood. Try a 2-minute breathing reset at your desk — box breathing (4-4-4-4) activates your parasympathetic nervous system quickly. I'll check back in 15 minutes." },
];

const weeklyData = [
  { day: "Mon", avg: 42, peak: 68 },
  { day: "Tue", avg: 56, peak: 81 },
  { day: "Wed", avg: 38, peak: 55 },
  { day: "Thu", avg: 67, peak: 89 },
  { day: "Fri", avg: 71, peak: 94 },
  { day: "Sat", avg: 29, peak: 41 },
  { day: "Sun", avg: 22, peak: 35 },
];

const insightCards = [
  { title: "Peak Fatigue Window", body: "You consistently hit peak cognitive load between 13:30–15:00. Block lower-stakes work here.", icon: "🕑", color: tokens.colors.amber },
  { title: "Break Consistency", body: "Only 2 of 6 scheduled breaks taken today. Consider shorter, more frequent micro-breaks.", icon: "⏸", color: tokens.colors.purple },
  { title: "Morning Advantage", body: "Your 09:00–11:00 window shows lowest load and highest focus depth — protect it fiercely.", icon: "☀", color: tokens.colors.green },
  { title: "Error Pattern", body: "Error rate spikes after 80-min focus blocks. This is your personal cognitive limit signal.", icon: "◈", color: tokens.colors.accent },
];

const privacyToggles = [
  { label: "Keystroke cadence analysis", desc: "Timing patterns only. No content captured.", on: true },
  { label: "Screen activity inference", desc: "App-switch frequency. No screenshots.", on: true },
  { label: "Behavioral baseline sync", desc: "Helps calibrate your personal normal.", on: true },
  { label: "AI coach personalization", desc: "Coach learns from your response patterns.", on: false },
  { label: "Anonymous aggregate insights", desc: "Opt into improving models for everyone.", on: false },
];

// ============================================================
// UTILITY
// ============================================================
function getStateColor(state) {
  if (state === "Normal") return tokens.colors.normal;
  if (state === "High Load") return tokens.colors.highLoad;
  if (state === "Fatigue") return tokens.colors.fatigue;
  if (state === "Risk") return tokens.colors.risk;
  return tokens.colors.accent;
}

function getStateGlow(state) {
  if (state === "Normal") return tokens.colors.greenGlow;
  if (state === "High Load") return tokens.colors.amberGlow;
  if (state === "Fatigue") return tokens.colors.purpleGlow;
  if (state === "Risk") return tokens.colors.redGlow;
  return tokens.colors.accentGlow;
}

function useAnimatedValue(target, duration = 1200) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    let start = null;
    const from = value;
    const step = (ts) => {
      if (!start) start = ts;
      const p = Math.min((ts - start) / duration, 1);
      const ease = 1 - Math.pow(1 - p, 4);
      setValue(Math.round(from + (target - from) * ease));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target]);
  return value;
}

// ============================================================
// GLOBAL STYLES
// ============================================================
const GlobalStyle = () => (
  <style>{`
    @import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    html { background: ${tokens.colors.bg0}; color: ${tokens.colors.text1}; font-family: ${tokens.font.ui}; font-size: 15px; -webkit-font-smoothing: antialiased; }

    :root {
      --bg0: ${tokens.colors.bg0};
      --bg1: ${tokens.colors.bg1};
      --bg2: ${tokens.colors.bg2};
      --surface1: ${tokens.colors.surface1};
      --border1: ${tokens.colors.border1};
      --text1: ${tokens.colors.text1};
      --text2: ${tokens.colors.text2};
      --text3: ${tokens.colors.text3};
      --accent: ${tokens.colors.accent};
    }

    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(16px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes pulse-ring {
      0%, 100% { box-shadow: 0 0 0 0 var(--glow-color, rgba(99,179,237,0.4)); }
      50% { box-shadow: 0 0 0 12px transparent; }
    }
    @keyframes spin-slow {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
    @keyframes drawLine {
      from { stroke-dashoffset: 1000; }
      to { stroke-dashoffset: 0; }
    }
    @keyframes glowPulse {
      0%, 100% { opacity: 0.6; }
      50% { opacity: 1; }
    }
    @keyframes shimmer {
      0% { background-position: -200% 0; }
      100% { background-position: 200% 0; }
    }
    @keyframes slideInRight {
      from { opacity: 0; transform: translateX(20px); }
      to { opacity: 1; transform: translateX(0); }
    }
    @keyframes scoreCount {
      from { opacity: 0; transform: scale(0.85); }
      to { opacity: 1; transform: scale(1); }
    }

    .fade-up { animation: fadeUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both; }
    .fade-in { animation: fadeIn 0.4s ease both; }

    button { cursor: pointer; border: none; background: none; font-family: inherit; }
    input, textarea { font-family: inherit; }
  `}</style>
);

// ============================================================
// LOADING SCREEN
// ============================================================
function LoadingScreen({ onDone }) {
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    const t = setInterval(() => {
      setProgress(p => {
        if (p >= 100) { clearInterval(t); setTimeout(onDone, 400); return 100; }
        return p + (p < 60 ? 1.8 : p < 85 ? 1.2 : 0.8);
      });
    }, 30);
    const t2 = setTimeout(() => setPhase(1), 800);
    const t3 = setTimeout(() => setPhase(2), 1600);
    return () => { clearInterval(t); clearTimeout(t2); clearTimeout(t3); };
  }, []);

  return (
    <div style={{
      position: "fixed", inset: 0, background: tokens.colors.bg0,
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      zIndex: 9999, overflow: "hidden",
    }}>
      {/* Ambient glow */}
      <div style={{
        position: "absolute", top: "30%", left: "50%", transform: "translate(-50%,-50%)",
        width: 600, height: 600, borderRadius: "50%",
        background: "radial-gradient(circle, rgba(99,179,237,0.08) 0%, transparent 70%)",
        animation: "glowPulse 3s ease-in-out infinite",
      }} />
      <div style={{
        position: "absolute", bottom: "20%", right: "25%",
        width: 400, height: 400, borderRadius: "50%",
        background: "radial-gradient(circle, rgba(183,148,244,0.06) 0%, transparent 70%)",
        animation: "glowPulse 4s ease-in-out infinite 1s",
      }} />

      {/* Logo */}
      <div style={{
        opacity: phase >= 0 ? 1 : 0,
        transform: phase >= 0 ? "translateY(0)" : "translateY(20px)",
        transition: "all 0.8s cubic-bezier(0.16,1,0.3,1)",
        textAlign: "center", marginBottom: 48,
      }}>
        {/* Eye icon */}
        <div style={{ position: "relative", display: "inline-block", marginBottom: 24 }}>
          <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
            <circle cx="32" cy="32" r="30" stroke={tokens.colors.accent} strokeWidth="1" strokeOpacity="0.3" />
            <circle cx="32" cy="32" r="22" stroke={tokens.colors.accent} strokeWidth="0.5" strokeOpacity="0.2"
              strokeDasharray="4 4" style={{ animation: "spin-slow 20s linear infinite" }} />
            <ellipse cx="32" cy="32" rx="20" ry="12" stroke={tokens.colors.accent} strokeWidth="1.5"
              style={{ animation: "glowPulse 2s ease-in-out infinite" }} />
            <circle cx="32" cy="32" r="6" fill={tokens.colors.accent} fillOpacity="0.9" />
            <circle cx="32" cy="32" r="10" stroke={tokens.colors.accent} strokeWidth="0.8" strokeOpacity="0.5" />
          </svg>
        </div>
        <div style={{
          fontFamily: tokens.font.display, fontSize: 36, fontWeight: 400,
          color: tokens.colors.text1, letterSpacing: "-0.02em",
          opacity: phase >= 1 ? 1 : 0, transform: phase >= 1 ? "translateY(0)" : "translateY(10px)",
          transition: "all 0.6s cubic-bezier(0.16,1,0.3,1) 0.2s",
        }}>
          NeuroLens <span style={{ color: tokens.colors.accent, fontStyle: "italic" }}>AI</span>
        </div>
        <div style={{
          fontFamily: tokens.font.ui, fontSize: 12, fontWeight: 400, letterSpacing: "0.18em",
          color: tokens.colors.text3, textTransform: "uppercase", marginTop: 8,
          opacity: phase >= 2 ? 1 : 0,
          transition: "opacity 0.6s ease 0.3s",
        }}>
          Cognitive Load Intelligence
        </div>
      </div>

      {/* Progress bar */}
      <div style={{ width: 240, opacity: phase >= 1 ? 1 : 0, transition: "opacity 0.4s ease 0.5s" }}>
        <div style={{
          width: "100%", height: 1, background: tokens.colors.border1,
          borderRadius: 1, overflow: "hidden",
        }}>
          <div style={{
            height: "100%", width: `${progress}%`,
            background: `linear-gradient(90deg, ${tokens.colors.accent}, ${tokens.colors.purple})`,
            transition: "width 0.1s linear",
            boxShadow: `0 0 8px ${tokens.colors.accentGlow}`,
          }} />
        </div>
        <div style={{
          display: "flex", justifyContent: "space-between", marginTop: 10,
          fontSize: 11, color: tokens.colors.text3, fontFamily: tokens.font.mono,
        }}>
          <span>Initializing sensors</span>
          <span>{Math.round(progress)}%</span>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// ONBOARDING
// ============================================================
const onboardingSteps = [
  {
    id: "welcome",
    title: "Understand your mind,\nnot just your metrics.",
    sub: "NeuroLens reads subtle behavioral patterns to detect cognitive load and fatigue — before they affect your work.",
    type: "intro",
  },
  {
    id: "role",
    title: "What best describes your work?",
    sub: "Your baseline is shaped by how you work.",
    type: "choice",
    choices: [
      { value: "student", label: "Student", desc: "Study sessions, exams, deep learning" },
      { value: "developer", label: "Developer", desc: "Code, debugging, system design" },
      { value: "office", label: "Office Worker", desc: "Meetings, documents, communication" },
    ],
  },
  {
    id: "sleep",
    title: "How did you sleep last night?",
    sub: "Sleep quality is the strongest predictor of cognitive baseline.",
    type: "scale",
    options: ["< 5 hrs", "5–6 hrs", "6–7 hrs", "7–8 hrs", "8+ hrs"],
    field: "sleep",
  },
  {
    id: "stress",
    title: "Current stress level?",
    sub: "Chronic stress shifts your cognitive load threshold.",
    type: "scale",
    options: ["Very low", "Low", "Moderate", "High", "Very high"],
    field: "stress",
  },
  {
    id: "privacy",
    title: "Your data stays yours.",
    sub: "Everything is processed locally. We never read content — only timing patterns and behavioral signals.",
    type: "privacy",
  },
  {
    id: "done",
    title: "Baseline captured.",
    sub: "NeuroLens will calibrate to your personal patterns over the next 24 hours. Let's begin.",
    type: "done",
  },
];

function OnboardingFlow({ onDone }) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState({});
  const [selected, setSelected] = useState(null);
  const [animKey, setAnimKey] = useState(0);

  const current = onboardingSteps[step];
  const progress = ((step) / (onboardingSteps.length - 1)) * 100;

  const next = () => {
    setAnimKey(k => k + 1);
    setSelected(null);
    if (step < onboardingSteps.length - 1) setStep(s => s + 1);
    else onDone();
  };

  const canNext = current.type === "intro" || current.type === "privacy" || current.type === "done" || selected !== null;

  return (
    <div style={{
      minHeight: "100vh", background: tokens.colors.bg0,
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      padding: "24px 16px", position: "relative", overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 2,
        background: tokens.colors.bg2,
      }}>
        <div style={{
          height: "100%", width: `${progress}%`,
          background: `linear-gradient(90deg, ${tokens.colors.accent}, ${tokens.colors.purple})`,
          transition: "width 0.5s cubic-bezier(0.16,1,0.3,1)",
        }} />
      </div>

      {/* Step indicator */}
      <div style={{
        position: "absolute", top: 20, right: 24,
        fontSize: 12, color: tokens.colors.text3, fontFamily: tokens.font.mono,
      }}>
        {step + 1} / {onboardingSteps.length}
      </div>

      <div key={animKey} style={{
        width: "100%", maxWidth: 560,
        animation: "fadeUp 0.5s cubic-bezier(0.16,1,0.3,1) both",
      }}>
        {/* Card */}
        <div style={{
          background: tokens.colors.bg2,
          border: `1px solid ${tokens.colors.border1}`,
          borderRadius: tokens.radii.xl,
          padding: "48px 40px",
          backdropFilter: "blur(20px)",
        }}>
          {current.type === "intro" && (
            <div style={{ textAlign: "center" }}>
              <div style={{
                width: 56, height: 56, borderRadius: "50%",
                background: tokens.colors.accentSoft,
                border: `1px solid ${tokens.colors.borderAccent}`,
                display: "flex", alignItems: "center", justifyContent: "center",
                margin: "0 auto 32px",
                fontSize: 24,
              }}>◎</div>
              <h1 style={{
                fontFamily: tokens.font.display, fontSize: 32, fontWeight: 400,
                color: tokens.colors.text1, lineHeight: 1.25, marginBottom: 16,
                whiteSpace: "pre-line",
              }}>{current.title}</h1>
              <p style={{ fontSize: 15, color: tokens.colors.text2, lineHeight: 1.7 }}>{current.sub}</p>
            </div>
          )}

          {current.type === "choice" && (
            <div>
              <h2 style={{
                fontFamily: tokens.font.display, fontSize: 26, fontWeight: 400,
                color: tokens.colors.text1, marginBottom: 8,
              }}>{current.title}</h2>
              <p style={{ fontSize: 14, color: tokens.colors.text3, marginBottom: 28 }}>{current.sub}</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {current.choices.map(c => (
                  <button key={c.value} onClick={() => setSelected(c.value)} style={{
                    padding: "16px 20px",
                    background: selected === c.value ? tokens.colors.accentSoft : tokens.colors.surface1,
                    border: `1px solid ${selected === c.value ? tokens.colors.borderAccent : tokens.colors.border1}`,
                    borderRadius: tokens.radii.md,
                    textAlign: "left", transition: "all 0.2s ease",
                    cursor: "pointer",
                  }}>
                    <div style={{ fontSize: 15, fontWeight: 500, color: selected === c.value ? tokens.colors.accent : tokens.colors.text1 }}>
                      {c.label}
                    </div>
                    <div style={{ fontSize: 13, color: tokens.colors.text3, marginTop: 3 }}>{c.desc}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {current.type === "scale" && (
            <div>
              <h2 style={{
                fontFamily: tokens.font.display, fontSize: 26, fontWeight: 400,
                color: tokens.colors.text1, marginBottom: 8,
              }}>{current.title}</h2>
              <p style={{ fontSize: 14, color: tokens.colors.text3, marginBottom: 28 }}>{current.sub}</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {current.options.map((opt, i) => (
                  <button key={opt} onClick={() => setSelected(i)} style={{
                    padding: "14px 18px",
                    background: selected === i ? tokens.colors.accentSoft : tokens.colors.surface1,
                    border: `1px solid ${selected === i ? tokens.colors.borderAccent : tokens.colors.border1}`,
                    borderRadius: tokens.radii.md,
                    textAlign: "left",
                    fontSize: 14, fontWeight: 400,
                    color: selected === i ? tokens.colors.accent : tokens.colors.text2,
                    transition: "all 0.2s ease",
                    cursor: "pointer",
                  }}>{opt}</button>
                ))}
              </div>
            </div>
          )}

          {current.type === "privacy" && (
            <div>
              <div style={{
                width: 48, height: 48, borderRadius: tokens.radii.md,
                background: tokens.colors.greenGlow,
                border: `1px solid rgba(104,211,145,0.2)`,
                display: "flex", alignItems: "center", justifyContent: "center",
                marginBottom: 24, fontSize: 22,
              }}>🔒</div>
              <h2 style={{
                fontFamily: tokens.font.display, fontSize: 26, fontWeight: 400,
                color: tokens.colors.text1, marginBottom: 12,
              }}>{current.title}</h2>
              <p style={{ fontSize: 14, color: tokens.colors.text2, lineHeight: 1.7, marginBottom: 24 }}>{current.sub}</p>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {[
                  ["✓", "No keystrokes or content ever captured"],
                  ["✓", "All analysis runs locally on your device"],
                  ["✓", "You control what syncs, if anything"],
                ].map(([icon, text]) => (
                  <div key={text} style={{ display: "flex", gap: 12, alignItems: "center" }}>
                    <span style={{ color: tokens.colors.green, fontWeight: 600, fontSize: 14 }}>{icon}</span>
                    <span style={{ fontSize: 14, color: tokens.colors.text2 }}>{text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {current.type === "done" && (
            <div style={{ textAlign: "center" }}>
              <div style={{
                width: 64, height: 64, borderRadius: "50%",
                background: tokens.colors.greenGlow,
                border: `1px solid rgba(104,211,145,0.25)`,
                display: "flex", alignItems: "center", justifyContent: "center",
                margin: "0 auto 28px", fontSize: 28,
              }}>✓</div>
              <h2 style={{
                fontFamily: tokens.font.display, fontSize: 28, fontWeight: 400,
                color: tokens.colors.text1, marginBottom: 12,
              }}>{current.title}</h2>
              <p style={{ fontSize: 15, color: tokens.colors.text2, lineHeight: 1.7 }}>{current.sub}</p>
            </div>
          )}
        </div>

        {/* CTA */}
        <div style={{ marginTop: 20, display: "flex", justifyContent: "center" }}>
          <button onClick={canNext ? next : undefined} style={{
            padding: "14px 40px",
            background: canNext
              ? `linear-gradient(135deg, ${tokens.colors.accent}, rgba(99,179,237,0.7))`
              : tokens.colors.surface1,
            border: `1px solid ${canNext ? tokens.colors.borderAccent : tokens.colors.border1}`,
            borderRadius: tokens.radii.pill,
            color: canNext ? "#fff" : tokens.colors.text3,
            fontSize: 14, fontWeight: 500, letterSpacing: "0.02em",
            transition: "all 0.25s ease",
            opacity: canNext ? 1 : 0.5,
            boxShadow: canNext ? `0 0 24px ${tokens.colors.accentGlow}` : "none",
          }}>
            {current.type === "done" ? "Open Dashboard →" : "Continue"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// SCORE RING
// ============================================================
function ScoreRing({ score, state, size = 220 }) {
  const animated = useAnimatedValue(score, 1400);
  const color = getStateColor(state);
  const glow = getStateGlow(state);
  const r = (size / 2) - 18;
  const circ = 2 * Math.PI * r;
  const dash = (animated / 100) * circ;

  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke={tokens.colors.border2} strokeWidth="3" />
        <circle cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke={color} strokeWidth="3.5"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circ}`}
          style={{
            transition: "stroke-dasharray 0.8s cubic-bezier(0.16,1,0.3,1)",
            filter: `drop-shadow(0 0 8px ${color})`,
          }}
        />
        {/* Outer glow ring */}
        <circle cx={size / 2} cy={size / 2} r={r + 10}
          fill="none" stroke={color} strokeWidth="0.5" strokeOpacity="0.15" />
      </svg>
      {/* Center content */}
      <div style={{
        position: "absolute", inset: 0,
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      }}>
        <div style={{
          fontFamily: tokens.font.display, fontSize: 56, fontWeight: 400,
          color: tokens.colors.text1, lineHeight: 1,
          animation: "scoreCount 0.6s cubic-bezier(0.16,1,0.3,1) both",
        }}>
          {animated}
        </div>
        <div style={{ fontSize: 11, color: tokens.colors.text3, letterSpacing: "0.1em", marginTop: 4 }}>
          LOAD SCORE
        </div>
        <div style={{
          marginTop: 12, padding: "4px 14px",
          background: `${glow}`,
          border: `1px solid ${color}30`,
          borderRadius: tokens.radii.pill,
          fontSize: 12, fontWeight: 500, color: color,
          letterSpacing: "0.04em",
        }}>
          {state}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// TREND CHART (SVG)
// ============================================================
function TrendChart({ data }) {
  const [drawn, setDrawn] = useState(false);
  const width = 100, height = 60;
  const maxVal = Math.max(...data.map(d => d.score));
  const minVal = Math.min(...data.map(d => d.score));

  const pts = data.map((d, i) => ({
    x: (i / (data.length - 1)) * width,
    y: height - ((d.score - minVal) / (maxVal - minVal + 1)) * (height - 8) - 4,
  }));

  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const area = `${line} L ${pts[pts.length - 1].x} ${height} L ${pts[0].x} ${height} Z`;

  useEffect(() => { const t = setTimeout(() => setDrawn(true), 400); return () => clearTimeout(t); }, []);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "100%", overflow: "visible" }}>
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={tokens.colors.accent} stopOpacity="0.18" />
          <stop offset="100%" stopColor={tokens.colors.accent} stopOpacity="0" />
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      {drawn && <path d={area} fill="url(#areaGrad)" />}
      <path d={line} fill="none" stroke={tokens.colors.accent} strokeWidth="1.5"
        strokeLinecap="round" strokeLinejoin="round"
        filter="url(#glow)"
        strokeDasharray="1000"
        strokeDashoffset={drawn ? 0 : 1000}
        style={{ transition: "stroke-dashoffset 1.2s cubic-bezier(0.16,1,0.3,1)" }}
      />
      {pts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="1.5"
          fill={getStateColor(data[i].state)}
          opacity={drawn ? 0.9 : 0}
          style={{ transition: `opacity 0.3s ease ${0.8 + i * 0.04}s` }}
        />
      ))}
    </svg>
  );
}

// ============================================================
// MINI BAR CHART
// ============================================================
function WeeklyBarChart({ data }) {
  const [shown, setShown] = useState(false);
  useEffect(() => { const t = setTimeout(() => setShown(true), 600); return () => clearTimeout(t); }, []);

  const max = Math.max(...data.map(d => d.peak));
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 80, padding: "0 4px" }}>
      {data.map((d, i) => (
        <div key={d.day} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
          <div style={{ width: "100%", flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", gap: 2 }}>
            <div style={{
              width: "100%", borderRadius: "3px 3px 0 0",
              background: `linear-gradient(180deg, ${tokens.colors.accent}50, ${tokens.colors.accent}20)`,
              height: shown ? `${(d.avg / max) * 60}px` : "0px",
              transition: `height 0.6s cubic-bezier(0.16,1,0.3,1) ${i * 0.06}s`,
            }} />
            <div style={{
              width: "100%", borderRadius: "3px 3px 0 0",
              background: `linear-gradient(180deg, ${tokens.colors.accent}, ${tokens.colors.accent}80)`,
              height: shown ? `${((d.peak - d.avg) / max) * 60}px` : "0px",
              transition: `height 0.6s cubic-bezier(0.16,1,0.3,1) ${i * 0.06 + 0.1}s`,
              boxShadow: `0 -2px 8px ${tokens.colors.accentGlow}`,
            }} />
          </div>
          <span style={{ fontSize: 10, color: tokens.colors.text3, letterSpacing: "0.02em" }}>{d.day}</span>
        </div>
      ))}
    </div>
  );
}

// ============================================================
// METRIC CARD
// ============================================================
function MetricCard({ metric, delay = 0 }) {
  const isUp = metric.up;
  const goodDirection = metric.label === "Focus Depth" || metric.label === "Break Gap";
  const isGood = goodDirection ? isUp : !isUp;

  return (
    <div style={{
      background: tokens.colors.surface1,
      border: `1px solid ${tokens.colors.border1}`,
      borderRadius: tokens.radii.lg,
      padding: "18px 20px",
      animation: `fadeUp 0.5s cubic-bezier(0.16,1,0.3,1) ${delay}s both`,
      transition: "border-color 0.2s, box-shadow 0.2s",
    }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = tokens.colors.borderAccent;
        e.currentTarget.style.boxShadow = `0 4px 24px ${tokens.colors.accentGlow}`;
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = tokens.colors.border1;
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ fontSize: 11, color: tokens.colors.text3, letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 8 }}>
            {metric.label}
          </div>
          <div style={{
            fontFamily: tokens.font.mono, fontSize: 26, fontWeight: 500,
            color: tokens.colors.text1, lineHeight: 1,
          }}>
            {metric.value}
          </div>
        </div>
        <div style={{
          padding: "4px 10px", borderRadius: tokens.radii.pill,
          background: isGood ? tokens.colors.greenGlow : tokens.colors.amberGlow,
          border: `1px solid ${isGood ? "rgba(104,211,145,0.2)" : "rgba(246,173,85,0.2)"}`,
          fontSize: 11, fontWeight: 500,
          color: isGood ? tokens.colors.green : tokens.colors.amber,
          fontFamily: tokens.font.mono,
        }}>
          {metric.delta}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// EXPLANATION PANEL
// ============================================================
function ExplanationPanel() {
  return (
    <div style={{
      background: tokens.colors.surface1,
      border: `1px solid ${tokens.colors.border1}`,
      borderRadius: tokens.radii.lg, padding: "20px 22px",
      animation: "fadeUp 0.5s cubic-bezier(0.16,1,0.3,1) 0.15s both",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
        <div style={{
          width: 6, height: 6, borderRadius: "50%",
          background: tokens.colors.amber,
          boxShadow: `0 0 6px ${tokens.colors.amber}`,
          animation: "glowPulse 2s ease-in-out infinite",
        }} />
        <span style={{ fontSize: 12, fontWeight: 500, color: tokens.colors.text2, letterSpacing: "0.04em" }}>
          Why this score?
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {explanationItems.map((item, i) => (
          <div key={item.label}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, alignItems: "center" }}>
              <span style={{ fontSize: 13, color: tokens.colors.text2 }}>{item.label}</span>
              <span style={{ fontSize: 12, color: tokens.colors.amber, fontFamily: tokens.font.mono }}>
                {item.weight}% {item.dir}
              </span>
            </div>
            <div style={{ height: 3, background: tokens.colors.border1, borderRadius: 2, overflow: "hidden" }}>
              <div style={{
                height: "100%",
                width: `${item.weight * 2.5}%`,
                background: `linear-gradient(90deg, ${tokens.colors.amber}, ${tokens.colors.amber}80)`,
                borderRadius: 2,
                animation: `fadeUp 0.5s ease ${0.3 + i * 0.1}s both`,
                boxShadow: `0 0 4px ${tokens.colors.amberGlow}`,
              }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// ALERT PANEL
// ============================================================
function AlertPanel({ onDismiss }) {
  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24,
      width: 360, zIndex: 1000,
      animation: "slideInRight 0.4s cubic-bezier(0.16,1,0.3,1) both",
    }}>
      <div style={{
        background: tokens.colors.bg2,
        border: `1px solid rgba(183,148,244,0.3)`,
        borderRadius: tokens.radii.xl,
        padding: "24px",
        backdropFilter: "blur(20px)",
        boxShadow: `0 8px 48px rgba(0,0,0,0.5), 0 0 40px ${tokens.colors.purpleGlow}`,
      }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 8, height: 8, borderRadius: "50%",
              background: tokens.colors.purple,
              boxShadow: `0 0 8px ${tokens.colors.purple}`,
              animation: "glowPulse 1.5s ease-in-out infinite",
            }} />
            <span style={{ fontSize: 11, fontWeight: 600, color: tokens.colors.purple, letterSpacing: "0.1em", textTransform: "uppercase" }}>
              Fatigue Detected
            </span>
          </div>
          <button onClick={onDismiss} style={{
            width: 24, height: 24, borderRadius: "50%",
            background: tokens.colors.border1, color: tokens.colors.text3,
            fontSize: 14, display: "flex", alignItems: "center", justifyContent: "center",
          }}>×</button>
        </div>

        <p style={{ fontSize: 14, color: tokens.colors.text1, lineHeight: 1.6, marginBottom: 18 }}>
          94 minutes without a break. Your error rate has climbed 0.8%. A rest now protects your next 2 hours.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <button style={{
            width: "100%", padding: "12px",
            background: `linear-gradient(135deg, ${tokens.colors.purple}30, ${tokens.colors.purple}15)`,
            border: `1px solid rgba(183,148,244,0.3)`,
            borderRadius: tokens.radii.md,
            color: tokens.colors.purple, fontSize: 13, fontWeight: 500,
            transition: "all 0.2s ease",
          }}>
            Guide me through a 2-min reset
          </button>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={onDismiss} style={{
              flex: 1, padding: "10px",
              background: tokens.colors.surface1,
              border: `1px solid ${tokens.colors.border1}`,
              borderRadius: tokens.radii.md,
              color: tokens.colors.text2, fontSize: 13,
            }}>
              Snooze 15 min
            </button>
            <button onClick={onDismiss} style={{
              flex: 1, padding: "10px",
              background: tokens.colors.surface1,
              border: `1px solid ${tokens.colors.border1}`,
              borderRadius: tokens.radii.md,
              color: tokens.colors.text2, fontSize: 13,
            }}>
              Dismiss
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// COACH CHAT
// ============================================================
function CoachPanel({ open, onToggle }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState(coachMessages);

  return (
    <div style={{
      background: tokens.colors.surface1,
      border: `1px solid ${tokens.colors.border1}`,
      borderRadius: tokens.radii.lg,
      overflow: "hidden",
      animation: "fadeUp 0.5s cubic-bezier(0.16,1,0.3,1) 0.3s both",
    }}>
      {/* Header */}
      <button onClick={onToggle} style={{
        width: "100%", padding: "16px 20px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        borderBottom: open ? `1px solid ${tokens.colors.border1}` : "none",
        transition: "background 0.2s",
        background: "transparent",
      }}
        onMouseEnter={e => e.currentTarget.style.background = tokens.colors.bg3}
        onMouseLeave={e => e.currentTarget.style.background = "transparent"}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 28, height: 28, borderRadius: tokens.radii.sm,
            background: tokens.colors.accentSoft,
            border: `1px solid ${tokens.colors.borderAccent}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 14,
          }}>◎</div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 500, color: tokens.colors.text1 }}>AI Coach</div>
            <div style={{ fontSize: 11, color: tokens.colors.green, display: "flex", alignItems: "center", gap: 4, marginTop: 1 }}>
              <div style={{ width: 5, height: 5, borderRadius: "50%", background: tokens.colors.green }} />
              Online
            </div>
          </div>
        </div>
        <span style={{
          fontSize: 12, color: tokens.colors.text3,
          transform: open ? "rotate(180deg)" : "rotate(0deg)",
          transition: "transform 0.3s ease",
        }}>▾</span>
      </button>

      {open && (
        <div style={{ animation: "fadeUp 0.3s ease both" }}>
          {/* Messages */}
          <div style={{ padding: "16px 16px 0", display: "flex", flexDirection: "column", gap: 12, maxHeight: 220, overflowY: "auto" }}>
            {messages.map((msg, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                animation: `fadeUp 0.3s ease ${i * 0.08}s both`,
              }}>
                <div style={{
                  maxWidth: "85%", padding: "10px 14px",
                  background: msg.role === "user" ? tokens.colors.accentSoft : tokens.colors.bg2,
                  border: `1px solid ${msg.role === "user" ? tokens.colors.borderAccent : tokens.colors.border1}`,
                  borderRadius: msg.role === "user" ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                  fontSize: 13, color: tokens.colors.text2, lineHeight: 1.55,
                }}>
                  {msg.text}
                </div>
              </div>
            ))}
          </div>
          {/* Input */}
          <div style={{ padding: "12px 16px 16px", display: "flex", gap: 8 }}>
            <input value={input} onChange={e => setInput(e.target.value)}
              placeholder="Ask your coach..."
              style={{
                flex: 1, padding: "10px 14px",
                background: tokens.colors.bg2,
                border: `1px solid ${tokens.colors.border1}`,
                borderRadius: tokens.radii.pill,
                color: tokens.colors.text1, fontSize: 13,
                outline: "none",
              }}
              onFocus={e => e.target.style.borderColor = tokens.colors.borderAccent}
              onBlur={e => e.target.style.borderColor = tokens.colors.border1}
            />
            <button style={{
              padding: "10px 16px",
              background: tokens.colors.accent,
              borderRadius: tokens.radii.pill,
              color: "#fff", fontSize: 13, fontWeight: 500,
              boxShadow: `0 0 16px ${tokens.colors.accentGlow}`,
            }}>↑</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// SIDEBAR
// ============================================================
function Sidebar({ active, setActive }) {
  const items = [
    { id: "dashboard", icon: "◈", label: "Dashboard" },
    { id: "insights", icon: "◑", label: "Insights" },
    { id: "privacy", icon: "◎", label: "Privacy" },
  ];

  return (
    <aside style={{
      width: 64, background: tokens.colors.bg1,
      borderRight: `1px solid ${tokens.colors.border1}`,
      display: "flex", flexDirection: "column", alignItems: "center",
      padding: "20px 0", gap: 4, flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{
        width: 36, height: 36, borderRadius: tokens.radii.md,
        background: tokens.colors.accentSoft,
        border: `1px solid ${tokens.colors.borderAccent}`,
        display: "flex", alignItems: "center", justifyContent: "center",
        marginBottom: 20, cursor: "pointer", fontSize: 18,
      }}>◎</div>

      {items.map(item => (
        <button key={item.id} onClick={() => setActive(item.id)} title={item.label} style={{
          width: 44, height: 44, borderRadius: tokens.radii.md,
          background: active === item.id ? tokens.colors.accentSoft : "transparent",
          border: `1px solid ${active === item.id ? tokens.colors.borderAccent : "transparent"}`,
          color: active === item.id ? tokens.colors.accent : tokens.colors.text3,
          fontSize: 18, display: "flex", alignItems: "center", justifyContent: "center",
          transition: "all 0.2s ease",
          cursor: "pointer",
        }}
          onMouseEnter={e => { if (active !== item.id) e.currentTarget.style.background = tokens.colors.surface1; }}
          onMouseLeave={e => { if (active !== item.id) e.currentTarget.style.background = "transparent"; }}
        >
          {item.icon}
        </button>
      ))}

      {/* Avatar at bottom */}
      <div style={{ marginTop: "auto" }}>
        <div style={{
          width: 36, height: 36, borderRadius: "50%",
          background: `linear-gradient(135deg, ${tokens.colors.accent}, ${tokens.colors.purple})`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 14, fontWeight: 600, color: "#fff",
        }}>A</div>
      </div>
    </aside>
  );
}

// ============================================================
// TOPBAR
// ============================================================
function Topbar({ page }) {
  const labels = { dashboard: "Dashboard", insights: "Insights", privacy: "Privacy & Data" };
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
    <header style={{
      height: 56, background: tokens.colors.bg1,
      borderBottom: `1px solid ${tokens.colors.border1}`,
      display: "flex", alignItems: "center",
      padding: "0 24px", gap: 16, flexShrink: 0,
    }}>
      <div style={{ fontFamily: tokens.font.display, fontSize: 20, fontWeight: 400, color: tokens.colors.text1 }}>
        {labels[page]}
      </div>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{
          padding: "5px 12px", borderRadius: tokens.radii.pill,
          background: tokens.colors.greenGlow,
          border: "1px solid rgba(104,211,145,0.2)",
          display: "flex", alignItems: "center", gap: 6,
          fontSize: 12, color: tokens.colors.green,
        }}>
          <div style={{ width: 5, height: 5, borderRadius: "50%", background: tokens.colors.green, animation: "glowPulse 2s ease-in-out infinite" }} />
          Monitoring
        </div>
        <div style={{ fontFamily: tokens.font.mono, fontSize: 12, color: tokens.colors.text3 }}>{timeStr}</div>
      </div>
    </header>
  );
}

// ============================================================
// DASHBOARD PAGE
// ============================================================
function DashboardPage({ showAlert, setShowAlert }) {
  const [coachOpen, setCoachOpen] = useState(true);
  const currentScore = 67;
  const currentState = "High Load";

  return (
    <div style={{ display: "flex", gap: 0, height: "100%", overflow: "hidden" }}>
      {/* Main scroll area */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px" }}>

        {/* Top row: Score + Explanation + Metrics */}
        <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 20, marginBottom: 20 }}>
          {/* Score block */}
          <div style={{
            background: tokens.colors.bg2,
            border: `1px solid ${tokens.colors.border1}`,
            borderRadius: tokens.radii.xl, padding: "28px 32px",
            display: "flex", flexDirection: "column", alignItems: "center",
            gap: 20, minWidth: 280,
            animation: "fadeUp 0.5s cubic-bezier(0.16,1,0.3,1) both",
          }}>
            <ScoreRing score={currentScore} state={currentState} />
            <div style={{ width: "100%", textAlign: "center" }}>
              <div style={{ fontSize: 12, color: tokens.colors.text3, marginBottom: 4 }}>Session</div>
              <div style={{ fontFamily: tokens.font.mono, fontSize: 13, color: tokens.colors.amber }}>
                Active 4h 12m · 3 alerts
              </div>
            </div>
          </div>

          {/* Right column */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {/* Explanation panel */}
            <ExplanationPanel />

            {/* Metrics grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {liveMetrics.map((m, i) => (
                <MetricCard key={m.label} metric={m} delay={0.1 + i * 0.08} />
              ))}
            </div>
          </div>
        </div>

        {/* Trend chart */}
        <div style={{
          background: tokens.colors.bg2,
          border: `1px solid ${tokens.colors.border1}`,
          borderRadius: tokens.radii.xl, padding: "22px 24px",
          marginBottom: 20,
          animation: "fadeUp 0.5s cubic-bezier(0.16,1,0.3,1) 0.2s both",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 500, color: tokens.colors.text2 }}>Cognitive Load — Today</div>
              <div style={{ fontSize: 12, color: tokens.colors.text3, marginTop: 2 }}>09:00 — 15:00</div>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              {["1D", "1W", "1M"].map(r => (
                <button key={r} style={{
                  padding: "4px 12px",
                  background: r === "1D" ? tokens.colors.accentSoft : "transparent",
                  border: `1px solid ${r === "1D" ? tokens.colors.borderAccent : tokens.colors.border1}`,
                  borderRadius: tokens.radii.pill,
                  color: r === "1D" ? tokens.colors.accent : tokens.colors.text3,
                  fontSize: 11, fontWeight: 500,
                }}>{r}</button>
              ))}
            </div>
          </div>
          <div style={{ height: 100 }}>
            <TrendChart data={cognitiveHistory} />
          </div>
          {/* Time labels */}
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
            {cognitiveHistory.filter((_, i) => i % 3 === 0).map(d => (
              <span key={d.time} style={{ fontSize: 10, color: tokens.colors.text3, fontFamily: tokens.font.mono }}>{d.time}</span>
            ))}
          </div>
        </div>

        {/* Alert history + coach */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {/* Alert history */}
          <div style={{
            background: tokens.colors.bg2,
            border: `1px solid ${tokens.colors.border1}`,
            borderRadius: tokens.radii.xl, padding: "22px 24px",
            animation: "fadeUp 0.5s cubic-bezier(0.16,1,0.3,1) 0.25s both",
          }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: tokens.colors.text2, marginBottom: 16 }}>Recent Alerts</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {alertHistory.map((alert, i) => (
                <div key={i} style={{
                  display: "flex", gap: 12, alignItems: "flex-start",
                  padding: "12px", borderRadius: tokens.radii.md,
                  background: tokens.colors.surface1,
                  border: `1px solid ${tokens.colors.border1}`,
                  opacity: alert.resolved ? 0.6 : 1,
                }}>
                  <div style={{
                    width: 6, height: 6, borderRadius: "50%", marginTop: 4, flexShrink: 0,
                    background: getStateColor(alert.type),
                    boxShadow: `0 0 6px ${getStateColor(alert.type)}`,
                  }} />
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 500, color: getStateColor(alert.type), marginBottom: 3 }}>
                      {alert.type} · {alert.time}
                    </div>
                    <div style={{ fontSize: 12, color: tokens.colors.text3, lineHeight: 1.5 }}>{alert.msg}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Coach */}
          <CoachPanel open={coachOpen} onToggle={() => setCoachOpen(o => !o)} />
        </div>
      </div>
    </div>
  );
}

// ============================================================
// INSIGHTS PAGE
// ============================================================
function InsightsPage() {
  return (
    <div style={{ overflowY: "auto", padding: "24px", flex: 1 }}>
      {/* Weekly bar chart */}
      <div style={{
        background: tokens.colors.bg2,
        border: `1px solid ${tokens.colors.border1}`,
        borderRadius: tokens.radii.xl, padding: "24px",
        marginBottom: 20,
        animation: "fadeUp 0.5s ease both",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 500, color: tokens.colors.text2 }}>Weekly Cognitive Load</div>
            <div style={{ fontSize: 12, color: tokens.colors.text3 }}>Avg vs Peak</div>
          </div>
          <div style={{ display: "flex", gap: 16, fontSize: 11, color: tokens.colors.text3 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <div style={{ width: 8, height: 3, background: tokens.colors.accent + "50", borderRadius: 2 }} /> Avg
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <div style={{ width: 8, height: 3, background: tokens.colors.accent, borderRadius: 2 }} /> Peak
            </div>
          </div>
        </div>
        <WeeklyBarChart data={weeklyData} />
      </div>

      {/* Insight cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 20 }}>
        {insightCards.map((card, i) => (
          <div key={i} style={{
            background: tokens.colors.bg2,
            border: `1px solid ${tokens.colors.border1}`,
            borderRadius: tokens.radii.xl, padding: "22px",
            animation: `fadeUp 0.5s ease ${i * 0.08}s both`,
            transition: "border-color 0.2s, transform 0.2s",
          }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = `${card.color}30`;
              e.currentTarget.style.transform = "translateY(-2px)";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = tokens.colors.border1;
              e.currentTarget.style.transform = "translateY(0)";
            }}
          >
            <div style={{
              width: 40, height: 40, borderRadius: tokens.radii.md,
              background: `${card.color}18`,
              border: `1px solid ${card.color}30`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 20, marginBottom: 14,
            }}>{card.icon}</div>
            <div style={{ fontSize: 14, fontWeight: 500, color: tokens.colors.text1, marginBottom: 8 }}>{card.title}</div>
            <div style={{ fontSize: 13, color: tokens.colors.text3, lineHeight: 1.6 }}>{card.body}</div>
          </div>
        ))}
      </div>

      {/* Daily breakdown */}
      <div style={{
        background: tokens.colors.bg2,
        border: `1px solid ${tokens.colors.border1}`,
        borderRadius: tokens.radii.xl, padding: "24px",
        animation: "fadeUp 0.5s ease 0.3s both",
      }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: tokens.colors.text2, marginBottom: 18 }}>Today's Focus Sessions</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {[
            { time: "09:00–11:00", dur: "2h", quality: 88, label: "Deep Work" },
            { time: "11:00–12:00", dur: "1h", quality: 54, label: "High Load" },
            { time: "13:00–15:00", dur: "2h", quality: 41, label: "Fatigue Pattern" },
          ].map((session, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 16,
              padding: "12px 16px", borderRadius: tokens.radii.md,
              background: tokens.colors.surface1,
              border: `1px solid ${tokens.colors.border1}`,
            }}>
              <div style={{ fontFamily: tokens.font.mono, fontSize: 11, color: tokens.colors.text3, minWidth: 100 }}>{session.time}</div>
              <div style={{ flex: 1, height: 4, background: tokens.colors.border1, borderRadius: 2, overflow: "hidden" }}>
                <div style={{
                  height: "100%", width: `${session.quality}%`,
                  background: session.quality > 70
                    ? `linear-gradient(90deg, ${tokens.colors.green}, ${tokens.colors.green}80)`
                    : session.quality > 50
                      ? `linear-gradient(90deg, ${tokens.colors.amber}, ${tokens.colors.amber}80)`
                      : `linear-gradient(90deg, ${tokens.colors.purple}, ${tokens.colors.purple}80)`,
                  borderRadius: 2,
                }} />
              </div>
              <div style={{ fontSize: 12, color: tokens.colors.text3, minWidth: 80, textAlign: "right" }}>{session.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// PRIVACY PAGE
// ============================================================
function PrivacyPage() {
  const [toggles, setToggles] = useState(privacyToggles);

  const toggle = (i) => {
    setToggles(t => t.map((item, idx) => idx === i ? { ...item, on: !item.on } : item));
  };

  return (
    <div style={{ overflowY: "auto", padding: "24px", flex: 1 }}>
      {/* Header card */}
      <div style={{
        background: tokens.colors.bg2,
        border: `1px solid rgba(104,211,145,0.2)`,
        borderRadius: tokens.radii.xl, padding: "28px",
        marginBottom: 20,
        animation: "fadeUp 0.5s ease both",
      }}>
        <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
          <div style={{
            width: 48, height: 48, borderRadius: tokens.radii.md,
            background: tokens.colors.greenGlow,
            border: "1px solid rgba(104,211,145,0.2)",
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, flexShrink: 0,
          }}>🔒</div>
          <div>
            <div style={{ fontFamily: tokens.font.display, fontSize: 22, color: tokens.colors.text1, marginBottom: 8 }}>
              Your data never leaves your device.
            </div>
            <div style={{ fontSize: 14, color: tokens.colors.text2, lineHeight: 1.7 }}>
              NeuroLens uses behavioral timing patterns — not content. All analysis runs locally. 
              You have complete control over what (if anything) is retained or synced.
            </div>
          </div>
        </div>
      </div>

      {/* Data model */}
      <div style={{
        background: tokens.colors.bg2,
        border: `1px solid ${tokens.colors.border1}`,
        borderRadius: tokens.radii.xl, padding: "24px",
        marginBottom: 20,
        animation: "fadeUp 0.5s ease 0.1s both",
      }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: tokens.colors.text2, marginBottom: 18 }}>What we capture vs. what we don't</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <div style={{ fontSize: 11, color: tokens.colors.green, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 12 }}>Captured</div>
            {["Keystroke timing (not content)", "App-switch frequency", "Error rate patterns", "Session duration", "Break gap timing"].map(item => (
              <div key={item} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
                <span style={{ color: tokens.colors.green, fontSize: 12 }}>✓</span>
                <span style={{ fontSize: 13, color: tokens.colors.text2 }}>{item}</span>
              </div>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 11, color: tokens.colors.red, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 12 }}>Never Captured</div>
            {["Keystrokes or typed content", "Screenshots or screen content", "Voice or microphone", "Location data", "Personal communications"].map(item => (
              <div key={item} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
                <span style={{ color: tokens.colors.red, fontSize: 12 }}>✕</span>
                <span style={{ fontSize: 13, color: tokens.colors.text2 }}>{item}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Toggles */}
      <div style={{
        background: tokens.colors.bg2,
        border: `1px solid ${tokens.colors.border1}`,
        borderRadius: tokens.radii.xl, padding: "24px",
        animation: "fadeUp 0.5s ease 0.2s both",
      }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: tokens.colors.text2, marginBottom: 18 }}>Data Controls</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {toggles.map((item, i) => (
            <div key={i} style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "16px 0",
              borderBottom: i < toggles.length - 1 ? `1px solid ${tokens.colors.border1}` : "none",
            }}>
              <div>
                <div style={{ fontSize: 14, color: tokens.colors.text1, marginBottom: 3 }}>{item.label}</div>
                <div style={{ fontSize: 12, color: tokens.colors.text3 }}>{item.desc}</div>
              </div>
              <button onClick={() => toggle(i)} style={{
                width: 44, height: 24, borderRadius: 12,
                background: item.on ? tokens.colors.accent : tokens.colors.surface1,
                border: `1px solid ${item.on ? tokens.colors.borderAccent : tokens.colors.border1}`,
                transition: "all 0.25s cubic-bezier(0.16,1,0.3,1)",
                position: "relative", flexShrink: 0,
                boxShadow: item.on ? `0 0 12px ${tokens.colors.accentGlow}` : "none",
              }}>
                <div style={{
                  position: "absolute", top: 2, left: item.on ? 22 : 2,
                  width: 18, height: 18, borderRadius: "50%",
                  background: item.on ? "#fff" : tokens.colors.text3,
                  transition: "left 0.25s cubic-bezier(0.16,1,0.3,1), background 0.2s",
                }} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// APP ROOT
// ============================================================
export default function App() {
  const [stage, setStage] = useState("loading"); // loading | onboarding | app
  const [activePage, setActivePage] = useState("dashboard");
  const [showAlert, setShowAlert] = useState(false);

  // Show alert after 3 seconds in dashboard
  useEffect(() => {
    if (stage === "app") {
      const t = setTimeout(() => setShowAlert(true), 3000);
      return () => clearTimeout(t);
    }
  }, [stage]);

  return (
    <>
      <GlobalStyle />
      {stage === "loading" && <LoadingScreen onDone={() => setStage("onboarding")} />}
      {stage === "onboarding" && <OnboardingFlow onDone={() => setStage("app")} />}
      {stage === "app" && (
        <div style={{
          height: "100vh", display: "flex", flexDirection: "column",
          background: tokens.colors.bg0, overflow: "hidden",
          animation: "fadeIn 0.4s ease both",
        }}>
          <Topbar page={activePage} />
          <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
            <Sidebar active={activePage} setActive={setActivePage} />
            <main style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
              {activePage === "dashboard" && <DashboardPage showAlert={showAlert} setShowAlert={setShowAlert} />}
              {activePage === "insights" && <InsightsPage />}
              {activePage === "privacy" && <PrivacyPage />}
            </main>
          </div>
          {showAlert && activePage === "dashboard" && (
            <AlertPanel onDismiss={() => setShowAlert(false)} />
          )}
        </div>
      )}
    </>
  );
}
