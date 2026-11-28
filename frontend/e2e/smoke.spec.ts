import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const api = "http://127.0.0.1:8000";

test("login, map loads, alerts view is accessible", async ({ page, request }) => {
  const seed = await request.post(`${api}/api/events/seed`, { data: { confirm: true } });
  expect(seed.ok()).toBeTruthy();
  // example.com, not example.test: the API validates emails with
  // Pydantic EmailStr, which rejects special-use TLDs such as .test.
  const email = `e2e-${Date.now()}@example.com`;
  const register = await request.post(`${api}/api/auth/register`, {
    data: { display_name: "E2E Observer", email, password: "local-demo-password" },
  });
  expect(register.ok()).toBeTruthy();
  const login = await request.post(`${api}/api/auth/login`, {
    data: { email, password: "local-demo-password" },
  });
  expect(login.ok()).toBeTruthy();
  const session = await login.json();

  await page.addInitScript((token) => {
    window.localStorage.setItem("gei.auth.access_token", token);
  }, session.access_token);
  await page.goto("/");
  const navigation = page.getByRole("navigation", { name: "Workspace" });
  await expect(navigation.getByRole("button", { name: /Overview/ })).toBeVisible();
  await navigation.getByRole("button", { name: /Map/ }).click();
  await expect(page.getByText("Spatial convergence", { exact: true })).toBeVisible();
  await expect(page.getByText(/Map layers/).first()).toBeVisible();

  await navigation.getByRole("button", { name: /Alerts/ }).click();
  await expect(page.getByRole("heading", { name: /Alerts & anomalies/ })).toBeVisible();
  await expect(page.getByText("Alert sensitivity", { exact: true })).toBeVisible();

  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const serious = accessibility.violations.filter((violation) => ["critical", "serious"].includes(violation.impact || ""));
  expect(serious, JSON.stringify(serious.map(({ id, description, nodes }) => ({ id, description, count: nodes.length })))).toEqual([]);
});
