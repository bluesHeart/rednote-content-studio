/* rednote-content-studio - Frontend Logic */

(function () {
    "use strict";

    // --------------- State ---------------
    let currentJobId = null;
    let ws = null;
    let templates = { visual: [], tone: [], defaults: {} };
    let selectedVisual = "";
    let selectedTone = "";
    let totalPages = 0;
    let envHasKey = false;
    let uploadedImages = []; // {url, filename}
    let editableStory = null;
    let selectedEditPage = 1;
    let draggingBlockId = null;

    // --------------- DOM refs ---------------
    const $mdInput = document.getElementById("markdown-input");
    const $fileUpload = document.getElementById("file-upload");
    const $apiKey = document.getElementById("api-key");
    const $baseUrl = document.getElementById("base-url");
    const $model = document.getElementById("model");
    const $visualFeedback = document.getElementById("visual-feedback");
    const $convertBtn = document.getElementById("convert-btn");

    const $progressSection = document.getElementById("progress-section");
    const $progressText = document.getElementById("progress-text");
    const $progressPct = document.getElementById("progress-pct");
    const $progressBar = document.getElementById("progress-bar");

    const $previewSection = document.getElementById("preview-section");
    const $previewCount = document.getElementById("preview-count");
    const $cardsGallery = document.getElementById("cards-gallery");

    const $editorSection = document.getElementById("editor-section");
    const $editorRefreshBtn = document.getElementById("editor-refresh-btn");
    const $editorApplyBtn = document.getElementById("editor-apply-btn");
    const $editorPageSelect = document.getElementById("editor-page-select");
    const $editorSavePageBtn = document.getElementById("editor-save-page-btn");
    const $editorRewritePageBtn = document.getElementById("editor-rewrite-page-btn");
    const $editorInstruction = document.getElementById("editor-instruction");
    const $editorBlocks = document.getElementById("editor-blocks");

    const $downloadSection = document.getElementById("download-section");
    const $downloadZip = document.getElementById("download-zip-btn");
    const $copyAll = document.getElementById("copy-all-btn");
    const $newConvert = document.getElementById("new-convert-btn");

    const $cardModal = document.getElementById("card-modal");
    const $modalTitle = document.getElementById("modal-title");
    const $modalIframe = document.getElementById("modal-iframe");
    const $modalCopy = document.getElementById("modal-copy-btn");
    const $modalDownload = document.getElementById("modal-download-btn");

    const $imageStrip = document.getElementById("image-strip");
    const $imageThumbnails = document.getElementById("image-thumbnails");
    const $clearImages = document.getElementById("clear-images-btn");

    // --------------- Toast notifications ---------------
    function showToast(message, type) {
        type = type || "error";
        var existing = document.querySelector(".toast");
        if (existing) existing.remove();
        var el = document.createElement("div");
        el.className = "toast " + type;
        el.textContent = message;
        document.body.appendChild(el);
        // Trigger reflow then show
        el.offsetHeight;
        el.classList.add("show");
        setTimeout(function () {
            el.classList.remove("show");
            setTimeout(function () { el.remove(); }, 300);
        }, 3000);
    }

    // --------------- Init ---------------
    loadTemplates();
    loadEnvConfig();
    loadSavedSettings();
    bindEvents();

    // --------------- Env config detection ---------------
    async function loadEnvConfig() {
        try {
            var res = await fetch("/api/env-config");
            var data = await res.json();
            envHasKey = data.has_env_key;
            if (envHasKey) {
                $apiKey.placeholder = "已检测到服务器环境变量（可留空）";
                var hint = document.getElementById("api-key-hint");
                if (hint) hint.textContent = "服务器已配置 API Key 环境变量，无需手动填写";
                if (data.base_url_hint) {
                    $baseUrl.value = "";
                    $baseUrl.placeholder = data.base_url_hint;
                }
                if (data.model_hint) {
                    $model.value = "";
                    $model.placeholder = data.model_hint;
                }
            }
        } catch (e) { /* ignore */ }
    }

    // --------------- Template loading ---------------
    async function loadTemplates() {
        try {
            const res = await fetch("/api/templates");
            templates = await res.json();
            selectedVisual = templates.defaults.visual;
            selectedTone = templates.defaults.tone;
            renderVisualTemplates();
            renderToneTemplates();
        } catch (e) {
            console.error("Failed to load templates", e);
        }
    }

    function renderVisualTemplates() {
        const container = document.getElementById("visual-templates");
        container.innerHTML = "";
        templates.visual.forEach(function (t) {
            const chip = document.createElement("div");
            chip.className = "tmpl-chip" + (t.id === selectedVisual ? " selected" : "");
            chip.dataset.id = t.id;
            chip.innerHTML =
                '<span class="chip-dot" style="background:' + t.card_bg + '"></span>' +
                t.name;
            chip.addEventListener("click", function () {
                selectedVisual = t.id;
                container.querySelectorAll(".tmpl-chip").forEach(function (c) { c.classList.remove("selected"); });
                chip.classList.add("selected");
            });
            container.appendChild(chip);
        });
    }

    function renderToneTemplates() {
        const container = document.getElementById("tone-templates");
        container.innerHTML = "";
        templates.tone.forEach(function (t) {
            const chip = document.createElement("div");
            chip.className = "tmpl-chip" + (t.id === selectedTone ? " selected" : "");
            chip.dataset.id = t.id;
            chip.innerHTML =
                '<span class="chip-emoji">' + t.emoji_examples.slice(0, 2) + '</span>' +
                t.name;
            chip.addEventListener("click", function () {
                selectedTone = t.id;
                container.querySelectorAll(".tmpl-chip").forEach(function (c) { c.classList.remove("selected"); });
                chip.classList.add("selected");
            });
            container.appendChild(chip);
        });
    }

    // --------------- Settings persistence ---------------
    function loadSavedSettings() {
        var saved = localStorage.getItem("rednote_settings");
        if (saved) {
            try {
                var s = JSON.parse(saved);
                if (s.api_key) $apiKey.value = s.api_key;
                if (s.base_url) $baseUrl.value = s.base_url;
                if (s.model) $model.value = s.model;
            } catch (e) { /* ignore */ }
        }
    }

    function saveSettings() {
        localStorage.setItem("rednote_settings", JSON.stringify({
            api_key: $apiKey.value,
            base_url: $baseUrl.value,
            model: $model.value,
        }));
    }

    // --------------- Settings Modal ---------------
    function openSettingsModal() {
        var modal = document.getElementById("settings-modal");
        modal.classList.remove("hidden");
        modal.classList.add("flex");
    }

    window.closeSettingsModal = function (e) {
        if (e && e.target !== e.currentTarget) return;
        var modal = document.getElementById("settings-modal");
        modal.classList.add("hidden");
        modal.classList.remove("flex");
        saveSettings();
    };

    // --------------- Events ---------------
    function bindEvents() {
        $convertBtn.addEventListener("click", startConvert);
        $fileUpload.addEventListener("change", handleFileUpload);
        $downloadZip.addEventListener("click", downloadZip);
        $copyAll.addEventListener("click", copyAllText);
        $newConvert.addEventListener("click", resetUI);
        $clearImages.addEventListener("click", clearUploadedImages);

        $editorRefreshBtn.addEventListener("click", loadEditableStory);
        $editorApplyBtn.addEventListener("click", applyEditableStory);
        $editorSavePageBtn.addEventListener("click", saveCurrentEditablePage);
        $editorRewritePageBtn.addEventListener("click", regenerateCurrentPage);
        $editorPageSelect.addEventListener("change", function () {
            selectedEditPage = parseInt($editorPageSelect.value, 10) || 1;
            renderEditorPage();
        });

        // Settings modal
        document.getElementById("settings-btn").addEventListener("click", openSettingsModal);

        // Paste handler (Word images, screenshots, etc.)
        $mdInput.addEventListener("paste", handlePaste);

        // Drag & drop (supports both .md files and images)
        $mdInput.addEventListener("dragover", function (e) {
            e.preventDefault();
            $mdInput.classList.add("drag-over");
        });
        $mdInput.addEventListener("dragleave", function () {
            $mdInput.classList.remove("drag-over");
        });
        $mdInput.addEventListener("drop", function (e) {
            e.preventDefault();
            $mdInput.classList.remove("drag-over");
            var files = e.dataTransfer.files;
            if (files.length === 0) return;

            // Separate image files from text files
            var imageFiles = [];
            var mdFile = null;
            for (var i = 0; i < files.length; i++) {
                if (files[i].type && files[i].type.startsWith("image/")) {
                    imageFiles.push(files[i]);
                } else if (!mdFile) {
                    mdFile = files[i];
                }
            }

            if (imageFiles.length > 0) {
                imageFiles.forEach(function (f) { uploadAndInsertImage(f); });
            }
            if (mdFile) {
                uploadFile(mdFile);
            }
        });
    }

    // --------------- File upload ---------------
    function handleFileUpload(e) {
        if (e.target.files.length > 0) uploadFile(e.target.files[0]);
    }

    async function uploadFile(file) {
        var formData = new FormData();
        formData.append("file", file);
        try {
            var res = await fetch("/api/upload", { method: "POST", body: formData });
            if (!res.ok) {
                var err = await res.json();
                showToast(err.detail || "上传失败");
                return;
            }
            var data = await res.json();
            $mdInput.value = data.content;
        } catch (e) {
            showToast("上传失败: " + e.message);
        }
    }

    // --------------- Image paste/upload ---------------
    async function handlePaste(e) {
        var items = e.clipboardData && e.clipboardData.items;
        if (!items) return;

        var imageItems = [];
        var hasHtml = false;
        var htmlData = "";

        for (var i = 0; i < items.length; i++) {
            if (items[i].type.startsWith("image/")) {
                imageItems.push(items[i]);
            }
            if (items[i].type === "text/html") {
                hasHtml = true;
            }
        }

        // Case 1: Direct image paste (screenshot, single image copy)
        if (imageItems.length > 0 && !hasHtml) {
            e.preventDefault();
            for (var j = 0; j < imageItems.length; j++) {
                var file = imageItems[j].getAsFile();
                if (file) await uploadAndInsertImage(file);
            }
            return;
        }

        // Case 2: HTML paste (Word, web page with images)
        if (hasHtml) {
            // Get the HTML content
            var htmlPromise = new Promise(function (resolve) {
                for (var k = 0; k < items.length; k++) {
                    if (items[k].type === "text/html") {
                        items[k].getAsString(resolve);
                        return;
                    }
                }
                resolve("");
            });
            htmlData = await htmlPromise;

            // Check if HTML contains embedded images (base64 or blob)
            var imgRegex = /<img[^>]+src=["']([^"']+)["'][^>]*>/gi;
            var match;
            var embeddedImages = [];
            while ((match = imgRegex.exec(htmlData)) !== null) {
                var src = match[1];
                if (src.startsWith("data:image/")) {
                    embeddedImages.push(src);
                }
            }

            if (embeddedImages.length > 0) {
                // Prevent default paste — we'll handle text + images ourselves
                e.preventDefault();

                // Get plain text version for the textarea
                var textPromise = new Promise(function (resolve) {
                    for (var k = 0; k < items.length; k++) {
                        if (items[k].type === "text/plain") {
                            items[k].getAsString(resolve);
                            return;
                        }
                    }
                    resolve("");
                });
                var plainText = await textPromise;

                // Insert the plain text at cursor
                insertAtCursor(plainText);

                // Upload each embedded image and append markdown refs
                showToast("检测到 " + embeddedImages.length + " 张图片，正在上传...", "success");
                for (var m = 0; m < embeddedImages.length; m++) {
                    try {
                        var blob = dataURLtoBlob(embeddedImages[m]);
                        var imgFile = new File([blob], "paste_" + (m + 1) + ".png", { type: blob.type });
                        await uploadAndInsertImage(imgFile);
                    } catch (err) {
                        console.warn("Failed to upload embedded image", err);
                    }
                }
                return;
            }
            // If HTML has no embedded images, let default paste happen (plain text)
        }
    }

    function dataURLtoBlob(dataURL) {
        var parts = dataURL.split(",");
        var mime = parts[0].match(/:(.*?);/)[1];
        var b64 = atob(parts[1]);
        var arr = new Uint8Array(b64.length);
        for (var i = 0; i < b64.length; i++) arr[i] = b64.charCodeAt(i);
        return new Blob([arr], { type: mime });
    }

    function insertAtCursor(text) {
        var start = $mdInput.selectionStart;
        var end = $mdInput.selectionEnd;
        var before = $mdInput.value.substring(0, start);
        var after = $mdInput.value.substring(end);
        $mdInput.value = before + text + after;
        $mdInput.selectionStart = $mdInput.selectionEnd = start + text.length;
    }

    async function uploadAndInsertImage(file) {
        var formData = new FormData();
        formData.append("file", file);
        try {
            var res = await fetch("/api/upload-image", { method: "POST", body: formData });
            if (!res.ok) {
                var err = await res.json();
                showToast(err.detail || "图片上传失败");
                return;
            }
            var data = await res.json();

            // Track uploaded image
            uploadedImages.push({ url: data.url, filename: data.filename });

            // Insert markdown image reference at cursor
            var mdRef = "\n![" + data.filename + "](" + data.url + ")\n";
            insertAtCursor(mdRef);

            // Update thumbnail strip
            renderImageStrip();
            showToast("图片已上传: " + data.filename, "success");
        } catch (e) {
            showToast("图片上传失败: " + e.message);
        }
    }

    function renderImageStrip() {
        if (uploadedImages.length === 0) {
            $imageStrip.classList.add("hidden");
            return;
        }
        $imageStrip.classList.remove("hidden");
        $imageThumbnails.innerHTML = "";
        uploadedImages.forEach(function (img, idx) {
            var thumb = document.createElement("div");
            thumb.className = "img-thumb";
            thumb.innerHTML =
                '<img src="' + img.url + '" alt="' + img.filename + '">' +
                '<button class="img-remove" title="移除">&times;</button>';
            thumb.querySelector(".img-remove").addEventListener("click", function () {
                removeUploadedImage(idx);
            });
            $imageThumbnails.appendChild(thumb);
        });
    }

    function removeUploadedImage(idx) {
        var img = uploadedImages[idx];
        // Remove markdown reference from textarea
        var mdRef1 = "![" + img.filename + "](" + img.url + ")";
        $mdInput.value = $mdInput.value.split(mdRef1).join("");
        // Clean up empty lines left behind
        $mdInput.value = $mdInput.value.replace(/\n{3,}/g, "\n\n");

        uploadedImages.splice(idx, 1);
        renderImageStrip();
    }

    function clearUploadedImages() {
        // Remove all image markdown refs from textarea
        uploadedImages.forEach(function (img) {
            var mdRef = "![" + img.filename + "](" + img.url + ")";
            $mdInput.value = $mdInput.value.split(mdRef).join("");
        });
        $mdInput.value = $mdInput.value.replace(/\n{3,}/g, "\n\n");
        uploadedImages = [];
        renderImageStrip();
    }

    // --------------- Convert ---------------
    async function startConvert() {
        var markdown = $mdInput.value.trim();
        if (!markdown) { showToast("请输入 Markdown 内容", "warning"); return; }
        var apiKey = $apiKey.value.trim();
        if (!apiKey && !envHasKey) { showToast("请输入 API Key", "warning"); return; }

        saveSettings();

        // Reset UI
        $convertBtn.disabled = true;
        $convertBtn.innerHTML = '<span class="inline-block w-4 h-4 border-2 border-white\/30 border-t-white rounded-full animate-spin mr-2 align-middle"></span>转换中...';
        showProgress();
        hidePreview();
        hideDownload();

        try {
            var res = await fetch("/api/convert", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    markdown: markdown,
                    api_key: apiKey || null,
                    base_url: $baseUrl.value.trim() || null,
                    model: $model.value.trim() || null,
                    visual_template: selectedVisual,
                    tone_template: selectedTone,
                    use_visual_feedback: $visualFeedback.checked,
                }),
            });

            if (!res.ok) {
                var err = await res.json();
                showToast("提交失败: " + (err.detail || "未知错误"), "error");
                $convertBtn.disabled = false;
                $convertBtn.textContent = "开始转换";
                return;
            }

            var data = await res.json();
            currentJobId = data.job_id;

            // Connect WebSocket
            connectWebSocket(currentJobId);

            // Also start polling as fallback
            startPolling(currentJobId);

        } catch (e) {
                showToast("请求失败: " + e.message, "error");
            $convertBtn.disabled = false;
            $convertBtn.textContent = "开始转换";
        }
    }

    // --------------- WebSocket ---------------
    function connectWebSocket(jobId) {
        if (ws) { try { ws.close(); } catch (e) { /* */ } }

        var proto = location.protocol === "https:" ? "wss:" : "ws:";
        var url = proto + "//" + location.host + "/api/ws/" + jobId;
        ws = new WebSocket(url);

        ws.onmessage = function (event) {
            var msg;
            try { msg = JSON.parse(event.data); } catch (e) { return; }
            handleWsMessage(msg);
        };

        ws.onerror = function () {
            console.warn("WebSocket error, relying on polling");
        };

        ws.onclose = function () {
            ws = null;
        };
    }

    function handleWsMessage(msg) {
        if (msg.type === "ping") return;

        if (msg.type === "step") {
            updateProgress(msg.progress || 0, msg.detail || "");
            if (msg.total_pages) totalPages = msg.total_pages;
        }

        if (msg.type === "page_done") {
            totalPages = msg.total_pages || totalPages;
            updateProgress(msg.progress || 0, "已完成第 " + msg.page + "/" + totalPages + " 页");
            addCardToGallery(msg.page, totalPages);
        }

        if (msg.type === "complete") {
            totalPages = msg.total_pages || totalPages;
            updateProgress(1.0, msg.detail || "完成！");
            onConversionComplete();
        }

        if (msg.type === "error") {
            onConversionError(msg.detail || "转换失败");
        }
    }

    // --------------- Polling fallback ---------------
    var pollTimer = null;

    function startPolling(jobId) {
        if (pollTimer) clearInterval(pollTimer);
        var lastCompletedPages = 0;

        pollTimer = setInterval(async function () {
            try {
                var res = await fetch("/api/jobs/" + jobId + "/status");
                if (!res.ok) return;
                var data = await res.json();

                updateProgress(data.progress, data.detail);

                // Add new cards
                if (data.completed_pages > lastCompletedPages) {
                    for (var p = lastCompletedPages + 1; p <= data.completed_pages; p++) {
                        addCardToGallery(p, data.total_pages);
                    }
                    lastCompletedPages = data.completed_pages;
                    totalPages = data.total_pages;
                }

                if (data.status === "completed") {
                    clearInterval(pollTimer);
                    pollTimer = null;
                    onConversionComplete();
                }

                if (data.status === "failed") {
                    clearInterval(pollTimer);
                    pollTimer = null;
                    onConversionError(data.error || "转换失败");
                }
            } catch (e) { /* ignore */ }
        }, 2000);
    }

    // --------------- Progress UI ---------------
    function showProgress() {
        $progressSection.classList.remove("hidden");
        $progressText.classList.add("progress-pulse");
        $progressSection.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function hideProgress() {
        $progressText.classList.remove("progress-pulse");
    }

    function updateProgress(progress, text) {
        var pct = Math.round(progress * 100);
        $progressBar.style.width = pct + "%";
        $progressPct.textContent = pct + "%";
        if (text) $progressText.textContent = text;
    }

    // --------------- Preview UI ---------------
    function hidePreview() {
        $previewSection.classList.add("hidden");
        $cardsGallery.innerHTML = "";
    }

    function showPreview() {
        $previewSection.classList.remove("hidden");
    }

    var addedPages = new Set();

    function addCardToGallery(pageNum, total) {
        if (addedPages.has(pageNum)) return;
        addedPages.add(pageNum);

        showPreview();
        $previewCount.textContent = addedPages.size + " / " + total + " 页";

        var div = document.createElement("div");
        div.className = "card-item";
        div.innerHTML =
            '<div class="iframe-wrap"><iframe src="/api/jobs/' + currentJobId + '/page/' + pageNum + '/html" loading="lazy"></iframe></div>' +
            '<div class="card-label">第 ' + pageNum + ' 页</div>';
        div.addEventListener("click", function () { openCardModal(pageNum, total); });
        $cardsGallery.appendChild(div);

        // Scroll to newest
        div.scrollIntoView({ behavior: "smooth", inline: "end", block: "nearest" });
    }

    // --------------- Download section ---------------
    function hideDownload() {
        $downloadSection.classList.add("hidden");
    }

    function showDownload() {
        $downloadSection.classList.remove("hidden");
    }

    // --------------- Completion handlers ---------------
    function onConversionComplete() {
        hideProgress();
        updateProgress(1.0, "转换完成！");
        showDownload();
        $convertBtn.disabled = false;
        $convertBtn.textContent = "开始转换";
        loadEditableStory();
    }

    function onConversionError(detail) {
        hideProgress();
        $progressText.textContent = "转换失败: " + detail;
        $progressText.classList.add("text-red-500");
        $convertBtn.disabled = false;
        $convertBtn.textContent = "开始转换";
    }

    function resetUI() {
        currentJobId = null;
        addedPages = new Set();
        totalPages = 0;
        editableStory = null;
        selectedEditPage = 1;
        $progressSection.classList.add("hidden");
        $progressBar.style.width = "0%";
        $progressPct.textContent = "0%";
        $progressText.textContent = "准备中...";
        $progressText.classList.remove("text-red-500");
        hidePreview();
        hideDownload();
        hideEditor();
    }

    function showEditor() {
        $editorSection.classList.remove("hidden");
    }

    function hideEditor() {
        $editorSection.classList.add("hidden");
        $editorBlocks.innerHTML = "";
        $editorPageSelect.innerHTML = "";
    }

    function getEditablePage(pageNumber) {
        if (!editableStory || !Array.isArray(editableStory.pages)) return null;
        for (var i = 0; i < editableStory.pages.length; i++) {
            var page = editableStory.pages[i];
            if ((page.page_number || 0) === pageNumber) return page;
        }
        return null;
    }

    function rebuildEditorPageSelect() {
        if (!editableStory || !Array.isArray(editableStory.pages)) return;
        $editorPageSelect.innerHTML = "";
        editableStory.pages.forEach(function (page) {
            var opt = document.createElement("option");
            opt.value = String(page.page_number);
            opt.textContent = "第 " + page.page_number + " 页";
            $editorPageSelect.appendChild(opt);
        });

        if (!getEditablePage(selectedEditPage) && editableStory.pages.length > 0) {
            selectedEditPage = editableStory.pages[0].page_number;
        }
        $editorPageSelect.value = String(selectedEditPage);
    }

    function createLockCheckbox(pageNumber, blockId, locked) {
        var label = document.createElement("label");
        label.className = "editor-block-actions";

        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = !!locked;
        cb.addEventListener("change", function () {
            var page = getEditablePage(pageNumber);
            if (!page || !Array.isArray(page.blocks)) return;
            for (var i = 0; i < page.blocks.length; i++) {
                if (page.blocks[i].id === blockId) {
                    page.blocks[i].locked = cb.checked;
                    break;
                }
            }
        });

        var txt = document.createElement("span");
        txt.textContent = "锁定";

        label.appendChild(cb);
        label.appendChild(txt);
        return label;
    }

    function moveBlock(pageNumber, blockId, direction) {
        var page = getEditablePage(pageNumber);
        if (!page || !Array.isArray(page.blocks)) return;

        var idx = -1;
        for (var i = 0; i < page.blocks.length; i++) {
            if (page.blocks[i].id === blockId) {
                idx = i;
                break;
            }
        }
        if (idx < 0) return;

        var target = idx + direction;
        if (target < 0 || target >= page.blocks.length) return;

        var temp = page.blocks[idx];
        page.blocks[idx] = page.blocks[target];
        page.blocks[target] = temp;
        renderEditorPage();
    }

    function moveBlockByDrop(pageNumber, sourceBlockId, targetBlockId, placeAfter) {
        var page = getEditablePage(pageNumber);
        if (!page || !Array.isArray(page.blocks)) return;

        var sourceIdx = -1;
        var targetIdx = -1;
        for (var i = 0; i < page.blocks.length; i++) {
            if (page.blocks[i].id === sourceBlockId) sourceIdx = i;
            if (page.blocks[i].id === targetBlockId) targetIdx = i;
        }
        if (sourceIdx < 0 || targetIdx < 0 || sourceIdx === targetIdx) return;

        var sourceBlock = page.blocks[sourceIdx];
        page.blocks.splice(sourceIdx, 1);
        if (sourceIdx < targetIdx) targetIdx -= 1;

        var insertIdx = placeAfter ? targetIdx + 1 : targetIdx;
        if (insertIdx < 0) insertIdx = 0;
        if (insertIdx > page.blocks.length) insertIdx = page.blocks.length;

        page.blocks.splice(insertIdx, 0, sourceBlock);
        renderEditorPage();
    }

    function clearDropIndicators() {
        $editorBlocks.querySelectorAll(".editor-block").forEach(function (el) {
            el.classList.remove("drop-before");
            el.classList.remove("drop-after");
        });
    }

    function renderEditorPage() {
        var page = getEditablePage(selectedEditPage);
        if (!page) {
            $editorBlocks.innerHTML = "";
            return;
        }

        $editorBlocks.innerHTML = "";
        var blocks = Array.isArray(page.blocks) ? page.blocks : [];

        blocks.forEach(function (block, idx) {
            var wrap = document.createElement("div");
            wrap.className = "editor-block";
            wrap.dataset.blockId = block.id;

            if (block.type === "image") {
                wrap.classList.add("can-drag");
                wrap.draggable = true;

                wrap.addEventListener("dragstart", function (e) {
                    draggingBlockId = block.id;
                    wrap.classList.add("is-dragging");
                    if (e.dataTransfer) {
                        e.dataTransfer.effectAllowed = "move";
                        e.dataTransfer.setData("text/plain", block.id);
                    }
                });

                wrap.addEventListener("dragend", function () {
                    draggingBlockId = null;
                    wrap.classList.remove("is-dragging");
                    clearDropIndicators();
                });
            }

            wrap.addEventListener("dragover", function (e) {
                if (!draggingBlockId || draggingBlockId === block.id) return;
                e.preventDefault();
                clearDropIndicators();

                var rect = wrap.getBoundingClientRect();
                var placeAfter = e.clientY > (rect.top + rect.height / 2);
                wrap.classList.add(placeAfter ? "drop-after" : "drop-before");
            });

            wrap.addEventListener("drop", function (e) {
                if (!draggingBlockId || draggingBlockId === block.id) return;
                e.preventDefault();
                var rect = wrap.getBoundingClientRect();
                var placeAfter = e.clientY > (rect.top + rect.height / 2);
                moveBlockByDrop(selectedEditPage, draggingBlockId, block.id, placeAfter);
                draggingBlockId = null;
                clearDropIndicators();
            });

            wrap.addEventListener("dragleave", function () {
                wrap.classList.remove("drop-before");
                wrap.classList.remove("drop-after");
            });

            var header = document.createElement("div");
            header.className = "editor-block-header";

            var type = document.createElement("span");
            type.className = "editor-block-type";
            type.textContent = "#" + (idx + 1) + " · " + block.type;
            header.appendChild(type);

            var actions = document.createElement("div");
            actions.className = "editor-block-actions";

            var moveUp = document.createElement("button");
            moveUp.type = "button";
            moveUp.className = "editor-move-btn";
            moveUp.textContent = "↑";
            moveUp.disabled = idx === 0;
            moveUp.addEventListener("click", function () { moveBlock(selectedEditPage, block.id, -1); });

            var moveDown = document.createElement("button");
            moveDown.type = "button";
            moveDown.className = "editor-move-btn";
            moveDown.textContent = "↓";
            moveDown.disabled = idx === blocks.length - 1;
            moveDown.addEventListener("click", function () { moveBlock(selectedEditPage, block.id, 1); });

            actions.appendChild(moveUp);
            actions.appendChild(moveDown);
            actions.appendChild(createLockCheckbox(selectedEditPage, block.id, !!block.locked));

            header.appendChild(actions);
            wrap.appendChild(header);

            if (block.type === "image") {
                var row = document.createElement("div");
                row.className = "editor-image-row";

                var img = document.createElement("img");
                img.className = "editor-image-preview";
                img.src = block.url;
                img.alt = "image";

                var url = document.createElement("div");
                url.className = "editor-image-url";
                url.textContent = block.url;

                row.appendChild(img);
                row.appendChild(url);
                wrap.appendChild(row);
            } else {
                var ta = document.createElement("textarea");
                ta.className = "editor-block-text";
                ta.value = block.text || "";
                ta.disabled = !!block.locked;
                ta.addEventListener("input", function () {
                    block.text = ta.value;
                });
                wrap.appendChild(ta);
            }

            $editorBlocks.appendChild(wrap);
        });
    }

    async function loadEditableStory() {
        if (!currentJobId) return;
        try {
            var res = await fetch("/api/jobs/" + currentJobId + "/editable-story");
            if (!res.ok) {
                var err = await res.json();
                showToast(err.detail || "加载可编辑内容失败", "warning");
                return;
            }

            var data = await res.json();
            editableStory = data.story;
            if (!editableStory || !Array.isArray(editableStory.pages)) {
                showToast("可编辑结构无效", "warning");
                return;
            }

            showEditor();
            rebuildEditorPageSelect();
            renderEditorPage();
        } catch (e) {
            showToast("加载可编辑内容失败: " + e.message, "error");
        }
    }

    async function saveEditableStory() {
        if (!currentJobId || !editableStory) return false;
        try {
            var res = await fetch("/api/jobs/" + currentJobId + "/editable-story", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ story: editableStory }),
            });
            if (!res.ok) {
                var err = await res.json();
                showToast(err.detail || "保存编辑失败", "error");
                return false;
            }
            var data = await res.json();
            editableStory = data.story;
            return true;
        } catch (e) {
            showToast("保存编辑失败: " + e.message, "error");
            return false;
        }
    }

    async function saveCurrentEditablePage() {
        var ok = await saveEditableStory();
        if (ok) showToast("当前页编辑已保存", "success");
    }

    async function regenerateCurrentPage() {
        if (!currentJobId) return;
        var ok = await saveEditableStory();
        if (!ok) return;

        var instruction = ($editorInstruction.value || "").trim();
        try {
            var res = await fetch("/api/jobs/" + currentJobId + "/editable-story/regenerate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    page_number: selectedEditPage,
                    instruction: instruction || null,
                }),
            });

            if (!res.ok) {
                var err = await res.json();
                showToast(err.detail || "局部重写失败", "error");
                return;
            }

            var data = await res.json();
            editableStory = data.story;
            rebuildEditorPageSelect();
            renderEditorPage();
            showToast("已完成局部重写，请检查后应用", "success");
        } catch (e) {
            showToast("局部重写失败: " + e.message, "error");
        }
    }

    async function applyEditableStory() {
        if (!currentJobId || !editableStory) return;
        var ok = await saveEditableStory();
        if (!ok) return;

        try {
            var res = await fetch("/api/jobs/" + currentJobId + "/editable-story/apply", {
                method: "POST",
            });
            if (!res.ok) {
                var err = await res.json();
                showToast(err.detail || "应用编辑失败", "error");
                return;
            }

            var data = await res.json();
            totalPages = data.total_pages || totalPages;

            // refresh gallery
            addedPages = new Set();
            $cardsGallery.innerHTML = "";
            for (var p = 1; p <= totalPages; p++) {
                addCardToGallery(p, totalPages);
            }
            showToast("已应用编辑并更新预览", "success");
        } catch (e) {
            showToast("应用编辑失败: " + e.message, "error");
        }
    }

    // --------------- Modal ---------------
    window.closeModal = function (e) {
        if (e.target === $cardModal) {
            $cardModal.classList.add("hidden");
            $cardModal.classList.remove("flex");
        }
    };

    function openCardModal(pageNum, total) {
        $modalTitle.textContent = "第 " + pageNum + " / " + total + " 页";
        $modalIframe.src = "/api/jobs/" + currentJobId + "/page/" + pageNum + "/html";
        $cardModal.classList.remove("hidden");
        $cardModal.classList.add("flex");

        // Bind copy
        $modalCopy.onclick = async function () {
            try {
                var res = await fetch("/api/jobs/" + currentJobId + "/page/" + pageNum + "/text");
                var text = await res.text();
                await navigator.clipboard.writeText(text);
                $modalCopy.textContent = "已复制!";
                setTimeout(function () { $modalCopy.textContent = "复制文本"; }, 1500);
            } catch (e) {
                showToast("复制失败: " + e.message);
            }
        };

        // Bind download
        $modalDownload.onclick = function () {
            var a = document.createElement("a");
            a.href = "/api/jobs/" + currentJobId + "/page/" + pageNum + "/image";
            a.download = "page_" + pageNum + ".png";
            a.click();
        };
    }

    // --------------- Download / copy all ---------------
    function downloadZip() {
        if (!currentJobId) return;
        var a = document.createElement("a");
        a.href = "/api/jobs/" + currentJobId + "/download";
        a.download = "rednote_" + currentJobId + ".zip";
        a.click();
    }

    async function copyAllText() {
        if (!currentJobId || totalPages === 0) return;
        var parts = [];
        for (var i = 1; i <= totalPages; i++) {
            try {
                var res = await fetch("/api/jobs/" + currentJobId + "/page/" + i + "/text");
                parts.push(await res.text());
            } catch (e) { /* skip */ }
        }
        try {
            await navigator.clipboard.writeText(parts.join("\n\n---\n\n"));
            $copyAll.textContent = "已复制!";
            setTimeout(function () { $copyAll.textContent = "复制全部文本"; }, 1500);
        } catch (e) {
            showToast("复制失败: " + e.message);
        }
    }

})();
