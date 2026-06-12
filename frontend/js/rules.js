/* Rule editor modal: low-code flow (examples → suggested pattern → test)
   with an advanced toggle that exposes the raw regex. */

let editingRuleId = null;

const ruleModal = document.getElementById("rule-modal");
const ruleName = document.getElementById("rule-name");
const ruleEntity = document.getElementById("rule-entity");
const ruleExamples = document.getElementById("rule-examples");
const rulePattern = document.getElementById("rule-pattern");
const ruleConfidence = document.getElementById("rule-confidence");
const ruleAction = document.getElementById("rule-action");
const ruleAdvanced = document.getElementById("rule-advanced");
const ruleTestResults = document.getElementById("rule-test-results");
const ruleDeleteBtn = document.getElementById("rule-delete-btn");

function openRuleEditor(rule = null, prefillExample = null) {
  editingRuleId = rule ? rule.id : null;
  document.getElementById("rule-modal-title").textContent = rule ? "Edit rule" : "New rule";
  ruleName.value = rule ? rule.name : "";
  ruleEntity.value = rule ? rule.entity_type : "";
  ruleExamples.value = rule ? (rule.examples || []).join("\n") : (prefillExample || "");
  rulePattern.value = rule ? rule.pattern : "";
  ruleConfidence.value = rule ? rule.confidence : 0.7;
  ruleAction.value = rule ? rule.default_action : "review";
  ruleAdvanced.checked = false;
  rulePattern.readOnly = true;
  ruleTestResults.innerHTML = "";
  ruleDeleteBtn.classList.toggle("hidden", !rule);
  ruleModal.classList.remove("hidden");

  if (!rule && prefillExample) {
    suggestRulePattern();
  }
}

function closeRuleEditor() {
  ruleModal.classList.add("hidden");
}

function ruleExampleList() {
  return ruleExamples.value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

async function suggestRulePattern() {
  const examples = ruleExampleList();
  if (!examples.length) {
    ruleTestResults.innerHTML = '<p class="hint">Add at least one example value first.</p>';
    return;
  }
  try {
    const result = await API.suggestPattern(examples);
    rulePattern.value = result.pattern;
    ruleTestResults.innerHTML = result.matches_examples
      ? '<p class="hint pass">Suggested pattern matches all examples.</p>'
      : '<p class="hint fail">Warning: pattern does not match every example.</p>';
  } catch (err) {
    ruleTestResults.innerHTML = `<p class="hint fail">${err.message}</p>`;
  }
}

async function testRulePattern() {
  const pattern = rulePattern.value.trim();
  if (!pattern) {
    ruleTestResults.innerHTML = '<p class="hint">No pattern to test. Suggest or enter one.</p>';
    return;
  }
  const docIds = Actions.scopeDocIds();
  if (!docIds.length) {
    ruleTestResults.innerHTML = '<p class="hint">Select documents in the left panel first.</p>';
    return;
  }
  try {
    const result = await API.testPattern(pattern, docIds);
    if (!result.valid) {
      ruleTestResults.innerHTML = `<p class="hint fail">${result.error}</p>`;
      return;
    }
    let html = `<p class="hint">${result.total_matches} match(es) across ${result.documents.length} document(s)</p><ul>`;
    for (const doc of result.documents) {
      html += `<li>${doc.filename}: ${doc.match_count}`;
      if (doc.samples.length) html += ` <span class="muted">(${doc.samples.join(", ")})</span>`;
      html += "</li>";
    }
    html += "</ul>";
    ruleTestResults.innerHTML = html;
  } catch (err) {
    ruleTestResults.innerHTML = `<p class="hint fail">${err.message}</p>`;
  }
}

async function saveRule() {
  const payload = {
    name: ruleName.value.trim(),
    entity_type: ruleEntity.value.trim() || ruleName.value.trim().toUpperCase().replace(/\s+/g, "_"),
    pattern: rulePattern.value.trim(),
    examples: ruleExampleList(),
    confidence: parseFloat(ruleConfidence.value) || 0.7,
    default_action: ruleAction.value,
  };
  if (!payload.name) {
    ruleTestResults.innerHTML = '<p class="hint fail">Rule name is required.</p>';
    return;
  }
  if (!payload.pattern) {
    ruleTestResults.innerHTML = '<p class="hint fail">Pattern is required — click Suggest pattern.</p>';
    return;
  }
  try {
    if (editingRuleId) await API.updateRule(editingRuleId, payload);
    else await API.createRule(payload);
    closeRuleEditor();
    await Actions.refreshRules();
  } catch (err) {
    ruleTestResults.innerHTML = `<p class="hint fail">${err.message}</p>`;
  }
}

async function deleteEditingRule() {
  if (!editingRuleId) return;
  if (!confirm("Delete this rule? Existing findings from it are kept.")) return;
  await API.deleteRule(editingRuleId);
  closeRuleEditor();
  await Actions.refreshRules();
}

function initRuleModal() {
  document.getElementById("rule-modal-close").addEventListener("click", closeRuleEditor);
  document.getElementById("rule-cancel-btn").addEventListener("click", closeRuleEditor);
  document.getElementById("rule-save-btn").addEventListener("click", saveRule);
  document.getElementById("rule-suggest-btn").addEventListener("click", suggestRulePattern);
  document.getElementById("rule-test-btn").addEventListener("click", testRulePattern);
  ruleDeleteBtn.addEventListener("click", deleteEditingRule);
  ruleAdvanced.addEventListener("change", () => {
    rulePattern.readOnly = !ruleAdvanced.checked;
    if (ruleAdvanced.checked) rulePattern.focus();
  });
}
