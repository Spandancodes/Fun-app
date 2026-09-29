import { expect, test } from "@playwright/test";
import { startGame, steer } from "./helpers";

test("YES ends the chase, links the official track, and offers a reviewed plan", async ({ page }) => {
  await startGame(page);
  await steer(page, "right", "right");
  await expect(page.getByRole("heading", { name: /It’s done bro/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Play.*Don’t Stop the Music/ }))
    .toHaveAttribute("href", "https://www.youtube.com/watch?v=yd8jh9QYfEs");
  await expect(page.getByRole("link", { name: /Connect on Instagram/ }))
    .toHaveAttribute("href", "https://www.instagram.com/_.avalanche.who");
  await expect(page.getByLabel("Preferred date")).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveCount(0);

  await page.route("**/api/plan", async (route) => {
    expect(route.request().postDataJSON()).not.toHaveProperty("email");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sent: true, delivery: "local" }),
    });
  });
  await page.getByLabel("Preferred date").fill("2026-10-10");
  await page.getByLabel("Preferred time").fill("17:00");
  await page.getByLabel("Area or location").fill("South Kolkata");
  await page.getByRole("button", { name: "Review our plan" }).click();
  await expect(page.getByRole("region", { name: "Review your date plan" })).toContainText("Nothing has been sent yet");
  await page.getByRole("button", { name: "Send our plan" }).click();
  await expect(page.getByRole("status")).toContainText("local development outbox");
  await page.getByRole("button", { name: "Play again" }).click();
  await expect(page.getByRole("heading", { name: "Thanisha its done bro" })).toBeVisible();
});

test("three NO catches open a fake scanner assessment with free exits", async ({ page }) => {
  await startGame(page);
  await steer(page, "left", "left");
  await expect(page.getByText("1 / 3")).toBeVisible();
  await steer(page, "right", "up", "up");
  await expect(page.getByText("2 / 3")).toBeVisible();
  await expect(page.getByRole("status").getByRole("img", { name: "Benjamin Netanyahu reaction portrait" })).toBeVisible();
  await steer(page, "down", "down", "down", "down", "right", "right", "right");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("₹500");
  await expect(dialog).toContainText("No payment is requested or possible");
  await expect(dialog.getByRole("img", { name: /Non-scannable joke graphic/ })).toHaveAttribute("src", "/upi-scanner-joke.png");
  await expect(dialog.getByRole("img", { name: "Benjamin Netanyahu reaction portrait" })).toBeVisible();
  await expect(page.getByText(/Certainty is a brief candle/)).toBeVisible();
  await expect(page.locator("img[src='/images/salman-khan.jpg']")).toHaveCount(0);
  await expect(page.locator("img[src='/images/gyanesh-kumar.jpg']")).toHaveCount(0);
  await page.getByRole("button", { name: "Return to board" }).click();
  await expect(dialog).not.toBeVisible();
  await steer(page, "left", "left", "left", "left");
  await expect(dialog).toBeVisible();
  await page.getByRole("button", { name: "Exit for free" }).click();
  await expect(page.getByRole("heading", { name: "Free to go." })).toBeVisible();
});

test("keyboard, swipe, visible controls, and missing exact audio remain safe", async ({ page, isMobile }) => {
  await page.route("**/audio/no_first.mp3", (route) => route.abort());
  const warnings: string[] = [];
  await page.addInitScript(() => {
    const prior = HTMLMediaElement.prototype.play;
    (window as unknown as { attempts: string[] }).attempts = [];
    HTMLMediaElement.prototype.play = function () {
      (window as unknown as { attempts: string[] }).attempts.push(new URL(this.src).pathname);
      return prior.call(this);
    };
  });
  page.on("console", (message) => {
    if (message.type() === "warning") warnings.push(message.text());
  });
  await startGame(page);
  if (isMobile) {
    const board = page.getByRole("img", { name: /Snake ballot/ });
    const box = await board.boundingBox();
    expect(box).toBeTruthy();
    await page.evaluate(() => {
      const board = document.querySelector(".ballot-board")!;
      board.dispatchEvent(new TouchEvent("touchstart", { bubbles: true, touches: [new Touch({ identifier: 1, target: board, clientX: 200, clientY: 200 })] }));
      board.dispatchEvent(new TouchEvent("touchend", { bubbles: true, changedTouches: [new Touch({ identifier: 1, target: board, clientX: 100, clientY: 200 })] }));
    });
    await steer(page, "left");
  } else {
    await page.keyboard.press("ArrowLeft");
    await page.keyboard.press("a");
  }
  await expect(page.getByText("1 / 3")).toBeVisible();
  const attempts = await page.evaluate(() => (window as unknown as { attempts: string[] }).attempts);
  expect(attempts).toContain("/audio/no_first.mp3");
  expect(attempts).not.toContain("/audio/no_third_alarm.mp3");
  await expect.poll(() => warnings.some((warning) => warning.includes("/audio/no_first.mp3"))).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("sign-in only asks for invited name and email and does not reveal invite matching", async ({ page }) => {
  await page.route("**/api/session", (route) => route.fulfill({ status: 401, body: "{}" }));
  await page.route("**/api/login", (route) => route.fulfill({
    status: 202,
    contentType: "application/json",
    body: JSON.stringify({ message: "If this invitation matches, a sign-in link is on its way." }),
  }));
  await page.goto("/");
  await page.getByLabel("Name").fill("Test Guest");
  await page.getByLabel("Email").fill("test@example.test");
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  await expect(page.getByRole("status")).toContainText("If the invitation matches");
  await expect(page.getByLabel(/phone/i)).toHaveCount(0);
});
