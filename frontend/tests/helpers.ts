import { expect, Page } from "@playwright/test";

export async function startGame(page: Page) {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Thanisha its done bro" }),
  ).toBeVisible();
}

export async function steer(
  page: Page,
  ...directions: Array<"up" | "down" | "left" | "right">
) {
  for (const direction of directions) {
    await page.getByRole("button", { name: `Move ${direction}` }).click();
  }
}
