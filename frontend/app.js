const state = {
  history: [],
  selectedIds: new Set(),
};

const elements = {
  tabs: document.querySelectorAll(".tab-button"),
  extractPanel: document.querySelector("#extractPanel"),
  historyPanel: document.querySelector("#historyPanel"),
  extractForm: document.querySelector("#extractForm"),
  recipeUrl: document.querySelector("#recipeUrl"),
  previewButton: document.querySelector("#previewButton"),
  extractButton: document.querySelector("#extractButton"),
  message: document.querySelector("#message"),
  urlPreview: document.querySelector("#urlPreview"),
  recipeResult: document.querySelector("#recipeResult"),
  historyBody: document.querySelector("#historyBody"),
  historyCount: document.querySelector("#historyCount"),
  planButton: document.querySelector("#planButton"),
  mealPlanResult: document.querySelector("#mealPlanResult"),
  modalBackdrop: document.querySelector("#modalBackdrop"),
  modalBody: document.querySelector("#modalBody"),
  modalTitle: document.querySelector("#modalTitle"),
  closeModal: document.querySelector("#closeModal"),
};

elements.tabs.forEach((button) => {
  button.addEventListener("click", () => activateTab(button.dataset.tab));
});

elements.extractForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage();
  setLoading(true);

  try {
    const recipe = await apiFetch("/api/recipes/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: elements.recipeUrl.value.trim() }),
    });
    renderRecipe(recipe, elements.recipeResult);
    await loadHistory();
  } catch (error) {
    showMessage(error.message);
  } finally {
    setLoading(false);
  }
});

elements.previewButton.addEventListener("click", async () => {
  hideMessage();
  elements.urlPreview.classList.add("hidden");
  const url = elements.recipeUrl.value.trim();
  if (!url) {
    showMessage("Enter a recipe blog URL first.");
    return;
  }

  elements.previewButton.disabled = true;
  elements.previewButton.textContent = "Previewing...";
  try {
    const preview = await apiFetch("/api/recipes/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    renderUrlPreview(preview);
  } catch (error) {
    showMessage(error.message);
  } finally {
    elements.previewButton.disabled = false;
    elements.previewButton.textContent = "Preview URL";
  }
});

elements.planButton.addEventListener("click", async () => {
  hideMessage();
  const ids = Array.from(state.selectedIds);
  if (ids.length < 3 || ids.length > 5) {
    showMealPlanMessage("Select between 3 and 5 recipes.");
    return;
  }

  elements.planButton.disabled = true;
  elements.planButton.textContent = "Generating...";
  try {
    const plan = await apiFetch("/api/meal-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recipe_ids: ids }),
    });
    renderMealPlan(plan);
  } catch (error) {
    showMealPlanMessage(error.message);
  } finally {
    elements.planButton.disabled = false;
    elements.planButton.textContent = "Generate Meal Plan";
  }
});

elements.closeModal.addEventListener("click", closeModal);
elements.modalBackdrop.addEventListener("click", (event) => {
  if (event.target === elements.modalBackdrop) closeModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModal();
});

initialize();

function activateTab(tabName) {
  elements.tabs.forEach((button) => button.classList.toggle("active", button.dataset.tab === tabName));
  elements.extractPanel.classList.toggle("active", tabName === "extract");
  elements.historyPanel.classList.toggle("active", tabName === "history");
  if (tabName === "history") loadHistory();
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || "Request failed.";
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join(", ") : detail);
  }
  return payload;
}

async function loadHistory() {
  try {
    state.history = await apiFetch("/api/recipes");
    renderHistory();
  } catch (error) {
    showMessage(error.message);
  }
}

async function initialize() {
  await loadHistory();
  const params = new URLSearchParams(window.location.search);
  const tabName = params.get("tab");
  if (tabName === "history") {
    activateTab("history");
  }

  const demoRecipeId = params.get("demoRecipe");
  if (demoRecipeId) {
    try {
      const recipe = await apiFetch(`/api/recipes/${demoRecipeId}`);
      renderRecipe(recipe, elements.recipeResult);
    } catch (error) {
      showMessage(error.message);
    }
  }

  const detailsId = params.get("details");
  if (detailsId) {
    await openDetails(detailsId);
  }
}

