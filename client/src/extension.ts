import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient;

export function activate(context: vscode.ExtensionContext) {
  // Always use production mode in packaged extension
  let serverOptions: ServerOptions;

  console.log("Starting SCL server in PRODUCTION mode");
  serverOptions = {
    command: context.asAbsolutePath(
      path.join("dist", "SCLserver", "server.exe")
    ),
    options: {
      cwd: context.asAbsolutePath(path.join("dist", "SCLserver")),
    },
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: "file", language: "scl" }],
    outputChannel: vscode.window.createOutputChannel("SCL Language Server"),
    // Optimize initialization
    initializationOptions: {},
    // Only sync open/change/save events for better performance
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.scl")
    }
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
