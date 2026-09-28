import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient;

/**
 * VSIX extraction can drop the executable bit on non-Windows platforms.
 * If the server binary isn't executable, try to fix it up before launch.
 */
function ensureExecutable(serverPath: string): void {
  if (process.platform === "win32") {
    return;
  }
  try {
    fs.accessSync(serverPath, fs.constants.X_OK);
  } catch {
    try {
      fs.chmodSync(serverPath, 0o755);
    } catch {
      // Best-effort only; if this fails, the client.start() error below
      // will surface the real problem to the user.
    }
  }
}

export function activate(context: vscode.ExtensionContext) {
  // Always use production mode in packaged extension
  console.log("Starting SCL server in PRODUCTION mode");
  const serverBinary = process.platform === "win32" ? "server.exe" : "server";
  const serverPath = context.asAbsolutePath(
    path.join("dist", "SCLserver", serverBinary)
  );

  if (!fs.existsSync(serverPath)) {
    vscode.window.showErrorMessage(
      `SCL Language Server: server binary not found at "${serverPath}". ` +
        `This platform (${process.platform}/${process.arch}) may not be supported by this build.`
    );
    return;
  }

  ensureExecutable(serverPath);

  const serverOptions: ServerOptions = {
    command: serverPath,
    options: {
      cwd: context.asAbsolutePath(path.join("dist", "SCLserver")),
    },
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: "file", language: "scl" }],
    outputChannel: vscode.window.createOutputChannel("SCL Language Server"),
    // Optimize initialization
    initializationOptions: {},
  };

  client = new LanguageClient(
    "sclLanguageServer",
    "SCL Language Server",
    serverOptions,
    clientOptions
  );

  // Start the client asynchronously to avoid blocking activation
  context.subscriptions.push(client);
  
  client.start().then(
    () => {
      console.log("Language Client successfully started.");
    },
    (err: any) => {
      console.error("Language Client failed to start", err);
      vscode.window.showErrorMessage(
        "SCL Language Server failed to start: " + err.message
      );
    }
  );
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}
