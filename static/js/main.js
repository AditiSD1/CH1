/**
 * Examify - Flask Platform JavaScript Utilities
 * Features: QR Code Rendering, File Drag-Drop UI, Test Countdown Timer, Password Toggles.
 */

document.addEventListener('DOMContentLoaded', () => {

    // =========================================================================
    // 1. Password Visibility Toggle
    // =========================================================================
    const passwordToggles = document.querySelectorAll('.toggle-pass-btn');
    passwordToggles.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-target');
            const input = document.getElementById(targetId);
            const icon = btn.querySelector('i');

            if (input.type === 'password') {
                input.type = 'text';
                icon.classList.remove('fa-eye');
                icon.classList.add('fa-eye-slash');
            } else {
                input.type = 'password';
                icon.classList.remove('fa-eye-slash');
                icon.classList.add('fa-eye');
            }
        });
    });

    // =========================================================================
    // 2. Drag & Drop File Upload Visual Feedback
    // =========================================================================
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');

    if (dropzone && fileInput) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            dropzone.addEventListener(eventName, () => dropzone.classList.add('highlight'), false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropzone.addEventListener(eventName, () => dropzone.classList.remove('highlight'), false);
        });

        dropzone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length) {
                fileInput.files = files;
                updateDropzoneText(files[0].name);
            }
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length) {
                updateDropzoneText(fileInput.files[0].name);
            }
        });

        function updateDropzoneText(name) {
            const textElement = dropzone.querySelector('.dropzone-text');
            if (textElement) {
                textElement.innerHTML = `Selected File: <strong style="color:#a5b4fc;">${name}</strong>`;
            }
        }
    }

    // =========================================================================
    // 3. QR Code Generator (Page 3: Question Paper & Test Scheduler)
    // =========================================================================
    const qrContainer = document.getElementById('qrcode');
    if (qrContainer) {
        const testUrl = qrContainer.getAttribute('data-url');
        if (testUrl) {
            // Render QR Code using SVG API or QuickChart
            const encodedUrl = encodeURIComponent(testUrl);
            const qrImgUrl = `https://quickchart.io/qr?text=${encodedUrl}&size=180&margin=1`;
            
            qrContainer.innerHTML = `
                <img src="${qrImgUrl}" alt="Test Join QR Code" class="qr-img" style="width:180px; height:180px; border-radius:8px;">
            `;
        }
    }

    // =========================================================================
    // 4. Test Timer Countdown (Page 5: Student Test)
    // =========================================================================
    const timerElement = document.getElementById('testTimer');
    const testForm = document.getElementById('studentTestForm');

    if (timerElement && testForm) {
        let durationMinutes = parseInt(timerElement.getAttribute('data-duration') || '30', 10);
        let totalSeconds = durationMinutes * 60;

        const timerInterval = setInterval(() => {
            if (totalSeconds <= 0) {
                clearInterval(timerInterval);
                timerElement.textContent = "00:00 (Time Expired)";
                timerElement.style.color = "#ef4444";
                alert("Time has expired! Submitting your answers now...");
                testForm.submit();
            } else {
                totalSeconds--;
                const mins = Math.floor(totalSeconds / 60);
                const secs = totalSeconds % 60;
                timerElement.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
                
                if (totalSeconds < 300) {
                    timerElement.style.color = "#f87171"; // Warning red
                }
            }
        }, 1000);
    }
});
