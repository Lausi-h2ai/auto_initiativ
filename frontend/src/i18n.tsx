import {
  ReactNode,
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export const SUPPORTED_LOCALES = ["en", "de-DE"] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];

const EN_MESSAGES = {
  "language.label": "Language",
  "language.english": "English",
  "language.german": "German",
  "settings.language.title": "Interface and recruiter language",
  "settings.language.description":
    "New agent explanations follow this workspace language. Existing and external source text remains unchanged.",
} as const;

export type MessageKey = keyof typeof EN_MESSAGES;

const DE_MESSAGES: Record<MessageKey, string> = {
  "language.label": "Sprache",
  "language.english": "Englisch",
  "language.german": "Deutsch",
  "settings.language.title": "Sprache der Oberfläche und des Recruiters",
  "settings.language.description":
    "Neue Agentenerklärungen folgen dieser Workspace-Sprache. Bestehende und externe Originaltexte bleiben unverändert.",
};

export const LOCALE_REGISTRY: Record<
  AppLocale,
  { locale: AppLocale; label: string; fallback: AppLocale; messages: Record<MessageKey, string> }
> = {
  en: { locale: "en", label: "English", fallback: "en", messages: EN_MESSAGES },
  "de-DE": { locale: "de-DE", label: "Deutsch", fallback: "en", messages: DE_MESSAGES },
};

