const { app, BrowserWindow, shell } = require("electron");
const { spawn, spawnSync } = require("child_process");
const http = require("http");
const fs = require("fs");
const path = require("path");
const {
  backendEnvironment,
  publicRuntimeConfig,
  readStoredConfig,
  saveRuntimeConfig,
} = require("./runtime-config.cjs");

let server;
let backendProcess;
let backendStarting;
const backendPort = 8000;
const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
};

function sendJson(res, status, value) {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(value));
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 65536) reject(new Error("配置请求过大"));
    });
    req.on("end", () => {
      try {
        resolve(JSON.parse(body || "{}"));
      } catch {
        reject(new Error("配置数据不是有效 JSON"));
      }
    });
    req.on("error", reject);
  });
}

function healthCheck() {
  return new Promise((resolve) => {
    const request = http.get(
      { hostname: "127.0.0.1", port: backendPort, path: "/health", timeout: 1200 },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => { body += chunk; });
        response.on("end", () => {
          try {
            const value = JSON.parse(body);
            resolve(response.statusCode === 200 && value.app === "course-study-desk");
          } catch {
            resolve(false);
          }
        });
      },
    );
    request.on("timeout", () => request.destroy());
    request.on("error", () => resolve(false));
  });
}

async function waitForBackend(timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await healthCheck()) return;
    if (backendProcess && backendProcess.exitCode !== null) {
      throw new Error(`后端进程提前退出（代码 ${backendProcess.exitCode}），请检查 MySQL 配置`);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("后端启动超时，请确认 MySQL 已启动、数据库已创建且账号有访问权限");
}

function stopBackend() {
  if (!backendProcess || backendProcess.exitCode !== null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(backendProcess.pid), "/T", "/F"], {
      windowsHide: true,
      stdio: "ignore",
    });
  } else {
    backendProcess.kill();
  }
  backendProcess = undefined;
  backendStarting = undefined;
}

async function startBackend() {
  if (await healthCheck()) return;
  if (backendStarting) return backendStarting;

  backendStarting = (async () => {
    const frontendRoot = path.join(__dirname, "..");
    const backendRoot = path.resolve(frontendRoot, "..", "course-agent-backend");
    const packagedExecutable = path.join(process.resourcesPath, "backend", "course-agent-backend.exe");
    const executable = app.isPackaged
      ? packagedExecutable
      : path.join(backendRoot, ".venv", "Scripts", "python.exe");
    const args = app.isPackaged ? [] : [path.join(backendRoot, "desktop_backend.py")];
    const dataDir = app.isPackaged ? app.getPath("userData") : backendRoot;

    if (!fs.existsSync(executable)) throw new Error(`找不到后端运行程序：${executable}`);

    // 已保存的 Windows 加密配置仍然兼容；若没有，则由后端从
    // userData/.env 或进程环境变量读取 DATABASE_URL，前端始终直接进入登录页。
    const runtime = app.isPackaged ? backendEnvironment() : null;

    const logPath = path.join(dataDir, "backend.log");
    const log = fs.openSync(logPath, "a");
    backendProcess = spawn(executable, args, {
      cwd: dataDir,
      windowsHide: true,
      stdio: ["ignore", log, log],
      env: {
        ...process.env,
        ...(runtime || {}),
        ...(!app.isPackaged
          ? { COURSE_AGENT_ENV_PATH: path.join(backendRoot, ".env") }
          : {}),
        COURSE_AGENT_PORT: String(backendPort),
        COURSE_AGENT_DATA_DIR: dataDir,
      },
    });
    backendProcess.once("exit", () => {
      backendProcess = undefined;
      backendStarting = undefined;
    });
    await waitForBackend();
  })();

  try {
    await backendStarting;
  } catch (error) {
    stopBackend();
    throw error;
  } finally {
    backendStarting = undefined;
  }
}

async function handleDesktopConfig(req, res) {
  if (!app.isPackaged) {
    sendJson(res, 200, { configured: true, backend_ready: await healthCheck(), development: true });
    return;
  }
  if (req.method === "GET") {
    sendJson(res, 200, { ...publicRuntimeConfig(), backend_ready: await healthCheck() });
    return;
  }
  if (req.method !== "POST" && req.method !== "PUT") {
    sendJson(res, 405, { detail: "不支持的请求方法" });
    return;
  }
  try {
    const input = await readJson(req);
    stopBackend();
    const saved = saveRuntimeConfig(input);
    await startBackend();
    sendJson(res, 200, { ...saved, backend_ready: true });
  } catch (error) {
    sendJson(res, 400, { detail: String(error.message || error) });
  }
}

function startServer() {
  const root = path.join(__dirname, "..", "dist");
  server = http.createServer(async (req, res) => {
    if ((req.url || "").startsWith("/desktop/config")) {
      await handleDesktopConfig(req, res);
      return;
    }
    if ((req.url || "").startsWith("/api/")) {
      const proxy = http.request(
        {
          hostname: "127.0.0.1",
          port: backendPort,
          path: req.url,
          method: req.method,
          headers: { ...req.headers, host: `127.0.0.1:${backendPort}` },
        },
        (upstream) => {
          res.writeHead(upstream.statusCode || 500, upstream.headers);
          upstream.pipe(res);
        },
      );
      proxy.on("error", () => sendJson(res, 502, { detail: "后端正在启动或暂时不可用，请稍后重试" }));
      req.pipe(proxy);
      return;
    }

    const raw = decodeURIComponent((req.url || "/").split("?")[0]);
    let file = path.join(root, raw === "/" ? "index.html" : raw);
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      file = path.join(root, "index.html");
    }
    fs.readFile(file, (error, data) => {
      if (error) {
        res.writeHead(404);
        res.end();
        return;
      }
      res.writeHead(200, { "content-type": mime[path.extname(file)] || "application/octet-stream" });
      res.end(data);
    });
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server.address().port)));
}

function stopServices() {
  if (server) server.close();
  stopBackend();
}

function ensureLocalConfigTemplate() {
  if (!app.isPackaged) return;
  const source = path.join(process.resourcesPath, "config", ".env.example");
  const target = path.join(app.getPath("userData"), ".env.example");
  if (!fs.existsSync(target) && fs.existsSync(source)) {
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(source, target);
  }
}

app.whenReady().then(async () => {
  ensureLocalConfigTemplate();
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    backgroundColor: "#f2f3f0",
    titleBarStyle: "hidden",
    titleBarOverlay: { color: "#d9ded9", symbolColor: "#354039", height: 38 },
    webPreferences: { contextIsolation: true, sandbox: true },
  });
  win.once("ready-to-show", () => win.show());
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  const port = await startServer();
  startBackend().catch(() => undefined);
  await win.loadURL(`http://127.0.0.1:${port}`);
});

app.on("before-quit", stopServices);
app.on("window-all-closed", () => {
  stopServices();
  if (process.platform !== "darwin") app.quit();
});
