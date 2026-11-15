"""CodeForge visual system — dark developer workspace."""

from __future__ import annotations


def build_theme():
    import gradio as gr

    return gr.themes.Base(primary_hue="violet", neutral_hue="slate").set(
        body_background_fill="#0B0D12",
        body_background_fill_dark="#0B0D12",
        background_fill_primary="#151B26",
        background_fill_primary_dark="#151B26",
        background_fill_secondary="#11151D",
        background_fill_secondary_dark="#11151D",
        border_color_primary="#252D3A",
        border_color_primary_dark="#252D3A",
        body_text_color="#F1F5F9",
        body_text_color_dark="#F1F5F9",
        body_text_color_subdued="#94A3B8",
        button_primary_background_fill="#8B7CFF",
        button_primary_text_color="#0B0D12",
    )


THEME_CSS = """
:root {
  --cf-bg: #0B0D12;
  --cf-bg-2: #11151D;
  --cf-panel: #151B26;
  --cf-border: #252D3A;
  --cf-text: #F1F5F9;
  --cf-muted: #94A3B8;
  --cf-accent: #8B7CFF;
  --cf-ok: #22C55E;
  --cf-warn: #F59E0B;
  --cf-err: #EF4444;
  --cf-radius: 14px;
}

html, body, .gradio-container, .main, .contain {
  background: var(--cf-bg) !important;
  color: var(--cf-text) !important;
  font-family: "Segoe UI", Inter, ui-sans-serif, system-ui, sans-serif !important;
}

.gradio-container {
  max-width: 1440px !important;
  padding: 18px 20px 28px !important;
}

footer, .footer { display: none !important; }

#codeforge-app .block, #codeforge-app .form, #codeforge-app .panel {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}

/* Auth */
.auth-shell {
  max-width: 460px;
  margin: 8vh auto 0;
}
.brand {
  text-align: center;
  margin-bottom: 28px;
}
.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px; height: 42px;
  border-radius: 12px;
  background: linear-gradient(180deg, #9A8CFF, #6E5CFF);
  color: #0B0D12;
  font-weight: 700;
  letter-spacing: 0.04em;
  margin-bottom: 14px;
}
.brand h1 {
  font-size: 28px;
  letter-spacing: -0.04em;
  margin: 0 0 8px;
  color: var(--cf-text);
}
.brand p {
  margin: 0;
  color: var(--cf-muted);
  font-size: 14.5px;
  line-height: 1.5;
}

.auth-card {
  background: var(--cf-panel);
  border: 1px solid var(--cf-border);
  border-radius: 18px;
  padding: 8px 8px 16px;
}

.cf-error {
  color: var(--cf-err);
  font-size: 13.5px;
  min-height: 1.2em;
}

/* Workspace grid */
.workspace { min-height: 82vh; }
.sidebar {
  background: var(--cf-bg-2);
  border: 1px solid var(--cf-border);
  border-radius: var(--cf-radius);
  padding: 14px 12px 12px;
  min-height: 78vh;
}
.main-col, .artifact-col {
  background: var(--cf-bg-2);
  border: 1px solid var(--cf-border);
  border-radius: var(--cf-radius);
  padding: 12px;
  min-height: 78vh;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 6px 14px;
  font-weight: 650;
  letter-spacing: -0.03em;
}
.sidebar-logo span.mark {
  width: 28px; height: 28px; border-radius: 8px;
  background: var(--cf-accent); color: #0B0D12;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 800;
}

button.primary, .primary-btn button {
  background: var(--cf-accent) !important;
  color: #0B0D12 !important;
  border: none !important;
  font-weight: 650 !important;
}

.quota { padding: 8px 4px 12px; }
.quota-meta {
  display: flex; justify-content: space-between;
  color: var(--cf-muted); font-size: 12px; margin-bottom: 8px;
}
.quota-track {
  height: 6px; border-radius: 99px; background: #1C2430; overflow: hidden;
}
.quota-fill {
  height: 100%; background: var(--cf-accent); border-radius: 99px;
}
.quota-reset { color: var(--cf-muted); font-size: 11px; margin-top: 6px; }

.roadmap { padding: 8px 4px 4px; }
.roadmap-title {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.12em;
  color: var(--cf-muted); margin-bottom: 8px;
}
.roadmap-item {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 12.5px; padding: 5px 0; color: var(--cf-text);
}
.roadmap-item.next { color: var(--cf-muted); }
.roadmap-item .tag {
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
  padding: 2px 7px; border-radius: 99px; border: 1px solid var(--cf-border);
  color: var(--cf-muted);
}
.roadmap-item.live .tag { color: var(--cf-ok); border-color: #16351f; }

.profile {
  display: flex; gap: 10px; align-items: center; padding: 10px 4px 6px;
  border-top: 1px solid var(--cf-border); margin-top: 8px;
}
.avatar {
  width: 32px; height: 32px; border-radius: 10px;
  background: #1E2633; display: flex; align-items: center; justify-content: center;
  font-weight: 700; color: var(--cf-accent);
}
.profile-name { font-size: 13.5px; }
.profile-email { font-size: 11.5px; color: var(--cf-muted); }

.badge {
  display: inline-block; margin-top: 4px;
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em;
  padding: 2px 7px; border-radius: 99px; border: 1px solid var(--cf-border);
}
.badge-student { color: var(--cf-muted); }
.badge-instructor { color: var(--cf-accent); border-color: #3b3470; }

.empty-hero {
  text-align: center; padding: 48px 16px 12px; color: var(--cf-muted);
}
.empty-hero h2 {
  color: var(--cf-text); font-size: 28px; letter-spacing: -0.04em; margin: 0 0 8px;
}

.instructor-panel {
  border: 1px dashed var(--cf-border);
  border-radius: 12px;
  padding: 10px 12px;
  color: var(--cf-muted);
  font-size: 13px;
  margin-top: 8px;
}

#chatbot { background: transparent !important; border: none !important; }
#composer textarea {
  background: #0E131B !important;
  border: 1px solid var(--cf-border) !important;
  color: var(--cf-text) !important;
}

.code-actions { margin-top: 6px; }

@media (max-width: 980px) {
  .sidebar, .main-col, .artifact-col { min-height: auto; }
  .gradio-container { padding: 10px !important; }
  .auth-shell { margin-top: 4vh; }
}
"""