const DE_COPY: Record<string, string> = {
  "Personal recruiter": "Persönlicher Recruiter",
  "A recruiter that stays with you": "Ein Recruiter, der an deiner Seite bleibt",
  "Your search deserves a dedicated team.": "Deine Suche verdient ein eigenes Team.",
  "Specialist agents discover companies, understand your fit, prepare every application, and keep the work moving—quietly and carefully.": "Spezialisierte Agenten entdecken Unternehmen, bewerten deine Passung, bereiten jede Bewerbung vor und halten den Prozess ruhig und sorgfältig in Bewegung.",
  "Private workspace": "Privater Workspace",
  "Evidence-backed work": "Nachweisgestützte Arbeit",
  "Gated delivery": "Kontrollierter Versand",
  "Welcome to Auto Initiativ": "Willkommen bei Auto Initiativ",
  "Meet your recruiter.": "Lerne deinen Recruiter kennen.",
  "Sign in with the invited Google account. Gmail access is requested separately only when you choose to connect a sender.": "Melde dich mit dem eingeladenen Google-Konto an. Der Gmail-Zugriff wird erst separat angefragt, wenn du einen Absender verbindest.",
  "Continue with Google": "Mit Google fortfahren",
  "Your local workspaces": "Deine lokalen Workspaces",
  "Pick up where you left off.": "Mach dort weiter, wo du aufgehört hast.",
  "Each account keeps its profile, campaigns, companies, and documents in a separate workspace on this computer.": "Jedes Konto verwaltet Profil, Kampagnen, Unternehmen und Dokumente in einem eigenen Workspace auf diesem Computer.",
  "Local-only accounts": "Nur lokale Konten",
  "Isolated workspaces": "Getrennte Workspaces",
  "No Google setup": "Keine Google-Einrichtung",
  "Switch workspace": "Workspace wechseln",
  "Create another account.": "Weiteres Konto erstellen.",
  "Who is continuing?": "Wer macht weiter?",
  "Choose an existing local account. You can return here from Settings whenever you want to switch again.": "Wähle ein vorhandenes lokales Konto. Du kannst später in den Einstellungen wieder hierher zurückkehren.",
  "Create a new local account": "Neues lokales Konto erstellen",
  "Back to existing accounts": "Zurück zu vorhandenen Konten",
  "Return to the current workspace": "Zum aktuellen Workspace zurückkehren",
  "Your name": "Dein Name",
  "Create account": "Konto erstellen",
  "Creating workspace…": "Workspace wird erstellt…",
  Current: "Aktuell",
  "Mission control": "Übersicht",
  Companies: "Unternehmen",
  "My story": "Mein Profil",
  "Master CV": "Master-CV",
  Documents: "Dokumente",
  "Open positions": "Offene Stellen",
  "Needs me": "Meine Entscheidung",
  Settings: "Einstellungen",
  Administration: "Administration",
  "Your personal recruiter": "Dein persönlicher Recruiter",
  "Refresh activity": "Aktivitäten aktualisieren",
  "Your first conversation": "Dein erstes Gespräch",
  "Your team is assembled": "Dein Team steht bereit",
  "Your existing work is here": "Deine bisherige Arbeit ist da",
  "A little guidance needed": "Etwas Unterstützung ist nötig",
  "Your search is moving": "Deine Suche kommt voran",
  "Let's give your recruiter the full picture.": "Gib deinem Recruiter das vollständige Bild.",
  "Ready to discover where you belong next.": "Bereit, deinen nächsten passenden Ort zu finden.",
  "Your search history is ready to pick up.": "Deine bisherige Suche kann fortgesetzt werden.",
  "Meet my onboarding recruiter": "Onboarding-Recruiter kennenlernen",
  "Plan my first search": "Meine erste Suche planen",
  "Review my outreach history": "Kontaktverlauf ansehen",
  "Resolve what needs me": "Offene Entscheidungen klären",
  "See what my team found": "Ergebnisse meines Teams ansehen",
  "Reusable foundation": "Wiederverwendbare Grundlage",
  "Your application readiness": "Deine Bewerbungsbereitschaft",
  "Career story approved": "Karriereprofil freigegeben",
  "Master CV ready": "Master-CV bereit",
  "Campaign active": "Kampagne aktiv",
  "Continue Master CV": "Master-CV fortsetzen",
  "Open Master CV": "Master-CV öffnen",
  "Your team": "Dein Team",
  "Working on your behalf": "Arbeitet für dich",
  "View pipeline": "Pipeline ansehen",
  "Your previous work is organized": "Deine bisherige Arbeit ist organisiert",
  "Your team is ready": "Dein Team ist bereit",
  "Start a campaign and the right specialists will take it from there.": "Starte eine Kampagne und die passenden Spezialisten übernehmen den nächsten Schritt.",
  "Search pulse": "Suchfortschritt",
  "Progress that matters": "Fortschritt, der zählt",
  "Companies in your pipeline": "Unternehmen in deiner Pipeline",
  "Applications ready": "Bewerbungen bereit",
  "Outreach sent": "Kontaktaufnahmen gesendet",
  "Decisions waiting": "Offene Entscheidungen",
  "Recruiter notes": "Recruiter-Notizen",
  "A concise record of what happened": "Ein kompakter Verlauf der Ereignisse",
  "Open documents": "Dokumente öffnen",
  "Activity will appear here as your specialists begin their work.": "Aktivitäten erscheinen hier, sobald deine Spezialisten ihre Arbeit beginnen.",
  "Active campaign": "Aktive Kampagne",
  "Existing outreach": "Bisherige Kontaktaufnahmen",
  "Confirm the interpretation": "Interpretation bestätigen",
  "Balanced search coverage": "Ausgewogene Suchabdeckung",
  "Here is how your team understood the brief": "So hat dein Team den Auftrag verstanden",
  "Every target gets its own search pass": "Jedes Ziel erhält einen eigenen Suchlauf",
  "Confirm and start research": "Bestätigen und Recherche starten",
  "New campaign": "Neue Kampagne",
  "Start a new campaign": "Neue Kampagne starten",
  "Application language": "Bewerbungssprache",
  "Match the vacancy or recipient": "An Stelle oder Empfänger anpassen",
  "Career profile": "Karriereprofil",
  Languages: "Sprachen",
  Skills: "Kompetenzen",
  Experience: "Berufserfahrung",
  Education: "Ausbildung",
  "Version history": "Versionsverlauf",
  Portrait: "Porträt",
  Content: "Inhalt",
  Claims: "Aussagen",
  Versions: "Versionen",
  "Professional, and optional": "Professionell und optional",
  "German and Swiss CVs often include a photo. You decide when it appears.": "Deutsche und Schweizer Lebensläufe enthalten häufig ein Foto. Du entscheidest, ob es erscheint.",
  "Add your portrait": "Porträt hinzufügen",
  "Replace portrait": "Porträt ersetzen",
  "Horizontal focus": "Horizontaler Fokus",
  "Vertical focus": "Vertikaler Fokus",
  Zoom: "Zoom",
  "Save crop": "Ausschnitt speichern",
  "Private by design": "Datenschutz von Anfang an",
  "Location metadata is removed. The coach works with the portrait slot, not your image bytes.": "Standortmetadaten werden entfernt. Der Coach arbeitet mit dem Porträtplatz, nicht mit deinen Bilddaten.",
  "Safe iterations": "Sichere Iterationen",
  "Approving creates an immutable source for future tailored CVs.": "Die Freigabe erstellt eine unveränderliche Grundlage für künftige angepasste Lebensläufe.",
  "Approved master": "Freigegebener Master",
  "Saved draft": "Gespeicherter Entwurf",
  "Your first version starts here": "Deine erste Version beginnt hier",
  "Approve the finished design to create a stable reference for tailoring.": "Gib das fertige Design frei, um eine stabile Grundlage für Anpassungen zu schaffen.",
  "See all generated documents": "Alle erzeugten Dokumente ansehen",
  "Nothing needs you right now": "Aktuell ist keine Entscheidung nötig",
  "Your specialists are continuing independently. Genuine exceptions will appear here with a recommendation.": "Deine Spezialisten arbeiten selbstständig weiter. Echte Ausnahmen erscheinen hier mit einer Empfehlung.",
  "Your workspace": "Dein Workspace",
  "Simple controls for how your recruiter works": "Einfache Einstellungen für die Arbeit deines Recruiters",
  Account: "Konto",
  "Create or switch local account": "Lokales Konto erstellen oder wechseln",
  Active: "Aktiv",
  "Sending connection": "Versandverbindung",
  "Gmail is connected": "Gmail ist verbunden",
  "Connect Gmail when you are ready": "Verbinde Gmail, wenn du bereit bist",
  "Gmail connection needs configuration": "Die Gmail-Verbindung muss konfiguriert werden",
  "Using the existing Gmail token configured in your local .env. No additional Google sign-in is required.": "Das vorhandene, lokal in deiner .env konfigurierte Gmail-Token wird verwendet. Eine weitere Google-Anmeldung ist nicht erforderlich.",
  "Sign-in and sending consent stay separate. Agents never receive access to your credentials.": "Anmeldung und Versandfreigabe bleiben getrennt. Agenten erhalten niemals Zugriff auf deine Zugangsdaten.",
  "Add the Google OAuth client ID and secret to the local environment before connecting this workspace.": "Füge der lokalen Umgebung die Google-OAuth-Client-ID und das Client-Secret hinzu, bevor du diesen Workspace verbindest.",
  "Disconnect Gmail": "Gmail trennen",
  "Connect Gmail": "Gmail verbinden",
  "Delivery boundary": "Versandgrenze",
  "Deterministic checks always stay in control.": "Deterministische Prüfungen behalten immer die Kontrolle.",
  "Autopilot campaigns can remove repetitive confirmations, but they cannot bypass dedupe, source, claim, attachment, limit, policy, reservation, or audit checks.": "Autopilot-Kampagnen können wiederholte Bestätigungen vermeiden, aber niemals Duplikat-, Quellen-, Aussagen-, Anhangs-, Limit-, Richtlinien-, Reservierungs- oder Audit-Prüfungen umgehen.",
  "Duplicate protection": "Duplikatschutz",
  "Approved claims": "Freigegebene Aussagen",
  "Send limits": "Versandlimits",
  "Audit trail": "Audit-Protokoll",
  Language: "Sprache",
  English: "Englisch",
  German: "Deutsch",
  "Interface and recruiter language": "Sprache der Oberfläche und des Recruiters",
  "New agent explanations follow this workspace language. Existing and external source text remains unchanged.": "Neue Agentenerklärungen folgen dieser Workspace-Sprache. Bestehende und externe Originaltexte bleiben unverändert.",
  "Gathering your recruiter's latest work…": "Die neuesten Ergebnisse deines Recruiters werden geladen…",
  "Bringing your recruiter team together…": "Dein Recruiter-Team wird zusammengestellt…",
  "Your workspace could not be opened.": "Dein Workspace konnte nicht geöffnet werden.",
  "Try again": "Erneut versuchen",
  "Research specialist": "Recherche-Spezialist",
  "Fit analyst": "Passungsanalyst",
  "CV specialist": "CV-Spezialist",
  "Application team": "Bewerbungsteam",
  "Email writer": "E-Mail-Autor",
  "Delivery coordinator": "Versandkoordinator",
  "Onboarding recruiter": "Onboarding-Recruiter",
  "Vacancy scout": "Stellen-Scout",
  "Vacancy verifier": "Stellenprüfer",
  Discovered: "Entdeckt",
  Qualified: "Qualifiziert",
  Preparing: "In Vorbereitung",
  Ready: "Bereit",
  Sent: "Gesendet",
  Replied: "Beantwortet",
  Running: "Läuft",
  Completed: "Abgeschlossen",
  Failed: "Fehlgeschlagen",
  Blocked: "Blockiert",
  "Needs Review": "Prüfung nötig",
  today: "heute",
};

