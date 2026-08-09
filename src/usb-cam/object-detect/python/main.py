# SPDX-FileCopyrightText: Copyright (C) Arduino s.r.l. and/or its affiliated companies
#
# SPDX-License-Identifier: MPL-2.0

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.video_objectdetection import VideoObjectDetection
from datetime import datetime, UTC
import time

ui = WebUI()

detection_stream = VideoObjectDetection(confidence=0.5, debounce_sec=0.0)

ui.on_message("override_th", lambda sid, threshold: detection_stream.override_threshold(threshold))

# Register a callback for when all objects are detected
fps_start_time = None
frame_count = 0

def send_detections_to_ui(detections: dict):
  global fps_start_time, frame_count
  
  now = time.time()
  if fps_start_time is None:
      fps_start_time = now
  frame_count += 1
  
  elapsed = now - fps_start_time
  if elapsed >= 1.0:
      fps = frame_count / elapsed
      ui.send_message("fps", message={"fps": round(fps, 1)})
      frame_count = 0
      fps_start_time = now

  for key, values in detections.items():
    for value in values:
      entry = {
        "content": key,
        "confidence": value.get("confidence"),
        "timestamp": datetime.now(UTC).isoformat()
      }
      ui.send_message("detection", message=entry)

detection_stream.on_detect_all(send_detections_to_ui)

App.run()
