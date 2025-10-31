// src/preload.js
const { contextBridge, ipcRenderer } = require("electron");

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld("api", {
    // Camera operations
    initCamera: () => ipcRenderer.invoke("init-camera"),
    getFrame: () => ipcRenderer.invoke("get-frame"),

    // // Configuration
    // getConfig: (config) => ipcRenderer.invoke("get-config", config),

    // Image processing
    processImage: () => ipcRenderer.invoke("process-image"),

    // UI interactions
    showError: (options) => ipcRenderer.invoke("show-error", options),

    // UI interactions
    playPauseFrame: (pause) => ipcRenderer.invoke("play-pause-frame", pause),
});
