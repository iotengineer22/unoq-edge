/*
 * Ultra-Simple MIPI-CSI2 Camera Web Streamer (C++)
 * 1280x720 High Resolution & Live Camera FPS
 * Target: Arduino UNO Q (Qualcomm Linux) / Linux
 * Port: 7000
 */

#include <iostream>
#include <vector>
#include <string>
#include <thread>
#include <mutex>
#include <chrono>
#include <atomic>
#include <sstream>
#include <iomanip>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>

#include <gst/gst.h>
#include <gst/app/gstappsink.h>

// Global Camera State
std::vector<uint8_t> g_latest_jpeg;
std::mutex g_jpeg_mutex;
std::atomic<bool> g_running(true);
std::atomic<float> g_camera_fps(0.0f);

const int CAM_WIDTH = 1280;
const int CAM_HEIGHT = 720;

// GStreamer Thread: Captures 1280x720 MIPI-CSI2 Camera Feed and converts to JPEG
void camera_thread_func() {
    gst_init(NULL, NULL);

    std::string pipeline_str = 
        "libcamerasrc ! "
        "video/x-raw, width=" + std::to_string(CAM_WIDTH) + ", height=" + std::to_string(CAM_HEIGHT) + " ! "
        "videoconvert ! "
        "jpegenc quality=80 ! "
        "appsink name=mysink sync=false max-buffers=2 drop=true";

    GError* error = NULL;
    GstElement* pipeline = gst_parse_launch(pipeline_str.c_str(), &error);

    if (!pipeline) {
        if (error) {
            std::cerr << "[GStreamer ERROR] " << error->message << std::endl;
            g_error_free(error);
        }
        return;
    }

    GstElement* mysink = gst_bin_get_by_name(GST_BIN(pipeline), "mysink");
    if (!mysink) {
        gst_object_unref(pipeline);
        return;
    }

    gst_element_set_state(pipeline, GST_STATE_PLAYING);
    std::cout << "[Camera C++] 1280x720 MIPI-CSI2 Camera Pipeline Running!" << std::endl;

    int frame_counter = 0;
    auto fps_start_time = std::chrono::steady_clock::now();

    while (g_running) {
        GstSample* sample = gst_app_sink_pull_sample(GST_APP_SINK(mysink));
        if (!sample) {
            if (gst_app_sink_is_eos(GST_APP_SINK(mysink))) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            continue;
        }

        GstBuffer* buffer = gst_sample_get_buffer(sample);
        GstMapInfo map;
        if (gst_buffer_map(buffer, &map, GST_MAP_READ)) {
            std::vector<uint8_t> jpeg_buf(map.data, map.data + map.size);
            {
                std::lock_guard<std::mutex> lock(g_jpeg_mutex);
                g_latest_jpeg = jpeg_buf;
            }
            gst_buffer_unmap(buffer, &map);
        }
        gst_sample_unref(sample);

        // Calculate Real-Time Camera FPS
        frame_counter++;
        auto now = std::chrono::steady_clock::now();
        std::chrono::duration<float> elapsed = now - fps_start_time;
        if (elapsed.count() >= 1.0f) {
            g_camera_fps = frame_counter / elapsed.count();
            frame_counter = 0;
            fps_start_time = now;
        }
    }

    gst_element_set_state(pipeline, GST_STATE_NULL);
    gst_object_unref(mysink);
    gst_object_unref(pipeline);
    std::cout << "[Camera C++] Camera Pipeline stopped." << std::endl;
}

// Embedded HTML5 Web Interface (16:9 Aspect Ratio optimized for 1280x720)
const std::string INDEX_HTML = R"rawhtml(
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Arduino UNO Q 1280x720 Camera Stream</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(21, 30, 48, 0.75);
            --accent-primary: #38bdf8;
            --accent-gradient: linear-gradient(135deg, #38bdf8, #818cf8);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --border-color: rgba(255, 255, 255, 0.12);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 1.5rem 1rem;
        }
        .header { text-align: center; margin-bottom: 1.5rem; }
        .header h1 {
            font-size: 2.2rem;
            font-weight: 800;
            background: var(--accent-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.4rem;
        }
        .container {
            width: 100%;
            max-width: 1200px;
            display: grid;
            grid-template-columns: 1fr 300px;
            gap: 1.5rem;
        }
        @media (max-width: 900px) { .container { grid-template-columns: 1fr; } }
        .video-card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            aspect-ratio: 16 / 9;
            width: 100%;
            margin: 0 auto;
            background-color: #000;
        }
        img { width: 100%; height: 100%; object-fit: contain; display: block; }
        .sidebar { display: flex; flex-direction: column; gap: 1rem; }
        .card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.25rem;
        }
        .card h2 { font-size: 1.1rem; font-weight: 700; color: var(--accent-primary); margin-bottom: 1rem; }
        .metric-box {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 0.85rem;
            text-align: center;
            margin-bottom: 0.75rem;
        }
        .metric-val { font-size: 1.4rem; font-weight: 700; color: #f8fafc; }
        .metric-lbl { font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.2rem; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Arduino UNO Q Camera Stream</h1>
        <p>MIPI-CSI2 Live Feed (1280x720 HD)</p>
    </div>
    <div class="container">
        <div class="video-card">
            <img src="/video_feed" alt="MIPI-CSI2 1280x720 Stream">
        </div>
        <div class="sidebar">
            <div class="card">
                <h2>📊 Camera Info</h2>
                <div class="metric-box">
                    <div class="metric-val" id="res-val">1280x720</div>
                    <div class="metric-lbl">Resolution</div>
                </div>
                <div class="metric-box">
                    <div class="metric-val" id="fps-val" style="color: #38bdf8;">0.0 FPS</div>
                    <div class="metric-lbl">Camera Frame Rate</div>
                </div>
                <div class="metric-box">
                    <div class="metric-val" style="color: #4ade80;">Active</div>
                    <div class="metric-lbl">Status</div>
                </div>
            </div>
        </div>
    </div>
    <script>
        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                document.getElementById('fps-val').innerText = data.fps.toFixed(1) + ' FPS';
                document.getElementById('res-val').innerText = data.width + 'x' + data.height;
            } catch(e){}
        }
        setInterval(fetchStatus, 500);
    </script>
