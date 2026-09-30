import { expect, test } from "@playwright/test";
import { startGame, steer } from "./helpers";

test("first two NO catches play the supplied clip; third plays only the alarm", async ({ page, request }) => {
  const response = await request.get("/audio/no_first.mp3");
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("audio/mpeg");
  const alarmResponse = await request.get("/audio/no_third_alarm.mp3");
  expect(alarmResponse.status()).toBe(200);
  await page.addInitScript(() => {
    const previous = HTMLMediaElement.prototype.play;
    const media = {
      played: [] as string[],
      attempts: [] as string[],
      elements: [] as HTMLMediaElement[],
    };
    (window as unknown as { media: typeof media }).media = media;
    HTMLMediaElement.prototype.play = function () {
      const path = new URL(this.src).pathname;
      media.attempts.push(path);
      media.elements.push(this);
      this.addEventListener("playing", () => media.played.push(path), {
        once: true,
      });
      return previous.call(this);
    };
  });
  await startGame(page);
  await steer(
    page,
    "left",
    "left",
    "right",
    "up",
    "up",
    "down",
    "down",
    "down",
    "down",
    "right",
    "right",
    "right",
  );
  await expect(page.getByRole("dialog")).toBeVisible();
  const attempts = await page.evaluate(
    () =>
      (window as unknown as { media: { attempts: string[] } }).media.attempts,
  );
  expect(attempts).toEqual([
    "/audio/no_first.mp3",
    "/audio/no_first.mp3",
    "/audio/no_third_alarm.mp3",
  ]);
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as { media: { played: string[] } }).media.played,
      ),
    )
    .toContain("/audio/no_third_alarm.mp3");
  await page.getByRole("button", { name: "Return to board" }).click();
  expect(
    await page.evaluate(() =>
      (window as unknown as { media: { elements: HTMLMediaElement[] } }).media.elements.every(
        (element) => element.paused,
      ),
    ),
  ).toBe(true);
});
