"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { AudioController } from "@/lib/audio";
import { RECIPIENT_FIRST_NAME } from "@/lib/site";

type Screen = "opening" | "question" | "yes" | "exit";
type Plan = { name: string; email: string; date: string; time: string; area: string; outing: string; note: string };
const guest = RECIPIENT_FIRST_NAME.trim();
const YES_SONG = "/audio/yes_date_song.mp3";
const EXIT_ALARM = "/audio/no_third_alarm.mp3";
const questions = [
  ["Why an entire website?", "Apparently I find deploying a website less intimidating than asking you out normally."],
  ["What’s the plan?", "Good music, somewhere we can hear each other, and a second stop only if we both want one."],
  ["Why me?", "Because you caught my attention, and I’d rather get to know you across a table than through a screen."],
  ["What if it’s awkward?", "We finish our coffee, part as reasonable adults, and never speak of this website again."],
  ["What if I say no?", "Then it’s no. The website may behave badly; I won’t."],
] as const;

export default function Home() {
  const [screen, setScreen] = useState<Screen>("opening");
  const [noCount, setNoCount] = useState(0);
  const [muted, setMuted] = useState(false);
  const [songPlaying, setSongPlaying] = useState(false);
  const [assessment, setAssessment] = useState(false);
  const [terms, setTerms] = useState(false);
  const [openQuestion, setOpenQuestion] = useState<number | null>(null);
  const [planAvailable, setPlanAvailable] = useState<boolean | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<"local" | "resend" | null>(null);
  const [error, setError] = useState("");
  const [plan, setPlan] = useState<Plan>({ name: guest, email: "", date: "", time: "", area: "", outing: "Coffee", note: "" });
  const audio = useRef<AudioController | null>(null);
  const song = useRef<HTMLAudioElement>(null);
  const alarm = useRef<HTMLAudioElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const alarmTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const submissionId = useRef("");
  const sendingRef = useRef(false);

  function stopAlarm() {
    if (alarmTimer.current) clearTimeout(alarmTimer.current);
    if (alarm.current) { alarm.current.pause(); alarm.current.currentTime = 0; }
  }
  function stopAll() {
    audio.current?.stop();
    stopAlarm();
    if (song.current) { song.current.pause(); song.current.currentTime = 0; }
  }
  useEffect(() => {
    const controller = new AudioController();
    audio.current = controller;
    const preference = localStorage.getItem("bro-muted") === "true";
    setMuted(preference);
    controller.setMuted(preference);
    const onHide = () => { if (document.hidden) { controller.stop(); song.current?.pause(); alarm.current?.pause(); } };
    const onLeave = () => { controller.stop(); song.current?.pause(); alarm.current?.pause(); };
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", onLeave);
    return () => { controller.dispose(); if (alarmTimer.current) clearTimeout(alarmTimer.current); alarm.current?.pause(); song.current?.pause(); document.removeEventListener("visibilitychange", onHide); window.removeEventListener("pagehide", onLeave); };
  }, []);
  useEffect(() => {
    if (assessment && !dialog.current?.open) dialog.current?.showModal();
    if (!assessment && dialog.current?.open) dialog.current.close();
  }, [assessment]);
  useEffect(() => {
    if (screen !== "yes") return;
    const controller = new AbortController();
    fetch("/api/plan/status", { signal: controller.signal, cache: "no-store" })
      .then(response => setPlanAvailable(response.ok))
      .catch(() => { if (!controller.signal.aborted) setPlanAvailable(false); });
    return () => controller.abort();
  }, [screen]);

  function toggleSound() {
    const next = !muted;
    setMuted(next);
    localStorage.setItem("bro-muted", String(next));
    audio.current?.setMuted(next);
    if (next) { song.current?.pause(); stopAlarm(); }
  }
  function playSong() {
    if (!song.current || muted) return;
    audio.current?.stop();
    void song.current.play().catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      console.warn("Missing or unreadable YES music: " + YES_SONG);
    });
  }
  function chooseYes() {
    stopAll();
    setAssessment(false);
    setPlanAvailable(null);
    setScreen("yes");
    playSong();
  }
  function chooseNo() {
    stopAll();
    const next = Math.min(noCount + 1, 3);
    setNoCount(next);
    if (next < 3) { void audio.current?.play("no_first"); return; }
    setAssessment(true);
    if (muted || !alarm.current) return;
    void alarm.current.play().then(() => {
      alarmTimer.current = setTimeout(stopAlarm, 3500);
    }).catch(() => console.warn("Missing or unreadable exit alarm: " + EXIT_ALARM));
  }
  function closeAssessment() { stopAlarm(); setAssessment(false); }
  function leave() { stopAll(); setAssessment(false); setScreen("exit"); }
  function updatePlan(update: Partial<Plan>) {
    setPlan(current => ({ ...current, ...update }));
    submissionId.current = "";
    setSent(null); setReviewing(false); setError("");
  }
  function reviewPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!submissionId.current) submissionId.current = crypto.randomUUID();
    setError(""); setReviewing(true);
  }
  async function submitPlan() {
    if (sendingRef.current || sent || !reviewing) return;
    sendingRef.current = true; setSending(true); setError("");
    try {
      const response = await fetch("/api/plan", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: submissionId.current, name: plan.name, email: plan.email, when: plan.date + " at " + plan.time, area: plan.area, outing: plan.outing, note: plan.note }),
      });
      if (!response.ok) {
        setError(response.status === 429 ? "The plan limit has been reached for today. Your draft is still here." : response.status === 409 ? "This plan needs a manual delivery check. Please contact Spandan before sending another copy." : "Plan delivery was not confirmed. Your draft is still here; retry this same plan.");
        return;
      }
      const result: { delivery?: "local" | "resend" } = await response.json();
      if (result.delivery !== "local" && result.delivery !== "resend") throw new Error("Unexpected delivery result");
      setSent(result.delivery);
    } catch {
      setError("Plan delivery was not confirmed. Your draft is still here; retry this same plan.");
    } finally { sendingRef.current = false; setSending(false); }
  }

  return <div className="shell">
    <header className="topbar"><span className="wordmark">A message from Spandan<span className="accent">.</span></span><button className="sound-button" onClick={toggleSound} aria-pressed={muted}>{muted ? "Sound off" : "Sound on"}</button></header>
    {screen === "opening" && <main className="opening" aria-labelledby="opening-title"><div className="opening-content"><span className="kicker">ONE QUESTION <span className="line" /></span><h1 id="opening-title">{guest ? "For " + guest + "." : "For you."}</h1><p>A message from Spandan.</p><button className="primary-button open-button" onClick={() => setScreen("question")}>Open it <span aria-hidden="true">↗</span></button></div><p className="opening-foot">Just between us.</p></main>}
    {screen === "question" && <main className="conversation" aria-labelledby="invitation-title"><span className="kicker">ONE QUESTION / FROM SPANDAN</span><h1 id="invitation-title" className="message-title">{guest ? "Hey " + guest + "." : "Hey."}</h1><p className="invitation">I’ve wanted to ask you this properly: I’d like to take you out—somewhere we can talk and see where the evening goes. <strong>Would you go on a date with me?</strong></p><div className="signature">— Spandan</div>
      <section className="questions" aria-labelledby="questions-title"><h2 id="questions-title">Questions before you answer?</h2><p className="section-hint">Pick any. Or skip straight to your answer.</p><div className="question-list">{questions.map(([question, answer], index) => <div className="question-item" key={question}><button className="question-button" aria-expanded={openQuestion === index} aria-controls={"answer-" + index} onClick={() => setOpenQuestion(openQuestion === index ? null : index)}><span>{question}</span><span aria-hidden="true">{openQuestion === index ? "−" : "+"}</span></button><div id={"answer-" + index} hidden={openQuestion !== index} className="answer">{answer}<small>Spandan</small></div></div>)}</div><button className="terms-link" onClick={() => setTerms(!terms)} aria-expanded={terms}>Terms and conditions</button>{terms && <p className="terms-copy">One date. No compulsory sequel.</p>}</section>
      <section className="decision" aria-label="Your answer"><p>Your answer, whenever you’re ready.</p><div className="decision-buttons"><button className="primary-button" onClick={chooseYes}>Yes, take me out <span aria-hidden="true">↗</span></button><button className="no-button" onClick={chooseNo}>No</button></div>{noCount > 0 && <div className="no-response" role="status"><span className="kicker">NO RECORDED · {noCount} / 3</span><p>{noCount === 1 ? "No recorded. I tested this button more than the YES button, which says more about me than I intended." : noCount === 2 ? "I asked the website to take this gracefully. It opened an inquiry." : "Your answer is still no. You can leave for free."}</p><button className="text-button" onClick={leave}>Leave this page</button><span className="gentle-note">The No button only repeats the joke if you choose it again.</span></div>}</section></main>}
    {screen === "yes" && <main className="success" aria-labelledby="success-title"><div className="confetti" aria-hidden="true">{Array.from({ length: 14 }, (_, i) => <i key={i} style={{ left: ((i * 37) % 97) + "%", animationDelay: ((i % 5) * .12) + "s" }} />)}</div><span className="kicker">YES / RECEIVED</span><p className="success-lead">Excellent. The website worked. Now I have to.</p><h1 id="success-title">It’s done bro<span className="accent">.</span></h1><p className="success-subtitle">I’d really like to make this worth your time.</p><div className="music-row"><span>Your YES song</span><button className="text-button" disabled={muted} onClick={() => songPlaying ? song.current?.pause() : playSong()}>{songPlaying ? "Pause song" : "Play song"}</button></div>
      <section className="plan-panel" aria-labelledby="plan-title"><span className="kicker">THE NEXT PART</span><h2 id="plan-title">A plan we can actually make.</h2><p>Pick what sounds good. This is a proposal, not a confirmed booking.</p>{planAvailable === null ? <p role="status">Checking plan delivery…</p> : !planAvailable ? <p role="status">Plan delivery is unavailable right now. Please try again later.</p> : sent ? <p className="success-message" role="status">{sent === "local" ? "Saved to the local development outbox. No email was sent." : "Your proposed plan was accepted for email delivery to you and Spandan."}</p> : reviewing ? <section className="plan-review" aria-label="Review your date plan"><h3>Review your plan</h3><dl><dt>Name</dt><dd>{plan.name}</dd><dt>Email</dt><dd>{plan.email}</dd><dt>Preferred day and time</dt><dd>{plan.date} · {plan.time}</dd><dt>Area</dt><dd>{plan.area}</dd><dt>Type of date</dt><dd>{plan.outing}</dd><dt>Note</dt><dd>{plan.note || "None"}</dd></dl><p>Nothing has been sent yet. Send our plan emails this proposal to you and Spandan.</p><div className="form-actions"><button className="secondary-button" onClick={() => setReviewing(false)}>Edit plan</button><button className="primary-button" disabled={sending} onClick={submitPlan}>{sending ? "Sending…" : "Send our plan"}</button></div>{error && <p className="form-error" role="alert">{error}</p>}</section> : <form onSubmit={reviewPlan}><div className="field-pair"><label>Your name<input required maxLength={80} autoComplete="name" value={plan.name} onChange={e => updatePlan({ name: e.target.value })} /></label><label>Your email<input required type="email" maxLength={254} autoComplete="email" value={plan.email} onChange={e => updatePlan({ email: e.target.value })} /></label></div><div className="field-pair"><label>Preferred date<input required type="date" value={plan.date} onChange={e => updatePlan({ date: e.target.value })} /></label><label>Preferred time<input required type="time" value={plan.time} onChange={e => updatePlan({ time: e.target.value })} /></label></div><label>Area or location<input required maxLength={100} value={plan.area} onChange={e => updatePlan({ area: e.target.value })} /></label><label>Type of date<select value={plan.outing} onChange={e => updatePlan({ outing: e.target.value })}><option>Coffee</option><option>Dinner</option><option>Walk and a drink</option><option>Something else</option></select></label><label>Note (optional)<textarea maxLength={500} rows={3} value={plan.note} onChange={e => updatePlan({ note: e.target.value })} /></label><p className="form-note">You’ll review everything before anything is sent.</p><button className="primary-button" type="submit">Review our plan</button></form>}</section></main>}
    {screen === "exit" && <main className="exit-screen"><span className="kicker">NO RECORDED</span><h1>All good.</h1><p>Thank you for opening it. You can close this page whenever you like.</p><button className="secondary-button" onClick={() => setScreen("question")}>Back to the question</button></main>}
    <footer className="footer"><span>ONE QUESTION · SPANDAN</span><span>No pressure. No payment. Just a question.</span></footer>
    <audio ref={song} src={YES_SONG} preload="none" muted={muted} onPlay={() => setSongPlaying(true)} onPause={() => setSongPlaying(false)} onEnded={() => setSongPlaying(false)} onError={() => console.warn("Missing or unreadable YES music: " + YES_SONG)} />
    <audio ref={alarm} src={EXIT_ALARM} preload="none" muted={muted} onError={() => console.warn("Missing or unreadable exit alarm: " + EXIT_ALARM)} />
    <dialog ref={dialog} className="assessment" aria-labelledby="assessment-title" onCancel={event => { event.preventDefault(); closeAssessment(); }}><span className="kicker">THIRD NO / AN ENTIRELY UNNECESSARY ESCALATION</span><h2 id="assessment-title">EXIT ASSESSMENT: ₹500</h2><p>This is a joke. Nothing will be charged.</p><div className="scanner"><img src="/upi-scanner-joke.jpg" alt="Non-scannable joke graphic. No payment possible." /></div><p className="assessment-note">No payment link, no working QR, no actual assessment.</p><div className="form-actions"><button className="primary-button" autoFocus onClick={leave}>Exit for free</button><button className="secondary-button" onClick={closeAssessment}>Back to the question</button></div><small>Escape closes this screen.</small></dialog>
  </div>;
}