</body>
</html>
)rawhtml";

// HTTP Client Handler
void handle_client(int client_fd) {
    char buffer[2048] = {0};
    ssize_t bytes_read = read(client_fd, buffer, sizeof(buffer) - 1);
    if (bytes_read <= 0) {
        close(client_fd);
        return;
    }

    std::string req(buffer);

    // Serve HTML Home Page
    if (req.rfind("GET / ", 0) == 0 || req.rfind("GET /index.html", 0) == 0) {
        std::string header = 
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html\r\n"
            "Content-Length: " + std::to_string(INDEX_HTML.size()) + "\r\n\r\n";
        send(client_fd, header.c_str(), header.size(), 0);
        send(client_fd, INDEX_HTML.c_str(), INDEX_HTML.size(), 0);
    }
    // Serve Camera Status API
    else if (req.rfind("GET /api/status", 0) == 0) {
        std::ostringstream ss;
        ss << "{\n";
        ss << "  \"fps\": " << g_camera_fps.load() << ",\n";
        ss << "  \"width\": " << CAM_WIDTH << ",\n";
        ss << "  \"height\": " << CAM_HEIGHT << "\n";
        ss << "}\n";

        std::string json_body = ss.str();
        std::string header = 
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Content-Length: " + std::to_string(json_body.size()) + "\r\n\r\n";
        send(client_fd, header.c_str(), header.size(), 0);
        send(client_fd, json_body.c_str(), json_body.size(), 0);
    }
    // Serve MJPEG Video Stream
    else if (req.rfind("GET /video_feed", 0) == 0) {
        std::string header = 
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
            "Access-Control-Allow-Origin: *\r\n\r\n";
        send(client_fd, header.c_str(), header.size(), 0);

        std::vector<uint8_t> frame_buf;
        while (g_running) {
            {
                std::lock_guard<std::mutex> lock(g_jpeg_mutex);
                frame_buf = g_latest_jpeg;
            }

            if (!frame_buf.empty()) {
                std::string part_header = 
                    "--frame\r\n"
                    "Content-Type: image/jpeg\r\n"
                    "Content-Length: " + std::to_string(frame_buf.size()) + "\r\n\r\n";
                if (send(client_fd, part_header.c_str(), part_header.size(), MSG_NOSIGNAL) < 0) break;
                if (send(client_fd, frame_buf.data(), frame_buf.size(), MSG_NOSIGNAL) < 0) break;
                if (send(client_fd, "\r\n", 2, MSG_NOSIGNAL) < 0) break;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(33));
        }
    }
    else {
        std::string not_found = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n";
        send(client_fd, not_found.c_str(), not_found.size(), 0);
    }

    close(client_fd);
}

int main() {
    std::thread cam_thread(camera_thread_func);

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        std::cerr << "[Socket ERROR] Failed to create socket." << std::endl;
        return 1;
    }

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in address;
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(7000);

    if (bind(server_fd, (struct sockaddr*)&address, sizeof(address)) < 0) {
        std::cerr << "[Socket ERROR] Bind failed on Port 7000." << std::endl;
        return 1;
    }

    if (listen(server_fd, 10) < 0) {
        std::cerr << "[Socket ERROR] Listen failed." << std::endl;
        return 1;
    }

    std::cout << "==================================================" << std::endl;
    std::cout << "  Arduino UNO Q Camera Server" << std::endl;
    std::cout << "  Resolution: " << CAM_WIDTH << "x" << CAM_HEIGHT << " (HD 16:9)" << std::endl;
    std::cout << "  Access WebUI at: http://localhost:7000" << std::endl;
    std::cout << "==================================================" << std::endl;

    while (g_running) {
        sockaddr_in client_addr;
        socklen_t addrlen = sizeof(client_addr);
        int client_fd = accept(server_fd, (struct sockaddr*)&client_addr, &addrlen);
        if (client_fd >= 0) {
            std::thread(handle_client, client_fd).detach();
        }
    }

    close(server_fd);
    cam_thread.join();
    return 0;
}
