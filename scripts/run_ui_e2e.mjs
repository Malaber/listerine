import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.PREVIEW_BASE_URL ?? "http://127.0.0.1:8000";
const artifactDir = process.env.PREVIEW_ARTIFACT_DIR ?? "e2e-artifacts/ui-e2e";
const videoDir = path.join(artifactDir, "videos");
const seedPath = process.env.E2E_SEED_PATH ?? "app/fixtures/review_seed.json";

async function resetDir(dir) {
  await fs.rm(dir, { recursive: true, force: true });
  await fs.mkdir(dir, { recursive: true });
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

function toBase64(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  return normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
}

async function loadSeed() {
  const seed = JSON.parse(await fs.readFile(seedPath, "utf8"));
  assert(seed?.e2e, "Expected e2e metadata in seed fixture");
  assert(Array.isArray(seed?.users), "Expected users array in seed fixture");
  assert(Array.isArray(seed?.households), "Expected households array in seed fixture");
  return seed;
}

function fixtureUser(seed, email) {
  const user = seed.users.find((entry) => entry.email === email);
  assert(user, `Expected seeded user ${email}`);
  assert(user.passkey, `Expected seeded passkey for ${email}`);
  assert(user.passkey.private_key_pkcs8_b64, `Expected private key fixture for ${email}`);
  assert(user.passkey.user_handle_b64, `Expected user handle fixture for ${email}`);
  return user;
}

function fixturePrimaryList(seed) {
  const household = seed.households.find((entry) => entry.name === seed.e2e.primary_household);
  assert(household, `Expected primary household ${seed.e2e.primary_household}`);
  const groceryList = household.lists.find((entry) => entry.name === seed.e2e.primary_list);
  assert(groceryList, `Expected primary list ${seed.e2e.primary_list}`);
  return groceryList;
}

async function apiJson(requestContext, url, options = {}) {
  const response = await requestContext.fetch(new URL(url, baseUrl).toString(), options);
  if (!response.ok()) {
    throw new Error(`Request failed for ${url}: ${response.status()} ${response.statusText()}`);
  }
  return response.json();
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

async function installSeededPasskey(page, user, rpId) {
  const client = await page.context().newCDPSession(page);
  await client.send("WebAuthn.enable", { enableUI: false });
  const { authenticatorId } = await client.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      ctap2Version: "ctap2_1",
      transport: "usb",
      hasResidentKey: true,
      hasUserVerification: true,
      automaticPresenceSimulation: true,
      isUserVerified: true,
    },
  });
  await client.send("WebAuthn.setAutomaticPresenceSimulation", {
    authenticatorId,
    enabled: true,
  });
  await client.send("WebAuthn.setUserVerified", {
    authenticatorId,
    isUserVerified: true,
  });
  await client.send("WebAuthn.addCredential", {
    authenticatorId,
    credential: {
      credentialId: toBase64(user.passkey.credential_id),
      isResidentCredential: true,
      rpId,
      privateKey: user.passkey.private_key_pkcs8_b64,
      userHandle: user.passkey.user_handle_b64,
      signCount: Number(user.passkey.sign_count ?? 0),
      userName: user.email,
      userDisplayName: user.display_name,
    },
  });
  const { credentials } = await client.send("WebAuthn.getCredentials", { authenticatorId });
  assert.equal(credentials.length, 1, `Expected seeded credential for ${user.email}`);
  return client;
}

async function loginFromLoginPage(page, user, expectedUrlPattern) {
  await page.locator('[data-passkey-login] input[name="email"]').fill(user.email);
  await page.getByRole("button", { name: "Sign in with passkey" }).click();
  await page.waitForURL(expectedUrlPattern);
}

async function loginFromRoot(page, user, expectedHeading) {
  await page.goto(new URL("/", baseUrl).toString(), { waitUntil: "networkidle" });
  await page.waitForURL(/\/login(\?|$)/);
  await screenshot(page, "redirect-login");
  await loginFromLoginPage(page, user, new URL("/", baseUrl).toString());
  await expectVisible(
    page.getByRole("heading", { name: expectedHeading }),
    `Expected heading ${expectedHeading}`,
  );
}

async function scenarioFromSeed(seed, requestContext) {
  const households = await apiJson(requestContext, "/api/v1/households");
  const household = households.find((entry) => entry.name === seed.e2e.primary_household);
  assert(household, `Expected household ${seed.e2e.primary_household} from seeded fixture`);
  const lists = await apiJson(requestContext, `/api/v1/households/${household.id}/lists`);
  const groceryList = lists.find((entry) => entry.name === seed.e2e.primary_list);
  assert(groceryList, `Expected seeded list ${seed.e2e.primary_list}`);
  return {
    householdId: household.id,
    householdName: household.name,
    listId: groceryList.id,
    listName: groceryList.name,
  };
}