function initialLocale(): AppLocale {
  const saved = window.localStorage.getItem("ai_locale");
  if (saved === "en" || saved === "de-DE") return saved;
  return navigator.language.toLowerCase().startsWith("de") ? "de-DE" : "en";
}

function translateGerman(value: string): string {
  if (DE_COPY[value]) return DE_COPY[value];
  const patterns: Array<[RegExp, (match: string, capture: string) => string]> = [
    [/^Good (?:morning|afternoon|evening), (.+)\.$/, (_match, name) => `Guten Tag, ${name}.`],
    [/^(\d+) compan(?:y|ies)$/, (_match, count) => `${count} Unternehmen`],
    [/^(\d+) days ago$/, (_match, count) => `vor ${count} Tagen`],
    [/^Posted (.+)$/, (_match, date) => `Veröffentlicht ${date}`],
    [/^Apply by (.+)$/, (_match, date) => `Bewerben bis ${date}`],
  ];
  for (const [pattern, replacement] of patterns) {
    const match = value.match(pattern);
    if (match) return replacement(match[0], match[1]);
  }
  if (value === "1 day ago") return "vor 1 Tag";
  if (value.startsWith("✓ ")) return `✓ ${translateGerman(value.slice(2))}`;
  return value;
}

export function localizeText(value: string, locale: AppLocale): string {
  return locale === "de-DE" ? translateGerman(value) : value;
}

