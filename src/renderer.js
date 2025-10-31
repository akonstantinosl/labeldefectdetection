// renderer.js

// DOM Elements
let process_btn = document.getElementById("process_btn");
let live_camera_img = document.getElementById("live_camera_img");
let processed_img = document.getElementById("processed_img");
let matched_results_txt = document.getElementById("matched_results_txt");
let defect_results_txt = document.getElementById("defect_results_txt");
let play_pause_overlay = document.getElementById("play_pause_overlay");
let toggle_icon = document.getElementById("play_pause_icon");
let frame_guide_select = document.getElementById("frame_guide_select");
let camera_overlay_svg = document.getElementById("camera_overlay_svg");

// Global variables
let stop_camera = false;
let is_playing = true;

// Event listeners
document.addEventListener("DOMContentLoaded", init);
process_btn.addEventListener("click", processImage);
play_pause_overlay.addEventListener("click", playPauseFrame);
frame_guide_select.addEventListener("change", updateFrameGuide);

// Initialize on page load
async function init() {
    updateFrameGuide(); // Set initial frame state
    let cameraInitialized = await initCamera();
    if (cameraInitialized) startCameraFeed();
}

// Function to show error message
function showError(title, message) {
    window.api.showError({ title, message });
}

// Calculates the actual dimensions and position of an image
function getContainedImageDimensions(img) {
    const containerWidth = img.clientWidth;
    const containerHeight = img.clientHeight;
    const imageRatio = img.naturalWidth / img.naturalHeight;
    const containerRatio = containerWidth / containerHeight;

    let renderedWidth, renderedHeight, x, y;

    if (imageRatio > containerRatio) {
        renderedWidth = containerWidth;
        renderedHeight = containerWidth / imageRatio;
        x = 0;
        y = (containerHeight - renderedHeight) / 2;
    } else {
        renderedHeight = containerHeight;
        renderedWidth = containerHeight * imageRatio;
        y = 0;
        x = (containerWidth - renderedWidth) / 2;
    }

    return { width: renderedWidth, height: renderedHeight, x: x, y: y };
}

// Draws the camera-style guide frame
function updateFrameGuide() {
    camera_overlay_svg.innerHTML = ""; // Clear the previous frame
    const selection = frame_guide_select.value;

    if (selection === "none" || !live_camera_img.naturalWidth) {
        return;
    }

    const imageRect = getContainedImageDimensions(live_camera_img);
    let frameWidth, frameHeight;
    if (selection === "inside") {
        frameWidth = imageRect.width * 0.8;
        frameHeight = imageRect.height * 0.5;
    } else {
        const side = Math.min(imageRect.width, imageRect.height) * 0.7;
        frameWidth = side;
        frameHeight = side;
    }

    const frameX = imageRect.x + (imageRect.width - frameWidth) / 2;
    const frameY = imageRect.y + (imageRect.height - frameHeight) / 2;
    const svgNS = "http://www.w3.org/2000/svg";
    const mask = document.createElementNS(svgNS, "path");
    mask.setAttribute("class", "frame-mask");
    mask.setAttribute("fill-rule", "evenodd");
    mask.setAttribute("d", `M 0 0 H ${live_camera_img.clientWidth} V ${live_camera_img.clientHeight} H 0 Z M ${frameX} ${frameY} H ${frameX + frameWidth} V ${frameY + frameHeight} H ${frameX} Z`);
    camera_overlay_svg.appendChild(mask);

    const cornerLength = Math.min(frameWidth, frameHeight) * 0.15;
    const paths = {
        topLeft: `M ${frameX + cornerLength} ${frameY} L ${frameX} ${frameY} L ${frameX} ${frameY + cornerLength}`,
        topRight: `M ${frameX + frameWidth - cornerLength} ${frameY} L ${frameX + frameWidth} ${frameY} L ${frameX + frameWidth} ${frameY + cornerLength}`,
        bottomLeft: `M ${frameX + cornerLength} ${frameY + frameHeight} L ${frameX} ${frameY + frameHeight} L ${frameX} ${frameY + frameHeight - cornerLength}`,
        bottomRight: `M ${frameX + frameWidth - cornerLength} ${frameY + frameHeight} L ${frameX + frameWidth} ${frameY + frameHeight} L ${frameX + frameWidth} ${frameY + frameHeight - cornerLength}`,
    };

    for (const key in paths) {
        const path = document.createElementNS(svgNS, "path");
        path.setAttribute("d", paths[key]);
        path.setAttribute("class", "frame-guide-corner");
        camera_overlay_svg.appendChild(path);
    }
}