async function resetFixtureItems(requestContext, listId, expectedChecked) {
  const items = await apiJson(requestContext, `/api/v1/lists/${listId}/items`);
  for (const item of items) {
    if (item.name.startsWith("Fresh thing")) {
      await apiJson(requestContext, `/api/v1/items/${item.id}`, { method: "DELETE" });
      continue;
    }

    if (!expectedChecked.has(item.name)) {
      continue;
    }

    const shouldBeChecked = expectedChecked.get(item.name);
    if (Boolean(item.checked) === shouldBeChecked) {
      continue;
    }

    await apiJson(requestContext, `/api/v1/items/${item.id}/${shouldBeChecked ? "check" : "uncheck"}`, {
      method: "POST",
    });
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

async function runInviteFlow(ownerPage, browser, scenario, seed, rpId) {
  await ownerPage.goto(new URL("/", baseUrl).toString(), { waitUntil: "networkidle" });
  await expectVisible(
    ownerPage.getByRole("heading", { name: "Households and Lists" }),
    "Expected dashboard heading",
  );

  const ownerHouseholdCard = ownerPage
    .locator(".household-card", { hasText: scenario.householdName })
    .first();
  await expectVisible(ownerHouseholdCard, "Expected seeded household card on dashboard");

  await ownerHouseholdCard.getByRole("button", { name: "Create invite link" }).click();
  const inviteInput = ownerHouseholdCard.locator(
    `[data-invite-link-input="${scenario.householdId}"]`,
  );
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
  const inviteePage = await inviteeContext.newPage();
  const invitee = fixtureUser(seed, seed.e2e.invitee_email);

  try {
    await installSeededPasskey(inviteePage, invitee, rpId);
    await inviteePage.goto(new URL("/", baseUrl).toString(), { waitUntil: "networkidle" });
    await inviteePage.waitForURL(/\/login(\?|$)/);
    await loginFromLoginPage(inviteePage, invitee, new URL("/", baseUrl).toString());
    await expectVisible(
      inviteePage.getByRole("heading", { name: "No households yet" }),
      "Invitee should not see any household before accepting an invite",
    );

    await inviteeContext.request.post(new URL("/api/v1/auth/logout", baseUrl).toString());
    await inviteePage.goto(inviteUrl, { waitUntil: "networkidle" });
    await inviteePage.waitForURL(/\/login\?next=%2Finvite%2F|\/login\?next=\/invite\//);
    await screenshot(inviteePage, "invite-redirect-login");

    await loginFromLoginPage(inviteePage, invitee, /\/invite\//);
    await expectVisible(
      inviteePage.getByRole("heading", { name: "Join a shared grocery space" }),
      "Expected invite details page after passkey login",
    );
    await expectVisible(
      inviteePage.getByRole("heading", { name: scenario.householdName }),
      "Expected invite page household name",
    );
    await inviteePage.getByRole("button", { name: "Accept invite" }).click();
    await inviteePage.waitForURL(new URL("/", baseUrl).toString());
    const acceptedHouseholdCard = inviteePage
      .locator(".household-card", { hasText: scenario.householdName })
      .filter({ hasText: scenario.listName })
      .first();
    await expectVisible(
      acceptedHouseholdCard,
      "Invitee should see the seeded list after accepting the invite",
    );
    await expectVisible(
      acceptedHouseholdCard.getByRole("link", { name: "Open list" }).first(),
      "Invitee should be able to reach the seeded list after accepting the invite",
    );
    await screenshot(inviteePage, "invite-accepted");
  } finally {
    await inviteeContext.close();
  }
}

async function main() {
  await resetDir(artifactDir);
  await ensureDir(videoDir);

  const seed = await loadSeed();
  const rpId = process.env.WEBAUTHN_RP_ID ?? seed.e2e.rp_id ?? new URL(baseUrl).hostname;
  const owner = fixtureUser(seed, seed.e2e.owner_email);
  const seededPrimaryList = fixturePrimaryList(seed);
  const expectedChecked = new Map(
    seededPrimaryList.items.map((item) => [item.name, Boolean(item.checked)]),
  );

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
    await installSeededPasskey(page, owner, rpId);
    await loginFromRoot(page, owner, "Households and Lists");

    const scenario = await scenarioFromSeed(seed, context.request);
    await resetFixtureItems(context.request, scenario.listId, expectedChecked);
    const listUrl = new URL(`/lists/${scenario.listId}`, baseUrl).toString();

    await expectVisible(page.getByRole("link", { name: "Admin" }), "Expected admin link");

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
    await expectVisible(
      page.locator("[data-list-toast]", { hasText: "Brot added back to the list." }),
      "Expected re-add toast",
    );
    await page.locator(".item-category-header h3", { hasText: "Checked off" }).waitFor({ state: "hidden" });
    await expectVisible(page.locator(".item-card", { hasText: "Brot" }), "Brot should be active again");

    const backwarenHeader = page.locator(".item-category-header h3", { hasText: "Backwaren" }).first();
    await expectVisible(backwarenHeader, "Expected Backwaren section");

    const looseItemCard = page.locator(".item-card", { hasText: "Loose item" });
    await looseItemCard.getByRole("button").first().click();
    await expectVisible(
      page.locator("[data-list-toast]", { hasText: "Loose item checked." }),
      "Expected check toast",
    );
    await page.locator("[data-list-toast-undo]").click();
    await expectVisible(
      page.locator(".item-card", { hasText: "Loose item" }),
      "Undo should restore unchecked item",
    );

    const tofuCard = itemCard(page, "Tofu");
    await tofuCard.getByRole("button").first().click();
    await expectVisible(
      page.locator("[data-list-toast]", { hasText: "Tofu checked." }),
      "Expected tofu check toast",
    );
    await page.waitForFunction(
      () => [...document.querySelectorAll(".item-category-header h3")].some((node) => node.textContent?.includes("Checked off")),
    );
    await pageTwo.waitForFunction(
      () => {
        const card = [...document.querySelectorAll(".item-card")].find((node) =>
          node.textContent?.includes("Tofu"),
        );
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
          group.querySelector(".item-category-header h3")?.textContent?.includes("Checked off"),
        );
        if (!checkedGroup) {
          return false;
        }
        const checkedNames = [...checkedGroup.querySelectorAll(".item-card .item-name")].map(
          (node) => node.textContent?.trim(),
        );
        return checkedNames[0] === "Eier" && checkedNames.includes("Tofu");
      },
      { timeout: 5000 },
    );
    const checkedNames = await textList(
      page.locator(".item-category-group:last-child .item-card .item-name"),
    );
    assert.equal(checkedNames[0], "Eier", "Most recently checked item should be first in checked section");
    assert(checkedNames.includes("Tofu"), "Expected previously checked item in checked section");

    const hackfleischCard = itemCard(page, "Hackfleisch");
    await hackfleischCard.getByRole("button", { name: "Delete" }).click();
    await expectVisible(
      page.locator("[data-list-toast]", { hasText: "Hackfleisch deleted." }),
      "Expected delete toast",
    );
    await page.locator("[data-list-toast-undo]").click();
    await expectVisible(
      page.locator(".item-card", { hasText: "Hackfleisch" }),
      "Undo should restore deleted item",
    );

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
    const aliasTexts = await textList(
      editForm.locator(".category-radio-option .category-radio-copy span"),
    );
    assert(!aliasTexts.some((text) => text.includes("Also found as")), "Alias helper text should stay hidden");
    await editForm.locator(".category-radio-option", { hasText: "Backwaren" }).click();
    await editForm.locator('input[name="quantity_text"]').fill("4 loaves");
    await editForm.locator('input[name="note"]').fill("for the weekend");
    await editForm.getByRole("button", { name: "Save changes" }).click();
    await page.locator("[data-item-edit-panel] .add-item-close[data-item-edit-close]").click();
    await expectVisible(itemCard(page, "Tomaten"), "Updated item should remain visible");
    await expectVisible(
      itemCard(page, "Tomaten").locator(".item-meta", { hasText: "4 loaves" }),
      "Updated quantity should render",
    );

    await page.getByRole("button", { name: "Open list settings" }).click();
    await expectVisible(page.getByRole("heading", { name: "Category order" }), "Expected settings modal");
    const topCategoryBefore = (
      await textList(page.locator(".item-category-group > .item-category-header h3"))
    ).slice(0, 3);
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
      page
        .locator(".item-category-group", { hasText: "Backwaren" })
        .locator(".item-card", { hasText: freshThingName }),
      "New item should land in the Backwaren section",
    );

    const toast = page.locator("[data-list-toast]");
    await freshThingCard.getByRole("button").first().click();
    await expectVisible(toast, "Expected temporary undo toast");
    await page.waitForTimeout(10500);
    await expectHidden(toast, "Undo toast should disappear after timeout");

    await runInviteFlow(page, browser, scenario, seed, rpId);

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
    "Browser UI flow passed using seeded real database data and passkey auth for route rendering, login gating, add/edit flows, duplicate suggestions, undo toasts, category alias search, admin navigation, websocket updates, and household invite acceptance.",
    "",
  ].join("\n");
  await fs.writeFile(path.join(artifactDir, "summary.md"), summary);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
