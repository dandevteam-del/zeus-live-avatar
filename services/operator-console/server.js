/**
 * Zeus Live Avatar — Operator Console Server
 *
 * Express server that serves the operator dashboard, proxies WebSocket
 * connections to zeus-gateway, subscribes to Redis event channels, and
 * pushes real-time state updates to connected browser clients.
 *
 * Opulent Bots LLC — All rights reserved
 */

"use strict";

const express = require("express");
const http = require("http");
const path = require("path");
const { WebSocketServer, WebSocket } = require("ws");
const { createClient } = require("redis");

// ─── Configuration ──────────────────────────────────────────────────────────

const PORT = parseInt(process.env.OPERATOR_PORT || "8080", 10);
const OPERATOR_AUTH_TOKEN = process.env.OPERATOR_AUTH_TOKEN || "changeme-operator-token";
const GATEWAY_URL = process.env.GATEWAY_URL || "http://zeus-gateway:8000";
const GATEWAY_WS_URL = process.env.GATEWAY_WS_URL || "ws://zeus-gateway:8000/ws";
const REDIS_HOST = process.env.REDIS_HOST || "redis";
const REDIS_PORT = parseInt(process.env.REDIS_PORT || "6379", 10);
const REDIS_PASSWORD = process.env.REDIS_PASSWORD || "";
const LOG_LEVEL = process.env.LOG_LEVEL || "info";

// ─── Logger ─────────────────────────────────────────────────────────────────

const LOG_LEVELS = { debug: 0, info: 1, warning: 2, error: 3 };
const currentLogLevel = LOG_LEVELS[LOG_LEVEL] ?? 1;

function log(level, message, extra = {}) {
  if ((LOG_LEVELS[level] ?? 1) < currentLogLevel) return;
  const entry = {
    timestamp: new Date().toISOString(),
    level,
    service: "operator-console",
    message,
    ...extra,
  };
  console.log(JSON.stringify(entry));
}

// ─── Application State ─────────────────────────────────────────────────────

const state = {
  mode: "conversation",
  speaking: false,
  muted: false,
  turn: "idle",
  services: {
    stt: false,
    tts: false,
    a2f: false,
    gateway: false,
    obs: false,
  },
  latencyMs: 0,
  emotion: "neutral",
  volumeLevel: 0,
  lastUserText: "",
  lastZeusText: "",
};

// Track connected browser clients
const browserClients = new Set();

// ─── Auth Middleware ─────────────────────────────────────────────────────────

function authMiddleware(req, res, next) {
  const token =
    req.query.token ||
    req.headers["x-operator-token"] ||
    req.headers.authorization?.replace("Bearer ", "");

  if (token !== OPERATOR_AUTH_TOKEN) {
    log("warning", "Unauthorized access attempt", { ip: req.ip });
    return res.status(401).json({ error: "Unauthorized — invalid operator token" });
  }
  next();
}

// ─── Express App ────────────────────────────────────────────────────────────

const app = express();
app.use(express.json());

// Health check (no auth required)
app.get("/health", (_req, res) => {
  res.json({ status: "healthy", service: "operator-console", uptime: process.uptime() });
});

// Static files (no auth required — auth handled by token on WS + API)
app.use(express.static(path.join(__dirname, "public")));

// ─── API Routes (all require auth) ─────────────────────────────────────────

