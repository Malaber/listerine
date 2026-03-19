import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.PREVIEW_BASE_URL ?? "http://127.0.0.1:8000";
const artifactDir = process.env.PREVIEW_ARTIFACT_DIR ?? "e2e-artifacts/ui-e2e";
const videoDir = path.join(artifactDir, "videos");
const previewEmail = "preview@example.com";
const previewInviteeEmail = "preview-invitee@example.com";
const previewHouseholdName = "Preview Household";
const fixtureListName = process.env.UI_E2E_LIST_NAME ?? "Browser Test Shop";

async function resetDir(dir) {
  await fs.rm(dir, { recursive: true, force: true });
  await fs.mkdir(dir, { recursive: true });
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

async function fetchJson(url, init = {}) {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`Request failed for ${url}: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

function withHeaders(token, init = {}) {
  return {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  };
}

async function expectVisible(locator, message) {
  await locator.waitFor({ state: "visible" });
  assert(await locator.isVisible(), message);
}

async function expectHidden(locator, message) {
  await locator.waitFor({ state: "hidden" });
  assert(!(await locator.isVisible().catch(() => false)), message);
}

async function screenshot(page, name) {
  await page.screenshot({ path: path.join(artifactDir, `${name}.png`), fullPage: true });
}

async function loginPreview(context, email = previewEmail) {
  const auth = await fetchJson(new URL("/api/v1/auth/preview/login", baseUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  await context.request.post(new URL("/api/v1/auth/preview/login", baseUrl).toString(), {
    data: { email },
  });
  return auth.access_token;
}

async function getPreviewHouseholdAndList(token) {
  const households = await fetchJson(new URL("/api/v1/households", baseUrl), withHeaders(token));
  assert(households.length > 0, "Expected preview household to exist");
  const householdId = households[0].id;
  const lists = await fetchJson(
    new URL(`/api/v1/households/${householdId}/lists`, baseUrl),
    withHeaders(token),
  );
  const fixtureList = lists.find((list) => list.name === fixtureListName);
  assert(fixtureList, `Expected seeded fixture list named "${fixtureListName}"`);
  return { householdId, previewListId: fixtureList.id };
}

async function resetFixtureItems(token, listId) {
  const items = await fetchJson(new URL(`/api/v1/lists/${listId}/items`, baseUrl), withHeaders(token));
  const expectedChecked = new Map([
    ["Brot", true],
    ["Eier", false],
    ["Hackfleisch", false],
    ["Loose item", false],
    ["Spaghetti", false],
    ["Tofu", false],
    ["Tomaten", false],
  ]);

  for (const item of items) {
    if (item.name.startsWith("Fresh thing")) {
      await fetchJson(
        new URL(`/api/v1/items/${item.id}`, baseUrl),
        withHeaders(token, { method: "DELETE" }),
      );
      continue;
    }

    if (!expectedChecked.has(item.name)) {
      continue;
    }

    const shouldBeChecked = expectedChecked.get(item.name);
    if (Boolean(item.checked) === shouldBeChecked) {
      continue;
    }

    await fetchJson(
      new URL(`/api/v1/items/${item.id}/${shouldBeChecked ? "check" : "uncheck"}`, baseUrl),
      withHeaders(token, { method: "POST" }),
    );
  }
}

async function textList(locator) {
  return locator.evaluateAll((nodes) => nodes.map((node) => node.textContent?.trim() || ""));
}

function itemCard(page, text) {
  return page.locator(".item-card", { hasText: text }).first();
}

function extractInviteToken(inviteUrl) {
  const invitePath = new URL(inviteUrl).pathname;
  return invitePath.split("/").filter(Boolean).at(-1);
}

async function assertPreviewAndDashboardRoutes(context) {
  const previewPage = await context.newPage();
  await previewPage.goto(new URL("/preview", baseUrl).toString(), { waitUntil: "networkidle" });
  await expectVisible(
    previewPage.getByRole("heading", { name: previewHouseholdName }),
    "Expected preview route to render the seeded household",
  );
  await previewPage.close();
}

async function runInviteFlow(ownerPage, browser, scenario) {
  await ownerPage.goto(new URL("/", baseUrl).toString(), { waitUntil: "networkidle" });
  await expectVisible(
    ownerPage.getByRole("heading", { name: "Households and Lists" }),
    "Expected dashboard heading",
  );

  const ownerHouseholdCard = ownerPage.locator(".household-card", { hasText: previewHouseholdName }).first();
  await expectVisible(ownerHouseholdCard, "Expected preview household card on dashboard");

  await ownerHouseholdCard.getByRole("button", { name: "Create invite link" }).click();
  const inviteInput = ownerHouseholdCard.locator(`[data-invite-link-input="${scenario.householdId}"]`);
  await expectVisible(inviteInput, "Expected invite link field after creating invite");
  const inviteUrl = await inviteInput.inputValue();
  assert(inviteUrl.includes("/invite/"), "Expected invite URL");
  const inviteToken = extractInviteToken(inviteUrl);
  assert(inviteToken, "Expected invite token");

  const inviteeContext = await browser.newContext({
    viewport: { width: 1440, height: 1200 },
    recordVideo: {
      dir: videoDir,
      size: { width: 1440, height: 1200 },
    },
  });
  const inviteeDashboard = await inviteeContext.newPage();

  try {
    await loginPreview(inviteeContext, previewInviteeEmail);
    await inviteeDashboard.goto(new URL("/", baseUrl).toString(), { waitUntil: "networkidle" });
    await expectVisible(
      inviteeDashboard.getByRole("heading", { name: "No households yet" }),
      "Invitee should not see any household before accepting an invite",
    );

    const invitePage = await inviteeContext.newPage();
    await inviteeContext.request.post(new URL("/api/v1/auth/logout", baseUrl).toString());
    await invitePage.goto(inviteUrl, { waitUntil: "networkidle" });
    await invitePage.waitForURL(/\/login\?next=%2Finvite%2F|\/login\?next=\/invite\//);
    await screenshot(invitePage, "invite-redirect-login");

    await loginPreview(inviteeContext, previewInviteeEmail);
    await invitePage.reload({ waitUntil: "networkidle" });
    await invitePage.waitForURL(/\/invite\//);
    await expectVisible(
      invitePage.getByRole("heading", { name: "Join a shared grocery space" }),
      "Expected invite details page after preview login",
    );
    await expectVisible(
      invitePage.getByRole("heading", { name: previewHouseholdName }),
      "Expected invite page household name",
    );
    await invitePage.getByRole("button", { name: "Accept invite" }).click();
    await invitePage.waitForURL(new URL("/", baseUrl).toString());
    await expectVisible(
      invitePage.locator(".household-card", { hasText: previewHouseholdName }).first(),
      "Invitee should see the household after accepting the invite",
    );
    const acceptedHouseholdCard = invitePage
      .locator(".household-card", { hasText: previewHouseholdName })
      .filter({ hasText: fixtureListName })
      .first();
    await expectVisible(
      acceptedHouseholdCard,
      "Invitee should see the seeded UI e2e list after accepting the invite",
    );
    await expectVisible(
      acceptedHouseholdCard.getByRole("link", { name: "Open list" }).first(),
      "Invitee should be able to reach the seeded UI e2e list after accepting the invite",
    );
    await screenshot(invitePage, "invite-accepted");
  } finally {
    await inviteeContext.close();
  }
}

async function main() {
  await resetDir(artifactDir);
  await ensureDir(videoDir);

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1200 },
    recordVideo: {
      dir: videoDir,
      size: { width: 1440, height: 1200 },
    },
  });
  const page = await context.newPage();

  try {
    const loginPage = await context.newPage();
    await loginPage.goto(new URL("/", baseUrl).toString(), { waitUntil: "networkidle" });
    await loginPage.waitForURL(/\/login$/);
    await screenshot(loginPage, "redirect-login");
    await loginPage.close();

    const token = await loginPreview(context);
    const scenario = await getPreviewHouseholdAndList(token);
    await resetFixtureItems(token, scenario.previewListId);
    const listUrl = new URL(`/lists/${scenario.previewListId}`, baseUrl).toString();

    await assertPreviewAndDashboardRoutes(context);

    await page.goto(new URL("/", baseUrl).toString(), { waitUntil: "networkidle" });
    await expectVisible(page.getByRole("link", { name: "Admin" }), "Expected admin link for preview user");
    await expectVisible(
      page.getByRole("heading", { name: "Households and Lists" }),
      "Expected dashboard heading for preview user",
    );

    const adminPage = await context.newPage();
    await adminPage.goto(new URL("/admin", baseUrl).toString(), { waitUntil: "networkidle" });
    await expectVisible(
      adminPage.getByRole("link", { name: "Go to application" }),
      "Expected Go to application link in admin",
    );
    await screenshot(adminPage, "admin-home");
    await adminPage.close();

    const pageTwo = await context.newPage();
    await Promise.all([
      page.goto(listUrl, { waitUntil: "networkidle" }),
      pageTwo.goto(listUrl, { waitUntil: "networkidle" }),
    ]);

    const addForm = page.locator("[data-item-form]");
    const editForm = page.locator("[data-item-edit-form]");

    await expectVisible(page.getByRole("button", { name: "Add item" }), "Expected floating add button");

    await page.keyboard.press("Enter");
    await expectVisible(page.getByRole("heading", { name: "Add an item" }), "Enter should open add modal");
    await addForm.getByLabel("Item name").fill("Spag");
    const activeSuggestion = addForm.locator(".item-suggestion", { hasText: "Spaghetti" });
    await expectVisible(activeSuggestion, "Expected duplicate suggestion for active item");
    await activeSuggestion.locator("button").click();
    await expectHidden(page.locator("[data-item-panel]"), "Suggestion reuse should close add modal");
    await page.waitForSelector('[data-item-card].is-highlighted', { timeout: 3000 });

    await page.getByRole("button", { name: "Add item" }).click();
    await addForm.getByLabel("Item name").fill("Brot");
    const checkedSuggestion = addForm.locator(".item-suggestion", { hasText: "Brot" });
    await expectVisible(checkedSuggestion, "Expected suggestion for checked duplicate item");
    await checkedSuggestion.locator("button").click();
    await expectVisible(page.locator("[data-list-toast]", { hasText: "Brot added back to the list." }), "Expected re-add toast");
    await page.locator(".item-category-header h3", { hasText: "Checked off" }).waitFor({ state: "hidden" });
    await expectVisible(page.locator(".item-card", { hasText: "Brot" }), "Brot should be active again");

    const backwarenHeader = page.locator(".item-category-header h3", { hasText: "Backwaren" }).first();
    await expectVisible(backwarenHeader, "Expected Backwaren section");

    const looseItemCard = page.locator(".item-card", { hasText: "Loose item" });
    await looseItemCard.getByRole("button").first().click();
    await expectVisible(page.locator("[data-list-toast]", { hasText: "Loose item checked." }), "Expected check toast");
    await page.locator("[data-list-toast-undo]").click();
    await expectVisible(page.locator(".item-card", { hasText: "Loose item" }), "Undo should restore unchecked item");

    const tofuCard = itemCard(page, "Tofu");
    await tofuCard.getByRole("button").first().click();
    await expectVisible(page.locator("[data-list-toast]", { hasText: "Tofu checked." }), "Expected tofu check toast");
    await page.waitForFunction(
      () => [...document.querySelectorAll(".item-category-header h3")].some((node) => node.textContent?.includes("Checked off")),
    );
    await pageTwo.waitForFunction(
      () => {
        const card = [...document.querySelectorAll(".item-card")].find((node) => node.textContent?.includes("Tofu"));
        return Boolean(card && card.classList.contains("is-checked"));
      },
      { timeout: 5000 },
    );

    const eierCard = itemCard(page, "Eier");
    await eierCard.getByRole("button").first().click();
    await expectVisible(
      page.locator("[data-list-toast]", { hasText: "Eier checked." }),
      "Expected Eier check toast",
    );
    await page.waitForFunction(
      () => {
        const groups = [...document.querySelectorAll(".item-category-group")];
        const checkedGroup = groups.find((group) =>
          group.querySelector(".item-category-header h3")?.textContent?.includes("Checked off")
        );
        if (!checkedGroup) {
          return false;
        }
        const checkedNames = [...checkedGroup.querySelectorAll(".item-card .item-name")].map((node) =>
          node.textContent?.trim()
        );
        return checkedNames[0] === "Eier" && checkedNames.includes("Tofu");
      },
      { timeout: 5000 },
    );
    const checkedNames = await textList(page.locator(".item-category-group:last-child .item-card .item-name"));
    assert.equal(checkedNames[0], "Eier", "Most recently checked item should be first in checked section");
    assert(checkedNames.includes("Tofu"), "Expected previously checked item in checked section");

    const hackfleischCard = itemCard(page, "Hackfleisch");
    await hackfleischCard.getByRole("button", { name: "Delete" }).click();
    await expectVisible(page.locator("[data-list-toast]", { hasText: "Hackfleisch deleted." }), "Expected delete toast");
    await page.locator("[data-list-toast-undo]").click();
    await expectVisible(page.locator(".item-card", { hasText: "Hackfleisch" }), "Undo should restore deleted item");

    await itemCard(page, "Tomaten").click();
    await expectVisible(
      page.locator("[data-item-edit-panel]").getByRole("heading", { name: "Tomaten" }),
      "Clicking item should open edit modal",
    );
    const editSearch = editForm.locator("[data-item-edit-category-search]");
    await editSearch.fill("brot");
    await expectVisible(
      editForm.locator(".category-radio-option", { hasText: "Backwaren" }),
      "Alias search should find Backwaren",
    );
    const aliasTexts = await textList(editForm.locator(".category-radio-option .category-radio-copy span"));
    assert(!aliasTexts.some((text) => text.includes("Also found as")), "Alias helper text should stay hidden");
    await editForm.locator(".category-radio-option", { hasText: "Backwaren" }).click();
    await editForm.locator('input[name="quantity_text"]').fill("4 loaves");
    await editForm.locator('input[name="note"]').fill("for the weekend");
    await editForm.getByRole("button", { name: "Save changes" }).click();
    await page.locator("[data-item-edit-panel] .add-item-close[data-item-edit-close]").click();
    await expectVisible(itemCard(page, "Tomaten"), "Updated item should remain visible");
    await expectVisible(itemCard(page, "Tomaten").locator(".item-meta", { hasText: "4 loaves" }), "Updated quantity should render");

    await page.getByRole("button", { name: "Open list settings" }).click();
    await expectVisible(page.getByRole("heading", { name: "Category order" }), "Expected settings modal");
    const topCategoryBefore = (await textList(page.locator(".item-category-group > .item-category-header h3"))).slice(0, 3);
    assert.equal(topCategoryBefore[0], "Uncategorized", "Uncategorized should stay on top");

    const backwarenSettingsRow = page.locator(".settings-category-row", { hasText: "Backwaren" });
    for (let i = 0; i < 4; i += 1) {
      await backwarenSettingsRow.getByRole("button", { name: /Move Backwaren up/i }).click();
      await page.waitForTimeout(150);
    }
    await page.locator("[data-list-settings-panel] .add-item-close").click();

    await page.waitForFunction(
      () => {
        const headers = [...document.querySelectorAll(".item-category-group > .item-category-header h3")].map(
          (node) => node.textContent?.trim(),
        );
        return headers.indexOf("Backwaren") > -1 && headers.indexOf("Backwaren") < headers.indexOf("Nudeln");
      },
      { timeout: 5000 },
    );
    await pageTwo.waitForFunction(
      () => {
        const headers = [...document.querySelectorAll(".item-category-group > .item-category-header h3")].map(
          (node) => node.textContent?.trim(),
        );
        return headers.indexOf("Backwaren") > -1 && headers.indexOf("Backwaren") < headers.indexOf("Nudeln");
      },
      { timeout: 5000 },
    );

    await page.getByRole("button", { name: "Add item" }).click();
    const freshThingName = `Fresh thing ${Date.now()}`;
    await addForm.getByLabel("Item name").fill(freshThingName);
    await addForm.locator("[data-item-category-search]").fill("brot");
    await addForm.locator(".category-radio-option", { hasText: "Backwaren" }).click();
    await addForm.locator('input[name="quantity_text"]').fill("1");
    await addForm.locator('button[type="submit"]').click();
    const freshThingCard = itemCard(page, freshThingName);
    await expectVisible(freshThingCard, "Expected newly added item");
    await expectVisible(
      page.locator(".item-category-group", { hasText: "Backwaren" }).locator(".item-card", { hasText: freshThingName }),
      "New item should land in the Backwaren section",
    );

    const toast = page.locator("[data-list-toast]");
    await freshThingCard.getByRole("button").first().click();
    await expectVisible(toast, "Expected temporary undo toast");
    await page.waitForTimeout(10500);
    await expectHidden(toast, "Undo toast should disappear after timeout");

    await runInviteFlow(page, browser, scenario);

    await screenshot(page, "ui-e2e-final");
    await screenshot(pageTwo, "ui-e2e-second-client");
  } catch (error) {
    await screenshot(page, "ui-e2e-failure-main").catch(() => {});
    throw error;
  } finally {
    await browser.close();
  }

  const summary = [
    "## UI E2E",
    "",
    "Browser UI flow passed for route rendering, login gating, add/edit flows, duplicate suggestions, undo toasts, category alias search, admin navigation, websocket updates, and household invite acceptance.",
    "",
  ].join("\n");
  await fs.writeFile(path.join(artifactDir, "summary.md"), summary);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