type LocaleContextValue = {
  locale: AppLocale;
  setLocale: (locale: AppLocale) => void;
  t: (key: MessageKey) => string;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<AppLocale>(initialLocale);
  const setLocale = (next: AppLocale) => {
    window.localStorage.setItem("ai_locale", next);
    document.cookie = `ai_locale=${next}; Path=/; Max-Age=31536000; SameSite=Lax`;
    setLocaleState(next);
  };
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  const value = useMemo(
    () => ({
      locale,
      setLocale,
      t: (key: MessageKey) =>
        LOCALE_REGISTRY[locale].messages[key] ||
        LOCALE_REGISTRY[LOCALE_REGISTRY[locale].fallback].messages[key],
    }),
    [locale],
  );
  return <LocaleContext.Provider value={value}><DocumentLocalizer locale={locale} />{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const value = useContext(LocaleContext);
  if (!value) throw new Error("Locale context is unavailable.");
  return value;
}

export function LanguageToggle({ compact = false }: { compact?: boolean }) {
  const { locale, setLocale, t } = useLocale();
  return (
    <div className={`language-toggle ${compact ? "compact" : ""}`} aria-label={t("language.label")}>
      <button className={locale === "en" ? "active" : ""} onClick={() => setLocale("en")} type="button">EN</button>
      <button className={locale === "de-DE" ? "active" : ""} onClick={() => setLocale("de-DE")} type="button">DE</button>
    </div>
  );
}

const legacyTextOriginals = new WeakMap<Node, string>();
const legacyAttributeOriginals = new WeakMap<Element, Map<string, string>>();

function DocumentLocalizer({ locale }: { locale: AppLocale }) {
  useEffect(() => {
    const apply = (root: Node) => {
      const nodes: Node[] = [root];
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) nodes.push(walker.currentNode);
      for (const node of nodes) {
        if (node.nodeType === Node.TEXT_NODE && node.textContent) {
          if (!legacyTextOriginals.has(node)) legacyTextOriginals.set(node, node.textContent);
          const original = legacyTextOriginals.get(node) || node.textContent;
          const trimmed = original.trim();
          const next = trimmed
            ? original.replace(trimmed, localizeText(trimmed, locale))
            : original;
          if (node.textContent !== next) node.textContent = next;
        } else if (node instanceof Element) {
          for (const attribute of ["aria-label", "placeholder", "title"]) {
            const value = node.getAttribute(attribute);
            if (!value) continue;
            if (!legacyAttributeOriginals.has(node)) legacyAttributeOriginals.set(node, new Map());
            const originals = legacyAttributeOriginals.get(node)!;
            if (!originals.has(attribute)) originals.set(attribute, value);
            const next = localizeText(originals.get(attribute)!, locale);
            if (value !== next) node.setAttribute(attribute, next);
          }
        }
      }
    };
    apply(document.body);
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) apply(node);
        if (mutation.type === "characterData") apply(mutation.target);
      }
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [locale]);
  return null;
}
