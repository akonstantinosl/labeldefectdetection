const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const path = require("path");
const axios = require("axios");
const log = require("electron-log");
const { spawn, exec } = require("child_process");
const os = require("os");

let mainWindow;
let pythonProcess = null;
const API_URL = "http://127.0.0.1:5000/api";

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 800,
        minWidth: 1024,
        minHeight: 768,
        webPreferences: {
            preload: path.join(__dirname, "preload.js"),
            nodeIntegration: false,
            contextIsolation: true,
        },
        icon: path.join(__dirname, "../assets/logo.png"),
    });

    mainWindow.loadFile(path.join(__dirname, "index.html"));
    mainWindow.maximize();

    if (process.env.NODE_ENV === "development") {
        mainWindow.webContents.openDevTools();
    }
}

async function startPythonServer() {
    return new Promise((resolve, reject) => {
        log.info("Starting Python backend...");

        // if (app.isPackaged) {
        // DI PRODUCTION: Jalankan .exe
        // const scriptPath = path.join(__dirname, "../python/dist/detector");
        // pythonProcess = spawn(scriptPath, { stdio: "pipe" });
        // } else {
        //     // SAAT DEVELOPMENT: Jalankan .py
        const scriptPath = path.join(__dirname, "../python/detector.py");
        const pythonCmd = os.platform() === "win32" ? "python" : "python3";
        pythonProcess = spawn(pythonCmd, [scriptPath], { stdio: "pipe" });
        // }

        pythonProcess.stdout.on("data", () => {});
        pythonProcess.stderr.on("data", (data) => {
            const errorMsg = data.toString();
            // log.error(`Python stderr: ${errorMsg}`);

            if (errorMsg.includes("ModuleNotFoundError") || errorMsg.includes("ImportError")) {
                dialog.showErrorBox("Python Error", `Library Python belum terinstall:\n\n${errorMsg}`);
                reject(new Error(errorMsg));
            }
        });

        // pythonProcess.stdout.on("data", (data) => {
        //     log.info(`Python stdout: ${data.toString()}`);
        // });
        // pythonProcess.stderr.on("data", (data) => {
        //     log.error(`Python stderr: ${data.toString()}`);
        // });
        // pythonProcess.on("error", (err) => {
        //     log.error(`Failed to start Python process: ${err}`);
        //     reject(err);
        // });
        // pythonProcess.on("close", (code) => {
        //     log.info(`Python process exited with code ${code}`);
        //     pythonProcess = null;
        // });

        const checkServer = async () => {
            try {
                await axios.get(`${API_URL}/camera/frame`);
                log.info("Python server is running");
                resolve();
            } catch (error) {
                if (error.code === "ECONNREFUSED") {
                    log.info("Waiting for Python server to start...");
                    setTimeout(checkServer, 500);
                } else {
                    log.error(`Error checking server: ${error.message}`);
                    resolve(); // continue anyway
                }
            }
        };

        setTimeout(checkServer, 2000);
    });
}

function setupIpcHandlers() {
    ipcMain.handle("init-camera", async () => {
        try {
            log.info("getting camera...");
            const response = await axios.get(`${API_URL}/camera/init`);
            log.info("getting camera success...");
            return response.data;
        } catch (error) {
            return {
                success: false,
                message: `${error.message}\n(main.js)`,
            };
        }
    });

    ipcMain.handle("get-frame", async () => {
        try {
            // log.info("getting frame...");
            const response = await axios.get(`${API_URL}/camera/frame`);
            // log.info("frame get...");
            return response.data;
        } catch (error) {
            return {
                success: false,
                message: `${error.message}\n(main.js)`,
            };
        }
    });

    // ipcMain.handle("get-config", async (event, { partcode_val, labeltype_val }) => {
    //     try {
    //         const response = await axios.post(`${API_URL}/config`, {
    //             part_code: partcode_val,
    //             label_type: labeltype_val,
    //         });
    //         return response.data;
    //     } catch (error) {
    //         return {
    //             success: false,
    //             message: `${error.message}\n(main.js)`,
    //         };
    //     }
    // });

    ipcMain.handle("process-image", async () => {
        try {
            const response = await axios.get(`${API_URL}/process`);
            return response.data;
        } catch (error) {
            log.error(`Error processing image: ${error.message}`);
            return {
                success: false,
                message: `Failed to process image: ${error.message}`,
            };
        }
    });

    ipcMain.handle("show-error", (event, { title, message }) => {
        dialog.showErrorBox(title, message);
    });

    ipcMain.handle("play-pause-frame", async (event, { state }) => {
        try {
            const response = await axios.post(`${API_URL}/play/pause/frame`, {
                state: state,
            });
            return response.data;
        } catch (error) {
            return {
                success: false,
                message: `${error.message}\n(main.js)`,
            };
        }
    });
}

app.whenReady().then(async () => {
    try {
        await startPythonServer();
        setupIpcHandlers();
        createWindow();

        app.on("activate", () => {
            if (BrowserWindow.getAllWindows().length === 0) createWindow();
        });
    } catch (error) {
        log.error(`Error during app startup: ${error.message}`);
        app.quit();
        // dialog.showErrorBox("Startup Error", `Failed to start application: ${error.message}`);
    }
});

// Quit the app when all windows are closed
app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
    log.info("app.quit()");
});

// Clean up on quitting the app
app.on("before-quit", () => {
    // close the camera object in the Python backend if needed.
    try {
        axios.get(`${API_URL}/camera/close`);
        log.info("Camera feed has been closed.");
        // Stop Python process if it's running
        if (pythonProcess) {
            pythonProcess.kill();
            pythonProcess = null;
        }
    } catch (error) {
        log.error(`Error closing camera: ${error.message}`);
    }
    log.info("Process stopped");
});

process.on("uncaughtException", (error) => {
    log.error("Uncaught exception:", error);
    dialog.showErrorBox("Error", `An unexpected error occurred: ${error.message}`);
});
