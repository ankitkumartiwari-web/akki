from __future__ import annotations

import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

from . import __version__

logger = logging.getLogger("akki.webui")

ChatHandler = Callable[[str], dict[str, Any]]
StatusHandler = Callable[[], dict[str, Any]]
ToolsHandler = Callable[[], list[dict[str, Any]]]

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>AKKI</title>
  <style>
    :root {
      color-scheme: dark;
      --md-sys-color-primary: #6fe7d2;
      --md-sys-color-on-primary: #00382f;
      --md-sys-color-primary-container: #123b36;
      --md-sys-color-on-primary-container: #b8f5ea;
      --md-sys-color-secondary: #8fd0c2;
      --md-sys-color-secondary-container: #173c36;
      --md-sys-color-on-secondary-container: #cdeee2;
      --md-sys-color-tertiary: #c3a7f5;
      --md-sys-color-tertiary-container: #2f2250;
      --md-sys-color-on-tertiary-container: #e0d2fb;
      --md-sys-color-error: #ffb4ab;
      --md-sys-color-on-error: #690005;
      --md-sys-color-error-container: #93000a;
      --md-sys-color-background: #0b0d12;
      --md-sys-color-surface: #0e1014;
      --md-sys-color-surface-container-lowest: #090b0f;
      --md-sys-color-surface-container-low: #11141a;
      --md-sys-color-surface-container: #151922;
      --md-sys-color-surface-container-high: #1b2029;
      --md-sys-color-surface-container-highest: #22262f;
      --md-sys-color-surface-variant: #2a2e38;
      --md-sys-color-on-surface: #e7eaf2;
      --md-sys-color-on-surface-variant: #a9b1c1;
      --md-sys-color-outline: #3a3f4b;
      --md-sys-color-outline-variant: #242935;
      --md-sys-color-inverse-surface: #e7eaf2;
      --md-sys-color-inverse-on-surface: #191c22;
      --md-shape-extra-small: 4px;
      --md-shape-small: 8px;
      --md-shape-medium: 12px;
      --md-shape-large: 16px;
      --md-shape-extra-large: 28px;
      --md-shape-full: 9999px;
      --md-state-hover: rgba(255, 255, 255, 0.08);
      --md-state-pressed: rgba(255, 255, 255, 0.10);
      --font: "Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      font-family: var(--font);
      color: var(--md-sys-color-on-surface);
      background: var(--md-sys-color-background);
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }
    ::selection { background: rgba(111, 231, 210, 0.28); }
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-thumb { background: #272d38; border-radius: 9999px; border: 2px solid transparent; background-clip: content-box; }
    ::-webkit-scrollbar-thumb:hover { background: #333b49; background-clip: content-box; }
    ::-webkit-scrollbar-track { background: transparent; }

    .app {
      height: 100vh;
      display: grid;
      grid-template-columns: 92px minmax(0, 1fr);
      gap: 18px;
      padding: 20px;
    }
    .rail {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 10px;
      padding: 16px 10px;
      background: var(--md-sys-color-surface-container-low);
      border: 1px solid var(--md-sys-color-outline-variant);
      border-radius: var(--md-shape-extra-large);
    }
    .rail-brand {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      padding-bottom: 10px;
    }
    .rail-orb, .orb {
      background: radial-gradient(circle at 34% 28%, #b6fff2 0%, #6fe7d2 38%, #2bb9a5 70%, #145e55 100%);
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.16);
    }
    .rail-orb { width: 42px; height: 42px; border-radius: 15px; }
    .rail-word { font-size: 10px; letter-spacing: 0.16em; color: var(--md-sys-color-on-surface-variant); }
    .rail-btn {
      position: relative;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 4px;
      width: 68px;
      height: 62px;
      border: 0;
      border-radius: 20px;
      background: transparent;
      color: var(--md-sys-color-on-surface-variant);
      font: inherit;
      font-size: 11px;
      font-weight: 500;
      cursor: pointer;
      transition: background-color 180ms cubic-bezier(0.2, 0, 0, 1), color 180ms cubic-bezier(0.2, 0, 0, 1);
    }
    .rail-btn::before {
      content: "";
      position: absolute;
      inset: 0;
      border-radius: inherit;
      background: var(--md-state-hover);
      opacity: 0;
      transition: opacity 160ms ease;
    }
    .rail-btn:hover::before { opacity: 0.55; }
    .rail-btn:active::before { opacity: 1; background: var(--md-state-pressed); }
    .rail-btn svg { width: 21px; height: 21px; position: relative; z-index: 1; }
    .rail-btn span { position: relative; z-index: 1; }
    .rail-btn.selected {
      background: var(--md-sys-color-primary-container);
      color: var(--md-sys-color-on-primary-container);
    }
    .rail-space { flex: 1; }
    .rail-status {
      width: 40px;
      height: 40px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      border: 1px solid var(--md-sys-color-outline-variant);
      background: var(--md-sys-color-surface-container);
    }

    .shell {
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: 0;
      background: var(--md-sys-color-surface-container-low);
      border: 1px solid var(--md-sys-color-outline-variant);
      border-radius: var(--md-shape-extra-large);
      overflow: hidden;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 24px 30px 16px;
    }
    .topbar h1 {
      margin: 0;
      font-size: 27px;
      line-height: 34px;
      font-weight: 600;
      letter-spacing: -0.01em;
    }
    .topbar p {
      margin: 4px 0 0;
      font-size: 13px;
      color: var(--md-sys-color-on-surface-variant);
    }
    .status-pill {
      display: flex;
      align-items: center;
      gap: 9px;
      padding: 9px 16px;
      border-radius: var(--md-shape-full);
      border: 1px solid var(--md-sys-color-outline-variant);
      background: var(--md-sys-color-surface-container);
      font-size: 12.5px;
      color: var(--md-sys-color-on-surface-variant);
      white-space: nowrap;
    }
    .status-pill b { color: var(--md-sys-color-on-surface); font-weight: 600; }
    .status-pill .sep { opacity: 0.5; margin: 0 2px; }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #8ee3b4;
      box-shadow: 0 0 0 4px rgba(142, 227, 180, 0.14);
      flex: none;
    }
    .dot.off { background: #ffb4ab; box-shadow: 0 0 0 4px rgba(255, 180, 171, 0.14); }

    .view { display: none; flex: 1; min-height: 0; flex-direction: column; }
    .view.active { display: flex; }

    .thread {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 10px 30px 14px;
      display: flex;
      flex-direction: column;
      gap: 20px;
      scroll-behavior: smooth;
    }
    .row { display: flex; align-items: flex-end; gap: 10px; }
    .row.user { justify-content: flex-end; }
    .avatar {
      width: 30px;
      height: 30px;
      border-radius: 50%;
      flex: none;
      background: radial-gradient(circle at 34% 28%, #b6fff2 0%, #6fe7d2 38%, #2bb9a5 70%, #145e55 100%);
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.16);
      margin-bottom: 2px;
    }
    .stack { max-width: min(720px, 74%); display: flex; flex-direction: column; }
    .meta { font-size: 11px; color: var(--md-sys-color-on-surface-variant); opacity: 0.75; margin: 0 6px 6px; }
    .row.user .meta { text-align: right; }
    .bubble {
      padding: 12px 17px;
      border-radius: 19px;
      font-size: 14.5px;
      line-height: 1.55;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .row.akki .bubble {
      background: var(--md-sys-color-surface-container-high);
      border: 1px solid var(--md-sys-color-outline-variant);
      border-bottom-left-radius: 7px;
    }
    .row.user .bubble {
      background: var(--md-sys-color-primary-container);
      border: 1px solid #1e4f48;
      color: #d9fbf4;
      border-bottom-right-radius: 7px;
    }
    .bubble.error {
      background: rgba(147, 0, 10, 0.32);
      border-color: rgba(255, 180, 171, 0.45);
      color: #ffdad6;
    }
    .typing { display: inline-flex; gap: 5px; align-items: center; padding: 4px 2px; }
    .typing i {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--md-sys-color-on-surface-variant);
      opacity: 0.45;
      animation: pulse 1.1s ease-in-out infinite;
    }
    .typing i:nth-child(2) { animation-delay: 0.16s; }
    .typing i:nth-child(3) { animation-delay: 0.32s; }
    @keyframes pulse {
      0%, 100% { opacity: 0.3; transform: translateY(0); }
      40% { opacity: 0.95; transform: translateY(-3px); }
    }

    .empty {
      margin: auto;
      width: min(560px, 90%);
      padding-bottom: 40px;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      gap: 14px;
    }
    .empty .orb {
      width: 66px;
      height: 66px;
      border-radius: 23px;
    }
    .empty h2 { margin: 4px 0 0; font-size: 21px; font-weight: 600; letter-spacing: -0.01em; }
    .empty p { margin: 0; font-size: 13.5px; line-height: 1.6; color: var(--md-sys-color-on-surface-variant); }
    .suggestions { display: flex; flex-wrap: wrap; gap: 9px; justify-content: center; margin-top: 6px; }
    .suggestion {
      height: 36px;
      padding: 0 15px;
      border-radius: var(--md-shape-full);
      border: 1px solid var(--md-sys-color-outline);
      background: var(--md-sys-color-surface-container);
      color: var(--md-sys-color-on-surface-variant);
      font: inherit;
      font-size: 12.5px;
      cursor: pointer;
      transition: background-color 160ms ease, color 160ms ease;
    }
    .suggestion:hover { background: var(--md-sys-color-surface-container-high); color: var(--md-sys-color-on-surface); }


    .composer-block { padding: 4px 26px 20px; flex: none; }
    .composer {
      display: flex;
      align-items: flex-end;
      gap: 10px;
      padding: 8px 8px 8px 20px;
      background: var(--md-sys-color-surface-container);
      border: 1px solid var(--md-sys-color-outline-variant);
      border-radius: 26px;
      transition: border-color 180ms ease, box-shadow 180ms ease;
    }
    .composer:focus-within {
      border-color: #3f8a7f;
      box-shadow: 0 0 0 3px rgba(111, 231, 210, 0.08);
    }
    .composer textarea {
      flex: 1;
      min-height: 44px;
      max-height: 138px;
      padding: 11px 0;
      border: 0;
      outline: 0;
      resize: none;
      background: transparent;
      color: var(--md-sys-color-on-surface);
      font: inherit;
      font-size: 14.5px;
      line-height: 1.5;
    }
    .composer textarea::placeholder { color: #747c89; }
    .send {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      height: 44px;
      padding: 0 20px;
      border: 0;
      border-radius: var(--md-shape-full);
      background: var(--md-sys-color-primary);
      color: var(--md-sys-color-on-primary);
      font: inherit;
      font-size: 13.5px;
      font-weight: 600;
      cursor: pointer;
      transition: filter 160ms ease, opacity 160ms ease;
    }
    .send svg { width: 16px; height: 16px; }
    .send:hover { filter: brightness(1.06); }
    .send:disabled { opacity: 0.45; cursor: default; filter: none; }
    .hint {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 9px 12px 0;
      font-size: 11.5px;
      color: #747c89;
    }
    kbd {
      font: inherit;
      font-size: 10.5px;
      padding: 1px 6px;
      border-radius: 6px;
      border: 1px solid var(--md-sys-color-outline-variant);
      background: var(--md-sys-color-surface-container);
      color: var(--md-sys-color-on-surface-variant);
    }

    .system-wrap {
      flex: 1;
      min-height: 0;
      overflow: auto;
      padding: 8px 30px 28px;
      display: grid;
      grid-template-columns: minmax(300px, 0.85fr) minmax(0, 1.15fr);
      gap: 16px;
      align-content: start;
    }
    .card {
      background: var(--md-sys-color-surface-container);
      border: 1px solid var(--md-sys-color-outline-variant);
      border-radius: var(--md-shape-large);
      padding: 20px 22px;
      min-width: 0;
    }
    .section-label {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.09em;
      text-transform: uppercase;
      color: #8b93a3;
    }
    .kv {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      padding: 10px 0;
      border-bottom: 1px solid #1e232d;
      font-size: 13px;
      color: var(--md-sys-color-on-surface-variant);
    }
    .kv:last-child { border-bottom: 0; padding-bottom: 2px; }
    .kv > span:last-child { color: var(--md-sys-color-on-surface); text-align: right; overflow-wrap: anywhere; }
    .tools {
      display: flex;
      flex-direction: column;
      gap: 2px;
      max-height: 560px;
      overflow-y: auto;
      margin: 0 -8px;
      padding: 0 4px;
    }
    .tool {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
      gap: 2px 12px;
      padding: 10px 10px;
      border-radius: var(--md-shape-medium);
      transition: background-color 150ms ease;
    }
    .tool:hover { background: var(--md-sys-color-surface-container-high); }
    .tool-name { font-size: 13px; font-weight: 600; overflow-wrap: anywhere; }
    .tool-desc { grid-column: 1; font-size: 11.5px; line-height: 1.45; color: #8b93a3; }
    .chip {
      grid-column: 2;
      grid-row: 1 / span 2;
      align-self: center;
      padding: 3px 9px;
      border-radius: var(--md-shape-full);
      border: 1px solid var(--md-sys-color-outline-variant);
      font-size: 10.5px;
      font-weight: 500;
      color: var(--md-sys-color-on-surface-variant);
      white-space: nowrap;
      text-transform: capitalize;
    }
    .chip.read_only { color: #9fe8dc; border-color: #24443f; background: rgba(111, 231, 210, 0.07); }
    .chip.reversible { color: #f3d59b; border-color: #4a3f26; background: rgba(243, 213, 155, 0.07); }
    .chip.sensitive { color: #ddc8ff; border-color: #413459; background: rgba(195, 167, 245, 0.08); }
    .chip.destructive, .chip.elevated { color: #ffc9c2; border-color: #53302d; background: rgba(255, 180, 171, 0.08); }

    .snackbar {
      position: fixed;
      left: 50%;
      bottom: 28px;
      transform: translate(-50%, 16px);
      opacity: 0;
      pointer-events: none;
      padding: 12px 20px;
      border-radius: var(--md-shape-medium);
      background: var(--md-sys-color-inverse-surface);
      color: var(--md-sys-color-inverse-on-surface);
      font-size: 13px;
      font-weight: 500;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
      transition: opacity 200ms ease, transform 200ms ease;
      z-index: 10;
    }
    .snackbar.show { opacity: 1; transform: translate(-50%, 0); }

    @media (max-width: 980px) {
      .app { grid-template-columns: 76px minmax(0, 1fr); gap: 12px; padding: 12px; }
      .rail-btn { width: 56px; height: 56px; font-size: 10px; }
      .rail-btn span { display: none; }
      .system-wrap { grid-template-columns: 1fr; }
      .thread, .system-wrap { padding-left: 18px; padding-right: 18px; }
      .composer-block { padding-left: 16px; padding-right: 16px; }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { animation-duration: 0.001ms !important; transition-duration: 0.001ms !important; }
      .thread { scroll-behavior: auto; }
    }
  </style>
</head>
<body>
  <div class="app">
    <nav class="rail" aria-label="Primary">
      <div class="rail-brand">
        <div class="rail-orb" aria-hidden="true"></div>
        <div class="rail-word">AKKI</div>
      </div>
      <button class="rail-btn selected" type="button" data-view="chat" aria-pressed="true">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 4h13a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H8l-5 4v-4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M8 8h8M8 12h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
        <span>Chat</span>
      </button>
      <button class="rail-btn" type="button" data-view="system" aria-pressed="false">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="4" y="4" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="4" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.8"/><rect x="4" y="13" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="13" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.8"/></svg>
        <span>System</span>
      </button>
      <div class="rail-space"></div>
      <div class="rail-status" title="Connected">
        <span class="dot on" id="rail-dot"></span>
      </div>
    </nav>

    <main class="shell">
      <header class="topbar">
        <div>
          <h1 id="view-title">Chat</h1>
          <p id="view-sub">Ask a question or run a command on this PC.</p>
        </div>
        <div class="status-pill" id="status-pill" title="">
          <span class="dot on" id="pill-dot"></span>
          <span><b id="pill-profile">AKKI</b><span class="sep">&#183;</span><span id="pill-model">connecting</span></span>
        </div>
      </header>

      <section class="view active" id="view-chat">
        <div class="thread" id="thread" aria-live="polite"></div>
        <div class="composer-block">
          <form class="composer" id="chat-form">
            <textarea id="message" rows="1" autocomplete="off" placeholder="Message AKKI" aria-label="Message AKKI"></textarea>
            <button class="send" id="send" type="submit" aria-label="Send message">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4.2 11.3 19.4 4.6c.8-.35 1.65.5 1.3 1.3l-6.7 15.2c-.36.82-1.55.8-1.88-.03l-2.1-5.32-5.32-2.1c-.83-.33-.85-1.52-.03-1.88Z" fill="currentColor"/></svg>
              <span>Send</span>
            </button>
          </form>
          <div class="hint">
            <span><kbd>Enter</kbd> to send &#183; <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line</span>
            <span id="latency"></span>
          </div>
        </div>
      </section>

      <section class="view" id="view-system">
        <div class="system-wrap">
          <article class="card">
            <div class="section-label"><span>Status</span><span class="dot on" id="dot"></span></div>
            <div class="kv"><span>Connection</span><span id="conn">Connected</span></div>
            <div class="kv"><span>Version</span><span id="version">-</span></div>
            <div class="kv"><span>Profile</span><span id="profile">-</span></div>
            <div class="kv"><span>Model</span><span id="model" title="">-</span></div>
            <div class="kv"><span>Session</span><span><strong id="session-count">0 messages</strong></span></div>
            <div class="kv"><span>Started</span><span><strong id="session-start">-</strong></span></div>
            <div class="kv"><span>Endpoint</span><span>127.0.0.1</span></div>
          </article>
          <article class="card">
            <div class="section-label"><span>Tools</span><span id="tool-count"></span></div>
            <div class="tools" id="tools"></div>
          </article>
        </div>
      </section>
    </main>
  </div>

  <div class="snackbar" id="toast" role="status"></div>


  <script>
    const thread = document.querySelector("#thread");
    const form = document.querySelector("#chat-form");
    const input = document.querySelector("#message");
    const send = document.querySelector("#send");
    const toastEl = document.querySelector("#toast");
    const views = { chat: "#view-chat", system: "#view-system" };
    const subtitles = {
      chat: ["Chat", "Ask a question or run a command on this PC."],
      system: ["System", "Live status and every tool AKKI can use on this machine."]
    };
    const status = {
      dot: document.querySelector("#dot"),
      railDot: document.querySelector("#rail-dot"),
      pillDot: document.querySelector("#pill-dot"),
      conn: document.querySelector("#conn"),
      version: document.querySelector("#version"),
      profile: document.querySelector("#profile"),
      model: document.querySelector("#model"),
      pillProfile: document.querySelector("#pill-profile"),
      pillModel: document.querySelector("#pill-model"),
      pill: document.querySelector("#status-pill"),
      latency: document.querySelector("#latency"),
      toolCount: document.querySelector("#tool-count"),
      tools: document.querySelector("#tools"),
      sessionCount: document.querySelector("#session-count"),
      sessionStart: document.querySelector("#session-start")
    };
    const started = new Date();
    let messages = 0;
    let busy = false;
    let snackTimer = null;

    function setConnection(ok) {
      const classes = "dot " + (ok ? "on" : "off");
      status.dot.className = classes;
      status.railDot.className = classes;
      status.pillDot.className = classes;
      status.conn.textContent = ok ? "Connected" : "Unavailable";
    }

    function showToast(text) {
      toastEl.textContent = text;
      toastEl.classList.add("show");
      clearTimeout(snackTimer);
      snackTimer = setTimeout(() => toastEl.classList.remove("show"), 2600);
    }

    function emptyState() {
      thread.innerHTML = "";
      const wrap = document.createElement("div");
      wrap.className = "empty";
      wrap.innerHTML =
        '<div class="orb" aria-hidden="true"></div>' +
        '<h2>AKKI is running on this PC</h2>' +
        "<p>Ask a question, switch languages, or give it a task. Everything here talks to the same assistant that runs on your desktop.</p>" +
        '<div class="suggestions"></div>';
      const words = ["Volume down", "Tum kaun ho?", "Kya tum locally chalti ho?"];
      const box = wrap.querySelector(".suggestions");
      for (const word of words) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "suggestion";
        button.textContent = word;
        button.addEventListener("click", () => {
          input.value = word;
          autoGrow();
          input.focus();
        });
        box.append(button);
      }
      thread.append(wrap);
    }

    function append(role, text, when, isError) {
      const empty = thread.querySelector(".empty");
      if (empty) empty.remove();
      const row = document.createElement("div");
      row.className = "row " + role;
      if (role === "akki") {
        const avatar = document.createElement("div");
        avatar.className = "avatar";
        avatar.setAttribute("aria-hidden", "true");
        row.append(avatar);
      }
      const stack = document.createElement("div");
      stack.className = "stack";
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = (role === "user" ? "You" : "AKKI") + "  " + timeLabel(when || new Date());
      const bubble = document.createElement("div");
      bubble.className = "bubble" + (isError ? " error" : "");
      bubble.textContent = text;
      stack.append(meta, bubble);
      row.append(stack);
      thread.append(row);
      thread.scrollTop = thread.scrollHeight;
      messages += 1;
      status.sessionCount.textContent = messages + (messages === 1 ? " message" : " messages");
      return bubble;
    }

    function typingBubble() {
      const empty = thread.querySelector(".empty");
      if (empty) empty.remove();
      const row = document.createElement("div");
      row.className = "row akki";
      row.id = "typing-row";
      const avatar = document.createElement("div");
      avatar.className = "avatar";
      avatar.setAttribute("aria-hidden", "true");
      const stack = document.createElement("div");
      stack.className = "stack";
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = "AKKI";
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      const dots = document.createElement("span");
      dots.className = "typing";
      dots.innerHTML = "<i></i><i></i><i></i>";
      bubble.append(dots);
      stack.append(meta, bubble);
      row.append(avatar, stack);
      thread.append(row);
      thread.scrollTop = thread.scrollHeight;
      return row;
    }

    function autoGrow() {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 138) + "px";
    }

    function timeLabel(date) {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    async function refreshStatus() {
      try {
        const response = await fetch("/api/status");
        if (!response.ok) throw new Error("status");
        const data = await response.json();
        setConnection(true);
        status.version.textContent = data.version || "-";
        status.profile.textContent = data.profile || "-";
        status.model.textContent = data.model || "-";
        status.model.title = data.model || "";
        status.pillProfile.textContent = data.profile || "AKKI";
        status.pillModel.textContent = data.model || "ready";
        status.pill.title = (data.version || "") + "  " + (data.model || "");
      } catch (error) {
        setConnection(false);
        status.pillModel.textContent = "offline";
      }
    }

    async function refreshTools() {
      try {
        const response = await fetch("/api/tools");
        if (!response.ok) throw new Error("tools");
        const data = await response.json();
        const tools = Array.isArray(data.tools) ? data.tools : [];
        status.tools.innerHTML = "";
        status.toolCount.textContent = tools.length + (tools.length === 1 ? " tool" : " tools");
        for (const tool of tools) {
          const item = document.createElement("div");
          item.className = "tool";
          const name = document.createElement("div");
          name.className = "tool-name";
          name.textContent = tool.name || "tool";
          const desc = document.createElement("div");
          desc.className = "tool-desc";
          desc.textContent = tool.description || "";
          const level = document.createElement("span");
          const levelName = String(tool.level || "tool").toLowerCase();
          level.className = "chip " + levelName;
          level.textContent = levelName.replaceAll("_", " ");
          item.append(name, desc, level);
          status.tools.append(item);
        }
      } catch (error) {
        status.toolCount.textContent = "unavailable";
      }
    }

    async function sendMessage(text) {
      const startedAt = performance.now();
      append("user", text);
      busy = true;
      send.disabled = true;
      status.latency.textContent = "";
      const pending = typingBubble();
      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text })
        });
        const data = await response.json();
        pending.remove();
        append("akki", data.message || "No reply.", new Date(), !response.ok || data.ok === false);
        const seconds = (performance.now() - startedAt) / 1000;
        status.latency.textContent = seconds.toFixed(1) + "s";
      } catch (error) {
        pending.remove();
        append("akki", "Could not reach AKKI: " + error.message, new Date(), true);
        showToast("Request failed");
      } finally {
        busy = false;
        send.disabled = false;
        input.focus();
      }
    }

    document.querySelectorAll(".rail-btn").forEach((button) => {
      button.addEventListener("click", () => {
        const name = button.dataset.view;
        document.querySelectorAll(".rail-btn").forEach((other) => {
          const active = other === button;
          other.classList.toggle("selected", active);
          other.setAttribute("aria-pressed", String(active));
        });
        document.querySelectorAll(".view").forEach((view) => {
          view.classList.toggle("active", view.id === views[name]);
        });
        document.querySelector("#view-title").textContent = subtitles[name][0];
        document.querySelector("#view-sub").textContent = subtitles[name][1];
        if (name === "chat") {
          input.focus();
        } else {
          refreshStatus();
          refreshTools();
        }
      });
    });

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (busy) return;
      const text = input.value.trim();
      if (!text) return;
      input.value = "";
      autoGrow();
      sendMessage(text);
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        form.requestSubmit();
      }
    });

    input.addEventListener("input", autoGrow);

    status.sessionStart.textContent = timeLabel(started);
    status.sessionCount.textContent = "0 messages";
    emptyState();
    refreshStatus();
    refreshTools();
    setInterval(refreshStatus, 20000);
    input.focus();
  </script>