function renderHistory() {
  elements.historyCount.textContent = `${state.history.length} saved`;
  elements.historyBody.innerHTML = "";

  if (!state.history.length) {
    elements.historyBody.innerHTML = `<tr><td colspan="6">No saved recipes yet.</td></tr>`;
    return;
  }

  state.history.forEach((recipe) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input type="checkbox" aria-label="Add ${escapeHtml(recipe.title)} to meal plan" ${state.selectedIds.has(recipe.id) ? "checked" : ""}></td>
      <td><strong>${escapeHtml(recipe.title)}</strong><br><a class="source-link" href="${escapeAttribute(recipe.url)}" target="_blank" rel="noreferrer">${escapeHtml(shortUrl(recipe.url))}</a></td>
      <td>${escapeHtml(recipe.cuisine || "unknown")}</td>
      <td><span class="difficulty ${escapeAttribute(recipe.difficulty)}">${escapeHtml(recipe.difficulty)}</span></td>
      <td>${formatDate(recipe.created_at)}</td>
      <td><button class="text-button" type="button">Details</button></td>
    `;

    row.querySelector("input").addEventListener("change", (event) => {
      if (event.target.checked) state.selectedIds.add(recipe.id);
      else state.selectedIds.delete(recipe.id);
    });
    row.querySelector("button").addEventListener("click", () => openDetails(recipe.id));
    elements.historyBody.appendChild(row);
  });
}

async function openDetails(recipeId) {
  try {
    const recipe = await apiFetch(`/api/recipes/${recipeId}`);
    elements.modalTitle.textContent = recipe.title;
    renderRecipe(recipe, elements.modalBody);
    elements.modalBackdrop.classList.remove("hidden");
  } catch (error) {
    showMessage(error.message);
  }
}

function closeModal() {
  elements.modalBackdrop.classList.add("hidden");
  elements.modalBody.innerHTML = "";
}

function renderRecipe(recipe, target) {
  target.className = "recipe-grid";
  target.innerHTML = `
    <section class="summary-band">
      <div class="summary-title">
        <div>
          <h2>${escapeHtml(recipe.title)}</h2>
          <a class="source-link" href="${escapeAttribute(recipe.url)}" target="_blank" rel="noreferrer">${escapeHtml(recipe.url)}</a>
        </div>
        <span class="difficulty ${escapeAttribute(recipe.difficulty)}">${escapeHtml(recipe.difficulty)}</span>
      </div>
      <div class="meta-grid">
        ${metaItem("Cuisine", recipe.cuisine)}
        ${metaItem("Prep", recipe.prep_time)}
        ${metaItem("Cook", recipe.cook_time)}
        ${metaItem("Total", recipe.total_time)}
        ${metaItem("Servings", recipe.servings || "unknown")}
        ${metaItem("Difficulty", recipe.difficulty)}
      </div>
    </section>
    <section class="detail-card span-5">
      <h3>Ingredients</h3>
      <ul class="ingredient-list">${recipe.ingredients.map(renderIngredient).join("")}</ul>
    </section>
    <section class="detail-card span-7">
      <h3>Instructions</h3>
      <ol>${recipe.instructions.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>
    </section>
    <section class="detail-card span-4">
      <h3>Nutrition estimate</h3>
      <div class="nutrition">
        ${nutritionItem("Calories", recipe.nutrition_estimate.calories)}
        ${nutritionItem("Protein", recipe.nutrition_estimate.protein)}
        ${nutritionItem("Carbs", recipe.nutrition_estimate.carbs)}
        ${nutritionItem("Fat", recipe.nutrition_estimate.fat)}
      </div>
    </section>
    <section class="detail-card span-4">
      <h3>Substitutions</h3>
      <ul>${recipe.substitutions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>
    <section class="detail-card span-4">
      <h3>Pairs well with</h3>
      <ul>${recipe.related_recipes.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>
    <section class="detail-card span-12">
      <h3>Shopping list</h3>
      ${renderShoppingList(recipe.shopping_list)}
    </section>
  `;
}

function renderUrlPreview(preview) {
  elements.urlPreview.classList.remove("hidden");
  elements.urlPreview.innerHTML = `
    ${preview.image ? `<img src="${escapeAttribute(preview.image)}" alt="">` : ""}
    <div>
      <span>${escapeHtml(preview.site_name || "unknown")}</span>
      <h2>${escapeHtml(preview.title)}</h2>
      <p>${escapeHtml(preview.description || "unknown")}</p>
      <a class="source-link" href="${escapeAttribute(preview.url)}" target="_blank" rel="noreferrer">${escapeHtml(shortUrl(preview.url))}</a>
    </div>
  `;
}

function renderMealPlan(plan) {
  elements.mealPlanResult.classList.remove("hidden");
  elements.mealPlanResult.innerHTML = `
    <h3>Combined Shopping List</h3>
    <p>${plan.recipes.map((recipe) => escapeHtml(recipe.title)).join(" + ")}</p>
    ${renderShoppingList(plan.combined_shopping_list)}
    <ul>${plan.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>
  `;
}

function showMealPlanMessage(message) {
  elements.mealPlanResult.classList.remove("hidden");
  elements.mealPlanResult.innerHTML = `<p>${escapeHtml(message)}</p>`;
}

function renderIngredient(ingredient) {
  return `
    <li>
      <span class="quantity">${escapeHtml(ingredient.quantity || "")}</span>
      <span class="unit">${escapeHtml(ingredient.unit || "")}</span>
      <span>${escapeHtml(ingredient.item || "")}</span>
    </li>
  `;
}

function renderShoppingList(list) {
  const categories = Object.entries(list || {});
  if (!categories.length) return "<p>No shopping list available.</p>";
  return categories
    .map(
      ([category, items]) => `
        <div class="shopping-category">
          <strong>${escapeHtml(category)}</strong>
          <span>${items.map((item) => escapeHtml(item)).join(", ")}</span>
        </div>
      `,
    )
    .join("");
}

function metaItem(label, value) {
  return `<div class="meta-item"><span class="meta-label">${escapeHtml(label)}</span><span class="meta-value">${escapeHtml(String(value || "unknown"))}</span></div>`;
}

function nutritionItem(label, value) {
  return `<div><span class="meta-label">${escapeHtml(label)}</span><strong>${escapeHtml(String(value || "unknown"))}</strong></div>`;
}

function setLoading(isLoading) {
  elements.extractButton.disabled = isLoading;
  elements.extractButton.textContent = isLoading ? "Extracting..." : "Extract Recipe";
}

function showMessage(message) {
  elements.message.textContent = message;
  elements.message.classList.remove("hidden");
}

function hideMessage() {
  elements.message.classList.add("hidden");
  elements.message.textContent = "";
}

function formatDate(value) {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function shortUrl(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname}`.replace(/\/$/, "");
  } catch {
    return url;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}