const resizeObserver = new ResizeObserver(() => {
    requestAnimationFrame(updateFrameGuide);
});
resizeObserver.observe(document.body);
live_camera_img.addEventListener("load", updateFrameGuide);

async function initCamera() {
    try {
        let result = await window.api.initCamera();
        if (result.success) return true;
        live_camera_img.src = "../assets/no_camera.png";
        showError("Camera Error", `Failed to initialize camera: ${result.message}`);
        return false;
    } catch (error) {
        showError("Camera Error", `Failed to initialize camera: ${error.message}`);
        return false;
    }
}

async function startCameraFeed() {
    while (!stop_camera) {
        try {
            let result = await window.api.getFrame();
            if (result.success == "success") {
                live_camera_img.src = `data:image/jpeg;base64,${result.frame}`;
            } else if (result.success == "nocamera") {
                live_camera_img.src = "../assets/no_camera.png";
                stop_camera = true;
                break;
            }
        } catch (error) {
            live_camera_img.src = "../assets/no_camera.png";
            stop_camera = true;
            showError("Camera Error", `Failed to get camera frame: ${error.message}`);
            break;
        }
        await new Promise((resolve) => setTimeout(resolve, 33));
    }
}

// NEW: Helper function to format the result arrays into a readable string
function formatResults(resultsArray) {
    if (!resultsArray || resultsArray.length === 0) {
        return "No items to display.";
    }

    return resultsArray
        .map((item) => {
            let block = `Item           : ${item.item}\n`;
            // Only add 'reason' if it's a defect
            if (item.reason) {
                block += `Reason         : ${item.reason}\n`;
            }
            block += `Database Value : ${item.db_value}\n`;
            block += `OCR Value      : ${item.ocr_value}`;
            return block;
        })
        .join("\n------------------------------------\n");
}

// Process image
async function processImage() {
    if (!is_playing) {
        showError("Process Error", "Camera is paused. Please play the camera feed to process.");
        return;
    }

    process_btn.disabled = true;
    process_btn.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...`;

    // Clear previous results
    matched_results_txt.value = "";
    defect_results_txt.value = "";
    processed_img.src = "../assets/process_image.png";

    try {
        let result = await window.api.processImage();

        if (result.success) {
            processed_img.src = `data:image/jpeg;base64,${result.detection_image}`;

            // MODIFIED: Use the new formatResults function to display detailed results
            matched_results_txt.value = formatResults(result.matched_results);
            defect_results_txt.value = formatResults(result.defect_results);

            // Show an alert only if there are defects
            if (result.status !== "OK") {
                showError("Defect Detected", "A defect was found. Check the Defect Results panel for details.");
            }
        } else {
            processed_img.src = "../assets/no_image.png";
            // MODIFIED: Display the error message in the defect box for clarity
            defect_results_txt.value = `Process Error: ${result.message}`;
            showError("Process Error", `Failed to process image: ${result.message}`);
        }
    } catch (error) {
        processed_img.src = "../assets/no_image.png";
        defect_results_txt.value = `Process Error: ${error.message}`;
        showError("Process Error", `Failed to process image: ${error.message}`);
    } finally {
        process_btn.disabled = false;
        process_btn.innerHTML = `<i class="bi bi-camera-fill me-2"></i>Process`;
    }
}

async function playPauseFrame() {
    try {
        is_playing = toggle_icon.classList.contains("bi-play-circle-fill");
        const result = await window.api.playPauseFrame({ state: is_playing });

        if (result.success) {
            stop_camera = !is_playing;
            if (is_playing) {
                startCameraFeed();
                toggle_icon.classList.remove("bi-play-circle-fill");
                toggle_icon.classList.add("bi-pause-circle-fill");
            } else {
                toggle_icon.classList.remove("bi-pause-circle-fill");
                toggle_icon.classList.add("bi-play-circle-fill");
            }
        } else {
            showError("Error", `Failed to pause/play camera: ${result.message}`);
        }
    } catch (error) {
        showError("Error", `Failed to pause/play camera: ${error.message}`);
    }
}