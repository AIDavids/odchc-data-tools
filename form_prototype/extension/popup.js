// Prototype. Uses only the "activeTab" permission (the original prototype asked for every site).
// The field map is a plain config file, so pointing it at another form means editing JSON, not code.
let records = [], index = 0, fieldMap = {};
const status = document.getElementById("status");
const show = () => (status.textContent = records.length ? `Record ${index + 1} of ${records.length}` : "Load records.json");

fetch("fieldmap.json").then(r => r.json()).then(m => (fieldMap = m));

chrome.storage.local.get(["records", "index"], d => {
  records = d.records || [];
  index = d.index || 0;
  show();
});

document.getElementById("file").addEventListener("change", async e => {
  records = JSON.parse(await e.target.files[0].text());
  index = 0;
  chrome.storage.local.set({ records, index });
  show();
});

document.getElementById("next").addEventListener("click", () => {
  if (index < records.length - 1) index++;
  chrome.storage.local.set({ index });
  show();
});

document.getElementById("fill").addEventListener("click", async () => {
  if (!records.length) return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    args: [records[index], fieldMap],
    func: (rec, map) => {
      for (const [field, id] of Object.entries(map)) {
        const el = document.getElementById(id);
        if (!el || rec[field] == null) continue;
        el.value = rec[field];
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));  // lets the page compute age etc.
      }
    },
  });
});
