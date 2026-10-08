import { expect, test } from "@playwright/test";

async function openQuestion(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /Open it/ }).click();
}

test("opening, all five replies, terms, and both answers stay usable", async ({ page }) => {
  await openQuestion(page);
  await expect(page.getByText("Would you go on a date with me?")).toBeVisible();
  for (const label of ["Why an entire website?", "What’s the plan?", "Why me?", "What if it’s awkward?", "What if I say no?"]) {
    const button = page.getByRole("button", { name: label });
    await button.click();
    await expect(button).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("button", { name: "Yes, take me out" })).toBeVisible();
  }
  await page.getByRole("button", { name: "Terms and conditions" }).click();
  await expect(page.getByText("One date. No compulsory sequel.")).toBeVisible();
  await expect(page.getByRole("button", { name: "No", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("three deliberate NO selections use original audio, and free exit works", async ({ page, request }) => {
  for (const asset of ["no_first.mp3", "no_third_alarm.mp3", "yes_date_song.mp3"]) {
    expect((await request.get("/audio/" + asset)).status()).toBe(200);
  }
  await page.addInitScript(() => {
    const prior = HTMLMediaElement.prototype.play;
    (window as unknown as { audioAttempts: string[] }).audioAttempts = [];
    HTMLMediaElement.prototype.play = function () {
      (window as unknown as { audioAttempts: string[] }).audioAttempts.push(new URL(this.src).pathname);
      return prior.call(this);
    };
  });
  await openQuestion(page);
  const no = page.getByRole("button", { name: "No", exact: true });
  await no.click();
  await expect(page.getByText("No recorded. I tested this button more than the YES button, which says more about me than I intended.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Leave this page" })).toBeVisible();
  await no.click();
  await expect(page.getByText("I asked the website to take this gracefully. It opened an inquiry.")).toBeVisible();
  await no.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Nothing will be charged");
  expect(await page.evaluate(() => (window as unknown as { audioAttempts: string[] }).audioAttempts)).toEqual([
    "/audio/no_first.mp3", "/audio/no_first.mp3", "/audio/no_third_alarm.mp3"
  ]);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await no.click();
  await page.getByRole("button", { name: "Exit for free" }).click();
  await expect(page.getByRole("heading", { name: "All good." })).toBeVisible();
});

test("YES after NO keeps plan draft, posts guest email once after review, and retries same id", async ({ page }) => {
  await page.route("**/api/plan/status", route => route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  const submissions: Record<string, string>[] = [];
  await page.route("**/api/plan", async route => {
    submissions.push(route.request().postDataJSON());
    await route.fulfill({ status: submissions.length === 1 ? 503 : 200, contentType: "application/json", body: submissions.length === 1 ? "{}" : '{"sent":true,"delivery":"local"}' });
  });
  await openQuestion(page);
  await page.getByRole("button", { name: "No", exact: true }).click();
  await page.getByRole("button", { name: "Yes, take me out" }).click();
  await expect(page.getByRole("heading", { name: "It’s done bro." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause song" })).toBeVisible();
  await page.getByRole("button", { name: "Pause song" }).click();
  await page.getByLabel("Your name").fill("Test Guest");
  await page.getByLabel("Your email").fill("guest@example.test");
  await page.getByLabel("Preferred date").fill("2026-10-15");
  await page.getByLabel("Preferred time").fill("18:00");
  await page.getByLabel("Area or location").fill("South Kolkata");
  await page.getByRole("button", { name: "Review our plan" }).click();
  expect(submissions).toHaveLength(0);
  await expect(page.getByRole("region", { name: "Review your date plan" })).toContainText("guest@example.test");
  await page.getByRole("button", { name: "Send our plan" }).click();
  await expect(page.locator(".form-error")).toContainText("retry this same plan");
  await page.getByRole("button", { name: "Send our plan" }).click();
  await expect(page.locator(".success-message")).toContainText("local development outbox");
  expect(submissions).toHaveLength(2);
  expect(submissions[0].id).toBe(submissions[1].id);
  expect(submissions[0].name).toBe("Test Guest");
  expect(submissions[0].email).toBe("guest@example.test");
});

test("mute persists and missing audio does not block the NO path", async ({ page }) => {
  await page.route("**/audio/no_first.mp3", route => route.abort());
  const warnings: string[] = [];
  page.on("console", message => { if (message.type() === "warning") warnings.push(message.text()); });
  await openQuestion(page);
  await page.getByRole("button", { name: "No", exact: true }).click();
  await expect(page.getByText(/No recorded. I tested this button/)).toBeVisible();
  await expect.poll(() => warnings.some(w => w.includes("/audio/no_first.mp3"))).toBe(true);
  await page.getByRole("button", { name: "Sound on" }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: "Sound off" })).toBeVisible();
});

test("YES works immediately and after dismissing the third NO assessment", async ({ page }) => {
  await page.route("**/api/plan/status", route => route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await openQuestion(page);
  await page.getByRole("button", { name: "Yes, take me out" }).click();
  await expect(page.getByRole("heading", { name: "It’s done bro." })).toBeVisible();
  await expect(page.getByLabel("Your email")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /Open it/ }).click();
  const no = page.getByRole("button", { name: "No", exact: true });
  await no.click(); await no.click(); await no.click();
  await page.getByRole("button", { name: "Back to the question" }).click();
  await page.getByRole("button", { name: "Yes, take me out" }).click();
  await expect(page.getByRole("heading", { name: "It’s done bro." })).toBeVisible();
  expect(await page.locator("audio").evaluateAll(elements => elements.every(element => (element as HTMLAudioElement).src.includes("yes_date_song") || (element as HTMLAudioElement).paused))).toBe(true);
});