app.post("/api/stop", authMiddleware, async (_req, res) => {
  try {
    log("warning", "STOP command issued by operator");
    state.muted = true;
    state.speaking = false;
    await forwardToGateway("/control/stop", { action: "stop" });
    broadcastToBrowsers({ type: "state", state });
    res.json({ ok: true, action: "stop" });
  } catch (err) {
    log("error", "Stop command failed", { error: err.message });
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/reset", authMiddleware, async (_req, res) => {
  try {
    log("info", "RESET command issued by operator");
    state.muted = false;
    state.speaking = false;
    state.turn = "idle";
    state.emotion = "neutral";
    state.volumeLevel = 0;
    await forwardToGateway("/control/reset", { action: "reset" });
    broadcastToBrowsers({ type: "state", state });
    res.json({ ok: true, action: "reset" });
  } catch (err) {
    log("error", "Reset command failed", { error: err.message });
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/mode", authMiddleware, async (req, res) => {
  const { mode } = req.body;
  const validModes = ["meeting", "webinar", "training", "conversation"];
  if (!validModes.includes(mode)) {
    return res.status(400).json({ error: `Invalid mode. Valid: ${validModes.join(", ")}` });
  }
  try {
    log("info", `Mode changed to: ${mode}`);
    state.mode = mode;
    await forwardToGateway("/control/mode", { mode });
    broadcastToBrowsers({ type: "state", state });
    res.json({ ok: true, mode });
  } catch (err) {
    log("error", "Mode change failed", { error: err.message });
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/inject", authMiddleware, async (req, res) => {
  const { text } = req.body;
  if (!text || typeof text !== "string" || text.trim().length === 0) {
    return res.status(400).json({ error: "Text is required" });
  }
  try {
    log("info", `Inject text: "${text.slice(0, 80)}..."`);
    await forwardToGateway("/message", { text: text.trim() });
    broadcastToBrowsers({
      type: "conversation",
      role: "operator",
      text: text.trim(),
      timestamp: Date.now(),
    });
    res.json({ ok: true, text: text.trim() });
  } catch (err) {
    log("error", "Inject failed", { error: err.message });
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/state", authMiddleware, (_req, res) => {
  res.json(state);
});

// ─── Gateway Forwarding ────────────────────────────────────────────────────

async function forwardToGateway(path, body) {
  const url = `${GATEWAY_URL}${path}`;
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${OPERATOR_AUTH_TOKEN}`,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`Gateway returned ${resp.status}: ${text}`);
    }
    return await resp.json().catch(() => ({}));
  } catch (err) {
    log("warning", `Gateway forward failed: ${path}`, { error: err.message });
    throw err;
  }
}

// ─── HTTP + WebSocket Server ───────────────────────────────────────────────

const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: "/ws" });

wss.on("connection", (ws, req) => {
  // Authenticate WebSocket connections
  const url = new URL(req.url, `http://${req.headers.host}`);
  const token = url.searchParams.get("token") || req.headers["x-operator-token"];

  if (token !== OPERATOR_AUTH_TOKEN) {
    log("warning", "Unauthorized WebSocket connection attempt");
    ws.close(4001, "Unauthorized");
    return;
  }

  log("info", "Browser client connected via WebSocket");
  browserClients.add(ws);

  // Send current state immediately
  ws.send(JSON.stringify({ type: "state", state }));

  ws.on("close", () => {
    browserClients.delete(ws);
    log("info", "Browser client disconnected");
  });

  ws.on("error", (err) => {
    log("error", "WebSocket error", { error: err.message });
    browserClients.delete(ws);
  });

  // Handle messages from browser (e.g., quick inject)
  ws.on("message", (data) => {
    try {
      const msg = JSON.parse(data.toString());
      if (msg.type === "ping") {
        ws.send(JSON.stringify({ type: "pong", timestamp: Date.now() }));
      }
    } catch {
      // Ignore malformed messages
    }
  });
});

function broadcastToBrowsers(message) {
  const payload = JSON.stringify(message);
  for (const client of browserClients) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(payload);
    }
  }
}

// ─── Redis Subscriber ───────────────────────────────────────────────────────

let redisClient = null;
let redisSubscriber = null;

async function connectRedis() {
  const redisUrl = REDIS_PASSWORD
    ? `redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}`
    : `redis://${REDIS_HOST}:${REDIS_PORT}`;

  let retryDelay = 1000;
  const maxRetryDelay = 30000;

  while (true) {
    try {
      redisClient = createClient({ url: redisUrl });
      redisSubscriber = redisClient.duplicate();

      redisClient.on("error", (err) => log("warning", "Redis client error", { error: err.message }));
      redisSubscriber.on("error", (err) => log("warning", "Redis subscriber error", { error: err.message }));

      await redisClient.connect();
      await redisSubscriber.connect();

      log("info", "Connected to Redis", { host: REDIS_HOST, port: REDIS_PORT });
      retryDelay = 1000;
      break;
    } catch (err) {
      log("warning", `Redis connection failed, retrying in ${retryDelay / 1000}s`, {
        error: err.message,
      });
      await new Promise((r) => setTimeout(r, retryDelay));
      retryDelay = Math.min(retryDelay * 2, maxRetryDelay);
    }
  }
}

async function subscribeToRedisChannels() {
  if (!redisSubscriber) return;

  const channels = [
    "zeus:speaking",
    "zeus:stop_talking",
    "zeus:barge_in",
    "zeus:user_turn_complete",
    "zeus:response_ready",
    "zeus:emotion",
    "zeus:latency",
    "zeus:volume",
    "zeus:error",
  ];

  for (const channel of channels) {
    await redisSubscriber.subscribe(channel, (message) => {
      handleRedisEvent(channel, message);
    });
  }

  log("info", `Subscribed to ${channels.length} Redis channels`);
}

function handleRedisEvent(channel, message) {
  let data;
  try {
    data = JSON.parse(message);
  } catch {
    data = message;
  }

  switch (channel) {
    case "zeus:speaking":
      state.speaking = String(data).toLowerCase() === "true" || data === true || data === 1;
      state.turn = state.speaking ? "zeus" : "idle";
      broadcastToBrowsers({ type: "speaking", speaking: state.speaking });
      break;

    case "zeus:stop_talking":
      state.speaking = false;
      state.turn = "idle";
      broadcastToBrowsers({ type: "speaking", speaking: false });
      break;

    case "zeus:barge_in":
      state.speaking = false;
      state.turn = "user";
      broadcastToBrowsers({ type: "barge_in", timestamp: data });
      break;

    case "zeus:user_turn_complete":
      state.turn = "processing";
      if (data && data.text) {
        state.lastUserText = data.text;
        broadcastToBrowsers({
          type: "conversation",
          role: "user",
          text: data.text,
          confidence: data.confidence,
          timestamp: Date.now(),
        });
      }
      break;

    case "zeus:response_ready":
      if (data && data.text) {
        state.lastZeusText = data.text;
        broadcastToBrowsers({
          type: "conversation",
          role: "zeus",
          text: data.text,
          timestamp: Date.now(),
        });
      }
      break;

    case "zeus:emotion":
      state.emotion = typeof data === "string" ? data : data.emotion || "neutral";
      broadcastToBrowsers({ type: "emotion", emotion: state.emotion });
      break;

    case "zeus:latency":
      state.latencyMs = typeof data === "number" ? data : parseInt(data, 10) || 0;
      broadcastToBrowsers({ type: "latency", latencyMs: state.latencyMs });
      break;

    case "zeus:volume":
      state.volumeLevel = typeof data === "number" ? data : parseFloat(data) || 0;
      broadcastToBrowsers({ type: "volume", volumeLevel: state.volumeLevel });
      break;

    case "zeus:error":
      broadcastToBrowsers({ type: "error", message: typeof data === "string" ? data : JSON.stringify(data) });
      break;

    default:
      log("debug", `Unhandled Redis channel: ${channel}`);
  }

  broadcastToBrowsers({ type: "state", state });
}

// ─── Service Health Polling ────────────────────────────────────────────────

async function pollServiceHealth() {
  const services = {
    gateway: `${GATEWAY_URL}/health`,
    stt: `${process.env.STT_URL || "http://stt-service:8001"}/health`,
    tts: `${process.env.TTS_URL || "http://tts-service:8002"}/health`,
    a2f: `${process.env.A2F_URL || "http://a2f-bridge:8003"}/health`,
  };

  for (const [name, url] of Object.entries(services)) {
    try {
      const resp = await fetch(url, { signal: AbortSignal.timeout(3000) });
      state.services[name] = resp.ok;
    } catch {
      state.services[name] = false;
    }
  }

  broadcastToBrowsers({ type: "health", services: state.services });
}

// ─── Startup ────────────────────────────────────────────────────────────────

async function main() {
  log("info", "Starting Zeus Operator Console...");

  // Connect to Redis (non-blocking — continues even if Redis is down)
  connectRedis()
    .then(() => subscribeToRedisChannels())
    .catch((err) => log("error", "Redis setup failed", { error: err.message }));

  // Start HTTP server
  server.listen(PORT, () => {
    log("info", `Operator Console listening on port ${PORT}`);
    log("info", `Dashboard: http://localhost:${PORT}/?token=${OPERATOR_AUTH_TOKEN}`);
  });

  // Poll service health every 10 seconds
  setInterval(pollServiceHealth, 10000);
  // Initial health check after 2 seconds (give services time to start)
  setTimeout(pollServiceHealth, 2000);
}

// Graceful shutdown
process.on("SIGTERM", () => {
  log("info", "SIGTERM received, shutting down...");
  server.close();
  if (redisClient) redisClient.quit().catch(() => {});
  if (redisSubscriber) redisSubscriber.quit().catch(() => {});
  process.exit(0);
});

process.on("SIGINT", () => {
  log("info", "SIGINT received, shutting down...");
  server.close();
  if (redisClient) redisClient.quit().catch(() => {});
  if (redisSubscriber) redisSubscriber.quit().catch(() => {});
  process.exit(0);
});

main().catch((err) => {
  log("error", "Fatal startup error", { error: err.message });
  process.exit(1);
});
