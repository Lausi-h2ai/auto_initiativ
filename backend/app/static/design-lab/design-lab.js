(() => {
  "use strict";

  const companies = [
    {
      name: "LatticeFlow",
      location: "Zurich, Switzerland",
      description: "Builds tools for evaluating and improving computer vision systems in regulated environments.",
      reasons: ["Strong overlap with model quality work", "Practical AI product with Swiss presence"],
      confidence: "High fit",
      detail:
        "This is a strong match if you want applied AI with real customer constraints. The clearest angle is reliability work around model behavior, data quality, and trustworthy deployment.",
    },
    {
      name: "Scandit",
      location: "Zurich, Switzerland",
      description: "Creates smart data capture products for logistics, retail, and field operations.",
      reasons: ["Computer vision at production scale", "Clear product engineering path"],
      confidence: "High fit",
      detail:
        "The best application angle is practical AI in operational workflows, with emphasis on robust user-facing systems and document or visual data capture.",
    },
    {
      name: "Viso.ai",
      location: "Schaffhausen, Switzerland",
      description: "Offers an end-to-end platform for deploying computer vision applications across edge devices.",
      reasons: ["Applied computer vision platform", "Relevant infrastructure and workflow needs"],
      confidence: "Promising fit",
      detail:
        "This match is promising, but contact quality should be verified before preparing outreach. The role angle should stay focused on platform reliability and useful AI deployment.",
    },
    {
      name: "Lakera",
      location: "Zurich, Switzerland",
      description: "Works on security and safety tooling for generative AI applications.",
      reasons: ["AI safety with product focus", "Good match for careful claims and evaluation"],
      confidence: "Promising fit",
      detail:
        "This is most relevant if you want safety-oriented AI product work. The outreach should avoid overstating security credentials and focus on evaluation discipline.",
    },
    {
      name: "Synthara",
      location: "Zurich, Switzerland",
      description: "Develops efficient AI chips and software for low-power intelligent devices.",
      reasons: ["Technical product environment", "Useful AI systems near hardware"],
      confidence: "Selective fit",
      detail:
        "This is a selective match. It may be worthwhile if the target role values product engineering around AI systems rather than deep hardware specialization.",
    },
  ];

  const focusFirst = (root) => {
    const focusable = root.querySelector("button, [href], input, textarea, select, [tabindex]:not([tabindex='-1'])");
    focusable?.focus();
  };

  const openModal = (name) => {
    const modal = document.querySelector(`[data-modal="${name}"]`);
    if (!modal) return;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    focusFirst(modal);
  };

  const closeModal = (modal) => {
    modal.hidden = true;
    document.body.style.overflow = "";
  };

  document.addEventListener("click", (event) => {
    const target = event.target.closest("button, a");
    if (!target) return;

    const modalName = target.getAttribute("data-open-modal");
    if (modalName) {
      openModal(modalName);
      return;
    }

    if (target.hasAttribute("data-close-modal")) {
      const modal = target.closest("[data-modal]");
      if (modal) closeModal(modal);
      return;
    }

    const panelId = target.getAttribute("data-toggle-panel");
    if (panelId) {
      const panel = document.getElementById(panelId);
      if (!panel) return;
      panel.hidden = !panel.hidden;
      target.textContent = panel.hidden ? "See recent progress" : "Hide recent progress";
      return;
    }

    if (target.hasAttribute("data-complete-item")) {
      const item = target.closest("li");
      item?.classList.add("is-complete");
      target.textContent = "Confirmed";
      target.disabled = true;
      return;
    }

    const companyIndex = target.getAttribute("data-select-company");
    if (companyIndex !== null) {
      selectCompany(Number(companyIndex));
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll("[data-modal]:not([hidden])").forEach((modal) => closeModal(modal));
  });

  document.querySelectorAll("[data-modal]").forEach((modal) => {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeModal(modal);
    });
  });

  document.querySelectorAll(".choice-card input").forEach((input) => {
    input.addEventListener("change", () => {
      document.querySelectorAll(".choice-card").forEach((card) => card.classList.remove("selected"));
      input.closest(".choice-card")?.classList.add("selected");
    });
  });

  const guidedForm = document.querySelector("[data-guided-form]");
  guidedForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const preview = document.querySelector("[data-next-preview]");
    if (preview) {
      preview.innerHTML = "<strong>Saved locally</strong><span>The next screen would ask for exclusions before launching research.</span>";
    }
  });

  document.querySelector("[data-step-back]")?.addEventListener("click", () => {
    const preview = document.querySelector("[data-next-preview]");
    if (preview) {
      preview.innerHTML = "<strong>Previous</strong><span>You would return to target locations and work model preferences.</span>";
    }
  });

  const renderCompanies = () => {
    const list = document.querySelector("[data-company-list]");
    if (!list) return;
    list.innerHTML = companies
      .map(
        (company, index) => `
          <article class="company-row ${index === 0 ? "selected" : ""}" data-company-row="${index}">
            <div>
              <h2>${company.name}</h2>
              <p>${company.description}</p>
              <div class="company-meta">
                <span>${company.location}</span>
                <span>${company.reasons[0]}</span>
                <span>${company.confidence}</span>
              </div>
            </div>
            <button type="button" data-select-company="${index}">Review fit</button>
          </article>
        `,
      )
      .join("");
    selectCompany(0);
  };

  function selectCompany(index) {
    const company = companies[index];
    const detail = document.querySelector("[data-company-detail]");
    if (!company || !detail) return;

    document.querySelectorAll("[data-company-row]").forEach((row) => {
      row.classList.toggle("selected", row.getAttribute("data-company-row") === String(index));
    });

    detail.innerHTML = `
      <span class="detail-confidence">${company.confidence}</span>
      <h2>${company.name}</h2>
      <p>${company.detail}</p>
      <div class="detail-section">
        <h3>Why it matches</h3>
        <ul>
          ${company.reasons.map((reason) => `<li>${reason}</li>`).join("")}
        </ul>
      </div>
      <div class="detail-section">
        <h3>What would happen next</h3>
        <p>Prepare a tailored application brief for your review. Nothing is sent from this concept.</p>
      </div>
    `;
  }

  if (document.body.dataset.concept === "c") {
    renderCompanies();
  }
})();
