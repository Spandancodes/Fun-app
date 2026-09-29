"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { AudioController } from "@/lib/audio";
import { advance, Direction, Game, newGame, SIZE } from "@/lib/game";

type Screen = "board" | "yes" | "exit";
type AuthState = "checking" | "signed-out" | "signed-in";
type Booking = {
  date: string;
  time: string;
  area: string;
  outing: string;
  note: string;
};
const RIHANNA_URL = "https://www.youtube.com/watch?v=yd8jh9QYfEs";
const EXIT_ALARM = "/audio/no_third_alarm.mp3";
const INSTAGRAM_URL = "https://www.instagram.com/_.avalanche.who";

export default function Home() {
  const [muted, setMuted] = useState(false);
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [guestName, setGuestName] = useState("");
  const [loginName, setLoginName] = useState("");
  const [loginEmail, setLoginEmail] = useState("");
  const [loginSending, setLoginSending] = useState(false);
  const [loginMessage, setLoginMessage] = useState("");
  const [screen, setScreen] = useState<Screen>("board");
  const [game, setGame] = useState<Game>(newGame);
  const [recount, setRecount] = useState(false);
  const [assessment, setAssessment] = useState(false);
  const [alarmNeedsGesture, setAlarmNeedsGesture] = useState(false);
  const [bookingSending, setBookingSending] = useState(false);
  const [bookingSent, setBookingSent] = useState<"local" | "resend" | null>(null);
  const [reviewingPlan, setReviewingPlan] = useState(false);
  const [bookingError, setBookingError] = useState("");
  const [booking, setBooking] = useState<Booking>({
    date: "",
    time: "",
    area: "",
    outing: "Coffee",
    note: "",
  });
  const gameRef = useRef(game);
  const audio = useRef<AudioController | null>(null);
  const assessmentRef = useRef<HTMLDialogElement>(null);
  const exitAlarmRef = useRef<HTMLAudioElement>(null);
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const recountTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const exitAlarmTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const moveRef = useRef<(direction: Direction) => void>(() => {});
  const bookingId = useRef("");
  const bookingSendingRef = useRef(false);

  useEffect(() => {
    const controller = new AudioController();
    audio.current = controller;
    const preference = localStorage.getItem("bro-muted") === "true";
    setMuted(preference);
    controller.setMuted(preference);
    const stop = () => {
      audio.current?.stop();
      if (exitAlarmTimer.current) clearTimeout(exitAlarmTimer.current);
      if (exitAlarmRef.current) {
        exitAlarmRef.current.pause();
        exitAlarmRef.current.currentTime = 0;
      }
    };
    const visibility = () => {
      if (document.hidden) stop();
    };
    window.addEventListener("pagehide", stop);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      if (recountTimer.current) clearTimeout(recountTimer.current);
      if (exitAlarmTimer.current) clearTimeout(exitAlarmTimer.current);
      controller.dispose();
      window.removeEventListener("pagehide", stop);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);

  useEffect(() => {
    let active = true;
    const query = new URLSearchParams(window.location.search);
    const verifiedLink = query.get("link") === "verified";
    fetch("/api/session", { credentials: "same-origin" })
      .then(async (response) => {
        if (!active) return;
        if (!response.ok) {
          setAuthState("signed-out");
          if (query.get("link") === "invalid")
            setLoginMessage("That sign-in link is invalid, expired, or already used.");
          return;
        }
        const result: { display_name: string } = await response.json();
        if (!active) return;
        setGuestName(result.display_name);
        setAuthState("signed-in");
        if (verifiedLink) void audio.current?.play("login_right");
        if (query.has("link")) window.history.replaceState({}, "", "/");
      })
      .catch(() => {
        if (active) {
          setAuthState("signed-out");
          setLoginMessage("Sign-in service is temporarily unavailable. Please retry.");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (assessment && !assessmentRef.current?.open)
      assessmentRef.current?.showModal();
    if (!assessment && assessmentRef.current?.open)
      assessmentRef.current.close();
  }, [assessment]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const direction: Record<string, Direction> = {
        arrowup: "up",
        w: "up",
        arrowdown: "down",
        s: "down",
        arrowleft: "left",
        a: "left",
        arrowright: "right",
        d: "right",
      };
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, dialog")) return;
      const chosen = direction[event.key.toLowerCase()];
      if (chosen) {
        event.preventDefault();
        moveRef.current(chosen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function toggleSound() {
    const next = !muted;
    setMuted(next);
    audio.current?.setMuted(next);
    if (next && exitAlarmRef.current) {
      exitAlarmRef.current.pause();
      exitAlarmRef.current.currentTime = 0;
    }
    localStorage.setItem("bro-muted", String(next));
  }

  async function requestSignIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loginSending) return;
    setLoginSending(true);
    setLoginMessage("");
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: loginName, email: loginEmail }),
      });
      if (!response.ok) throw new Error("request failed");
      setLoginMessage("If the invitation matches, a short-lived sign-in link will arrive by email.");
    } catch {
      setLoginMessage("The sign-in request could not be sent. Please try again shortly.");
    } finally {
      setLoginSending(false);
    }
  }

  async function signOut() {
    audio.current?.stop();
    await fetch("/api/logout", { method: "POST", credentials: "same-origin" }).catch(() => {});
    setGuestName("");
    setAuthState("signed-out");
    setScreen("board");
  }

  function restartGame() {
    audio.current?.stop();
    setScreen("board");
    const fresh = newGame();
    gameRef.current = fresh;
    setGame(fresh);
    setRecount(false);
    setAssessment(false);
    bookingId.current = "";
    setBookingSent(null);
    setBookingError("");
  }

  function closeAssessment() {
    audio.current?.stop();
    if (exitAlarmTimer.current) clearTimeout(exitAlarmTimer.current);
    if (exitAlarmRef.current) {
      exitAlarmRef.current.pause();
      exitAlarmRef.current.currentTime = 0;
    }
    setAssessment(false);
    setAlarmNeedsGesture(false);
  }

  function exitForFree() {
    closeAssessment();
    setScreen("exit");
  }

  function playAssessmentAlarm() {
    const alarm = exitAlarmRef.current;
    if (!alarm) return;
    if (muted) {
      setMuted(false);
      audio.current?.setMuted(false);
      localStorage.setItem("bro-muted", "false");
    }
    if (exitAlarmTimer.current) clearTimeout(exitAlarmTimer.current);
    alarm.pause();
    alarm.currentTime = 0;
    alarm.volume = 1;
    setAlarmNeedsGesture(false);
    void alarm.play().then(() => {
      exitAlarmTimer.current = setTimeout(() => {
        alarm.pause();
        alarm.currentTime = 0;
      }, 3500);
    }).catch(() => {
      setAlarmNeedsGesture(true);
      console.warn("Browser blocked exit alarm playback: " + EXIT_ALARM);
    });
  }

  function startAssessment() {
    setAssessment(true);
    playAssessmentAlarm();
  }

  function move(direction: Direction) {
    if (authState !== "signed-in" || screen !== "board" || assessment) return;
    const result = advance(gameRef.current, direction);
    if (result.game === gameRef.current) return;
    gameRef.current = result.game;
    setGame(result.game);
    if (result.catch === "yes") {
      audio.current?.stop();
      setScreen("yes");
    } else if (result.catch === "no") {
      if (result.game.noCount < 3) {
        void audio.current?.play("no_first");
        setRecount(true);
        if (recountTimer.current) clearTimeout(recountTimer.current);
        recountTimer.current = setTimeout(() => setRecount(false), 850);
      } else {
        audio.current?.stop();
        startAssessment();
      }
    }
  }
  moveRef.current = move;

  const snakeTrail = [...game.snake].reverse();
  const snakePath = snakeTrail
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"} ${point.x * 100 + 50} ${point.y * 100 + 50}`,
    )
    .join(" ");
  const tail = snakeTrail[0];
  const tailNext = snakeTrail[1] ?? tail;
  let tailDx = Math.sign(tail.x - tailNext.x);
  let tailDy = Math.sign(tail.y - tailNext.y);
  if (tailDx === 0 && tailDy === 0) tailDy = 1;
  const tailPx = -tailDy;
  const tailPy = tailDx;
  const tailX = tail.x * 100 + 50;
  const tailY = tail.y * 100 + 50;
  const tailPath = `M ${tailX + tailDx * 36} ${tailY + tailDy * 36} L ${tailX + tailPx * 14} ${tailY + tailPy * 14} L ${tailX - tailPx * 14} ${tailY - tailPy * 14} Z`;
  const snakeHead = game.snake[0];
  const snakeNeck = game.snake[1] ?? snakeHead;
  const facingAngle =
    snakeHead.x > snakeNeck.x
      ? 0
      : snakeHead.y > snakeNeck.y
        ? 90
        : snakeHead.x < snakeNeck.x
          ? 180
          : 270;
  const headX = snakeHead.x * 100 + 50;
  const headY = snakeHead.y * 100 + 50;

  function updateBooking(update: Partial<Booking>) {
    setBooking((current) => ({ ...current, ...update }));
    bookingId.current = crypto.randomUUID();
    setBookingSent(null);
    setReviewingPlan(false);
    setBookingError("");
  }

  function reviewBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!bookingId.current) bookingId.current = crypto.randomUUID();
    setBookingError("");
    setReviewingPlan(true);
  }

  async function submitPlan() {
    if (bookingSendingRef.current || bookingSent || !reviewingPlan) return;
    bookingSendingRef.current = true;
    setBookingSending(true);
    setBookingError("");
    if (!bookingId.current) bookingId.current = crypto.randomUUID();
    try {
      const response = await fetch("/api/plan", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: bookingId.current,
          when: `${booking.date} at ${booking.time}`,
          area: booking.area,
          outing: booking.outing,
          note: booking.note,
        }),
      });
      if (!response.ok) throw new Error();
      const result: { delivery?: "local" | "resend" } = await response.json();
      if (result.delivery !== "local" && result.delivery !== "resend")
        throw new Error();
      setBookingSent(result.delivery);
    } catch {
      setBookingError(
        "The plan email was not accepted. Your draft is still here; please retry.",
      );
    } finally {
      bookingSendingRef.current = false;
      setBookingSending(false);
    }
  }

  return (
    <div className="shell">
      <header className="masthead">
        <div className="brand">
          <span className="brand-mark">✓</span>
          <span>
            THANISHA, IT’S DONE BRO
            <small>FICTIONAL ELECTION OFFICE · FILE 001</small>
          </span>
        </div>
        <div className="header-actions">
          <button
            className="plain-button"
            onClick={toggleSound}
            aria-pressed={muted}
          >
            {muted ? "Sound off" : "Sound on"}
          </button>
          {authState === "signed-in" && (
            <button className="plain-button" onClick={signOut}>Sign out</button>
          )}
        </div>
      </header>

      {authState === "checking" ? (
        <main className="card loading" role="status">Checking invitation…</main>
      ) : authState === "signed-out" ? (
        <main className="card sign-in">
          <section className="sign-in-copy">
            <span className="eyebrow">PRIVATE INVITATION · FILE 001</span>
            <h1>Thanisha,<br />it’s done bro.</h1>
            <p>Enter your invited name and email. We’ll send a short-lived sign-in link.</p>
            <div className="seal">EMAIL VERIFIED<br />BEFORE ENTRY</div>
          </section>
          <form className="sign-in-form" onSubmit={requestSignIn}>
            <h2>Open your invitation</h2>
            <label htmlFor="login-name">Name</label>
            <input
              id="login-name"
              autoComplete="name"
              required
              maxLength={80}
              value={loginName}
              onChange={(event) => setLoginName(event.target.value)}
            />
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              required
              maxLength={254}
              value={loginEmail}
              onChange={(event) => setLoginEmail(event.target.value)}
            />
            <button className="action-button" disabled={loginSending}>
              {loginSending ? "Sending link…" : "Email me a sign-in link"}
            </button>
            <p className="form-message" role="status" aria-live="polite">{loginMessage}</p>
          </form>
        </main>
      ) : screen === "board" ? (
        <main
          className={"card arcade " + (game.noCount >= 2 ? "escalated" : "")}
        >
          <div className="arcade-heading">
            <div>
              <span className="eyebrow">BALLOT 01 · THE GREAT NO CHASE</span>
              <h1>Thanisha its done bro</h1>
              <p>Steer the snake toward your answer.</p>
              <aside className="official-notice">
                <span>OFFICIAL FOOTNOTE</span>
                <p>Certainty is a brief candle; the paperwork has tenure.</p>
              </aside>
            </div>
            <div className="count-card">
              <span>NO RECOUNTS</span>
              <strong>{game.noCount} / 3</strong>
              <small className="doom-note">PAPERWORK IS IMMORTAL</small>
            </div>
          </div>
          <div className={"game-wrap " + (recount ? "recount" : "")}>
            <div
              className="ballot-board"
              role="img"
              aria-label={`Snake ballot. YES at column ${game.yes.x + 1}, row ${game.yes.y + 1}; NO at column ${game.no.x + 1}, row ${game.no.y + 1}. Snake at column ${game.snake[0].x + 1}, row ${game.snake[0].y + 1}.`}
              onTouchStart={(event) => {
                touchStart.current = {
                  x: event.touches[0].clientX,
                  y: event.touches[0].clientY,
                };
              }}
              onTouchEnd={(event) => {
                if (!touchStart.current) return;
                const dx =
                  event.changedTouches[0].clientX - touchStart.current.x;
                const dy =
                  event.changedTouches[0].clientY - touchStart.current.y;
                touchStart.current = null;
                if (Math.max(Math.abs(dx), Math.abs(dy)) < 20) return;
                move(
                  Math.abs(dx) > Math.abs(dy)
                    ? dx > 0
                      ? "right"
                      : "left"
                    : dy > 0
                      ? "down"
                      : "up",
                );
              }}
            >
              {Array.from({ length: SIZE * SIZE }, (_, index) => {
                const x = index % SIZE,
                  y = Math.floor(index / SIZE);
                const head = game.snake[0].x === x && game.snake[0].y === y;
                const body = game.snake
                  .slice(1)
                  .some((point) => point.x === x && point.y === y);
                const yes = game.yes.x === x && game.yes.y === y;
                const no = game.no.x === x && game.no.y === y;
                return (
                  <div
                    key={index}
                    className={[
                      "square",
                      head && "head",
                      body && "body",
                      yes && "yes-tile",
                      no && "no-tile",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    data-cell={`${x},${y}`}
                  >
                    {yes ? (
                      "YES"
                    ) : no ? (
                      "NO"
                    ) : null}
                  </div>
                );
              })}
              <svg
                className="snake-art"
                viewBox="0 0 700 700"
                aria-hidden="true"
              >
                <defs>
                  <linearGradient id="snake-skin" x1="0" y1="0" x2="0.8" y2="1">
                    <stop offset="0" stopColor="#8bcf76" />
                    <stop offset="0.48" stopColor="#39a36b" />
                    <stop offset="1" stopColor="#17634f" />
                  </linearGradient>
                  <radialGradient id="snake-face" cx="0.32" cy="0.25" r="0.9">
                    <stop offset="0" stopColor="#a6e17b" />
                    <stop offset="0.52" stopColor="#52bd70" />
                    <stop offset="1" stopColor="#187257" />
                  </radialGradient>
                </defs>
                <path className="snake-tail" d={tailPath} />
                <path className="snake-outline" d={snakePath} />
                <path className="snake-body-path" d={snakePath} />
                {snakeTrail.slice(1, -1).map((point) => {
                  const x = point.x * 100 + 50;
                  const y = point.y * 100 + 50;
                  return (
                    <g className="snake-scales" key={`${point.x},${point.y}`}>
                      <ellipse cx={x - 13} cy={y - 9} rx="6" ry="4" />
                      <ellipse cx={x + 13} cy={y + 9} rx="6" ry="4" />
                    </g>
                  );
                })}
                <g
                  className="snake-head-art"
                  transform={`translate(${headX} ${headY}) rotate(${facingAngle})`}
                >
                  <ellipse className="snake-face" cx="0" cy="0" rx="37" ry="31" />
                  <ellipse className="snake-eye-white" cx="14" cy="-13" rx="7.5" ry="7" />
                  <ellipse className="snake-eye-white" cx="14" cy="13" rx="7.5" ry="7" />
                  <ellipse className="snake-pupil" cx="17" cy="-13" rx="3" ry="4" />
                  <ellipse className="snake-pupil" cx="17" cy="13" rx="3" ry="4" />
                  <circle className="snake-nostril" cx="30" cy="-5" r="2" />
                  <circle className="snake-nostril" cx="30" cy="5" r="2" />
                  <path className="snake-tongue" d="M 34 0 L 48 0 M 48 0 L 56 -6 M 48 0 L 56 6" />
                </g>
              </svg>
            </div>
            {recount && (
              <div className="recount-stamp" role="status">
                <img src="/images/netanyahu.jpg" alt="Benjamin Netanyahu reaction portrait" />
                <strong>RECOUNT!</strong>
                <small>NO relocated by committee</small>
              </div>
            )}
          </div>
          <div className="control-row">
            <p>Arrow keys / WASD · Swipe the board · Or tap a direction</p>
            <div
              className="direction-pad"
              aria-label="Snake direction controls"
            >
              <button aria-label="Move up" onClick={() => move("up")}>
                ↑
              </button>
              <button aria-label="Move left" onClick={() => move("left")}>
                ←
              </button>
              <button aria-label="Move down" onClick={() => move("down")}>
                ↓
              </button>
              <button aria-label="Move right" onClick={() => move("right")}>
                →
              </button>
            </div>
          </div>
          <p className="board-note">
            No walls, no elimination. The fictional office insists your choice
            remains yours.
          </p>
        </main>
      ) : screen === "yes" ? (
        <main className="card result">
          <div className="confetti" aria-hidden="true">
            {Array.from({ length: 20 }, (_, index) => (
              <i
                key={index}
                style={{
                  left: `${(index * 37) % 100}%`,
                  animationDelay: `${(index % 6) * 0.1}s`,
                }}
              />
            ))}
          </div>
          <span className="eyebrow">BALLOT COUNTED · DATE ACCEPTED</span>
          <div className="result-heart" aria-hidden="true">
            ♡
          </div>
          <h1>
            It’s done <em>bro.</em>
          </h1>
          <p>You caught YES. The committee is delighted.</p>
          <div className="song-box">
            <p>Your YES song</p>
            <a className="action-button" href={RIHANNA_URL} target="_blank" rel="noopener noreferrer">
              Play “Don’t Stop the Music” on YouTube ↗
            </a>
            <small>Opens Rihanna’s official music video; playback is controlled by YouTube.</small>
          </div>
          <a
            className="action-button instagram-link"
            href={INSTAGRAM_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            Connect on Instagram to plan a date ↗
          </a>
          <section className="plan-panel" aria-labelledby="booking-title">
            <h2 id="booking-title">Request a date</h2>
            {bookingSent ? (
              <p className="booking-success" role="status">
                {bookingSent === "local"
                  ? "Saved in the local development outbox; no email has been sent."
                  : "Your plan email was accepted for delivery to both addresses. This is not a confirmed calendar booking."}
              </p>
            ) : reviewingPlan ? (
              <section className="plan-review" aria-label="Review your date plan">
                <p>Hi {guestName || "there"} — here’s the plan for review:</p>
                <dl>
                  <dt>Preferred date and time</dt><dd>{booking.date} · {booking.time}</dd>
                  <dt>Area or location</dt><dd>{booking.area}</dd>
                  <dt>Outing</dt><dd>{booking.outing}</dd>
                  <dt>Note</dt><dd>{booking.note || "None"}</dd>
                </dl>
                <p className="booking-disclaimer">When you press Send our plan, it will go to your verified sign-in email and the organizer. Nothing has been sent yet.</p>
                <div className="overlay-actions">
                  <button className="secondary-button" onClick={() => setReviewingPlan(false)}>Edit plan</button>
                  <button className="action-button" disabled={bookingSending} onClick={submitPlan}>
                    {bookingSending ? "Sending plan…" : "Send our plan"}
                  </button>
                </div>
                {bookingError && <p className="error" role="alert">{bookingError}</p>}
              </section>
            ) : (
              <form onSubmit={reviewBooking}>
                <div className="booking-row">
                  <div>
                    <label htmlFor="booking-date">Preferred date</label>
                    <input
                      id="booking-date"
                      type="date"
                      required
                      value={booking.date}
                      onChange={(event) => updateBooking({ date: event.target.value })}
                    />
                  </div>
                  <div>
                    <label htmlFor="booking-time">Preferred time</label>
                    <input
                      id="booking-time"
                      type="time"
                      required
                      value={booking.time}
                      onChange={(event) => updateBooking({ time: event.target.value })}
                    />
                  </div>
                </div>
                <label htmlFor="booking-area">Area or location</label>
                <input
                  id="booking-area"
                  maxLength={100}
                  required
                  value={booking.area}
                  onChange={(event) => updateBooking({ area: event.target.value })}
                />
                <label htmlFor="booking-outing">Type of outing</label>
                <select
                  id="booking-outing"
                  value={booking.outing}
                  onChange={(event) => updateBooking({ outing: event.target.value })}
                >
                  <option>Coffee</option>
                  <option>Walk</option>
                  <option>Dinner</option>
                  <option>Something else</option>
                </select>
                <label htmlFor="booking-note">Note (optional)</label>
                <textarea
                  id="booking-note"
                  maxLength={500}
                  value={booking.note}
                  onChange={(event) => updateBooking({ note: event.target.value })}
                />
                <p className="booking-disclaimer">
                  Your verified email is added automatically. This is a date request, not a confirmed calendar booking.
                </p>
                <button className="action-button">
                  Review our plan
                </button>
              </form>
            )}
          </section>
          <button className="secondary-button" onClick={restartGame}>
            Play again
          </button>
        </main>
      ) : (
        <main className="card result">
          <span className="eyebrow">FILE CLOSED · ₹0 CHARGED</span>
          <h1>Free to go.</h1>
          <p>The ballot box remains open if you change your mind.</p>
          <button
            className="secondary-button"
            onClick={() => {
              if (exitAlarmTimer.current) clearTimeout(exitAlarmTimer.current);
              if (exitAlarmRef.current) {
                exitAlarmRef.current.pause();
                exitAlarmRef.current.currentTime = 0;
              }
              setScreen("board");
            }}
          >
            Return to the board
          </button>
        </main>
      )}

      <footer className="footer">
        A FICTIONAL ELECTION OFFICE · NO GOVERNMENT SERVICE · NO PAYMENT
        REQUIRED
      </footer>
      <audio
        ref={exitAlarmRef}
        src={EXIT_ALARM}
        preload="none"
        onError={() =>
          console.warn("Missing or unreadable exit alarm: " + EXIT_ALARM)
        }
      />
      <dialog
        ref={assessmentRef}
        className="assessment"
        aria-labelledby="assessment-title"
        onCancel={(event) => {
          event.preventDefault();
          closeAssessment();
        }}
      >
        <span className="eyebrow">THIRD NO · EMERGENCY RECOUNT</span>
        <h2 id="assessment-title">
          THE ₹500
          <br />
          ASSESSMENT
        </h2>
        <p>The fictional office has produced its most ridiculous form: a fake ₹500 UPI assessment. No payment is requested or possible.</p>
        <figure className="no-reaction-card">
          <img src="/images/netanyahu.jpg" alt="Benjamin Netanyahu reaction portrait" />
          <figcaption>NO FILED · REACTION DESK</figcaption>
        </figure>
        <div className="scanner-stage scanner-flash">
          <img
            className="scanner-image"
            src="/upi-scanner-joke.png"
            alt="Non-scannable joke graphic marked zero rupees and nothing charged"
          />
        </div>
        <p className="payment-disclaimer">
          Nothing is charged. The vault alarm plays briefly; Exit for free is always available.
        </p>
        {alarmNeedsGesture && (
          <button className="secondary-button" onClick={playAssessmentAlarm}>
            Play the alarm
          </button>
        )}
        <div className="overlay-actions">
          <button
            className="action-button"
            autoFocus
            onClick={exitForFree}
          >
            Exit for free
          </button>
          <button className="secondary-button" onClick={closeAssessment}>
            Return to board
          </button>
        </div>
        <p className="fine-print">
          Escape closes this screen. Your browser remains yours.
        </p>
      </dialog>
    </div>
  );
}
