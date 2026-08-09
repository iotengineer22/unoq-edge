// SPDX-FileCopyrightText: Copyright (C) Arduino s.r.l. and/or its affiliated companies
//
// SPDX-License-Identifier: MPL-2.0

const socket = io(`http://${window.location.host}`); // Initialize socket.io connection
let errorContainer = document.getElementById('error-container');

// Start the application
document.addEventListener('DOMContentLoaded', () => {
    initSocketIO();
});

function initSocketIO() {
    socket.on('connect', () => {
        if (errorContainer) {
            errorContainer.style.display = 'none';
            errorContainer.textContent = '';
        }
    });

    socket.on('disconnect', () => {
        if (errorContainer) {
            errorContainer.textContent = 'Connection to the board lost. Please check the connection.';
            errorContainer.style.display = 'block';
        }
    });

    socket.on('fps', (data) => {
        const fpsValueElement = document.getElementById('fpsValue');
        if (fpsValueElement && data && typeof data.fps !== 'undefined') {
            fpsValueElement.textContent = data.fps.toFixed(1);
        }
        const resolutionValueElement = document.getElementById('resolutionValue');
        if (resolutionValueElement && data && data.width && data.height) {
            resolutionValueElement.textContent = `${data.width}x${data.height}`;
        }
    });
}

