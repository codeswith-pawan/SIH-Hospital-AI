import { test } from "@playwright/test";

test.describe("Capture Redesigned Portal Screenshots", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  });

  test("Capture desktop & mobile screenshots of major redesigned pages", async ({ page }, testInfo) => {
    // Only capture for Desktop Chrome project to prevent duplicate captures
    if (testInfo.project.name === "Desktop Chrome") {
      // 1. Landing Page
      await page.goto("/");
      await page.waitForTimeout(500);
      await page.screenshot({ path: "public/screenshots/01_landing_page_desktop.png", fullPage: true });

      // 2. Department Selection Page
      await page.goto("/portal");
      await page.waitForTimeout(500);
      await page.screenshot({ path: "public/screenshots/02_department_selection_desktop.png", fullPage: true });

      // 3. Hospital Login
      await page.goto("/portal/hospital/login");
      await page.waitForTimeout(500);
      await page.screenshot({ path: "public/screenshots/03_hospital_login.png", fullPage: true });

      // 4. District Login
      await page.goto("/portal/district/login");
      await page.waitForTimeout(500);
      await page.screenshot({ path: "public/screenshots/04_district_login.png", fullPage: true });

      // 5. State Login
      await page.goto("/portal/state/login");
      await page.waitForTimeout(500);
      await page.screenshot({ path: "public/screenshots/05_state_login.png", fullPage: true });

      // 6. Central Login
      await page.goto("/portal/central/login");
      await page.waitForTimeout(500);
      await page.screenshot({ path: "public/screenshots/06_central_login.png", fullPage: true });

      // 7. Role Mismatch State
      await page.goto("/portal/hospital/login");
      await page.locator("input[placeholder*='gh00046']").fill("amritsar_district_admin");
      await page.locator("input[placeholder*='password']").fill("district123");
      await page.locator("button:has-text('Sign In to Hospital Portal')").click();
      await page.waitForSelector("text=Department Role Mismatch");
      await page.screenshot({ path: "public/screenshots/07_role_mismatch_state.png", fullPage: false });
    }

    if (testInfo.project.name === "Mobile Chrome") {
      // Mobile Landing Page
      await page.goto("/");
      await page.waitForTimeout(500);
      await page.screenshot({ path: "public/screenshots/08_landing_page_mobile.png", fullPage: true });

      // Mobile Department Selection Page
      await page.goto("/portal");
      await page.waitForTimeout(500);
      await page.screenshot({ path: "public/screenshots/09_department_selection_mobile.png", fullPage: true });
    }
  });
});