</body>
</html>

"""


class WebUIError(RuntimeError):
    pass


class _Handler(BaseHTTPRequestHandler):
    server_version = f"AKKI/{__version__}"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/status":
            self._send_json(self.server.akki_status())
            return
        if path == "/api/tools":
            self._send_json({"tools": self.server.akki_tools()})
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json({"ok": False, "message": "invalid content length"}, HTTPStatus.BAD_REQUEST)
            return
        if length <= 0 or length > 1_000_000:
            self._send_json({"ok": False, "message": "request body is empty or too large"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"ok": False, "message": "invalid JSON body"}, HTTPStatus.BAD_REQUEST)
            return
        text = str(payload.get("text", "")).strip() if isinstance(payload, dict) else ""
        if not text:
            self._send_json({"ok": False, "message": "text is required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            reply = self.server.akki_chat(text)
        except Exception as exc:
            logger.exception("web chat failed")
            self._send_json({"ok": False, "message": f"request failed: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(reply)

    def log_message(self, format: str, *args: object) -> None:
        logger.debug("webui %s - %s", self.address_string(), format % args)

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status=status)

    def _send_bytes(
        self, body: bytes, content_type: str, *, status: int = HTTPStatus.OK
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class WebUI:
    def __init__(
        self,
        chat: ChatHandler,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        status: StatusHandler | None = None,
        tools: ToolsHandler | None = None,
    ) -> None:
        self.chat = chat
        self.host = host
        self.port = port
        self.status = status or (lambda: {})
        self.tools = tools or (lambda: [])
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> str:
        if self.active:
            return self.url
        try:
            server = ThreadingHTTPServer((self.host, self.port), _Handler)
        except OSError as exc:
            raise WebUIError(f"could not start web UI on {self.host}:{self.port}: {exc}") from exc
        server.akki_chat = self.chat
        server.akki_status = self.status
        server.akki_tools = self.tools
        server.daemon_threads = True
        self.port = int(server.server_address[1])
        thread = threading.Thread(target=server.serve_forever, name="akki-webui", daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        logger.info("web ui started at %s", self.url)
        return self.url

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(2)
        logger.info("web ui stopped")
