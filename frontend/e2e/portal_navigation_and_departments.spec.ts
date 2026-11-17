import { test, expect } from "@playwright/test";

test.describe("Government Portal Redesign - Navigation & Department Journey", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  });

  test("1. Landing Page renders government branding and hero sections", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/SIH Hospital AI/);

    // Official Header Banner
    await expect(page.locator("text=SMART INDIA HACKATHON INITIATIVE").first()).toBeVisible();
    await expect(page.locator("text=SIH Hospital AI").first()).toBeVisible();
    await expect(page.locator("text=1075").first()).toBeVisible();

    // Hero Section
    await expect(
      page.locator("h1:has-text('National Hospital Management & Coordination Portal')")
    ).toBeVisible();
    await expect(
      page.locator(
        "text=A unified digital platform for hospital administration, healthcare coordination, registration, verification and monitoring."
      )
    ).toBeVisible();

    // CTAs in Hero
    await expect(page.locator("section a:has-text('Explore Portal')").first()).toBeVisible();
    await expect(page.locator("section a:has-text('Register Hospital')").first()).toBeVisible();

    // Meaningful Sections
    await expect(page.locator("text=About the National Healthcare Coordination Portal")).toBeVisible();
    await expect(page.locator("text=Comprehensive Health System Services")).toBeVisible();
    await expect(page.locator("text=Accredited Hospital Network & Capacity Surveillance")).toBeVisible();
    await expect(page.locator("text=Hospital Registration & Verification Pipeline")).toBeVisible();
    await expect(page.locator("text=Sign In to Health Operations")).toBeVisible();
  });

  test("2. Explore Portal navigation opens Department Selection Page", async ({ page }) => {
    await page.goto("/");
    // Click the hero Explore Portal CTA
    await page.locator("section a:has-text('Explore Portal')").first().click();

    await expect(page).toHaveURL(/\/portal$/);
    await expect(page.locator("h1:has-text('Select Your Department')")).toBeVisible();
    await expect(
      page.locator("text=Choose your authorized department to access the portal.")
    ).toBeVisible();

    // 4 Department Cards
    await expect(page.locator("h2:has-text('HOSPITAL PORTAL')")).toBeVisible();
    await expect(page.locator("h2:has-text('DISTRICT PORTAL')")).toBeVisible();
    await expect(page.locator("h2:has-text('STATE PORTAL')")).toBeVisible();
    await expect(page.locator("h2:has-text('CENTRAL PORTAL')")).toBeVisible();

    // Key Features in Cards
    await expect(page.locator("text=Bed and inventory management")).toBeVisible();
    await expect(page.locator("text=District hospital monitoring")).toBeVisible();
    await expect(page.locator("text=State hospital administration")).toBeVisible();
    await expect(page.locator("text=National-level monitoring")).toBeVisible();
  });

  test("3. Department cards navigate to dedicated login experiences and back", async ({ page }) => {
    await page.goto("/portal");

    // Hospital Login
    await page.locator("a:has-text('Login to Hospital')").click();
    await expect(page).toHaveURL(/\/portal\/hospital\/login$/);
    await expect(page.locator("h1:has-text('Hospital Operations Login')")).toBeVisible();
    await expect(page.locator("input[placeholder*='gh00046']")).toBeVisible();
    await expect(page.locator("input[placeholder*='password']")).toBeVisible();

    // Back navigation to /portal
    await page.locator("a:has-text('Back to Department Selection')").click();
    await expect(page).toHaveURL(/\/portal$/);

    // District Login
    await page.locator("a:has-text('Login to District')").click();
    await expect(page).toHaveURL(/\/portal\/district\/login$/);
    await expect(page.locator("h1:has-text('District Health Authority Login')")).toBeVisible();

    await page.locator("a:has-text('Back to Department Selection')").click();
    await expect(page).toHaveURL(/\/portal$/);

    // State Login
    await page.locator("a:has-text('Login to State')").click();
    await expect(page).toHaveURL(/\/portal\/state\/login$/);
    await expect(page.locator("h1:has-text('State Health Directorate Login')")).toBeVisible();

    await page.locator("a:has-text('Back to Department Selection')").click();
    await expect(page).toHaveURL(/\/portal$/);

    // Central Login
    await page.locator("a:has-text('Login to Central')").click();
    await expect(page).toHaveURL(/\/portal\/central\/login$/);
    await expect(page.locator("h1:has-text('Central Health Command Login')")).toBeVisible();
  });

  test("4. Dedicated Department Login enforces Role Mismatch protection", async ({ page }) => {
    // Attempting to log into Hospital Portal using District Admin credentials
    await page.goto("/portal/hospital/login");

    await page.locator("input[placeholder*='gh00046']").fill("amritsar_district_admin");
    await page.locator("input[placeholder*='password']").fill("district123");
    await page.locator("button:has-text('Sign In to Hospital Portal')").click();

    // Verify Role Mismatch Alert
    await expect(page.locator("text=Department Role Mismatch")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("text=DISTRICT_ADMIN")).toBeVisible();
    await expect(page.locator("a:has-text('Proceed to District Portal')")).toBeVisible();

    // Click redirect to proper authorized portal
    await page.locator("a:has-text('Proceed to District Portal')").click();
    await expect(page).toHaveURL(/\/portal\/district\/login$/);
  });

  test("5. Successful Department Login routes to authorized Role Dashboard", async ({ page }) => {
    await page.goto("/portal/district/login");

    await page.locator("input[placeholder*='amritsar_district_admin']").fill("amritsar_district_admin");
    await page.locator("input[placeholder*='password']").fill("district123");
    await page.locator("button:has-text('Sign In to District Portal')").click();

    // Verify authorized dashboard is shown
    await expect(page.locator("button:has-text('Sign Out')").first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator("text=District Administration").first()).toBeVisible();
    await expect(page.locator("text=Amritsar Health Operations").first()).toBeVisible();

    // Clean sign out
    await page.locator("button:has-text('Sign Out')").first().click();
    await page.waitForTimeout(500);
  });

  test("6. Public links provide direct access to Hospital Registration & Track Application", async ({ page }) => {
    await page.goto("/");

    // Register Hospital from Hero Section
    await page.locator("section a:has-text('Register Hospital')").first().click();
    await expect(page).toHaveURL(/\/register$/);
    await expect(page.locator("text=Healthcare Entity Registration")).toBeVisible();

    // Back to home & Track Application from Hero Section
    await page.goto("/");
    await page.locator("section a:has-text('Track Application')").first().click();
    await expect(page).toHaveURL(/\/application\/track$/);
    await expect(page.locator("text=Track Application Verification Status")).toBeVisible();
  });
});
